"""
╔══════════════════════════════════════════════════════════╗
║  관찰 리스트 매니저 (Watchlist Manager)                    ║
║  보유 종목 등록 · 실시간 손절 감시 · 텔레그램 알림           ║
╚══════════════════════════════════════════════════════════╝
"""
import json
import os
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

from config import kis_config, risk_config, telegram_config
from data_collector import collector
from indicators import TechnicalIndicators as TI

logger = logging.getLogger(__name__)

WATCHLIST_FILE = "watchlist.json"


# ──────────────────────────────────────────
# 데이터 구조
# ──────────────────────────────────────────
@dataclass
class WatchItem:
    """관찰 종목"""
    ticker: str
    name: str
    buy_price: float
    quantity: int = 0
    added_date: str = ""
    # 자동 분석 결과
    stop_loss_price: float = 0.0       # 기계적 손절가
    ma20_price: float = 0.0            # 현재 20일선
    current_price: float = 0.0         # 현재가
    pnl_pct: float = 0.0              # 손익률 %
    pnl_amount: float = 0.0           # 손익 금액
    status: str = "정상"               # 정상 / 경고 / 손절임박 / 손절도달
    alert_sent: bool = False           # 알림 전송 여부
    last_checked: str = ""
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WatchItem":
        d.pop("reasons", None)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ──────────────────────────────────────────
# 관찰 리스트 매니저
# ──────────────────────────────────────────
class WatchlistManager:
    """보유 종목 관리 + 실시간 손절 감시"""

    def __init__(self):
        self.items: Dict[str, WatchItem] = {}
        self._load()
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitoring = False

    # ══════════════════════════════════════
    # 1. CRUD 기능
    # ══════════════════════════════════════
    def add(self, ticker: str, buy_price: float, name: str = "",
            quantity: int = 0) -> WatchItem:
        """관찰 종목 추가"""
        if not name:
            name = collector.get_stock_name(ticker)

        item = WatchItem(
            ticker=ticker,
            name=name,
            buy_price=buy_price,
            quantity=quantity,
            added_date=datetime.now().isoformat(),
        )

        # 자동 손절가 분석
        item = self._analyze_stop_loss(item)

        self.items[ticker] = item
        self._save()
        logger.info(f"📌 관찰 등록: {name}({ticker}) 매수가 {int(buy_price):,}원")
        return item

    def remove(self, ticker: str) -> bool:
        """관찰 종목 제거"""
        if ticker in self.items:
            name = self.items[ticker].name
            del self.items[ticker]
            self._save()
            logger.info(f"🗑️ 관찰 해제: {name}({ticker})")
            return True
        return False

    def update_price(self, ticker: str, buy_price: float) -> Optional[WatchItem]:
        """매수가 수정"""
        if ticker in self.items:
            self.items[ticker].buy_price = buy_price
            self.items[ticker] = self._analyze_stop_loss(self.items[ticker])
            self._save()
            return self.items[ticker]
        return None

    def get_all(self) -> List[WatchItem]:
        """전체 관찰 리스트"""
        return list(self.items.values())

    def get(self, ticker: str) -> Optional[WatchItem]:
        """특정 종목 조회"""
        return self.items.get(ticker)

    # ══════════════════════════════════════
    # 2. 손절가 자동 분석
    # ══════════════════════════════════════
    def _analyze_stop_loss(self, item: WatchItem) -> WatchItem:
        """차트 기반 맞춤 손절가 계산"""
        try:
            df = collector.get_ohlcv(item.ticker, 100)
            if df.empty or len(df) < 20:
                # 기본 손절가: 매수가 -3%
                item.stop_loss_price = round(item.buy_price * 0.97, 0)
                return item

            df = TI.add_all_ma(df)

            # ATR 기반 손절가
            atr = TI.atr(df)
            if len(atr.dropna()) > 0:
                atr_val = atr.iloc[-1]
                atr_stop = item.buy_price - (atr_val * risk_config.atr_multiplier)
            else:
                atr_stop = item.buy_price * 0.95

            # 20일선 기반 손절가
            if "MA20" in df.columns and not df["MA20"].isna().all():
                ma20_stop = df["MA20"].iloc[-1] * 0.98  # MA20의 2% 아래
                item.ma20_price = float(df["MA20"].iloc[-1])
            else:
                ma20_stop = item.buy_price * 0.95
                item.ma20_price = 0

            # 3% 기계적 손절
            pct_stop = item.buy_price * 0.97

            # 가장 보수적(높은) 손절가 채택
            item.stop_loss_price = round(max(atr_stop, ma20_stop, pct_stop), 0)

        except Exception as e:
            logger.warning(f"{item.ticker} 손절 분석 실패: {e}")
            item.stop_loss_price = round(item.buy_price * 0.97, 0)

        return item

    # ══════════════════════════════════════
    # 3. 실시간 가격 체크 + 손절 감시
    # ══════════════════════════════════════
    def check_all(self) -> List[dict]:
        """전 종목 현재가 체크 + 상태 업데이트"""
        results = []

        for ticker, item in self.items.items():
            try:
                price_data = collector.get_current_price(ticker)
                if not price_data:
                    continue

                current_price = price_data.get("현재가", 0)
                if current_price <= 0:
                    continue

                item.current_price = current_price
                item.pnl_pct = round(
                    (current_price - item.buy_price) / item.buy_price * 100, 2
                )
                item.pnl_amount = round(
                    (current_price - item.buy_price) * max(item.quantity, 1), 0
                )
                item.last_checked = datetime.now().isoformat()
                item.reasons = []

                # ── 상태 판별 ──
                old_status = item.status

                # 1) -3% 이하 도달
                if item.pnl_pct <= -3.0:
                    item.status = "손절도달"
                    item.reasons.append(
                        f"🚨 매수가 대비 {item.pnl_pct:+.1f}% 하락 (손절 기준 -3% 도달)"
                    )

                # 2) 손절가 근접 (-1% 이내)
                elif current_price <= item.stop_loss_price * 1.01:
                    item.status = "손절임박"
                    item.reasons.append(
                        f"⚠️ 손절가({int(item.stop_loss_price):,}원) 근접! "
                        f"현재가 {int(current_price):,}원"
                    )

                # 3) 20일선 하향 돌파 체크
                elif item.ma20_price > 0 and current_price < item.ma20_price:
                    # 추가 확인: OHLCV에서 어제는 위였는지
                    df = collector.get_ohlcv(ticker, 30)
                    if not df.empty and len(df) >= 2:
                        df = TI.add_all_ma(df, [20])
                        if "MA20" in df.columns:
                            yesterday_close = df["종가"].iloc[-2]
                            yesterday_ma20 = df["MA20"].iloc[-2]
                            item.ma20_price = float(df["MA20"].iloc[-1])

                            if yesterday_close > yesterday_ma20:
                                item.status = "경고"
                                item.reasons.append(
                                    f"📉 20일선({int(item.ma20_price):,}원) 하향 돌파! "
                                    f"현재가 {int(current_price):,}원"
                                )
                            else:
                                item.status = "경고"
                                item.reasons.append(
                                    f"20일선({int(item.ma20_price):,}원) 아래 위치"
                                )

                # 4) -1% ~ -3% 경고
                elif item.pnl_pct <= -1.0:
                    item.status = "경고"
                    item.reasons.append(f"주의: 매수가 대비 {item.pnl_pct:+.1f}% 하락 중")

                # 5) 정상
                else:
                    item.status = "정상"
                    if item.pnl_pct > 5:
                        item.reasons.append(f"✅ 수익 구간 ({item.pnl_pct:+.1f}%)")
                    elif item.pnl_pct > 0:
                        item.reasons.append(f"소폭 수익 ({item.pnl_pct:+.1f}%)")
                    else:
                        item.reasons.append(f"소폭 하락 ({item.pnl_pct:+.1f}%)")

                # ── 알림 조건 ──
                need_alert = (
                    item.status in ("손절도달", "손절임박", "경고")
                    and old_status != item.status
                )

                results.append({
                    "item": item.to_dict(),
                    "alert": need_alert,
                })

                if need_alert:
                    item.alert_sent = True

            except Exception as e:
                logger.warning(f"{ticker} 체크 실패: {e}")

        self._save()
        return results

    # ══════════════════════════════════════
    # 4. 일일 요약 보고
    # ══════════════════════════════════════
    def generate_daily_report(self) -> str:
        """일일 손익 요약 보고서 생성"""
        if not self.items:
            return "📋 관찰 리스트가 비어 있습니다."

        # 먼저 체크
        self.check_all()

        lines = [
            "━" * 36,
            "📊 일일 포트폴리오 요약",
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "━" * 36,
            "",
        ]

        total_pnl = 0
        danger_items = []
        profit_items = []

        for item in sorted(self.items.values(), key=lambda x: x.pnl_pct):
            emoji = "🟢" if item.pnl_pct >= 0 else "🔴"
            status_emoji = {
                "정상": "✅", "경고": "⚠️",
                "손절임박": "🚨", "손절도달": "💀"
            }.get(item.status, "❓")

            lines.append(
                f"{status_emoji} {item.name}({item.ticker})"
            )
            lines.append(
                f"   매수가: {int(item.buy_price):,} → "
                f"현재가: {int(item.current_price):,} "
                f"({emoji}{item.pnl_pct:+.1f}%)"
            )
            if item.reasons:
                lines.append(f"   {item.reasons[0]}")
            lines.append(
                f"   손절가: {int(item.stop_loss_price):,} / "
                f"MA20: {int(item.ma20_price):,}"
            )
            lines.append("")

            total_pnl += item.pnl_amount
            if item.status in ("경고", "손절임박", "손절도달"):
                danger_items.append(item.name)
            if item.pnl_pct > 0:
                profit_items.append(item.name)

        lines.append("━" * 36)
        lines.append(f"💰 총 손익: {int(total_pnl):+,}원")
        lines.append(f"📈 수익 종목: {len(profit_items)}개")
        lines.append(f"⚠️ 주의 종목: {len(danger_items)}개")
        if danger_items:
            lines.append(f"   → {', '.join(danger_items)}")
        lines.append("━" * 36)

        return "\n".join(lines)

    def generate_alert_message(self, item: WatchItem) -> str:
        """긴급 알림 메시지 생성"""
        emoji_map = {
            "손절도달": "🚨🚨🚨",
            "손절임박": "⚠️🚨",
            "경고": "⚠️",
        }
        emoji = emoji_map.get(item.status, "📌")

        msg = f"""
{emoji} *{item.status}* — {item.name}({item.ticker})

💰 매수가: {int(item.buy_price):,}원
📊 현재가: {int(item.current_price):,}원
📉 손익: {item.pnl_pct:+.1f}%
🛑 손절가: {int(item.stop_loss_price):,}원
📐 MA20: {int(item.ma20_price):,}원
"""
        if item.reasons:
            msg += f"\n📌 사유: {item.reasons[0]}"

        if item.status == "손절도달":
            msg += "\n\n🎬 *지금 매도를 준비하세요!*"
        elif item.status == "손절임박":
            msg += "\n\n⏰ *매도 준비 단계 — 추가 하락 시 즉시 매도*"

        return msg.strip()

    # ══════════════════════════════════════
    # 5. 백그라운드 모니터링
    # ══════════════════════════════════════
    def start_monitoring(self, interval_sec: int = 60):
        """백그라운드 가격 감시 시작 (기본 1분 간격)"""
        if self._monitoring:
            logger.info("이미 모니터링 중")
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval_sec,),
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info(f"🔄 관찰 리스트 모니터링 시작 ({interval_sec}초 간격)")

    def stop_monitoring(self):
        """모니터링 중지"""
        self._monitoring = False
        logger.info("⏹️ 모니터링 중지")

    def _monitor_loop(self, interval_sec: int):
        """모니터링 루프"""
        while self._monitoring:
            try:
                if self.items:
                    results = self.check_all()

                    # 알림 필요한 종목 처리
                    for r in results:
                        if r["alert"]:
                            item_data = r["item"]
                            ticker = item_data["ticker"]
                            item = self.items.get(ticker)
                            if item:
                                msg = self.generate_alert_message(item)
                                self._send_telegram(msg)
                                logger.warning(
                                    f"🚨 알림 전송: {item.name} [{item.status}] "
                                    f"({item.pnl_pct:+.1f}%)"
                                )

                    # 매일 17시에 일일 보고
                    now = datetime.now()
                    if now.hour == 17 and now.minute < 2:
                        report = self.generate_daily_report()
                        self._send_telegram(report)
                        logger.info("📊 일일 보고서 전송 완료")

            except Exception as e:
                logger.error(f"모니터링 오류: {e}")

            time.sleep(interval_sec)

    def _send_telegram(self, message: str):
        """텔레그램 메시지 전송"""
        if not telegram_config.enabled:
            logger.info(f"[텔레그램 비활성] {message[:80]}...")
            return

        try:
            import requests
            url = f"https://api.telegram.org/bot{telegram_config.bot_token}/sendMessage"
            payload = {
                "chat_id": telegram_config.chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"텔레그램 전송 실패: {e}")

    # ══════════════════════════════════════
    # 6. 저장/로드
    # ══════════════════════════════════════
    def _save(self):
        """JSON 파일로 저장"""
        data = {k: v.to_dict() for k, v in self.items.items()}
        try:
            with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"관찰 리스트 저장 실패: {e}")

    def _load(self):
        """JSON 파일에서 로드"""
        if not os.path.exists(WATCHLIST_FILE):
            return
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for ticker, item_dict in data.items():
                self.items[ticker] = WatchItem(**{
                    k: v for k, v in item_dict.items()
                    if k in WatchItem.__dataclass_fields__
                })
            logger.info(f"📂 관찰 리스트 로드: {len(self.items)}개 종목")
        except Exception as e:
            logger.error(f"관찰 리스트 로드 실패: {e}")


# ──────────────────────────────────────────
# 텔레그램 봇 수신 (관찰 종목 등록)
# ──────────────────────────────────────────
class TelegramWatchBot:
    """텔레그램 메시지 수신하여 관찰 리스트 관리"""

    def __init__(self, watchlist: WatchlistManager):
        self.watchlist = watchlist
        self._running = False
        self._last_update_id = 0

    def start(self):
        """텔레그램 봇 폴링 시작"""
        if not telegram_config.enabled:
            logger.info("텔레그램 비활성 — 봇 시작 안함")
            return

        self._running = True
        thread = threading.Thread(target=self._poll_loop, daemon=True)
        thread.start()
        logger.info("🤖 텔레그램 봇 수신 시작")

    def stop(self):
        self._running = False

    def _poll_loop(self):
        """텔레그램 메시지 폴링"""
        import requests
        while self._running:
            try:
                url = (
                    f"https://api.telegram.org/bot{telegram_config.bot_token}"
                    f"/getUpdates?offset={self._last_update_id + 1}&timeout=30"
                )
                resp = requests.get(url, timeout=35)
                data = resp.json()

                for update in data.get("result", []):
                    self._last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "").strip()
                    chat_id = msg.get("chat", {}).get("id")

                    if text and chat_id:
                        reply = self._handle_message(text)
                        self._reply(chat_id, reply)

            except Exception as e:
                logger.debug(f"텔레그램 폴링 오류: {e}")
                time.sleep(5)

            time.sleep(1)

    def _handle_message(self, text: str) -> str:
        """메시지 파싱 및 처리"""
        text = text.strip()

        # /목록 — 관찰 리스트 조회
        if text in ("/목록", "/list", "/리스트"):
            items = self.watchlist.get_all()
            if not items:
                return "📋 관찰 리스트가 비어 있습니다."
            lines = ["📋 *관찰 리스트*\n"]
            for item in items:
                emoji = "🟢" if item.pnl_pct >= 0 else "🔴"
                lines.append(
                    f"• {item.name}({item.ticker}) "
                    f"{int(item.buy_price):,}원 "
                    f"{emoji}{item.pnl_pct:+.1f}%"
                )
            return "\n".join(lines)

        # /보고 — 일일 보고서
        if text in ("/보고", "/report", "/요약"):
            return self.watchlist.generate_daily_report()

        # /삭제 종목코드
        if text.startswith(("/삭제", "/remove")):
            parts = text.split()
            if len(parts) >= 2:
                ticker = parts[1].strip()
                if self.watchlist.remove(ticker):
                    return f"🗑️ {ticker} 관찰 해제 완료"
                return f"❌ {ticker}를 찾을 수 없습니다."

        # 종목 등록: "삼성전자 / 78500" 또는 "005930 / 78500"
        if "/" in text:
            return self._parse_add(text)

        # 종목 등록: "삼성전자 78500"
        parts = text.split()
        if len(parts) >= 2:
            try:
                float(parts[-1].replace(",", ""))
                return self._parse_add(text.replace(" ", " / ", 1))
            except ValueError:
                pass

        return (
            "📌 *관찰 리스트 사용법*\n\n"
            "종목 등록:\n"
            " `삼성전자 / 78500`\n"
            " `005930 / 78500`\n\n"
            "명령어:\n"
            " /목록 — 관찰 리스트 보기\n"
            " /보고 — 일일 요약 보고\n"
            " /삭제 005930 — 종목 제거\n"
        )

    def _parse_add(self, text: str) -> str:
        """종목 등록 파싱"""
        parts = [p.strip() for p in text.split("/")]
        if len(parts) < 2:
            return "❌ 형식: `종목명 / 매수가` (예: 삼성전자 / 78500)"

        name_or_ticker = parts[0].strip()
        try:
            buy_price = float(parts[1].replace(",", "").replace("원", ""))
        except ValueError:
            return f"❌ 매수가를 숫자로 입력해주세요: `{parts[1]}`"

        # 종목코드인지 확인
        ticker = name_or_ticker
        name = ""
        if not name_or_ticker.isdigit():
            # 이름으로 코드 찾기
            known = {
                "삼성전자": "005930", "SK하이닉스": "000660",
                "LG에너지솔루션": "373220", "현대차": "005380",
                "삼성바이오로직스": "207940", "삼성SDI": "006400",
                "NAVER": "035420", "네이버": "035420",
                "LG화학": "051910", "셀트리온": "068270",
                "삼성물산": "028260", "카카오": "035720",
                "KB금융": "105560", "신한지주": "055550",
                "LG전자": "066570", "포스코퓨처엠": "003670",
                "기아": "000270", "현대모비스": "012330",
                "SK이노베이션": "096770", "SK": "034730",
                "한국전력": "015760",
            }
            ticker = known.get(name_or_ticker, "")
            name = name_or_ticker
            if not ticker:
                return f"❌ '{name_or_ticker}' 종목코드를 찾을 수 없습니다."

        item = self.watchlist.add(ticker, buy_price, name)
        return (
            f"✅ 관찰 등록 완료!\n\n"
            f"📌 {item.name}({item.ticker})\n"
            f"💰 매수가: {int(item.buy_price):,}원\n"
            f"🛑 자동 손절가: {int(item.stop_loss_price):,}원\n"
            f"📐 MA20: {int(item.ma20_price):,}원"
        )

    def _reply(self, chat_id, text: str):
        """텔레그램 응답"""
        try:
            import requests
            url = f"https://api.telegram.org/bot{telegram_config.bot_token}/sendMessage"
            requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)
        except Exception as e:
            logger.error(f"텔레그램 응답 실패: {e}")


# ──────────────────────────────────────────
# 싱글톤 인스턴스
# ──────────────────────────────────────────
watchlist_manager = WatchlistManager()
