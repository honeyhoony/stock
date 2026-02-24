"""
╔══════════════════════════════════════════════════════════╗
║  퀀트 에이전트 — 24시간 자동 감시 엔진 v2                  ║
║  • 3단계 AND 교집합 필터 (패턴 + 수급 + 시장)             ║
║  • A급 종목만 텔레그램 보고 + [매수 실행] 버튼             ║
║  • 보유 종목 실시간 손절 감시 (1분 주기)                   ║
║  • Supabase ↔ KIS API 실시간 동기화                     ║
╚══════════════════════════════════════════════════════════╝

실행: python main.py
중지: Ctrl+C
"""
import os
import sys
import time
import logging
import signal
import threading
from datetime import datetime

# ──────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("agent")

# ──────────────────────────────────────────
# 설정 로드
# ──────────────────────────────────────────
from config import (
    system_config, telegram_config, kis_config,
    risk_config, supabase_config,
)
from scanner import QuantScanner
from risk_manager import risk_manager
from report_generator import ReportGenerator
from telegram_bot import trading_bot
import supabase_client as supa


# ──────────────────────────────────────────
# 시장 상태 체크
# ──────────────────────────────────────────
def check_market_status():
    """시장 상태 분석 — 약세장이면 매수 차단"""
    try:
        condition = risk_manager.analyze_market_condition()
        phase = condition.market_phase
        logger.info(f"📊 시장 국면: {phase} | 최대 비중: {condition.max_weight*100:.0f}%")

        if phase == "BEAR":
            trading_bot.send_message(
                "🔴 *약세장 감지*\n"
                "코스피·코스닥 5일선 하회\n"
                "→ 신규 매수 차단, '보수적 관망' 모드"
            )
        return condition

    except Exception as e:
        logger.error(f"시장 상태 분석 실패: {e}")
        return None


# ──────────────────────────────────────────
# 5대 전략 스캔 + 3단계 AND 필터
# ──────────────────────────────────────────
def run_strategy_scan(market_condition):
    """5대 전략 스캔 → 3단계 AND 교집합 필터 → A급만 텔레그램 보고"""
    scanner = QuantScanner()

    try:
        results = scanner.run_scan()
        signals = results.get("signals", [])

        if not signals:
            logger.info("📭 감지된 신호 없음")
            return

        # ── 3단계 AND 교집합 필터 적용 ──
        from server import analyze_intersections
        signals = analyze_intersections(signals, market_condition)

        # 등급별 분류
        s_grade = [s for s in signals if s.get("grade") == "S"]
        a_grade = [s for s in signals if s.get("grade") == "A"]
        b_plus = [s for s in signals if s.get("grade") == "B+"]
        b_only = [s for s in signals if s.get("grade") == "B"]

        logger.info(
            f"🔍 스캔 완료: "
            f"S급 {len(s_grade)} / A급 {len(a_grade)} / "
            f"B+ {len(b_plus)} / B {len(b_only)}"
        )

        # ── A급 이상만 텔레그램 보고 (인라인 매수 버튼 포함) ──
        top_signals = s_grade + a_grade

        if top_signals:
            # 요약 메시지
            summary = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 *교집합 A급 종목 탐지* ({len(top_signals)}건)\n"
                f"📅 {datetime.now().strftime('%H:%M:%S')}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"3단계 AND 필터 통과 종목만 보고합니다:\n"
                f"✅ 패턴 2개↑ 중첩\n"
                f"✅ 수급 2개↑ 매수세\n"
                f"✅ 시장 상승 추세\n"
            )
            trading_bot.send_message(summary)

            # 개별 종목별 상세 보고 (매수 버튼 포함)
            for sig in top_signals:
                trading_bot.send_a_grade_alert(sig)
                time.sleep(0.5)  # API Rate limit
        else:
            # B+ 요약만 간략히
            if b_plus:
                msg = (
                    f"📋 *B+ 종목* ({len(b_plus)}건) — AND 필터 미통과\n\n"
                )
                for s in b_plus[:5]:
                    msg += (
                        f"• {s.get('name', '')}({s.get('ticker', '')}) "
                        f"— {s.get('grade_label', '')}\n"
                    )
                trading_bot.send_message(msg)

    except Exception as e:
        logger.error(f"전략 스캔 오류: {e}")


# ──────────────────────────────────────────
# 보유 종목 감시
# ──────────────────────────────────────────
def check_holdings():
    """Supabase 보유종목 현재가 체크 + 손절 감시"""
    try:
        alerts = supa.check_and_update_all()

        for alert in alerts:
            msg = supa.format_alert_message(alert)
            trading_bot.send_message(msg)
            logger.warning(
                f"🚨 알림: {alert['name']} [{alert['status']}] "
                f"({alert['pnl_pct']:+.1f}%)"
            )

        if alerts:
            logger.info(f"⚠️ {len(alerts)}건 알림 전송")
        else:
            holdings_count = len(supa.get_all_holdings())
            if holdings_count > 0:
                logger.debug(f"✅ 보유 {holdings_count}종목 이상 없음")

    except Exception as e:
        logger.error(f"보유종목 체크 실패: {e}")


# ──────────────────────────────────────────
# 일일 보고
# ──────────────────────────────────────────
_daily_reported = False


def check_daily_report():
    """매일 지정 시각에 일일 보고서 전송"""
    global _daily_reported
    now = datetime.now()

    if now.hour == system_config.daily_report_hour and now.minute < 2:
        if not _daily_reported:
            report = supa.generate_daily_summary()
            trading_bot.send_message(report)
            logger.info("📊 일일 보고서 전송 완료")
            _daily_reported = True
    else:
        _daily_reported = False


# ──────────────────────────────────────────
# 장 운영 시간 체크
# ──────────────────────────────────────────
def is_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hour_min = now.hour * 100 + now.minute
    return 855 <= hour_min <= 1540


def is_pre_market() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hour_min = now.hour * 100 + now.minute
    return 800 <= hour_min <= 854


# ══════════════════════════════════════════
# 메인 에이전트 루프
# ══════════════════════════════════════════
class QuantAgent:
    """24시간 퀀트 에이전트 v2"""

    def __init__(self):
        self.running = True
        self._scan_count = 0
        self._check_count = 0
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        logger.info("🛑 종료 신호 수신 — 안전하게 종료합니다")
        self.running = False

    def start(self):
        """에이전트 시작"""
        logger.info("=" * 60)
        logger.info("🚀 퀀트 에이전트 v2 시작")
        logger.info(f"   📊 전략 스캔: {system_config.scan_interval_minutes}분 주기")
        logger.info(f"   📌 보유 감시: {system_config.holdings_check_interval}분 주기")
        logger.info(f"   🛡️ 손절 기준: {system_config.stop_loss_pct}%")
        logger.info(f"   📐 MA 이탈: {system_config.ma_stop_period}일선")
        logger.info(f"   🔔 텔레그램: {'활성' if telegram_config.enabled else '비활성'}")
        logger.info(f"   💾 Supabase: {'연결' if supabase_config.enabled else '미연결'}")
        logger.info(f"   🎯 교집합: 3단계 AND 필터 (패턴+수급+시장)")
        logger.info("=" * 60)

        # 텔레그램 봇 폴링 시작 (콜백 수신)
        trading_bot.start_polling()

        # 시작 알림
        trading_bot.send_message(
            "🚀 *퀀트 에이전트 v2 가동*\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"📊 스캔 주기: {system_config.scan_interval_minutes}분\n"
            f"📌 보유 감시: {system_config.holdings_check_interval}분\n"
            f"🛡 손절: {system_config.stop_loss_pct}%\n"
            f"🎯 필터: 3단계 AND (패턴·수급·시장)\n\n"
            "A급 종목 탐지 시 [매수 실행] 버튼이 전송됩니다.\n"
            "/help 로 명령어를 확인하세요."
        )

        # 메인 루프
        scan_interval = system_config.scan_interval_minutes * 60
        check_interval = system_config.holdings_check_interval * 60
        last_scan = 0
        last_check = 0

        while self.running:
            now = time.time()

            try:
                # ── 장 시간 ──
                if is_market_hours():
                    # 보유 종목 체크 (1분)
                    if now - last_check >= check_interval:
                        check_holdings()
                        self._check_count += 1
                        last_check = now

                    # 전략 스캔 (5분)
                    if now - last_scan >= scan_interval:
                        market = check_market_status()
                        run_strategy_scan(market)
                        self._scan_count += 1
                        last_scan = now

                # ── 장 시작 전 ──
                elif is_pre_market():
                    if now - last_scan >= scan_interval:
                        logger.info("⏰ 장 시작 전 — 시장 상태 사전 분석")
                        check_market_status()
                        last_scan = now

                # ── 장 외 시간 ──
                else:
                    check_daily_report()
                    if now - last_check >= 1800:
                        check_holdings()
                        last_check = now

            except Exception as e:
                logger.error(f"메인 루프 오류: {e}")

            time.sleep(10)

        # 종료
        trading_bot.stop_polling()
        trading_bot.send_message(
            f"🏁 *에이전트 종료*\n"
            f"스캔 {self._scan_count}회 / 체크 {self._check_count}회"
        )
        logger.info(f"🏁 에이전트 종료")


if __name__ == "__main__":
    agent = QuantAgent()
    agent.start()
