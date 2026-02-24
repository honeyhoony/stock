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

    def run_scan(self, scan_params: dict = None) -> dict:
        """
        전체 스캔 실행 (동적 파라미터 지원)
        scan_params 예시: {
            "min_market_cap": 100000000000,
            "top_rank": 300,
            "strategies": ["pullback", "golden_cross"],
            "urgency_mode": "safe"
        }
        """
        params = scan_params or {}
        start_time = time.time()
        results = {
            "scan_time": datetime.now().isoformat(),
            "market_condition": {},
            "signals": [],
            "summary": {},
        }

        # ─────────────────────────────────
        # Step 1: 시장 상태 분석
        # ─────────────────────────────────
        logger.info("=" * 50)
        logger.info("🔍 시장 상태 분석 중...")
        self.market_condition = risk_manager.analyze_market_condition()
        results["market_condition"] = ReportGenerator.market_condition_to_dict(
            self.market_condition
        )
        print(ReportGenerator.format_market_condition_console(self.market_condition))

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
        # Step 3: 전략 판별
        # ─────────────────────────────────
        # UI에서 선택한 전략 혹은 시장 조건에 따른 허용 전략
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

        for idx, ticker in enumerate(ticker_list, 1):
            pct = 20 + int((idx / total) * 75)  # 20% ~ 95% 구간
            self.progress = {"percent": pct, "message": f"🔍 {ticker} 분석 중 ({idx}/{total})"}
            
            if idx % 10 == 0 or idx == 1:
                logger.info(f"  스캔 진행: {idx}/{total} ({idx/total*100:.0f}%)")

            for strategy_key, check_fn in strategy_map.items():
                # 필터링된 허용 전략만 실행
                if strategy_key not in allowed:
                    continue

                try:
                    signal = check_fn(ticker)
                    if signal.triggered:
                        all_signals.append(signal)
                        logger.info(
                            f"  ✅ {signal.name}({ticker}) — {signal.strategy.value} "
                            f"(신뢰도 {signal.confidence:.0f}%)"
                        )
                except Exception as e:
                    logger.debug(f"  {ticker} {strategy_key} 오류: {e}")

            # API Rate Limit 방지
            time.sleep(0.3)

        # ─────────────────────────────────
        # Step 4: 결과 정렬 및 보고
        # ─────────────────────────────────
        # 신뢰도 내림차순 정렬
        all_signals.sort(key=lambda s: s.confidence, reverse=True)

        print("\n" + "=" * 60)
        print(f"  🏆 스캔 결과: {len(all_signals)}개 전략 신호 감지")
        print("=" * 60)

        for signal in all_signals:
            # 콘솔 출력
            print(ReportGenerator.format_signal_console(signal))

            # JSON 결과 추가
            results["signals"].append(
                ReportGenerator.signal_to_dict(signal)
            )

            # 텔레그램 전송
            if self.telegram and signal.verdict == "매수 승인":
                self.telegram.send_signal(signal)

        # ─────────────────────────────────
        # Summary
        # ─────────────────────────────────
        elapsed = time.time() - start_time
        approved = [s for s in all_signals if s.verdict == "매수 승인"]
        watch = [s for s in all_signals if s.verdict == "관망"]

        strategy_counts = {}
        for s in all_signals:
            key = s.strategy.value
            strategy_counts[key] = strategy_counts.get(key, 0) + 1

        results["summary"] = {
            "total_scanned": total,
            "total_signals": len(all_signals),
            "approved": len(approved),
            "watch": len(watch),
            "strategy_breakdown": strategy_counts,
            "elapsed_seconds": round(elapsed, 1),
            "market_phase": self.market_condition.market_phase,
        }

        print(f"\n{'─' * 50}")
        print(f"  📊 요약: 스캔 {total}개 → 신호 {len(all_signals)}개")
        print(f"    ✅ 매수 승인: {len(approved)}개")
        print(f"    ⏸️  관망:     {len(watch)}개")
        print(f"    ⏱️  소요시간:  {elapsed:.1f}초")
        print(f"{'─' * 50}")

        # 결과 저장
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
