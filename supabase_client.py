"""
╔══════════════════════════════════════════════════════════╗
║  Supabase REST 클라이언트 — eers_chatbot.my_holdings     ║
║  supabase 패키지 없이 REST API 직접 호출 (requests 기반)   ║
║  보유 종목 CRUD · 실시간 수익률 계산 · DB 동기화           ║
╚══════════════════════════════════════════════════════════╝
"""
import logging
import requests
from datetime import datetime
from typing import List, Optional, Dict

from config import supabase_config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# Supabase REST API 헬퍼
# ──────────────────────────────────────────
def _headers():
    """Supabase REST API 헤더"""
    return {
        "apikey": supabase_config.key,
        "Authorization": f"Bearer {supabase_config.key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _base_url():
    """테이블 REST URL"""
    # Supabase REST URL: {url}/rest/v1/{table}
    # 커스텀 스키마 사용 시 Content-Profile 헤더 필요
    return f"{supabase_config.url}/rest/v1/{supabase_config.table}"


def _schema_header():
    """eers_chatbot 스키마 접근 헤더 추가"""
    h = _headers()
    # PostgREST 는 Accept-Profile (GET) / Content-Profile (INSERT/UPDATE) 사용
    h["Accept-Profile"] = supabase_config.schema
    h["Content-Profile"] = supabase_config.schema
    return h


# ══════════════════════════════════════
# CRUD — 보유 종목 관리
# ══════════════════════════════════════
def get_all_holdings() -> List[Dict]:
    """전체 보유 종목 조회"""
    if not supabase_config.enabled:
        logger.debug("Supabase 미설정")
        return []
    try:
        r = requests.get(
            _base_url(),
            headers=_schema_header(),
            params={"select": "*", "order": "created_at.asc"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"보유 종목 조회 실패: {e}")
        return []


def add_holding(
    ticker: str,
    name: str,
    buy_price: float,
    quantity: int = 0,
    account_note: str = "",
    monitoring_mode: str = "손절 중심",
    trailing_stop_pct: float = 5.0,
) -> Optional[Dict]:
    """보유 종목 추가"""
    if not supabase_config.enabled:
        return None
    try:
        data = {
            "ticker": ticker,
            "name": name,
            "buy_price": buy_price,
            "quantity": quantity,
            "account_note": account_note,
            "current_price": buy_price,
            "pnl_pct": 0,
            "pnl_amount": 0,
            "status": "정상",
            "monitoring_mode": monitoring_mode,
            "highest_price": buy_price,
            "trailing_stop_pct": trailing_stop_pct,
            "stop_loss_price": round(buy_price * 0.97, 0),
            "ma20_price": 0,
            "last_reason": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        r = requests.post(
            _base_url(),
            headers=_schema_header(),
            json=data,
            timeout=10,
        )
        r.raise_for_status()
        result = r.json()
        logger.info(f"✅ 보유 종목 추가: {name}({ticker}) [{monitoring_mode}]")
        return result[0] if isinstance(result, list) and result else data
    except Exception as e:
        logger.error(f"종목 추가 실패: {e}")
        return None


def remove_holding(ticker: str) -> bool:
    """보유 종목 삭제"""
    if not supabase_config.enabled:
        return False
    try:
        r = requests.delete(
            _base_url(),
            headers=_schema_header(),
            params={"ticker": f"eq.{ticker}"},
            timeout=10,
        )
        r.raise_for_status()
        logger.info(f"🗑️ 보유 종목 삭제: {ticker}")
        return True
    except Exception as e:
        logger.error(f"종목 삭제 실패: {e}")
        return False


def update_holding(ticker: str, updates: Dict) -> bool:
    """보유 종목 업데이트"""
    if not supabase_config.enabled:
        return False
    try:
        updates["updated_at"] = datetime.now().isoformat()
        r = requests.patch(
            _base_url(),
            headers=_schema_header(),
            params={"ticker": f"eq.{ticker}"},
            json=updates,
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"종목 업데이트 실패 ({ticker}): {e}")
        return False


def upsert_holding(data: Dict) -> bool:
    """보유 종목 Upsert"""
    if not supabase_config.enabled:
        return False
    try:
        data["updated_at"] = datetime.now().isoformat()
        h = _schema_header()
        h["Prefer"] = "return=representation,resolution=merge-duplicates"
        r = requests.post(
            _base_url(),
            headers=h,
            json=data,
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Upsert 실패: {e}")
        return False


# ══════════════════════════════════════
# 실시간 가격 체크 + 상태 갱신
# ══════════════════════════════════════
def check_and_update_all() -> List[Dict]:
    """
    전 보유종목 현재가 체크 → 수익률·상태 갱신 → DB 업데이트
    Returns: 알림이 필요한 종목 리스트
    """
    from data_collector import collector
    from config import system_config

    holdings = get_all_holdings()
    if not holdings:
        return []

    alerts = []

    for h in holdings:
        ticker = h.get("ticker", "")
        buy_price = float(h.get("buy_price", 0))
        old_status = h.get("status", "정상")

        if not ticker or buy_price <= 0:
            continue

        try:
            # 현재가 조회 (KIS API)
            price_data = collector.get_current_price(ticker)
            if not price_data:
                continue

            current_price = price_data.get("현재가", 0)
            if current_price <= 0:
                continue

            # 수익률 계산
            pnl_pct = round((current_price - buy_price) / buy_price * 100, 2)
            quantity = int(h.get("quantity", 0)) or 1
            pnl_amount = round((current_price - buy_price) * quantity, 0)

            # 1. 최고가(Highest) 갱신 및 추적 손절 체크
            highest = float(h.get("highest_price", buy_price))
            if current_price > highest:
                highest = current_price
            
            trail_pct = float(h.get("trailing_stop_pct", 5.0))
            drop_from_high = ((highest - current_price) / highest) * 100
            is_trailing_hit = drop_from_high >= trail_pct and pnl_pct > 0 # 수익권에서만 발동
            
            # 2. MA20 체크
            ma20 = 0
            ma20_break = False
            try:
                from indicators import TechnicalIndicators as TI
                df = collector.get_ohlcv(ticker, 30)
                if not df.empty and len(df) >= system_config.ma_stop_period:
                    df = TI.add_all_ma(df, [system_config.ma_stop_period])
                    ma_col = f"MA{system_config.ma_stop_period}"
                    if ma_col in df.columns:
                        ma20 = float(df[ma_col].iloc[-1])
                        if len(df) >= 2:
                            y_close = float(df["종가"].iloc[-2])
                            y_ma = float(df[ma_col].iloc[-2])
                            if y_close > y_ma and current_price < ma20:
                                ma20_break = True
            except Exception:
                pass

            # 3. 상태 판별 (V2: 추적 손절 추가)
            reasons = []
            if pnl_pct <= system_config.stop_loss_pct:
                status = "손절도달"
                reasons.append(f"🚨 매수가 대비 {pnl_pct:+.1f}% 하락 (고정 손절)")
            elif is_trailing_hit:
                status = "익절도달"
                reasons.append(f"💰 추적 익절: 고점({int(highest):,}) 대비 {drop_from_high:.1f}% 하락")
            elif ma20_break:
                status = "경고"
                reasons.append(f"📉 {system_config.ma_stop_period}일선 이탈!")
            elif pnl_pct <= -1.0:
                status = "경고"
                reasons.append(f"주의: {pnl_pct:+.1f}% 하락 중")
            else:
                status = "정상"
                if pnl_pct > 0:
                    reasons.append(f"수익 {pnl_pct:+.1f}% (최고가 {int(highest):,})")

            # 4. DB 업데이트
            update_holding(ticker, {
                "current_price": current_price,
                "pnl_pct": pnl_pct,
                "pnl_amount": pnl_amount,
                "ma20_price": ma20,
                "highest_price": highest,
                "status": status,
                "last_reason": reasons[0] if reasons else "",
            })

            # 알림 필요 여부
            if status in ("손절도달", "익절도달", "경고") and old_status != status:
                alerts.append({
                    "ticker": ticker,
                    "name": h.get("name", ticker),
                    "buy_price": buy_price,
                    "current_price": current_price,
                    "pnl_pct": pnl_pct,
                    "status": status,
                    "reason": reasons[0] if reasons else "",
                    "highest": highest,
                })

        except Exception as e:
            logger.warning(f"{ticker} 체크 실패: {e}")

    return alerts


# ══════════════════════════════════════
# 일일 요약 보고
# ══════════════════════════════════════
def generate_daily_summary() -> str:
    """일일 포트폴리오 요약"""
    holdings = get_all_holdings()
    if not holdings:
        return "📋 보유 종목이 없습니다."

    lines = [
        "━" * 36,
        "📊 일일 포트폴리오 요약",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "━" * 36, "",
    ]

    total_pnl = 0
    danger = []

    for h in sorted(holdings, key=lambda x: float(x.get("pnl_pct", 0))):
        pnl = float(h.get("pnl_pct", 0))
        emoji = "🟢" if pnl >= 0 else "🔴"
        status_map = {
            "정상": "✅", "경고": "⚠️",
            "손절임박": "🚨", "손절도달": "💀",
        }
        st = status_map.get(h.get("status", ""), "❓")

        lines.append(f"{st} {h.get('name', '')}({h.get('ticker', '')})")
        lines.append(
            f"   매수: {int(float(h.get('buy_price', 0))):,} → "
            f"현재: {int(float(h.get('current_price', 0))):,} "
            f"({emoji}{pnl:+.1f}%)"
        )
        reason = h.get("last_reason", "")
        if reason:
            lines.append(f"   {reason}")
        lines.append("")

        total_pnl += float(h.get("pnl_amount", 0))
        if h.get("status") in ("경고", "손절도달"):
            danger.append(h.get("name", ""))

    lines.append("━" * 36)
    lines.append(f"💰 총 손익: {int(total_pnl):+,}원")
    lines.append(f"📈 보유: {len(holdings)}개 / ⚠️ 주의: {len(danger)}개")
    if danger:
        lines.append(f"   → {', '.join(danger)}")
    lines.append("━" * 36)

    return "\n".join(lines)


# ══════════════════════════════════════
# 알림 메시지 포맷
# ══════════════════════════════════════
def format_alert_message(alert: Dict) -> str:
    """텔레그램 알림 메시지 포맷"""
    emoji = "🚨🚨🚨" if alert["status"] == "손절도달" else "⚠️"
    action = "지금 매도를 준비하세요!" if alert["status"] == "손절도달" else "주의 관찰 필요"

    return f"""
{emoji} *{alert['status']}* — {alert['name']}({alert['ticker']})

💰 매수가: {int(alert['buy_price']):,}원
📊 현재가: {int(alert['current_price']):,}원
📉 손익: {alert['pnl_pct']:+.1f}%
📐 MA20: {int(alert.get('ma20', 0)):,}원

📌 {alert.get('reason', '')}

🎬 *{action}*
""".strip()
