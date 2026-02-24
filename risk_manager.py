"""
╔══════════════════════════════════════════════════════════╗
║  리스크 관리 모듈 (Risk Manager)                          ║
║  시장 필터 + 손절 자동화 + 포지션 관리                       ║
╚══════════════════════════════════════════════════════════╝
"""
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

from config import risk_config
from data_collector import collector
from indicators import TechnicalIndicators as TI

logger = logging.getLogger(__name__)


@dataclass
class MarketCondition:
    """시장 상태 분석 결과"""
    kospi_above_ma5: bool = False
    kosdaq_above_ma5: bool = False
    kospi_value: float = 0.0
    kospi_ma5: float = 0.0
    kosdaq_value: float = 0.0
    kosdaq_ma5: float = 0.0
    market_phase: str = "NEUTRAL"        # BULL / BEAR / NEUTRAL
    max_weight: float = 1.0              # 최대 투자 비중
    allowed_strategies: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class StopLossReport:
    """손절 리포트"""
    ticker: str = ""
    name: str = ""
    entry_price: float = 0.0
    current_price: float = 0.0
    stop_loss_price: float = 0.0
    ma20_price: float = 0.0
    trigger_reason: str = ""
    triggered: bool = False
    loss_pct: float = 0.0
    action: str = ""
    timestamp: str = ""


class RiskManager:
    """리스크 관리 엔진"""

    def __init__(self):
        self._positions: Dict[str, dict] = {}  # 보유 포지션 추적

    # ══════════════════════════════════════
    # 1. 시장 필터 (Market Filter)
    # ══════════════════════════════════════
    def analyze_market_condition(self) -> MarketCondition:
        """
        코스피/코스닥 지수가 5일 이동평균선 아래인지 확인
        - 아래: 약세장 → 비중 30% 이하, 바닥탈출만 운용
        - 위: 정상 → 모든 전략 운용
        """
        condition = MarketCondition(
            timestamp=datetime.now().isoformat(),
            allowed_strategies=["pullback", "bottom_escape", "golden_cross", "breakout", "convergence"],
        )

        # 코스피 지수 분석
        kospi = collector.get_market_index("1001", 30)
        if not kospi.empty and len(kospi) >= 5:
            ma5 = kospi["종가"].rolling(5).mean()
            condition.kospi_value = float(kospi["종가"].iloc[-1])
            condition.kospi_ma5 = float(ma5.iloc[-1])
            condition.kospi_above_ma5 = bool(kospi["종가"].iloc[-1] > ma5.iloc[-1])
            if condition.kospi_above_ma5:
                condition.reasons.append(
                    f"코스피 5일선 위 ({kospi['종가'].iloc[-1]:,.0f} > MA5 {ma5.iloc[-1]:,.0f})"
                )
            else:
                condition.reasons.append(
                    f"⚠️ 코스피 5일선 이탈 ({kospi['종가'].iloc[-1]:,.0f} < MA5 {ma5.iloc[-1]:,.0f})"
                )

        # 코스닥 지수 분석
        kosdaq = collector.get_market_index("2001", 30)
        if not kosdaq.empty and len(kosdaq) >= 5:
            ma5 = kosdaq["종가"].rolling(5).mean()
            condition.kosdaq_value = float(kosdaq["종가"].iloc[-1])
            condition.kosdaq_ma5 = float(ma5.iloc[-1])
            condition.kosdaq_above_ma5 = bool(kosdaq["종가"].iloc[-1] > ma5.iloc[-1])
            if condition.kosdaq_above_ma5:
                condition.reasons.append(
                    f"코스닥 5일선 위 ({kosdaq['종가'].iloc[-1]:,.0f} > MA5 {ma5.iloc[-1]:,.0f})"
                )
            else:
                condition.reasons.append(
                    f"⚠️ 코스닥 5일선 이탈 ({kosdaq['종가'].iloc[-1]:,.0f} < MA5 {ma5.iloc[-1]:,.0f})"
                )

        # 시장 상태 판별
        both_below = not condition.kospi_above_ma5 and not condition.kosdaq_above_ma5
        both_above = condition.kospi_above_ma5 and condition.kosdaq_above_ma5

        if both_below:
            condition.market_phase = "BEAR"
            condition.max_weight = risk_config.bear_market_max_weight
            condition.allowed_strategies = [risk_config.bear_market_strategy]
            condition.reasons.append(
                f"🔴 약세장 감지 — 투자비중 {condition.max_weight:.0%} 이하, "
                f"'{risk_config.bear_market_strategy}' 전략만 운용"
            )
        elif both_above:
            condition.market_phase = "BULL"
            condition.max_weight = 1.0
            condition.reasons.append("🟢 강세장 — 전 전략 운용 가능")
        else:
            condition.market_phase = "NEUTRAL"
            condition.max_weight = 0.7
            condition.reasons.append("🟡 혼조세 — 투자비중 70% 이하 권고")

        return condition

    # ══════════════════════════════════════
    # 2. 손절 자동화
    # ══════════════════════════════════════
    def check_stop_loss(
        self,
        ticker: str,
        entry_price: float,
        stop_loss_price: float,
    ) -> StopLossReport:
        """
        손절 조건 확인
        1) ATR 기반 손절가 이탈
        2) 20일선 종가 기준 이탈
        """
        report = StopLossReport(
            ticker=ticker,
            name=collector.get_stock_name(ticker),
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            timestamp=datetime.now().isoformat(),
        )

        df = collector.get_ohlcv(ticker, 30)
        if df.empty:
            return report

        df = TI.add_all_ma(df, [20])
        current_price = df["종가"].iloc[-1]
        report.current_price = current_price

        # 20일선 가격
        ma20 = df["MA20"].iloc[-1] if "MA20" in df.columns and pd.notna(df["MA20"].iloc[-1]) else None
        report.ma20_price = ma20 if ma20 else 0.0

        # 손익률 계산
        report.loss_pct = round((current_price - entry_price) / entry_price * 100, 2)

        # 손절 조건 1: ATR 기반 손절가 이탈
        if current_price <= stop_loss_price:
            report.triggered = True
            report.trigger_reason = f"ATR 기반 손절가({int(stop_loss_price):,}원) 이탈"
            report.action = "즉시 매도"

        # 손절 조건 2: 20일선 종가 기준 이탈
        elif ma20 and current_price < ma20:
            report.triggered = True
            report.trigger_reason = f"20일선({int(ma20):,}원) 종가 이탈"
            report.action = "종가 매도 추천"

        else:
            report.action = "보유 유지"
            report.trigger_reason = "손절 조건 미해당"

        return report

    def generate_stop_loss_report(self, positions: List[dict]) -> List[StopLossReport]:
        """전체 보유 종목 손절 리포트 생성"""
        reports = []
        for pos in positions:
            report = self.check_stop_loss(
                ticker=pos["ticker"],
                entry_price=pos["entry_price"],
                stop_loss_price=pos["stop_loss"],
            )
            reports.append(report)
        return reports

    # ══════════════════════════════════════
    # 3. 포지션 비중 관리
    # ══════════════════════════════════════
    def validate_position_size(
        self,
        total_capital: float,
        current_positions: List[dict],
        new_entry_price: float,
        market_condition: MarketCondition,
    ) -> Dict[str, any]:
        """
        신규 매수 시 포지션 비중 검증
        - 단일 종목 최대 10%
        - 약세장 시 총 비중 30% 이하
        """
        total_invested = sum(p.get("invested", 0) for p in current_positions)
        invested_ratio = total_invested / total_capital if total_capital > 0 else 0

        # 시장 상태별 최대 비중
        max_allowed = market_condition.max_weight
        remaining = max(max_allowed - invested_ratio, 0)

        # 단일 종목 최대 비중
        single_max = risk_config.max_position_pct * total_capital
        recommended_qty = int(min(single_max, remaining * total_capital) / max(new_entry_price, 1))

        return {
            "현재_투자비중": round(invested_ratio * 100, 1),
            "시장_최대비중": round(max_allowed * 100, 0),
            "잔여_투자가능비중": round(remaining * 100, 1),
            "추천_매수수량": max(recommended_qty, 0),
            "추천_매수금액": int(recommended_qty * new_entry_price),
            "매수가능": remaining > 0 and len(current_positions) < risk_config.max_total_positions,
            "보유종목수": len(current_positions),
            "최대보유수": risk_config.max_total_positions,
        }


# ──────────────────────────────────────────
# 싱글톤 인스턴스
# ──────────────────────────────────────────
risk_manager = RiskManager()
