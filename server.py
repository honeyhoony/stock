"""
╔══════════════════════════════════════════════════════════╗
║  FastAPI 서버 — 대시보드 백엔드                            ║
║  5대 전략 스캔 + 관찰 리스트 + 교집합 판별                  ║
╚══════════════════════════════════════════════════════════╝
"""
import json
import os
import logging
import numpy as np
from datetime import datetime
from typing import List, Optional
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from config import system_config
from scanner import QuantScanner
from risk_manager import risk_manager
from report_generator import ReportGenerator
from watchlist import watchlist_manager, TelegramWatchBot

logger = logging.getLogger(__name__)


def sanitize(obj):
    """numpy 타입 → Python 기본 타입 재귀 변환"""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize(v) for v in obj]
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


# ──────────────────────────────────────────
# 교집합 3단계 AND 필터
# ──────────────────────────────────────────
# 1단계: 패턴 중첩   → 5가지 유형 중 2개 이상 동시 포착
# 2단계: 수급 동기화  → 외인/기관/프로그램 중 2개 이상 매수세
# 3단계: 시장 환경   → 코스피/코스닥 MA5 위 (상승 추세)
# ──────────────────────────────────────────
def analyze_intersections(signals: list, market_condition=None) -> list:
    """
    3단계 교집합(AND) 필터 — 시그널을 분석하여 등급 부여
    모든 조건을 통과해야 A급/S급 인정 (가산점 없음)
    """
    from data_collector import collector

    # 시장 상태 조회 (없으면 새로 분석)
    if market_condition is None:
        try:
            market_condition = risk_manager.analyze_market_condition()
        except Exception:
            market_condition = None

    # ── 종목별 그룹핑 ──
    by_ticker = defaultdict(list)
    for s in signals:
        by_ticker[s.get("ticker", "")].append(s)

    enriched = []

    for ticker, group in by_ticker.items():
        strategies = list(set(g["strategy"] for g in group))
        pattern_count = len(strategies)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1단계: 패턴 중첩 검증
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        filter1_pass = pattern_count >= 2

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2단계: 수급 동기화 (외인/기관/프로그램)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        supply_demand = {"buy_count": 0, "details": {}, "acceleration": {"label": "분석 중"}}
        filter2_pass = False

        if filter1_pass:
            try:
                supply_demand = collector.get_supply_demand(ticker)
                filter2_pass = supply_demand.get("buy_count", 0) >= 2
            except Exception:
                filter2_pass = False

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3단계: 시장 환경 (MA5 위 = 상승 추세)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        filter3_pass = False
        market_phase = "UNKNOWN"

        if filter1_pass and filter2_pass:
            if market_condition:
                market_phase = getattr(market_condition, "market_phase", "UNKNOWN")
                # BULL 또는 NEUTRAL 이면 통과 (BEAR만 차단)
                kospi_ok = getattr(market_condition, "kospi_above_ma5", False)
                kosdaq_ok = getattr(market_condition, "kosdaq_above_ma5", False)
                filter3_pass = kospi_ok or kosdaq_ok
            else:
                filter3_pass = True  # 시장 데이터 없으면 패스

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 최종 등급 부여
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        all_pass = filter1_pass and filter2_pass and filter3_pass

        for s in group:
            s["multi_strategy_count"] = pattern_count
            s["multi_strategies"] = strategies
            s["supply_acceleration"] = supply_demand.get("acceleration", {}).get("label", "")

            # 핵심 근거에 수급 가속도 추가 (V2)
            if s["supply_acceleration"] and s["supply_acceleration"] != "수급 완만":
                if "reasons" not in s: s["reasons"] = []
                s["reasons"].insert(0, f"🚀 수급 가속: {s['supply_acceleration']}")

            # 필터 통과 기록
            s["filter_results"] = {
                "pattern_overlap": filter1_pass,
                "pattern_count": pattern_count,
                "supply_sync": filter2_pass,
                "supply_buy_count": supply_demand.get("buy_count", 0),
                "supply_details": supply_demand.get("details", {}),
                "market_ok": filter3_pass,
                "market_phase": market_phase,
            }

            if all_pass and pattern_count >= 3:
                s["grade"] = "S"
                s["grade_label"] = "S급 (3중 교집합 + 수급 + 시장)"
                s["verdict"] = "매수 승인"
            elif all_pass and pattern_count >= 2:
                s["grade"] = "A"
                s["grade_label"] = "A급 (교집합 AND 필터 통과)"
                s["verdict"] = "매수 승인"
            elif filter1_pass and not filter2_pass:
                s["grade"] = "B+"
                s["grade_label"] = f"패턴 중첩 O / 수급 미달 ({supply_demand.get('buy_count', 0)}/2)"
            elif filter1_pass and filter2_pass and not filter3_pass:
                s["grade"] = "B+"
                s["grade_label"] = "패턴+수급 O / 시장 환경 미달 (하락장)"
            else:
                s["grade"] = "B"
                s["grade_label"] = "단일 전략"

            # 보너스 없음 — 원본 신뢰도 유지
            s["confidence_bonus"] = 0
            s["original_confidence"] = s.get("confidence", 0)

            enriched.append(s)

    # S급 → A급 → B+ → B 순, 같은 등급 내 신뢰도 높은 순
    grade_order = {"S": 0, "A": 1, "B+": 2, "B": 3}
    enriched.sort(key=lambda x: (
        grade_order.get(x.get("grade", "B"), 3),
        -x.get("confidence", 0)
    ))

    return enriched


app = FastAPI(
    title="퀀트 트레이딩 대시보드",
    description="5대 전략 기반 퀀트 스캐너 + 관찰 리스트",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙
dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/static", StaticFiles(directory=dashboard_dir), name="static")

# 글로벌 스캐너 인스턴스
scanner = QuantScanner()
latest_results = {"signals": [], "market_condition": {}, "summary": {}}


# ══════════════════════════════════════
# 대시보드 페이지
# ══════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def root():
    """대시보드 메인 페이지"""
    index_path = os.path.join(dashboard_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard not found</h1>")


@app.get("/api/progress")
async def get_progress():
    """현재 스캔 진행률 반환"""
    return JSONResponse(content=scanner.progress)


# ══════════════════════════════════════
# 스캔 API (교집합 포함)
# ══════════════════════════════════════
@app.get("/api/scan")
async def run_scan(
    min_market_cap: Optional[int] = None,
    top_rank: Optional[int] = None,
    strats: Optional[str] = None,
    vars: Optional[str] = None
):
    """전체 스캔 실행 + 교집합 분석 (동적 파라미터 지원)"""
    global latest_results
    try:
        # 파라미터 구성
        params = {}
        if min_market_cap is not None: params["min_market_cap"] = min_market_cap
        if top_rank is not None: params["top_rank"] = top_rank
        if strats: params["strategies"] = strats.split(",")
        if vars: params["vars"] = json.loads(vars)

        # 무거운 스캔 작업을 스레드풀에서 실행 (메인 루프 차단 방지)
        results = await run_in_threadpool(scanner.run_scan, scan_params=params)

        # 교집합 분석 적용 (데이터 collector 접근 등이 포함되므로 역시 무거운 작업)
        if results.get("signals"):
            results["signals"] = await run_in_threadpool(analyze_intersections, results["signals"])

            # 교집합 요약 생성
            grades = {"S": 0, "A": 0, "B": 0}
            for s in results["signals"]:
                g = s.get("grade", "B")
                grades[g] = grades.get(g, 0) + 1

            results["intersection_summary"] = {
                "s_grade": grades["S"],
                "a_grade": grades["A"],
                "b_grade": grades["B"],
                "description": (
                    f"S급 {grades['S']}개 · A급 {grades['A']}개 · 단일 {grades['B']}개"
                ),
            }

        latest_results = results
        return JSONResponse(content=sanitize(results))
    except Exception as e:
        logger.error(f"스캔 오류: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
        )


@app.get("/api/results")
async def get_results():
    """최근 스캔 결과 반환"""
    if not latest_results.get("signals"):
        try:
            files = sorted(
                [f for f in os.listdir(".") if f.startswith("scan_result_")],
                reverse=True,
            )
            if files:
                with open(files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 저장된 결과에도 교집합 적용
                    if data.get("signals"):
                        data["signals"] = analyze_intersections(data["signals"])
                    return JSONResponse(content=data)
        except Exception:
            pass
    return JSONResponse(content=latest_results)


@app.get("/api/market")
async def get_market_condition():
    """시장 상태 분석"""
    try:
        condition = risk_manager.analyze_market_condition()
        return JSONResponse(
            content=sanitize(ReportGenerator.market_condition_to_dict(condition))
        )
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/stock/{ticker}")
async def analyze_stock(ticker: str):
    """개별 종목 분석"""
    from strategies import engine
    try:
        signals = engine.scan_all_strategies(ticker)
        results = [ReportGenerator.signal_to_dict(s) for s in signals]
        results = analyze_intersections(results)
        return JSONResponse(content=sanitize({
            "ticker": ticker,
            "signals": results,
            "total": len(results),
        }))
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/approve/{ticker}")
async def approve_signal(ticker: str, request: Request):
    """매수 승인/관망 처리"""
    body = await request.json()
    action = body.get("action", "관망")
    return JSONResponse(content={
        "ticker": ticker,
        "action": action,
        "timestamp": datetime.now().isoformat(),
        "status": "approved" if action == "매수 승인" else "watching",
    })


# ══════════════════════════════════════
# 관찰 리스트 API
# ══════════════════════════════════════
@app.get("/api/watchlist")
async def get_watchlist():
    """관찰 리스트 전체 조회"""
    items = watchlist_manager.get_all()
    return JSONResponse(content=sanitize([i.to_dict() for i in items]))


@app.post("/api/watchlist/add")
async def add_watchlist(request: Request):
    """관찰 종목 추가"""
    body = await request.json()
    ticker = body.get("ticker", "")
    buy_price = float(body.get("buy_price", 0))
    name = body.get("name", "")
    quantity = int(body.get("quantity", 0))

    if not ticker or buy_price <= 0:
        return JSONResponse(
            content={"error": "ticker와 buy_price 필수"},
            status_code=400,
        )

    item = watchlist_manager.add(ticker, buy_price, name, quantity)
    return JSONResponse(content=sanitize(item.to_dict()))


@app.delete("/api/watchlist/{ticker}")
async def remove_watchlist(ticker: str):
    """관찰 종목 제거"""
    ok = watchlist_manager.remove(ticker)
    if ok:
        return JSONResponse(content={"status": "removed", "ticker": ticker})
    return JSONResponse(content={"error": "not found"}, status_code=404)


@app.get("/api/watchlist/check")
async def check_watchlist():
    """전 종목 현재가 체크 + 상태 업데이트"""
    results = watchlist_manager.check_all()
    return JSONResponse(content=sanitize(results))


@app.get("/api/watchlist/report")
async def watchlist_report():
    """일일 요약 보고서"""
    report = watchlist_manager.generate_daily_report()
    return JSONResponse(content={"report": report})


@app.post("/api/watchlist/monitor/start")
async def start_monitor():
    """백그라운드 모니터링 시작"""
    watchlist_manager.start_monitoring(interval_sec=60)
    return JSONResponse(content={"status": "monitoring_started", "interval_sec": 60})


@app.post("/api/watchlist/monitor/stop")
async def stop_monitor():
    """모니터링 중지"""
    watchlist_manager.stop_monitoring()
    return JSONResponse(content={"status": "monitoring_stopped"})


# ══════════════════════════════════════
# 서버 시작
# ══════════════════════════════════════
@app.on_event("startup")
async def on_startup():
    """서버 시작 시 관찰 리스트 모니터링 자동 시작"""
    if watchlist_manager.items:
        watchlist_manager.start_monitoring(interval_sec=60)
        logger.info(f"📌 관찰 리스트 로드: {len(watchlist_manager.items)}개 종목")

    # 텔레그램 봇 시작
    bot = TelegramWatchBot(watchlist_manager)
    bot.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=system_config.dashboard_port,
        reload=False,
    )
