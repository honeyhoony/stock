"""
╔══════════════════════════════════════════════════════════╗
║  텔레그램 봇 — 인라인 키보드 매수 버튼 + KIS 주문 연동     ║
║  • A급 종목 전용 보고 (3단계 AND 필터 통과 종목만)         ║
║  • [매수 실행] 버튼 → 한국투자증권 시장가 주문             ║
║  • /status, /report, /list, /add, /del 명령어            ║
╚══════════════════════════════════════════════════════════╝
"""
import logging
import requests
import json
import time
import threading
from datetime import datetime
from typing import Optional, Dict, List

from config import telegram_config, kis_config

logger = logging.getLogger(__name__)


# ══════════════════════════════════════
# KIS API — 주문 기능
# ══════════════════════════════════════
class KISOrderAPI:
    """한국투자증권 주식 주문 API"""

    def __init__(self):
        from data_collector import kis_auth
        self.auth = kis_auth

    def place_buy_order(
        self,
        ticker: str,
        quantity: int,
        price: int = 0,
        order_type: str = "market",
    ) -> dict:
        """
        매수 주문 실행
        order_type: 'market' (시장가) / 'limit' (지정가)
        """
        if kis_config.is_paper:
            tr_id = "VTTC0802U"  # 모의투자 매수
        else:
            tr_id = "TTTC0802U"  # 실전 매수

        headers = self.auth.get_headers(tr_id)
        headers["Content-Type"] = "application/json; charset=utf-8"

        # 계좌번호 분리
        acct = kis_config.account_no.split("-")
        acct_prefix = acct[0] if acct else ""
        acct_suffix = acct[1] if len(acct) > 1 else "01"

        body = {
            "CANO": acct_prefix,
            "ACNT_PRDT_CD": acct_suffix,
            "PDNO": ticker,
            "ORD_DVSN": "01" if order_type == "market" else "00",
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0" if order_type == "market" else str(price),
        }

        url = f"{kis_config.base_url}/uapi/domestic-stock/v1/trading/order-cash"

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("rt_cd") == "0":
                output = data.get("output", {})
                return {
                    "success": True,
                    "order_no": output.get("ODNO", ""),
                    "order_time": output.get("ORD_TMD", ""),
                    "message": f"주문 체결: {ticker} {quantity}주",
                }
            else:
                return {
                    "success": False,
                    "message": data.get("msg1", "주문 실패"),
                    "detail": data.get("msg_cd", ""),
                }

        except Exception as e:
            logger.error(f"KIS 주문 오류: {e}")
            return {"success": False, "message": str(e)}


# ══════════════════════════════════════
# 텔레그램 봇
# ══════════════════════════════════════
class TradingTelegramBot:
    """
    트레이딩 전용 텔레그램 봇
    - A급 종목 탐지 시 인라인 [매수 실행] 버튼 전송
    - 사용자가 버튼 누르면 KIS API로 실제 주문
    """

    def __init__(self):
        self.token = telegram_config.bot_token
        self.chat_id = telegram_config.chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.order_api = KISOrderAPI()
        self._running = False
        self._offset = 0
        self._thread: Optional[threading.Thread] = None

    @property
    def enabled(self):
        return telegram_config.enabled

    # ── 기본 전송 ──
    def send_message(self, text: str, parse_mode: str = "Markdown"):
        """일반 텍스트 메시지 전송"""
        if not self.enabled:
            logger.info(f"[TG OFF] {text[:80]}...")
            return None
        try:
            r = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
                timeout=10,
            )
            return r.json()
        except Exception as e:
            logger.error(f"TG 전송 실패: {e}")
            return None

    def send_with_buttons(
        self, text: str, buttons: list, parse_mode: str = "Markdown"
    ):
        """인라인 키보드 버튼 포함 메시지 전송"""
        if not self.enabled:
            logger.info(f"[TG OFF] {text[:80]}...")
            return None
        try:
            r = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "reply_markup": {
                        "inline_keyboard": buttons,
                    },
                },
                timeout=10,
            )
            return r.json()
        except Exception as e:
            logger.error(f"TG 버튼 전송 실패: {e}")
            return None

    def answer_callback(self, callback_id: str, text: str):
        """콜백 쿼리 응답"""
        try:
            requests.post(
                f"{self.api_url}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text},
                timeout=5,
            )
        except Exception:
            pass

    def edit_message(self, message_id: int, text: str):
        """기존 메시지 편집"""
        try:
            requests.post(
                f"{self.api_url}/editMessageText",
                json={
                    "chat_id": self.chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=5,
            )
        except Exception:
            pass

    # ══════════════════════════════════════
    # A급 종목 보고 (3단계 AND 필터 통과)
    # ══════════════════════════════════════
    def send_a_grade_alert(self, signal: dict, default_qty: int = 10):
        """
        A급/S급 종목 알림 전송 — [매수 실행] 인라인 버튼 포함 (약세장 시 비활성)
        """
        from risk_manager import risk_manager
        mc = risk_manager.analyze_market_condition()
        is_bear = mc.market_phase == "BEAR"

        grade = signal.get("grade", "B")
        grade_emoji = {"S": "🏆", "A": "⭐"}.get(grade, "")
        ticker = signal.get("ticker", "")
        name = signal.get("name", "")
        strategies = signal.get("multi_strategies", [])
        filters = signal.get("filter_results", {})
        supply = filters.get("supply_details", {})
        
        # 수급 가속도 (V2 추가)
        accel_label = signal.get("supply_acceleration", "분석 중...")

        # 수급 현황 표시
        supply_lines = []
        if supply.get("외인순매수", 0) > 0:
            supply_lines.append(f"  🌐 외인: +{supply.get('외인순매수', 0):,}주")
        elif supply.get("외인순매수", 0) != 0:
            supply_lines.append(f"  🌐 외인: {supply.get('외인순매수', 0):,}주")
        if supply.get("기관순매수", 0) > 0:
            supply_lines.append(f"  🏛 기관: +{supply.get('기관순매수', 0):,}주")
        elif supply.get("기관순매수", 0) != 0:
            supply_lines.append(f"  🏛 기관: {supply.get('기관순매수', 0):,}주")
        if supply.get("프로그램순매수", 0) > 0:
            supply_lines.append(f"  🤖 프로그램: +{supply.get('프로그램순매수', 0):,}주")
        elif supply.get("프로그램순매수", 0) != 0:
            supply_lines.append(f"  🤖 프로그램: {supply.get('프로그램순매수', 0):,}주")

        supply_text = "\n".join(supply_lines) if supply_lines else "  (조회 중)"

        # 3단계 필터 통과 체크마크
        f1 = "✅" if filters.get("pattern_overlap") else "❌"
        f2 = "✅" if filters.get("supply_sync") else "❌"
        f3 = "✅" if filters.get("market_ok") else "❌"

        text = f"""
{grade_emoji} *{grade}급 종목 탐지* — {name}({ticker})

━━ 3단계 AND 필터 ━━
{f1} 패턴 중첩: {' + '.join(strategies)}
{f2} 수급 동기화: {filters.get('supply_buy_count', 0)}/3 매수세
{f3} 시장 환경: {filters.get('market_phase', 'N/A')}

━━ 실시간 수급 가속도 ━━
🚀 {accel_label}
{supply_text}

━━ 매매 포인트 ━━
📊 현재가: {int(signal.get('current_price', 0)):,}원
🎯 1차 매수: {int(signal.get('entry_price_1', 0)):,}원
📈 목표가: {int(signal.get('target_price_1', 0)):,}원
🛡 손절가: {int(signal.get('stop_loss', 0)):,}원
🚨 신뢰도: {signal.get('confidence', 0):.0f}%

{"⚠️ *[보호 모드]* 시장 약세로 매수 버튼이 비활성화되었습니다." if is_bear else ""}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""".strip()

        # 인라인 버튼: [매수 실행] [상세 보기]
        buttons = []
        if not is_bear:
            buttons.append([
                {
                    "text": f"🟢 매수 실행 ({default_qty}주)",
                    "callback_data": json.dumps({
                        "action": "buy",
                        "ticker": ticker,
                        "qty": default_qty,
                    }),
                }
            ])
        
        buttons.append([
            {
                "text": "📋 상세 근거",
                "callback_data": json.dumps({
                    "action": "detail",
                    "ticker": ticker,
                }),
            }
        ])

        return self.send_with_buttons(text, buttons)

    # ══════════════════════════════════════
    # 콜백 처리 ([매수 실행] 버튼)
    # ══════════════════════════════════════
    def handle_callback(self, callback_query: dict):
        """인라인 버튼 콜백 처리"""
        callback_id = callback_query.get("id", "")
        data_str = callback_query.get("data", "{}")
        message = callback_query.get("message", {})
        msg_id = message.get("message_id", 0)

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            self.answer_callback(callback_id, "⚠️ 잘못된 요청")
            return

        action = data.get("action", "")

        if action == "buy":
            # 매수 주문 실행!
            ticker = data.get("ticker", "")
            qty = data.get("qty", 10)

            self.answer_callback(callback_id, f"⏳ {ticker} {qty}주 매수 주문 중...")

            result = self.order_api.place_buy_order(
                ticker=ticker, quantity=qty, order_type="market",
            )

            if result.get("success"):
                reply = (
                    f"✅ *매수 체결 완료*\n\n"
                    f"종목: {ticker}\n"
                    f"수량: {qty}주\n"
                    f"주문번호: {result.get('order_no', '')}\n"
                    f"시간: {result.get('order_time', '')}\n\n"
                    f"📌 Supabase 보유 목록에 자동 등록됩니다."
                )

                # Supabase에 자동 등록
                try:
                    import supabase_client as supa
                    from data_collector import collector
                    price_data = collector.get_current_price(ticker)
                    buy_price = price_data.get("현재가", 0) if price_data else 0
                    stock_name = collector.get_stock_name(ticker)

                    supa.add_holding(
                        ticker=ticker,
                        name=stock_name,
                        buy_price=buy_price,
                        quantity=qty,
                        account_note="텔레그램 매수",
                    )
                except Exception as e:
                    logger.warning(f"Supabase 등록 실패: {e}")

            else:
                reply = (
                    f"❌ *매수 실패*\n\n"
                    f"종목: {ticker}\n"
                    f"사유: {result.get('message', '알 수 없음')}\n\n"
                    f"{'모의투자' if kis_config.is_paper else '실전'} 모드"
                )

            self.edit_message(msg_id, reply)

        elif action == "detail":
            ticker = data.get("ticker", "")
            self.answer_callback(callback_id, f"📋 {ticker} 상세 정보 조회 중...")

            try:
                from data_collector import collector
                price = collector.get_current_price(ticker)
                supply = collector.get_supply_demand(ticker)

                detail = (
                    f"📋 *{ticker} 상세 정보*\n\n"
                    f"현재가: {price.get('현재가', 0):,}원\n"
                    f"등락률: {price.get('등락률', 0):+.2f}%\n"
                    f"거래량: {price.get('거래량', 0):,}\n"
                    f"체결강도: {price.get('체결강도', 0):.1f}\n\n"
                    f"외인순매수: {supply.get('details', {}).get('외인순매수', 0):,}주\n"
                    f"기관순매수: {supply.get('details', {}).get('기관순매수', 0):,}주\n"
                    f"프로그램순매수: {supply.get('details', {}).get('프로그램순매수', 0):,}주\n"
                )
                self.send_message(detail)
            except Exception as e:
                self.send_message(f"조회 실패: {e}")

    # ── 명령어 처리 ──
    def handle_message(self, text: str) -> str:
        """텍스트 명령어 처리"""
        text = text.strip()

        if text.startswith("/status") or text == "상태":
            return self._cmd_status()
        elif text.startswith("/report") or text == "보고":
            return self._cmd_report()
        elif text.startswith("/list") or text == "보유":
            return self._cmd_list()
        elif text.startswith(("/add", "/등록")):
            return self._cmd_add(text)
        elif text.startswith(("/del", "/삭제")):
            return self._cmd_del(text)
        elif text.startswith("/help") or text == "도움":
            return self._cmd_help()
        else:
            return ""

    def _cmd_status(self) -> str:
        from risk_manager import risk_manager
        mc = risk_manager.analyze_market_condition()
        return (
            f"📊 *시스템 상태*\n\n"
            f"시장: {mc.market_phase}\n"
            f"코스피: {mc.kospi_value:,.0f} (MA5: {mc.kospi_ma5:,.0f})\n"
            f"코스닥: {mc.kosdaq_value:,.0f} (MA5: {mc.kosdaq_ma5:,.0f})\n"
            f"최대비중: {mc.max_weight:.0%}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )

    def _cmd_report(self) -> str:
        import supabase_client as supa
        return supa.generate_daily_summary()

    def _cmd_list(self) -> str:
        import supabase_client as supa
        holdings = supa.get_all_holdings()
        if not holdings:
            return "📋 보유 종목이 없습니다."
        lines = ["📌 *보유 종목*\n"]
        for h in holdings:
            pnl = float(h.get("pnl_pct", 0))
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{emoji} {h['name']}({h['ticker']}) "
                f"{pnl:+.1f}%"
            )
        return "\n".join(lines)

    def _cmd_add(self, text: str) -> str:
        """
        /add 005930 삼성전자 78500 10
        /등록 005930 삼성전자 78500
        """
        import supabase_client as supa
        parts = text.split()
        if len(parts) < 4:
            return "⚠️ 형식: /add [종목코드] [종목명] [매수가] [수량]"
        try:
            ticker = parts[1]
            name = parts[2]
            price = float(parts[3])
            qty = int(parts[4]) if len(parts) > 4 else 0
            result = supa.add_holding(ticker, name, price, qty)
            if result:
                return f"✅ {name}({ticker}) @{int(price):,} 등록 완료!"
            return "❌ 등록 실패"
        except Exception as e:
            return f"❌ 오류: {e}"

    def _cmd_del(self, text: str) -> str:
        import supabase_client as supa
        parts = text.split()
        if len(parts) < 2:
            return "⚠️ 형식: /del [종목코드]"
        ticker = parts[1]
        if supa.remove_holding(ticker):
            return f"🗑️ {ticker} 삭제 완료"
        return f"❌ {ticker} 삭제 실패"

    def _cmd_help(self) -> str:
        return (
            "🤖 *퀀트 에이전트 명령어*\n\n"
            "/status — 시장 상태\n"
            "/report — 일일 보고서\n"
            "/list — 보유 종목\n"
            "/add [코드] [이름] [매수가] [수량]\n"
            "/del [코드]\n"
            "/help — 도움말"
        )

    # ══════════════════════════════════════
    # 폴링 루프 (콜백 + 메시지 수신)
    # ══════════════════════════════════════
    def start_polling(self):
        """백그라운드에서 텔레그램 메시지/콜백 수신"""
        if not self.enabled:
            logger.info("텔레그램 봇 비활성")
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("🤖 텔레그램 봇 폴링 시작")

    def stop_polling(self):
        self._running = False

    def _poll_loop(self):
        while self._running:
            try:
                r = requests.get(
                    f"{self.api_url}/getUpdates",
                    params={"offset": self._offset, "timeout": 30},
                    timeout=35,
                )
                updates = r.json().get("result", [])

                for u in updates:
                    self._offset = u["update_id"] + 1

                    # 콜백 쿼리 (인라인 버튼)
                    if "callback_query" in u:
                        self.handle_callback(u["callback_query"])

                    # 일반 메시지
                    elif "message" in u:
                        msg = u["message"]
                        text = msg.get("text", "")
                        chat_id = msg.get("chat", {}).get("id")

                        if str(chat_id) == str(self.chat_id) and text:
                            reply = self.handle_message(text)
                            if reply:
                                self.send_message(reply)

            except requests.exceptions.Timeout:
                continue
            except Exception as e:
                logger.error(f"TG 폴링 오류: {e}")
                time.sleep(5)


# ──────────────────────────────────────────
# 싱글톤
# ──────────────────────────────────────────
trading_bot = TradingTelegramBot()
