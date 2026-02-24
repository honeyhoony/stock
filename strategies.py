"""
╔══════════════════════════════════════════════════════════╗
║  5대 전략 판별 모듈 (Strategy Engine)                      ║
║  눌림목 / 바닥탈출 / 골든크로스 / 박스권돌파 / 정배열초입      ║
╚══════════════════════════════════════════════════════════╝
"""
import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

from config import strategy_config, risk_config
from indicators import TechnicalIndicators as TI
from data_collector import collector

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────
# 전략 유형 열거
# ──────────────────────────────────────────
class StrategyType(str, Enum):
    PULLBACK = "눌림목"
    BOTTOM_ESCAPE = "바닥탈출"
    GOLDEN_CROSS = "골든크로스"
    BREAKOUT = "박스권돌파"
    CONVERGENCE = "정배열초입"


# ──────────────────────────────────────────
# 전략 판별 결과
# ──────────────────────────────────────────
@dataclass
class StrategySignal:
    """전략 판별 결과"""
    ticker: str = ""
    name: str = ""
    strategy: StrategyType = StrategyType.PULLBACK
    triggered: bool = False
    confidence: float = 0.0          # 0~100 신뢰도
    current_price: float = 0.0
    entry_price_1: float = 0.0       # 1차 매수가
    entry_price_2: float = 0.0       # 2차 매수가
    target_price_1: float = 0.0      # 1차 목표가
    target_price_2: float = 0.0      # 2차 목표가
    stop_loss: float = 0.0           # 손절가
    risk_reward_ratio: float = 0.0   # 위험/보상 비율
    reasons: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)
    verdict: str = "관망"             # "매수 승인" / "관망"


class StrategyEngine:
    """5대 전략 판별 엔진"""

    def __init__(self):
        self.params = strategy_config

    # ══════════════════════════════════════
    # 1. 눌림목 (Pullback)
    # ══════════════════════════════════════
    def check_pullback(self, ticker: str) -> StrategySignal:
        """
        눌림목 전략 판별
        조건:
        1) 기준봉 중심값 지지 확인
        2) 분봉상 거래량 절벽 (매도 고갈)
        3) 주가 하락 시 기관 보유 수량 유지
        """
        signal = StrategySignal(
            ticker=ticker,
            name=collector.get_stock_name(ticker),
            strategy=StrategyType.PULLBACK,
        )

        # OHLCV 수집
        df = collector.get_ohlcv(ticker, 100)
        if df.empty or len(df) < 30:
            return signal

        # MA 추가
        df = TI.add_all_ma(df)
        current_price = df["종가"].iloc[-1]
        signal.current_price = current_price

        # ① 기준봉 중심값
        p = self.params.pullback
        ref = TI.reference_candle(df, p.reference_candle_lookback)
        if not ref:
            return signal

        center_value = ref["기준봉_중심값"]
        # 현재가가 중심값 근처(±2%) 에서 지지
        near_center = abs(current_price - center_value) / center_value <= 0.02
        above_center = current_price >= center_value * 0.98

        if near_center or above_center:
            signal.reasons.append(
                f"기준봉 중심값({int(center_value):,}원) 지지 확인"
            )
        else:
            return signal

        # ② 거래량 절벽
        vol_cliff = TI.detect_volume_cliff(
            df,
            lookback=10,
            cliff_threshold=p.volume_cliff_threshold,
        )
        if vol_cliff["volume_cliff"]:
            signal.reasons.append(
                f"거래량 절벽 감지 (현재 거래량 = 평균의 {vol_cliff['현재거래량비율']:.0%})"
            )
        elif vol_cliff.get("매도고갈_신호"):
            signal.reasons.append("매도 고갈 신호 감지 (주가 하락 + 거래량 감소)")

        # ③ 기관 보유 수량 유지
        inv_data = collector.get_institution_holding(ticker, 20)
        institution_hold = False
        if not inv_data.empty and "기관합계" in inv_data.columns:
            inst_recent = inv_data["기관합계"].tail(5)
            inst_change = (inst_recent.max() - inst_recent.min()) / abs(inst_recent.mean()) if inst_recent.mean() != 0 else 1
            institution_hold = inst_change <= p.institution_hold_tolerance
            if institution_hold:
                signal.reasons.append("기관 보유 수량 유지 확인 (5일 변동 5% 이내)")

        # ④ 종합 판별
        score = 0
        if near_center or above_center:
            score += 40
        if vol_cliff["volume_cliff"] or vol_cliff.get("매도고갈_신호"):
            score += 35
        if institution_hold:
            score += 25

        signal.confidence = min(score, 100)
        signal.triggered = score >= 65

        # 매수가/목표가 산출
        if signal.triggered:
            atr_val = TI.atr(df).iloc[-1] if len(TI.atr(df).dropna()) > 0 else current_price * 0.02
            signal.entry_price_1 = round(center_value, 0)
            signal.entry_price_2 = round(center_value * 0.98, 0)

            targets = TI.calc_target_price(df)
            signal.target_price_1 = targets.get("1차_목표가", round(current_price * 1.05, 0))
            signal.target_price_2 = targets.get("2차_목표가", round(current_price * 1.10, 0))

            sl = TI.calc_stop_loss(signal.entry_price_1, atr_val, risk_config.atr_multiplier)
            signal.stop_loss = sl["손절가"]
            signal.risk_reward_ratio = round(
                (signal.target_price_1 - signal.entry_price_1) /
                max(signal.entry_price_1 - signal.stop_loss, 1), 2
            )
            signal.verdict = "매수 승인" if signal.confidence >= 75 else "관망"

        signal.details = {
            "기준봉": ref,
            "거래량절벽": vol_cliff,
        }
        return signal

    # ══════════════════════════════════════
    # 2. 바닥 탈출 (20일선 돌파)
    # ══════════════════════════════════════
    def check_bottom_escape(self, ticker: str) -> StrategySignal:
        """
        바닥 탈출 전략 판별
        조건:
        1) 20일선 상향 돌파
        2) 상방 5% 이내 두터운 매물대 벽 없음
        3) 최근 20일 내 매집봉 존재
        """
        signal = StrategySignal(
            ticker=ticker,
            name=collector.get_stock_name(ticker),
            strategy=StrategyType.BOTTOM_ESCAPE,
        )

        df = collector.get_ohlcv(ticker, 100)
        if df.empty or len(df) < 30:
            return signal

        df = TI.add_all_ma(df)
        p = self.params.bottom_escape
        current_price = df["종가"].iloc[-1]
        signal.current_price = current_price

        # ① 20일선 돌파 확인
        ma20_col = f"MA{p.ma_period}"
        if ma20_col not in df.columns or pd.isna(df[ma20_col].iloc[-1]):
            return signal

        ma20_today = df[ma20_col].iloc[-1]
        ma20_yesterday = df[ma20_col].iloc[-2] if len(df) >= 2 else ma20_today
        close_yesterday = df["종가"].iloc[-2] if len(df) >= 2 else 0

        breakout_20ma = (current_price > ma20_today) and (close_yesterday <= ma20_yesterday)

        if breakout_20ma:
            signal.reasons.append(
                f"20일선({int(ma20_today):,}원) 상향 돌파 확인"
            )
        else:
            # 이미 20일선 위에 있되, 최근 돌파한 경우 (3일 이내)
            recent_below = any(
                df["종가"].iloc[-(i + 1)] < df[ma20_col].iloc[-(i + 1)]
                for i in range(1, min(4, len(df)))
            )
            if current_price > ma20_today and recent_below:
                signal.reasons.append(f"최근 3일 이내 20일선 돌파 (현재 {int(ma20_today):,}원 위)")
                breakout_20ma = True
            else:
                return signal

        # ② 상방 매물대 벽 확인
        vol_profile = collector.get_volume_profile(ticker, 60)
        resistance = TI.check_resistance_wall(
            vol_profile, current_price, p.resistance_zone_pct
        )
        no_wall = not resistance.get("resistance_wall", True)
        if no_wall:
            signal.reasons.append(f"상방 5% 매물대 벽 없음 — {resistance.get('평가', '')}")
        else:
            signal.reasons.append(
                f"주의: 상방 매물대 벽 존재 (비율 {resistance.get('상방매물대비율', 0):.1f}%)"
            )

        # ③ 매집봉 확인
        accum = TI.detect_accumulation_candle(
            df, p.accumulation_lookback, p.accumulation_volume_ratio
        )
        has_accum = len(accum) > 0
        if has_accum:
            signal.reasons.append(
                f"매집봉 {len(accum)}개 감지 (최대 거래량 배수: {accum[0]['거래량배수']}x)"
            )

        # ④ 종합 판별
        score = 0
        if breakout_20ma:
            score += 40
        if no_wall:
            score += 30
        else:
            score += 10
        if has_accum:
            score += 30

        signal.confidence = min(score, 100)
        signal.triggered = score >= 60

        if signal.triggered:
            atr_val = TI.atr(df).iloc[-1] if len(TI.atr(df).dropna()) > 0 else current_price * 0.02
            signal.entry_price_1 = round(ma20_today, 0)
            signal.entry_price_2 = round(ma20_today * 0.98, 0)

            targets = TI.calc_target_price(df)
            signal.target_price_1 = targets.get("1차_목표가", round(current_price * 1.07, 0))
            signal.target_price_2 = targets.get("2차_목표가", round(current_price * 1.15, 0))

            sl = TI.calc_stop_loss(signal.entry_price_1, atr_val, risk_config.atr_multiplier)
            signal.stop_loss = sl["손절가"]
            signal.risk_reward_ratio = round(
                (signal.target_price_1 - signal.entry_price_1) /
                max(signal.entry_price_1 - signal.stop_loss, 1), 2
            )
            signal.verdict = "매수 승인" if (signal.confidence >= 70 and no_wall) else "관망"

        signal.details = {
            "매물대분석": resistance,
            "매집봉": accum,
        }
        return signal

    # ══════════════════════════════════════
    # 3. 골든 크로스 (Golden Cross)
    # ══════════════════════════════════════
    def check_golden_cross(self, ticker: str) -> StrategySignal:
        """
        골든 크로스 전략 판별
        조건:
        1) 5일선이 20일선을 상향 돌파 (골든크로스)
        2) 20일선 기울기 ≥ 0 (평탄 이상)
        3) RSI가 50선을 상향 돌파
        """
        signal = StrategySignal(
            ticker=ticker,
            name=collector.get_stock_name(ticker),
            strategy=StrategyType.GOLDEN_CROSS,
        )

        df = collector.get_ohlcv(ticker, 100)
        if df.empty or len(df) < 30:
            return signal

        df = TI.add_all_ma(df)
        p = self.params.golden_cross
        current_price = df["종가"].iloc[-1]
        signal.current_price = current_price

        short_col = f"MA{p.short_ma}"
        long_col = f"MA{p.long_ma}"
        if short_col not in df.columns or long_col not in df.columns:
            return signal

        # ① 골든 크로스 감지
        cross = TI.detect_cross(df[short_col], df[long_col])
        is_golden = cross["golden_cross"]

        # 최근 3일 이내 골든크로스도 허용
        if not is_golden:
            for i in range(1, 4):
                if len(df) > i + 1:
                    prev_short = df[short_col].iloc[-(i + 1)]
                    prev_long = df[long_col].iloc[-(i + 1)]
                    curr_short = df[short_col].iloc[-i]
                    curr_long = df[long_col].iloc[-i]
                    if prev_short < prev_long and curr_short >= curr_long:
                        is_golden = True
                        break

        if is_golden:
            signal.reasons.append(
                f"골든크로스 발생 (MA{p.short_ma} ↑ MA{p.long_ma})"
            )
        else:
            return signal

        # ② 20일선 기울기 확인
        ma20_slope = TI.ma_slope_degree(df[long_col], 5)
        slope_ok = ma20_slope >= p.ma_slope_min
        if slope_ok:
            signal.reasons.append(
                f"20일선 기울기 양호 ({ma20_slope:+.2f}%)"
            )
        else:
            signal.reasons.append(
                f"주의: 20일선 기울기 하락 ({ma20_slope:+.2f}%)"
            )

        # ③ RSI 50선 상향 돌파
        rsi = TI.rsi(df["종가"], p.rsi_period)
        rsi_today = rsi.iloc[-1]
        rsi_yesterday = rsi.iloc[-2] if len(rsi) >= 2 else 50
        rsi_cross_up = (rsi_today > p.rsi_threshold) and (rsi_yesterday <= p.rsi_threshold)

        # RSI가 이미 50 이상이고 상승 중이면 허용
        rsi_above_rising = rsi_today > p.rsi_threshold and rsi_today > rsi_yesterday

        if rsi_cross_up:
            signal.reasons.append(f"RSI 50선 상향 돌파 (RSI: {rsi_today:.1f})")
        elif rsi_above_rising:
            signal.reasons.append(f"RSI 50선 위 상승 중 (RSI: {rsi_today:.1f})")

        # ④ 종합 판별
        score = 0
        if is_golden:
            score += 40
        if slope_ok:
            score += 25
        else:
            score += 5
        if rsi_cross_up:
            score += 35
        elif rsi_above_rising:
            score += 20

        signal.confidence = min(score, 100)
        signal.triggered = score >= 65

        if signal.triggered:
            atr_val = TI.atr(df).iloc[-1] if len(TI.atr(df).dropna()) > 0 else current_price * 0.02
            ma20_val = df[long_col].iloc[-1]
            signal.entry_price_1 = round(current_price, 0)
            signal.entry_price_2 = round(ma20_val, 0)

            targets = TI.calc_target_price(df)
            signal.target_price_1 = targets.get("1차_목표가", round(current_price * 1.07, 0))
            signal.target_price_2 = targets.get("2차_목표가", round(current_price * 1.15, 0))

            sl = TI.calc_stop_loss(signal.entry_price_1, atr_val, risk_config.atr_multiplier)
            signal.stop_loss = sl["손절가"]
            signal.risk_reward_ratio = round(
                (signal.target_price_1 - signal.entry_price_1) /
                max(signal.entry_price_1 - signal.stop_loss, 1), 2
            )
            signal.verdict = "매수 승인" if (signal.confidence >= 75 and slope_ok) else "관망"

        signal.details = {
            "RSI": round(rsi_today, 1),
            "MA20_기울기": round(ma20_slope, 4),
        }
        return signal

    # ══════════════════════════════════════
    # 4. 박스권 돌파 (Breakout)
    # ══════════════════════════════════════
    def check_breakout(self, ticker: str) -> StrategySignal:
        """
        박스권 돌파 전략 판별
        조건:
        1) 전고점 돌파
        2) 매도 호가 잔량 > 매수 호가 × 2 (벽 뚫기 == 강한 매수)
        3) 프로그램 매수 가속도 확인
        """
        signal = StrategySignal(
            ticker=ticker,
            name=collector.get_stock_name(ticker),
            strategy=StrategyType.BREAKOUT,
        )

        df = collector.get_ohlcv(ticker, 120)
        if df.empty or len(df) < 30:
            return signal

        df = TI.add_all_ma(df)
        p = self.params.breakout
        current_price = df["종가"].iloc[-1]
        signal.current_price = current_price

        # ① 박스권 돌파 확인
        box = TI.detect_box_range(df, p.box_lookback)
        if not box:
            return signal

        is_breakout = box.get("돌파여부", False)
        if is_breakout:
            signal.reasons.append(
                f"전고점({int(box['박스상단']):,}원) 돌파 확인"
            )
        elif box.get("현재가_상단근접", False):
            signal.reasons.append(
                f"박스 상단({int(box['박스상단']):,}원) 근접 — 돌파 대기"
            )
        else:
            return signal

        # ② 매도/매수 호가 잔량 비율 확인
        orderbook = collector.get_orderbook(ticker)
        ask_bid_ok = False
        if orderbook:
            ratio = orderbook.get("매도매수비율", 0)
            ask_bid_ok = ratio >= p.ask_bid_ratio
            if ask_bid_ok:
                signal.reasons.append(
                    f"매도호가 잔량/매수호가 = {ratio:.1f}배 (강한 돌파 신호)"
                )
            else:
                signal.reasons.append(
                    f"매도/매수 비율 {ratio:.1f}배 (기준 {p.ask_bid_ratio}배 미달)"
                )

        # ③ 프로그램 매수 가속도
        prog = collector.get_program_trading(ticker)
        prog_accel = False
        if prog:
            net_buy = prog.get("프로그램순매수", 0)
            prog_accel = net_buy > 0
            if prog_accel:
                signal.reasons.append(
                    f"프로그램 순매수 {net_buy:,}주 유입"
                )

        # ④ 거래량 폭증 확인
        avg_vol = df["거래량"].tail(20).mean()
        vol_surge = df["거래량"].iloc[-1] / max(avg_vol, 1)
        if vol_surge >= p.volume_surge_ratio:
            signal.reasons.append(
                f"거래량 폭증 {vol_surge:.1f}배 (돌파 에너지 확인)"
            )

        # ⑤ 종합
        score = 0
        if is_breakout:
            score += 35
        elif box.get("현재가_상단근접"):
            score += 15
        if ask_bid_ok:
            score += 25
        if prog_accel:
            score += 20
        if vol_surge >= p.volume_surge_ratio:
            score += 20

        signal.confidence = min(score, 100)
        signal.triggered = score >= 55

        if signal.triggered:
            atr_val = TI.atr(df).iloc[-1] if len(TI.atr(df).dropna()) > 0 else current_price * 0.02
            signal.entry_price_1 = round(box["박스상단"], 0)
            signal.entry_price_2 = round(box["박스상단"] * 1.01, 0)

            targets = TI.calc_target_price(df)
            box_height = box["박스상단"] - box["박스하단"]
            signal.target_price_1 = round(box["박스상단"] + box_height * 0.5, 0)
            signal.target_price_2 = round(box["박스상단"] + box_height, 0)

            sl = TI.calc_stop_loss(signal.entry_price_1, atr_val, risk_config.atr_multiplier)
            signal.stop_loss = max(sl["손절가"], box["박스하단"])
            signal.risk_reward_ratio = round(
                (signal.target_price_1 - signal.entry_price_1) /
                max(signal.entry_price_1 - signal.stop_loss, 1), 2
            )
            signal.verdict = "매수 승인" if (is_breakout and signal.confidence >= 70) else "관망"

        signal.details = {
            "박스권": box,
            "호가잔량": orderbook,
            "프로그램매매": prog,
            "거래량배수": round(vol_surge, 2) if avg_vol > 0 else 0,
        }
        return signal

    # ══════════════════════════════════════
    # 5. 정배열 초입 (Convergence → Divergence)
    # ══════════════════════════════════════
    def check_convergence(self, ticker: str) -> StrategySignal:
        """
        정배열 초입 전략 판별
        조건:
        1) 5-20-60-120일선이 3% 이내 밀집
        2) 밀집 후 발산 시작
        3) 업종 지수 상승 추세 시 가중치
        """
        signal = StrategySignal(
            ticker=ticker,
            name=collector.get_stock_name(ticker),
            strategy=StrategyType.CONVERGENCE,
        )

        df = collector.get_ohlcv(ticker, 200)
        if df.empty or len(df) < 120:
            return signal

        df = TI.add_all_ma(df, strategy_config.convergence.ma_periods)
        p = self.params.convergence
        current_price = df["종가"].iloc[-1]
        signal.current_price = current_price

        # ① 이동평균선 밀집도 분석
        conv = TI.ma_convergence(df, p.ma_periods, p.convergence_pct)

        if conv.get("converged"):
            signal.reasons.append(
                f"이평선 밀집 확인 (스프레드 {conv['spread_pct']:.2f}%)"
            )
        elif conv.get("spread_pct") and conv["spread_pct"] <= p.convergence_pct * 100 * 1.5:
            signal.reasons.append(
                f"이평선 밀집 근접 (스프레드 {conv['spread_pct']:.2f}%)"
            )
        else:
            return signal

        # ② 정배열 여부
        if conv.get("is_aligned"):
            signal.reasons.append("정배열 형성 (MA5 > MA20 > MA60 > MA120)")

        # ③ 발산 확인
        if conv.get("diverging"):
            signal.reasons.append("밀집 후 발산 시작 감지")

        # ④ 업종 지수 상승 추세 확인
        # (실제로는 해당 종목의 업종 코드를 조회해야 하지만, 코스피 지수로 대체)
        market_idx = collector.get_market_index("1001", 30)
        sector_bonus = 0
        if not market_idx.empty:
            idx_ma5 = market_idx["종가"].rolling(5).mean()
            if len(idx_ma5.dropna()) >= 1:
                idx_above_ma5 = market_idx["종가"].iloc[-1] > idx_ma5.iloc[-1]
                if idx_above_ma5:
                    sector_bonus = 15
                    signal.reasons.append("시장 지수 5일선 위 — 업종 상승 추세 가중치 적용")

        # ⑤ 종합
        score = 0
        if conv.get("converged"):
            score += 30
        elif conv.get("spread_pct", 99) <= p.convergence_pct * 100 * 1.5:
            score += 15
        if conv.get("is_aligned"):
            score += 25
        if conv.get("diverging"):
            score += 30
        score += sector_bonus

        signal.confidence = min(score, 100)
        signal.triggered = score >= 55

        if signal.triggered:
            atr_val = TI.atr(df).iloc[-1] if len(TI.atr(df).dropna()) > 0 else current_price * 0.02
            ma_vals = conv.get("ma_values", {})
            ma120 = ma_vals.get(120, current_price * 0.95)

            signal.entry_price_1 = round(current_price, 0)
            signal.entry_price_2 = round(ma_vals.get(20, current_price * 0.98), 0)

            targets = TI.calc_target_price(df)
            signal.target_price_1 = targets.get("1차_목표가", round(current_price * 1.08, 0))
            signal.target_price_2 = targets.get("2차_목표가", round(current_price * 1.15, 0))

            sl = TI.calc_stop_loss(signal.entry_price_1, atr_val, risk_config.atr_multiplier)
            signal.stop_loss = max(sl["손절가"], round(ma120 * 0.97, 0))
            signal.risk_reward_ratio = round(
                (signal.target_price_1 - signal.entry_price_1) /
                max(signal.entry_price_1 - signal.stop_loss, 1), 2
            )
            signal.verdict = "매수 승인" if (
                signal.confidence >= 70 and conv.get("is_aligned") and conv.get("diverging")
            ) else "관망"

        signal.details = {
            "밀집도분석": conv,
            "업종가중치": sector_bonus,
        }
        return signal

    # ══════════════════════════════════════
    # 전체 전략 스캔
    # ══════════════════════════════════════
    def scan_all_strategies(self, ticker: str) -> List[StrategySignal]:
        """한 종목에 대해 5대 전략 모두 판별"""
        signals = []
        checks = [
            self.check_pullback,
            self.check_bottom_escape,
            self.check_golden_cross,
            self.check_breakout,
            self.check_convergence,
        ]
        for check_fn in checks:
            try:
                sig = check_fn(ticker)
                if sig.triggered:
                    signals.append(sig)
            except Exception as e:
                logger.warning(f"{ticker} {check_fn.__name__} 오류: {e}")
        return signals

    def get_best_signal(self, ticker: str) -> Optional[StrategySignal]:
        """가장 신뢰도 높은 전략 신호 반환"""
        signals = self.scan_all_strategies(ticker)
        if not signals:
            return None
        return max(signals, key=lambda s: s.confidence)


# ──────────────────────────────────────────
# 싱글톤 인스턴스
# ──────────────────────────────────────────
engine = StrategyEngine()
