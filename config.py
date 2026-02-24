"""
╔══════════════════════════════════════════════════════════╗
║  퀀트 트레이딩 시스템 — 설정(Config)                      ║
║  5대 전략: 눌림목 / 바닥탈출 / 골든크로스 / 박스권돌파 / 정배열초입  ║
╚══════════════════════════════════════════════════════════╝
"""
import os
from dataclasses import dataclass, field
from typing import Optional

# .env 파일에서 환경변수 로딩
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ──────────────────────────────────────────
# 1. 한국투자증권 KIS Open API
# ──────────────────────────────────────────
@dataclass
class KISConfig:
    """한국투자증권 Open API 설정"""
    app_key: str = os.getenv("KIS_APP_KEY", "YOUR_APP_KEY")
    app_secret: str = os.getenv("KIS_APP_SECRET", "YOUR_APP_SECRET")
    account_no: str = os.getenv("KIS_ACCOUNT_NO", "00000000-00")  # 계좌번호
    is_paper: bool = True  # True=모의투자, False=실전투자
    base_url: str = ""

    def __post_init__(self):
        if self.is_paper:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"


# ──────────────────────────────────────────
# 2. 텔레그램 알림
# ──────────────────────────────────────────
@dataclass
class TelegramConfig:
    """텔레그램 봇 알림 설정"""
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")
    enabled: bool = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"


# ──────────────────────────────────────────
# 2-1. Supabase (eers_chatbot 스키마)
# ──────────────────────────────────────────
@dataclass
class SupabaseConfig:
    """Supabase 연결 설정"""
    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_KEY", "")
    schema: str = "public" # 406 Not Acceptable 방지를 위해 public 사용 권장
    table: str = "my_holdings"
    enabled: bool = False

    def __post_init__(self):
        self.enabled = bool(self.url and self.key)


# ──────────────────────────────────────────
# 3. 필터링 조건
# ──────────────────────────────────────────
@dataclass
class FilterConfig:
    """잡주 배제용 필터"""
    min_market_cap: int = 100_000_000_000      # 시가총액 1,000억 원 이상
    top_trading_value_rank: int = 100           # 거래대금 상위 100 이내
    exclude_etf: bool = True                   # ETF 제외
    exclude_spac: bool = True                  # SPAC 제외
    markets: list = field(default_factory=lambda: ["KOSPI", "KOSDAQ"])


# ──────────────────────────────────────────
# 4. 전략 파라미터
# ──────────────────────────────────────────
@dataclass
class PullbackParams:
    """눌림목 전략 파라미터"""
    reference_candle_lookback: int = 5         # 기준봉 탐색 기간(일)
    volume_cliff_threshold: float = 0.3        # 분봉 거래량 절벽 임계값 (30% 이하)
    institution_hold_tolerance: float = 0.05   # 기관 보유 수량 변동 허용 범위 (5%)


@dataclass
class BottomEscapeParams:
    """바닥 탈출 전략 파라미터"""
    ma_period: int = 20                        # 이동평균선 기간
    resistance_zone_pct: float = 0.05          # 상방 5% 이내 매물대 벽 확인
    accumulation_volume_ratio: float = 2.0     # 매집봉 판별: 평균 대비 거래량 배수
    accumulation_lookback: int = 20            # 매집봉 탐색 기간(일)


@dataclass
class GoldenCrossParams:
    """골든 크로스 전략 파라미터"""
    short_ma: int = 5                          # 단기 이동평균
    long_ma: int = 20                          # 장기 이동평균
    ma_slope_min: float = 0.0                  # 20일선 기울기 최소값 (평탄 이상)
    rsi_period: int = 14                       # RSI 기간
    rsi_threshold: float = 50.0                # RSI 상향 돌파 기준선


@dataclass
class BreakoutParams:
    """박스권 돌파 전략 파라미터"""
    box_lookback: int = 60                     # 박스권 탐색 기간(일)
    ask_bid_ratio: float = 2.0                 # 매도호가/매수호가 잔량 비율
    program_buy_threshold: int = 10            # 프로그램 매수 초당 체결 횟수
    volume_surge_ratio: float = 2.0            # 돌파 시 거래량 폭증 배수


@dataclass
class ConvergenceParams:
    """정배열 초입 전략 파라미터"""
    ma_periods: list = field(default_factory=lambda: [5, 20, 60, 120])
    convergence_pct: float = 0.03              # 이동평균선 밀집 임계값 (3%)
    sector_trend_weight: float = 1.5           # 업종 상승 추세 가중치
    divergence_confirm_days: int = 3           # 발산 확인 기간


@dataclass
class StrategyConfig:
    """전략 통합 설정"""
    pullback: PullbackParams = field(default_factory=PullbackParams)
    bottom_escape: BottomEscapeParams = field(default_factory=BottomEscapeParams)
    golden_cross: GoldenCrossParams = field(default_factory=GoldenCrossParams)
    breakout: BreakoutParams = field(default_factory=BreakoutParams)
    convergence: ConvergenceParams = field(default_factory=ConvergenceParams)


# ──────────────────────────────────────────
# 5. 리스크 관리
# ──────────────────────────────────────────
@dataclass
class RiskConfig:
    """리스크 관리 설정"""
    market_ma_period: int = 5                  # 시장 지수 이동평균 기간
    bear_market_max_weight: float = 0.30       # 약세장 시 최대 투자비중 30%
    bear_market_strategy: str = "bottom_escape" # 약세장 시 운용 전략
    atr_period: int = 14                       # ATR 변동성 기간
    atr_multiplier: float = 2.0                # 손절가 = 매수가 - ATR × 배수
    trailing_stop_pct: float = 0.05            # 추적 손절 비율 (5%)
    max_position_pct: float = 0.10             # 단일 종목 최대 비중 (10%)
    max_total_positions: int = 10              # 최대 동시 보유 종목 수
    fibonacci_levels: list = field(
        default_factory=lambda: [0.236, 0.382, 0.5, 0.618, 0.786]
    )


# ──────────────────────────────────────────
# 6. 시스템 설정
# ──────────────────────────────────────────
@dataclass
class SystemConfig:
    """시스템 운영 설정"""
    scan_interval_minutes: int = 5             # 스캔 주기 (분)
    holdings_check_interval: int = 1           # 보유종목 체크 주기 (분)
    data_cache_minutes: int = 10               # 데이터 캐시 유효 시간
    log_level: str = "INFO"
    dashboard_port: int = 8000
    timezone: str = "Asia/Seoul"
    db_path: str = "quant_trading.db"          # SQLite DB 경로
    stop_loss_pct: float = -3.0                # 손절 기준 퍼센트
    ma_stop_period: int = 20                   # 이동평균선 이탈 감시 기간
    daily_report_hour: int = 17                # 일일 보고서 전송 시각


# ──────────────────────────────────────────
# 글로벌 설정 인스턴스
# ──────────────────────────────────────────
kis_config = KISConfig()
telegram_config = TelegramConfig()
supabase_config = SupabaseConfig()
filter_config = FilterConfig()
strategy_config = StrategyConfig()
risk_config = RiskConfig()
system_config = SystemConfig()
