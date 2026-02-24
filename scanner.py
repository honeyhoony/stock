"""
╔══════════════════════════════════════════════════════════╗
║  메인 스캐너 (Scanner) — 전체 시스템 진입점                  ║
║  필터링 → 전략 판별 → 리스크 → 보고                        ║
╚══════════════════════════════════════════════════════════╝
"""
import time
import json
import logging
import sys
from datetime import datetime
from typing import List
import threading
from concurrent.futures import ThreadPoolExecutor

from config import (
    filter_config, telegram_config, system_config,
    kis_config, strategy_config
)
from data_collector import collector
from strategies import engine as strategy_engine, StrategySignal
from risk_manager import risk_manager
from report_generator import reporter, ReportGenerator, TelegramSender

# ──────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, system_config.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scanner.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class QuantScanner:
    """퀀트 트레이딩 전체 스캐너"""

    def __init__(self):
        self.telegram = None
        if telegram_config.enabled:
            self.telegram = TelegramSender(
                telegram_config.bot_token,
                telegram_config.chat_id,
            )
        self.scan_results: List[dict] = []
        self.market_condition = None
        self.progress = {"percent": 0, "message": "대기 중..."}
        self._lock = threading.Lock()

    def run_scan(self, scan_params: dict = None) -> dict:
        """
        전체 스캔 실행 (동적 파라미터 지원 + 동시 실행 방지)
        """
        with self._lock:
            params = scan_params or {}
            start_time = time.time()
            results = {
                "scan_time": datetime.now().isoformat(),
                "market_condition": {},
                "signals": [],
                "summary": {},
            }
            self.progress = {"percent": 0, "message": "⚙️ 분석 엔진 초기화 중..."}

            # ─────────────────────────────────
            # Step 1: 시장 상태 분석
            # ─────────────────────────────────
            self.progress = {"percent": 5, "message": "📊 증시 상황 분석 중..."}
            logger.info("=" * 50)
            logger.info("🔍 시장 상태 분석 중...")
            self.market_condition = risk_manager.analyze_market_condition()
            results["market_condition"] = ReportGenerator.market_condition_to_dict(
                self.market_condition
            )
            print(ReportGenerator.format_market_condition_console(self.market_condition))

            # ─────────────────────────────────
            # Step 2: 종목 필터링
            # ─────────────────────────────────
            self.progress = {"percent": 15, "message": "📋 우량 종목 필터링 중..."}
            m_cap = params.get("min_market_cap")
            t_rank = params.get("top_rank")
            logger.info(f"📋 종목 필터링 중 (시총: {m_cap or '기본'}, 순위: {t_rank or '기본'})...")
            filtered = collector.filter_stocks(min_market_cap=m_cap, top_rank=t_rank)

            if filtered.empty:
                logger.warning("⚠️ 필터링된 종목이 없습니다. 수동 종목으로 대체...")
                manual_tickers = ["005930", "000660", "373220", "207940", "005380"]
                ticker_list = manual_tickers
            else:
                ticker_list = filtered.index.tolist()

            logger.info(f"  → 스캔 대상: {len(ticker_list)}개 종목")

            # ─────────────────────────────────
            # Step 3: 전략 판별 (동적 파라미터 반영)
            # ─────────────────────────────────
            v = params.get("vars", {})
            if v:
                logger.info("🎯 사용자 정의 전략 파라미터 적용 중...")
                # 눌림목
                strategy_engine.params.pullback.reference_candle_lookback = v.get("p_lookback", 5)
                strategy_engine.params.pullback.volume_cliff_threshold = v.get("p_vol", 0.3)
                # 바닥탈출
                strategy_engine.params.bottom_escape.ma_period = v.get("b_ma", 20)
                strategy_engine.params.bottom_escape.accumulation_volume_ratio = v.get("b_vol_ratio", 2.0)
                # 골든크로스
                strategy_engine.params.golden_cross.short_ma = v.get("g_short", 5)
                strategy_engine.params.golden_cross.long_ma = v.get("g_long", 20)
                strategy_engine.params.golden_cross.rsi_threshold = v.get("g_rsi", 50)
                # 박스권돌파
                strategy_engine.params.breakout.box_lookback = v.get("br_lookback", 60)
                strategy_engine.params.breakout.volume_surge_ratio = v.get("br_vol", 2.0)
                # 정배열초입
                strategy_engine.params.convergence.convergence_pct = v.get("c_pct", 0.03)

            selected_strats = params.get("strategies")
            allowed = selected_strats if selected_strats is not None else self.market_condition.allowed_strategies
            
            strategy_map = {
                "pullback": strategy_engine.check_pullback,
                "bottom_escape": strategy_engine.check_bottom_escape,
                "golden_cross": strategy_engine.check_golden_cross,
                "breakout": strategy_engine.check_breakout,
                "convergence": strategy_engine.check_convergence,
            }

            all_signals: List[StrategySignal] = []
            total = len(ticker_list)
            processed_count = 0
            
            # 병렬 분석 함수
            def analyze_ticker(ticker_info):
                nonlocal processed_count
                sigs = []
                # 분석 수행 (이 구간은 병렬로 진행)
                for strategy_key, check_fn in strategy_map.items():
                    if strategy_key not in allowed: continue
                    try:
                        signal = check_fn(ticker_info)
                        if signal.triggered: sigs.append(signal)
                    except: pass
                
                # 진행률 업데이트 (이 구간은 락을 사용하여 순차 처리)
                with self._lock:
                    processed_count += 1
                    curr_pct = 20 + int((processed_count / max(total, 1)) * 75)
                    stock_name = collector.get_stock_name(ticker_info)
                    # 메시지와 퍼센트가 꼬이지 않도록 락 배분
                    self.progress = {
                        "percent": curr_pct, 
                        "message": f"🔍 {stock_name}({ticker_info}) 분석 완료 ({processed_count}/{total})"
                    }
                return sigs

            # ThreadPool 활용하여 병렬 처리 (속도 향상)
            max_workers = 5 # API 제한 고려
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_results = list(executor.map(analyze_ticker, ticker_list))
                for sig_list in future_results:
                    all_signals.extend(sig_list)

            # ─────────────────────────────────
            # Step 4: 결과 정렬 및 보고
            # ─────────────────────────────────
            all_signals.sort(key=lambda s: s.confidence, reverse=True)
            for signal in all_signals:
                results["signals"].append(ReportGenerator.signal_to_dict(signal))
                if self.telegram and signal.verdict == "매수 승인":
                    self.telegram.send_signal(signal)

            # Summary
            elapsed = time.time() - start_time
            results["summary"] = {
                "total_scanned": total,
                "total_signals": len(all_signals),
                "elapsed_seconds": round(elapsed, 1),
                "market_phase": self.market_condition.market_phase,
            }

            self.scan_results = results["signals"]
            self._save_results(results)
            self.progress = {"percent": 100, "message": "✅ 분석 완료"}
            return results

    def _save_results(self, results: dict):
        """스캔 결과를 JSON 파일로 저장"""
        import numpy as np

        class NumpyEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (np.integer,)):
                    return int(obj)
                elif isinstance(obj, (np.floating,)):
                    return float(obj)
                elif isinstance(obj, (np.bool_,)):
                    return bool(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return super().default(obj)

        filename = f"scan_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)
            logger.info(f"💾 결과 저장: {filename}")
        except Exception as e:
            logger.error(f"결과 저장 실패: {e}")

    def get_latest_results(self) -> List[dict]:
        """최근 스캔 결과 반환 (대시보드 API용)"""
        return self.scan_results


# ──────────────────────────────────────────
# CLI 실행
# ──────────────────────────────────────────
if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║   🚀 퀀트 트레이딩 스캐너 v1.0                         ║
    ║   5대 전략: 눌림목 / 바닥탈출 / 골든크로스               ║
    ║             박스권돌파 / 정배열초입                      ║
    ║                                                       ║
    ║   데이터: pykrx + KIS Open API                        ║
    ║   리스크: ATR 손절 + 시장 필터 + 포지션 관리            ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """)

    scanner = QuantScanner()
    results = scanner.run_scan()
