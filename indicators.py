"""
╔══════════════════════════════════════════════════════════╗
║  기술적 지표 모듈 (Technical Indicators)                   ║
║  MA, RSI, ATR, 기울기, 피보나치, 밀집도 계산                ║
╚══════════════════════════════════════════════════════════╝
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """기술적 지표 계산 엔진"""

    # ══════════════════════════════════════
    # 1. 이동평균선 (Moving Average)
    # ══════════════════════════════════════
    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """단순 이동평균"""
        return series.rolling(window=period, min_periods=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """지수 이동평균"""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def add_all_ma(df: pd.DataFrame, periods: List[int] = None) -> pd.DataFrame:
        """OHLCV DataFrame에 주요 이동평균선 추가"""
        if periods is None:
            periods = [5, 10, 20, 60, 120]
        for p in periods:
            col = f"MA{p}"
            if len(df) >= p:
                df[col] = TechnicalIndicators.sma(df["종가"], p)
        return df

    # ══════════════════════════════════════
    # 2. RSI (Relative Strength Index)
    # ══════════════════════════════════════
    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """RSI 지표"""
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_val = 100 - (100 / (1 + rs))
        return rsi_val.fillna(50)

    # ══════════════════════════════════════
    # 3. ATR (Average True Range)
    # ══════════════════════════════════════
    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """평균 진폭 (변동성 지표)"""
        high = df["고가"]
        low = df["저가"]
        close = df["종가"].shift(1)

        tr1 = high - low
        tr2 = (high - close).abs()
        tr3 = (low - close).abs()

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return true_range.rolling(window=period, min_periods=period).mean()

    # ══════════════════════════════════════
    # 4. 이평선 기울기 (Slope)
    # ══════════════════════════════════════
    @staticmethod
    def ma_slope(series: pd.Series, lookback: int = 5) -> pd.Series:
        """이동평균선의 기울기 (일간 변화율 %)"""
        return series.pct_change(periods=lookback) * 100

    @staticmethod
    def ma_slope_degree(series: pd.Series, lookback: int = 5) -> float:
        """최근 기울기의 각도 (단위: %)"""
        if len(series) < lookback + 1:
            return 0.0
        slope = (series.iloc[-1] - series.iloc[-lookback]) / series.iloc[-lookback] * 100
        return round(slope, 4)

    # ══════════════════════════════════════
    # 5. 골든 크로스 / 데드 크로스 판별
    # ══════════════════════════════════════
    @staticmethod
    def detect_cross(short_ma: pd.Series, long_ma: pd.Series) -> Dict[str, bool]:
        """
        골든 크로스 / 데드 크로스 감지
        Returns: {"golden_cross": bool, "dead_cross": bool}
        """
        if len(short_ma) < 2 or len(long_ma) < 2:
            return {"golden_cross": False, "dead_cross": False}

        # 전일: short < long, 금일: short >= long → 골든크로스
        prev_below = short_ma.iloc[-2] < long_ma.iloc[-2]
        curr_above = short_ma.iloc[-1] >= long_ma.iloc[-1]
        golden = prev_below and curr_above

        # 전일: short > long, 금일: short <= long → 데드크로스
        prev_above = short_ma.iloc[-2] > long_ma.iloc[-2]
        curr_below = short_ma.iloc[-1] <= long_ma.iloc[-1]
        dead = prev_above and curr_below

        return {"golden_cross": golden, "dead_cross": dead}

    # ══════════════════════════════════════
    # 6. 피보나치 되돌림/확장
    # ══════════════════════════════════════
    @staticmethod
    def fibonacci_levels(
        high: float, low: float, levels: List[float] = None
    ) -> Dict[str, float]:
        """
        피보나치 되돌림 레벨 계산
        상승 추세: low → high 기준 되돌림
        """
        if levels is None:
            levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

        diff = high - low
        result = {}
        for level in levels:
            price = high - diff * level
            result[f"fib_{level}"] = round(price, 0)
        return result

    @staticmethod
    def fibonacci_extension(
        high: float, low: float, levels: List[float] = None
    ) -> Dict[str, float]:
        """피보나치 확장 레벨 (목표가 산출)"""
        if levels is None:
            levels = [1.0, 1.272, 1.618, 2.0, 2.618]

        diff = high - low
        result = {}
        for level in levels:
            price = low + diff * level
            result[f"ext_{level}"] = round(price, 0)
        return result

    # ══════════════════════════════════════
    # 7. 이동평균선 밀집도 (정배열 초입)
    # ══════════════════════════════════════
    @staticmethod
    def ma_convergence(
        df: pd.DataFrame,
        periods: List[int] = None,
        threshold: float = 0.03
    ) -> Dict[str, any]:
        """
        이동평균선 밀집도 분석
        - periods의 MA가 threshold(3%) 이내로 밀집했는지 확인
        - 밀집 후 발산 여부 감지
        """
        if periods is None:
            periods = [5, 20, 60, 120]

        # MA 값 수집
        ma_values = {}
        for p in periods:
            col = f"MA{p}"
            if col in df.columns and pd.notna(df[col].iloc[-1]):
                ma_values[p] = df[col].iloc[-1]

        if len(ma_values) < len(periods):
            return {"converged": False, "spread_pct": None, "diverging": False}

        values = list(ma_values.values())
        max_val = max(values)
        min_val = min(values)
        spread = (max_val - min_val) / min_val if min_val > 0 else 999

        # 밀집 여부
        converged = spread <= threshold

        # 정배열 여부: MA5 > MA20 > MA60 > MA120
        is_aligned = all(
            ma_values.get(periods[i], 0) >= ma_values.get(periods[i + 1], 0)
            for i in range(len(periods) - 1)
        )

        # 발산 확인: 최근 3일간 spread가 증가하는 추세
        diverging = False
        if len(df) >= 5:
            recent_spreads = []
            for offset in range(3):
                idx = -(offset + 1)
                vals = []
                for p in periods:
                    col = f"MA{p}"
                    if col in df.columns and len(df) >= abs(idx):
                        vals.append(df[col].iloc[idx])
                if vals:
                    s = (max(vals) - min(vals)) / min(vals) if min(vals) > 0 else 0
                    recent_spreads.append(s)

            if len(recent_spreads) >= 3:
                diverging = recent_spreads[0] > recent_spreads[1] > recent_spreads[2]

        return {
            "converged": converged,
            "spread_pct": round(spread * 100, 2),
            "is_aligned": is_aligned,
            "diverging": diverging,
            "ma_values": ma_values,
        }

    # ══════════════════════════════════════
    # 8. 기준봉 중심값 (눌림목용)
    # ══════════════════════════════════════
    @staticmethod
    def reference_candle(df: pd.DataFrame, lookback: int = 5) -> Dict[str, float]:
        """
        기준봉 탐색: lookback 기간 내 가장 큰 양봉을 기준봉으로 선정
        중심값 = (고가 + 저가) / 2
        """
        if len(df) < lookback:
            return {}

        recent = df.tail(lookback + 5).head(lookback)
        # 양봉 필터
        bullish = recent[recent["종가"] > recent["시가"]].copy()
        if bullish.empty:
            bullish = recent

        # 가장 큰 캔들 (고가-저가 범위)
        bullish["범위"] = bullish["고가"] - bullish["저가"]
        ref = bullish.loc[bullish["범위"].idxmax()]

        center = (ref["고가"] + ref["저가"]) / 2
        return {
            "기준봉_고가": float(ref["고가"]),
            "기준봉_저가": float(ref["저가"]),
            "기준봉_중심값": float(center),
            "기준봉_날짜": str(ref.name),
        }

    # ══════════════════════════════════════
    # 9. 매집봉 탐지 (바닥 탈출용)
    # ══════════════════════════════════════
    @staticmethod
    def detect_accumulation_candle(
        df: pd.DataFrame,
        lookback: int = 20,
        volume_ratio: float = 2.0
    ) -> List[Dict]:
        """
        매집봉 탐지
        - 거래량이 평균의 volume_ratio배 이상
        - 양봉 (종가 > 시가)
        - 긴 아래꼬리 (= 매수세 유입)
        """
        if len(df) < lookback:
            return []

        recent = df.tail(lookback)
        avg_vol = recent["거래량"].mean()

        accumulation_candles = []
        for idx, row in recent.iterrows():
            is_bullish = row["종가"] > row["시가"]
            high_volume = row["거래량"] > avg_vol * volume_ratio
            body = abs(row["종가"] - row["시가"])
            lower_wick = min(row["시가"], row["종가"]) - row["저가"]
            has_long_lower = lower_wick > body * 0.5 if body > 0 else False

            if high_volume and (is_bullish or has_long_lower):
                accumulation_candles.append({
                    "날짜": str(idx),
                    "종가": float(row["종가"]),
                    "거래량": int(row["거래량"]),
                    "거래량배수": round(row["거래량"] / avg_vol, 2),
                })

        return accumulation_candles

    # ══════════════════════════════════════
    # 10. 박스권 탐지
    # ══════════════════════════════════════
    @staticmethod
    def detect_box_range(
        df: pd.DataFrame,
        lookback: int = 60,
        tolerance: float = 0.05
    ) -> Dict[str, any]:
        """
        박스권 상/하단 감지
        tolerance: 주가 변동 폭이 ±5% 이내면 박스권으로 판단
        """
        if len(df) < lookback:
            return {}

        recent = df.tail(lookback)
        box_high = recent["고가"].max()
        box_low = recent["저가"].min()
        box_range_pct = (box_high - box_low) / box_low

        current = df["종가"].iloc[-1]
        near_high = (box_high - current) / current <= tolerance

        return {
            "박스상단": float(box_high),
            "박스하단": float(box_low),
            "박스범위%": round(box_range_pct * 100, 2),
            "현재가_상단근접": near_high,
            "돌파여부": current > box_high,
        }

    # ══════════════════════════════════════
    # 11. 거래량 절벽 감지 (눌림목용)
    # ══════════════════════════════════════
    @staticmethod
    def detect_volume_cliff(
        df: pd.DataFrame,
        lookback: int = 10,
        cliff_threshold: float = 0.3
    ) -> Dict[str, any]:
        """
        거래량 절벽 감지
        - 최근 거래량이 평균의 30% 이하로 급감
        - 주가 하락과 함께 거래량 감소 = 매도세 고갈
        """
        if len(df) < lookback:
            return {"volume_cliff": False}

        recent = df.tail(lookback)
        avg_vol = recent["거래량"].mean()
        last_vol = df["거래량"].iloc[-1]
        ratio = last_vol / avg_vol if avg_vol > 0 else 1.0

        # 최근 3일 거래량 감소 추세
        last_3_vol = df["거래량"].tail(3)
        decreasing = all(
            last_3_vol.iloc[i] <= last_3_vol.iloc[i - 1]
            for i in range(1, len(last_3_vol))
        )

        # 주가 하락 중인지
        price_declining = df["종가"].iloc[-1] < df["종가"].iloc[-3] if len(df) >= 3 else False

        is_cliff = ratio <= cliff_threshold and decreasing

        return {
            "volume_cliff": is_cliff,
            "현재거래량비율": round(ratio, 3),
            "거래량감소추세": decreasing,
            "주가하락중": price_declining,
            "매도고갈_신호": is_cliff and price_declining,
        }

    # ══════════════════════════════════════
    # 12. 매물대 벽 확인 (바닥 탈출용)
    # ══════════════════════════════════════
    @staticmethod
    def check_resistance_wall(
        volume_profile: pd.DataFrame,
        current_price: float,
        range_pct: float = 0.05
    ) -> Dict[str, any]:
        """
        상방 매물대 벽 확인
        현재가 상방 range_pct 이내에 두터운 매물대가 있는지 검사
        """
        if volume_profile.empty:
            return {"resistance_wall": False}

        upper_bound = current_price * (1 + range_pct)

        # 상방 매물대 필터
        above = volume_profile[
            (volume_profile["중심가격"] > current_price) &
            (volume_profile["중심가격"] <= upper_bound)
        ]

        if above.empty:
            return {
                "resistance_wall": False,
                "상방매물대비율": 0.0,
                "평가": "매물대 벽 없음 — 상승 여력 확보",
            }

        resistance_ratio = above["거래량비율"].sum()
        has_wall = resistance_ratio > 0.15  # 15% 이상이면 두터운 벽

        return {
            "resistance_wall": has_wall,
            "상방매물대비율": round(resistance_ratio * 100, 2),
            "평가": "두터운 매물대 벽 존재 — 주의" if has_wall else "매물대 벽 약함 — 상승 유리",
        }

    # ══════════════════════════════════════
    # 13. 손절가 계산
    # ══════════════════════════════════════
    @staticmethod
    def calc_stop_loss(
        entry_price: float,
        atr_value: float,
        multiplier: float = 2.0
    ) -> Dict[str, float]:
        """ATR 기반 손절가 산출"""
        stop_loss = entry_price - atr_value * multiplier
        risk_pct = (entry_price - stop_loss) / entry_price * 100

        return {
            "매수가": entry_price,
            "ATR": round(atr_value, 0),
            "손절가": round(stop_loss, 0),
            "리스크%": round(risk_pct, 2),
        }

    # ══════════════════════════════════════
    # 14. 목표가 산출 (피보나치 + 매물대)
    # ══════════════════════════════════════
    @staticmethod
    def calc_target_price(
        df: pd.DataFrame,
        volume_profile: pd.DataFrame = None,
        method: str = "fibonacci"
    ) -> Dict[str, float]:
        """
        목표가 산출
        - fibonacci: 피보나치 확장 기반
        - volume_profile: 매물대 상방 빈 공간 기반
        """
        if len(df) < 20:
            return {}

        # 최근 스윙 고/저점
        recent = df.tail(60) if len(df) >= 60 else df
        swing_high = recent["고가"].max()
        swing_low = recent["저가"].min()
        current = df["종가"].iloc[-1]

        # 피보나치 확장
        fib_ext = TechnicalIndicators.fibonacci_extension(swing_high, swing_low)

        # 피보나치 되돌림
        fib_ret = TechnicalIndicators.fibonacci_levels(swing_high, swing_low)

        targets = {
            "현재가": current,
            "스윙_고점": swing_high,
            "스윙_저점": swing_low,
        }
        targets.update(fib_ext)
        targets.update(fib_ret)

        # 1차/2차 목표가 설정
        ext_values = sorted([v for k, v in fib_ext.items() if v > current])
        if ext_values:
            targets["1차_목표가"] = ext_values[0]
            if len(ext_values) > 1:
                targets["2차_목표가"] = ext_values[1]

        return targets


# ──────────────────────────────────────────
# 싱글톤 인스턴스
# ──────────────────────────────────────────
indicators = TechnicalIndicators()
