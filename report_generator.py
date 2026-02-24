"""
╔══════════════════════════════════════════════════════════╗
║  보고서 생성 모듈 (Report Generator)                       ║
║  텔레그램 / HTML / 콘솔 보고서                              ║
╚══════════════════════════════════════════════════════════╝
"""
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime

from strategies import StrategySignal, StrategyType
from risk_manager import MarketCondition, StopLossReport

logger = logging.getLogger(__name__)


class ReportGenerator:
    """보고서 생성기"""

    # ══════════════════════════════════════
    # 1. 콘솔 보고서
    # ══════════════════════════════════════
    @staticmethod
    def format_signal_console(signal: StrategySignal) -> str:
        """전략 신호를 콘솔 출력 형식으로 변환"""
        divider = "═" * 52
        lines = [
            f"\n{divider}",
            f"  📊 {signal.name}({signal.ticker}) / {int(signal.current_price):,}원 / {signal.strategy.value}",
            f"{divider}",
            "",
            f"  🔍 핵심 근거:",
        ]
        for i, reason in enumerate(signal.reasons, 1):
            lines.append(f"     {i}. {reason}")

        lines.extend([
            "",
            f"  🎯 매수 타점:",
            f"     • 1차 매수가: {int(signal.entry_price_1):,}원",
            f"     • 2차 매수가: {int(signal.entry_price_2):,}원",
            "",
            f"  📈 목표가 / 📉 손절가:",
            f"     • 1차 목표가: {int(signal.target_price_1):,}원",
            f"     • 2차 목표가: {int(signal.target_price_2):,}원",
            f"     • 손절가:     {int(signal.stop_loss):,}원",
            f"     • R:R 비율:   {signal.risk_reward_ratio:.1f}",
            "",
            f"  ⚡ 신뢰도: {signal.confidence:.0f}%",
            f"  {'✅' if signal.verdict == '매수 승인' else '⏸️'} 승인 여부: [{signal.verdict}]",
            f"{divider}",
        ])
        return "\n".join(lines)

    @staticmethod
    def format_market_condition_console(condition: MarketCondition) -> str:
        """시장 상태를 콘솔 출력 형식으로 변환"""
        phase_emoji = {
            "BULL": "🟢", "BEAR": "🔴", "NEUTRAL": "🟡"
        }
        emoji = phase_emoji.get(condition.market_phase, "⚪")

        lines = [
            "\n╔══════════════════════════════════════════════╗",
            f"║  {emoji} 시장 상태: {condition.market_phase}",
            "╠══════════════════════════════════════════════╣",
        ]
        for reason in condition.reasons:
            lines.append(f"║  {reason}")
        lines.extend([
            f"║  최대 투자비중: {condition.max_weight:.0%}",
            f"║  허용 전략: {', '.join(condition.allowed_strategies)}",
            "╚══════════════════════════════════════════════╝",
        ])
        return "\n".join(lines)

    # ══════════════════════════════════════
    # 2. 텔레그램 보고서
    # ══════════════════════════════════════
    @staticmethod
    def format_signal_telegram(signal: StrategySignal) -> str:
        """텔레그램 마크다운 형식 보고서"""
        verdict_emoji = "✅" if signal.verdict == "매수 승인" else "⏸️"

        msg = f"""
📊 *{signal.name}* ({signal.ticker})
💰 현재가: {int(signal.current_price):,}원
🏷️ 전략: *{signal.strategy.value}*

🔍 *핵심 근거:*
"""
        for i, reason in enumerate(signal.reasons, 1):
            msg += f"  {i}. {reason}\n"

        msg += f"""
🎯 *매수 타점:*
  • 1차: {int(signal.entry_price_1):,}원
  • 2차: {int(signal.entry_price_2):,}원

📈 *목표가/손절가:*
  • 1차 목표: {int(signal.target_price_1):,}원
  • 2차 목표: {int(signal.target_price_2):,}원
  • 손절가: {int(signal.stop_loss):,}원
  • R:R = {signal.risk_reward_ratio:.1f}

⚡ 신뢰도: {signal.confidence:.0f}%
{verdict_emoji} *[{signal.verdict}]*
"""
        return msg.strip()

    @staticmethod
    def format_stop_loss_telegram(report: StopLossReport) -> str:
        """손절 리포트 텔레그램 형식"""
        emoji = "🚨" if report.triggered else "✅"
        msg = f"""
{emoji} *손절 알림: {report.name}* ({report.ticker})
📊 매수가: {int(report.entry_price):,}원
💰 현재가: {int(report.current_price):,}원
📉 손익률: {report.loss_pct:+.2f}%
🛑 손절가: {int(report.stop_loss_price):,}원
📐 20일선: {int(report.ma20_price):,}원

⚠️ *사유:* {report.trigger_reason}
🎬 *조치:* {report.action}
"""
        return msg.strip()

    # ══════════════════════════════════════
    # 3. HTML 카드 (대시보드용)
    # ══════════════════════════════════════
    @staticmethod
    def signal_to_dict(signal: StrategySignal) -> dict:
        """StrategySignal → JSON 직렬화 가능한 dict"""
        return {
            "ticker": signal.ticker,
            "name": signal.name,
            "strategy": signal.strategy.value,
            "triggered": signal.triggered,
            "confidence": signal.confidence,
            "current_price": signal.current_price,
            "entry_price_1": signal.entry_price_1,
            "entry_price_2": signal.entry_price_2,
            "target_price_1": signal.target_price_1,
            "target_price_2": signal.target_price_2,
            "stop_loss": signal.stop_loss,
            "risk_reward_ratio": signal.risk_reward_ratio,
            "market_cap": signal.market_cap,
            "reasons": signal.reasons,
            "verdict": signal.verdict,
            "details": _safe_serialize(signal.details),
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def market_condition_to_dict(condition: MarketCondition) -> dict:
        """MarketCondition → dict"""
        return {
            "kospi_above_ma5": condition.kospi_above_ma5,
            "kosdaq_above_ma5": condition.kosdaq_above_ma5,
            "kospi_value": condition.kospi_value,
            "kospi_ma5": condition.kospi_ma5,
            "kosdaq_value": condition.kosdaq_value,
            "kosdaq_ma5": condition.kosdaq_ma5,
            "market_phase": condition.market_phase,
            "max_weight": condition.max_weight,
            "allowed_strategies": condition.allowed_strategies,
            "reasons": condition.reasons,
            "timestamp": condition.timestamp,
        }

    @staticmethod
    def stop_loss_to_dict(report: StopLossReport) -> dict:
        """StopLossReport → dict"""
        return {
            "ticker": report.ticker,
            "name": report.name,
            "entry_price": report.entry_price,
            "current_price": report.current_price,
            "stop_loss_price": report.stop_loss_price,
            "ma20_price": report.ma20_price,
            "trigger_reason": report.trigger_reason,
            "triggered": report.triggered,
            "loss_pct": report.loss_pct,
            "action": report.action,
            "timestamp": report.timestamp,
        }


def _safe_serialize(obj):
    """JSON 직렬화 안전 변환 (numpy 타입 포함)"""
    import numpy as np

    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_safe_serialize(v) for v in obj]
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        return str(obj)


# ──────────────────────────────────────────
# 텔레그램 전송
# ──────────────────────────────────────────
class TelegramSender:
    """텔레그램 메시지 전송"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str) -> bool:
        """텔레그램 메시지 전송"""
        import requests
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"텔레그램 전송 실패: {e}")
            return False

    def send_signal(self, signal: StrategySignal) -> bool:
        """전략 신호 텔레그램 전송"""
        msg = ReportGenerator.format_signal_telegram(signal)
        return self.send_message(msg)

    def send_stop_alert(self, report: StopLossReport) -> bool:
        """손절 알림 텔레그램 전송"""
        msg = ReportGenerator.format_stop_loss_telegram(report)
        return self.send_message(msg)


# ──────────────────────────────────────────
# 싱글톤 인스턴스
# ──────────────────────────────────────────
reporter = ReportGenerator()
