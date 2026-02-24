"""
╔══════════════════════════════════════════════════════════╗
║  [주식 가이드] 안티그래비티 퀀트 v4.0 (Premium Finale)     ║
║  • 초고화질 프리미엄 UI: 그라데이션 카드 & 입체적 디자인     ║
║  • 다크/라이트 모드 완벽 시각 보정 (화이트 모드 가시성 해결)  ║
║  • 실시간 데이터 동기화 타임스탬프 & 데이터 상태 표시        ║
║  • 모바일 접속 전용 다이렉트 링크 (IP 자동 추출)             ║
║  • 5대 전략 가이드 & 수급 용어 사전 고도화                  ║
╚══════════════════════════════════════════════════════════╝
"""
import streamlit as st
import pandas as pd
import json
import os
import requests
import socket
import threading
import time
import subprocess
import sys
from datetime import datetime
from collections import defaultdict

# ──────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────
st.set_page_config(
    page_title="[주식 가이드] Premium v4.0",
    page_icon="👑",
    layout="wide",
)

# ──────────────────────────────────────────
# 테마 관리
# ──────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

# ──────────────────────────────────────────
# 유틸리티: 로컬 IP 추출 (모바일 접속용)
# ──────────────────────────────────────────
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

def check_backend_status():
    try:
        r = requests.get(f"{BACKEND_URL}/api/progress", timeout=2)
        return True
    except:
        return False

def start_backend_processes():
    """백엔드 서버 및 에이전트 자동 실행 (24시간 서버 대응)"""
    if not check_backend_status():
        # server.py 실행
        subprocess.Popen([sys.executable, "server.py"], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        # main.py (에이전트) 실행
        subprocess.Popen([sys.executable, "main.py"], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        time.sleep(3) # 서버 부팅 대기

# 앱 시작 시 백엔드 자동 가동
if "processes_checked" not in st.session_state:
    start_backend_processes()
    st.session_state.processes_checked = True

# ──────────────────────────────────────────
# 프리미엄 CSS (Aesthetics focus)
# ──────────────────────────────────────────
def inject_premium_css_v4():
    theme = st.session_state.theme
    if theme == "dark":
        bg = "#0f172a"
        card_bg = "linear-gradient(145deg, #1e293b, #0f172a)"
        text = "#ffffff"
        text_dim = "#94a3b8"
        border = "rgba(148, 163, 184, 0.1)"
        accent = "#6366f1"
        sub_card = "#1e293b"
        shadow = "rgba(0, 0, 0, 0.4)"
        header_text = "#ffffff"
    else:
        bg = "#f1f5f9"
        card_bg = "linear-gradient(145deg, #ffffff, #f1f5f9)"
        text = "#1e293b"
        text_dim = "#64748b"
        border = "rgba(0, 0, 0, 0.05)"
        accent = "#4f46e5"
        sub_card = "#ffffff"
        shadow = "rgba(0, 0, 0, 0.05)"
        header_text = "#0f172a"

    # 전역 사용을 위해 session_state에 저장
    st.session_state.theme_colors = {
        "bg": bg, "card_bg": card_bg, "text": text, "text_dim": text_dim,
        "border": border, "accent": accent, "sub_card": sub_card, "header_text": header_text
    }

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;700;800&family=Outfit:wght@400;600;800&display=swap');
    
    /* 전역 폰트 및 배경 */
    [data-testid="stAppViewContainer"] {{ background-color: {bg} !important; }}
    [data-testid="stSidebar"] {{ background-color: {sub_card} !important; border-right: 1px solid {border}; }}
    
    /* 텍스트 요소 강제 색성 (아이콘 클래스 제외) */
    html, body, .stMarkdown, p, span, label, div, li, b, small {{ 
        font-family: 'Pretendard', sans-serif !important; 
        color: {text} !important;
    }}

    /* 제목 가시성 확정 */
    h1, h2, h3, h4, h5, h6 {{ 
        color: {header_text} !important; 
        font-weight: 800 !important;
        font-family: 'Pretendard', sans-serif !important;
    }}
    
    /* 프리미엄 카드 스타일 */
    .p-card {{
        background: {card_bg};
        border-radius: 24px;
        padding: 26px;
        border: 1px solid {border};
        box-shadow: 0 20px 25px -5px {shadow}, 0 10px 10px -5px {shadow};
        margin-bottom: 24px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    .p-card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 25px 30px -5px {shadow};
        border-color: {accent};
    }}

    /* 수급 상황 전광판 */
    .status-bar {{
        background: linear-gradient(90deg, {accent}, #818cf8);
        color: white !important;
        padding: 12px 20px;
        border-radius: 16px;
        font-weight: 800;
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 0.85rem;
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
    }}

    /* 지표 강조 */
    .metric-title {{ font-size: 0.85rem; color: {text_dim} !important; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }}
    .metric-value {{ font-size: 1.6rem; font-weight: 800; color: {accent} !important; font-family: 'Outfit'; }}

    /* 필 태그 (Pills) */
    .p-pill {{
        background: rgba(99, 102, 241, 0.1);
        color: {accent} !important;
        padding: 6px 14px;
        border-radius: 100px;
        font-size: 0.75rem;
        font-weight: 800;
        border: 1px solid rgba(99, 102, 241, 0.2);
    }}

    /* 신뢰도 배지 */
    .confidence-badge {{
        position: absolute;
        top: 20px;
        right: 20px;
        background: {accent};
        color: white !important;
        padding: 4px 12px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.85rem;
        box-shadow: 0 4px 10px rgba(99, 102, 241, 0.4);
    }}

    .logo-font {{ font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 2rem; color: {accent} !important; }}
    
    /* 도움말 테이블 */
    .h-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; border-radius: 15px; overflow: hidden; }}
    .h-table th {{ background: {accent}; color: white !important; padding: 12px; text-align: left; }}
    .h-table td {{ background: {sub_card}; padding: 12px; border-bottom: 1px solid {border}; font-size: 0.85rem; }}

    .strat-label {{ font-size: 0.7rem; font-weight: 800; color: {text_dim} !important; margin-bottom: 2px; text-transform: uppercase; }}
    </style>
    """, unsafe_allow_html=True)

inject_premium_css_v4()

# ──────────────────────────────────────────
# 데이터 수집 (타임스탬프 포함)
# ──────────────────────────────────────────
BACKEND_URL = "http://127.0.0.1:8000"

@st.cache_data(ttl=5)
def load_quant_data():
    signals = []
    market = None
    last_update = "분석 전"
    
    files = sorted([f for f in os.listdir(".") if f.startswith("scan_result_")], reverse=True)
    if files:
        try:
            mtime = os.path.getmtime(files[0])
            last_update = datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
            with open(files[0], encoding="utf-8") as f:
                signals = json.load(f).get("signals", [])
        except: pass
    
    from risk_manager import risk_manager
    try: market = risk_manager.analyze_market_condition()
    except: pass
    
    return signals, market, last_update

raw_sigs, m_data, update_time = load_quant_data()

# ══════════════════════════════════════
# [1] 사이드바: 전문가 제어 패널
# ══════════════════════════════════════
with st.sidebar:
    st.markdown('<div class="logo-font">QUANT v4.0</div>', unsafe_allow_html=True)
    st.caption(f"최종 분석: {update_time}")
    st.divider()

    # 테마 스위치
    t_val = st.toggle("다크 모드 활성화", value=(st.session_state.theme == "dark"))
    if t_val != (st.session_state.theme == "dark"):
        st.session_state.theme = "dark" if t_val else "light"; st.rerun()

    st.markdown("### 🛠️ 엔진 운영 모드")
    mode = st.radio("전략 프리셋", ["💎 안전 투자 (우량주)", "💰 수익 추구 (중립)", "⚡ 공격 투자 (급등)", "🔥 전체 스캔 (ALL)"], index=1)
    
    # 설정값 프리셋
    mcap_p = 1000; rank_p = 100; strats_p = ["pullback", "bottom_escape", "golden_cross"]
    if "안전" in mode: mcap_p = 3000; rank_p = 100; strats_p = ["pullback", "bottom_escape"]
    elif "공격" in mode: mcap_p = 200; rank_p = 1000; strats_p = ["golden_cross", "breakout"]
    elif "전체" in mode: mcap_p = 0; rank_p = 0; strats_p = ["pullback", "bottom_escape", "golden_cross", "breakout", "convergence"]

    with st.expander("종목군 필터 설정", expanded=True):
        f_mcap = st.number_input("최소 시가총액 (억)", 0, 50000, mcap_p, step=100)
        f_rank = st.number_input("거래대금 상위 순위", 0, 3000, rank_p, step=50)

    with st.expander("전략별 정밀 튜닝 (VPI)", expanded=False):
        st.markdown("##### 1️⃣ 눌림목 (Pullback)")
        p_lookback = st.slider("기준봉 탐색 (일)", 1, 20, 5)
        p_vol = st.slider("거래량 절벽 (%)", 10, 100, 30) / 100
        
        st.markdown("##### 2️⃣ 바닥탈출 (Bottom)")
        b_ma = st.selectbox("기준 이평선", [20, 60, 120], index=0)
        b_vol_ratio = st.slider("매집봉 거래량 배수", 1.5, 5.0, 2.0)
        
        st.markdown("##### 3️⃣ 골든크로스 (GC)")
        g_short = st.number_input("단기 이평", 3, 10, 5)
        g_long = st.number_input("장기 이평", 15, 60, 20)
        g_rsi = st.slider("RSI 기준선", 30, 70, 50)
        
        st.markdown("##### 4️⃣ 박스권돌파 (Break)")
        br_lookback = st.slider("박스권 탐색 기간", 20, 120, 60)
        br_vol = st.slider("돌파 거래량 배수", 1.5, 5.0, 2.0)
        
        st.markdown("##### 5️⃣ 정배열초입 (MA Align)")
        c_pct = st.slider("이평선 밀집도 (%)", 1, 10, 3) / 100

    # 백엔드 전달용 파라미터 묶음
    strat_vars = {
        "p_lookback": p_lookback, "p_vol": p_vol,
        "b_ma": b_ma, "b_vol_ratio": b_vol_ratio,
        "g_short": g_short, "g_long": g_long, "g_rsi": g_rsi,
        "br_lookback": br_lookback, "br_vol": br_vol,
        "c_pct": c_pct
    }

    st.divider()
    
    if st.button("🚀 AI 분석 엔진 가동 (Deep Scan)", type="primary", use_container_width=True):
        # 백그라운드 스캔 실행용 함수
        def run_scan_request(p):
            try: requests.get(f"{BACKEND_URL}/api/scan", params=p, timeout=200)
            except: pass

        # 모든 전략 항상 분석하되 동적 파라미터 적용
        all_strats = ["pullback", "bottom_escape", "golden_cross", "breakout", "convergence"]
        scan_params = {
            "min_market_cap": f_mcap * 100000000, 
            "top_rank": f_rank, 
            "strats": ",".join(all_strats),
            "vars": json.dumps(strat_vars)
        }
        
        # 스레드 시작
        scan_thread = threading.Thread(target=run_scan_request, args=(scan_params,))
        scan_thread.start()

        # 실시간 진행률 표시를 위한 위젯
        p_bar = st.progress(0, text="분석 대기 중...")
        p_msg = st.empty()

        while scan_thread.is_alive():
            try:
                prog = requests.get(f"{BACKEND_URL}/api/progress", timeout=2).json()
                pct = prog.get("percent", 0)
                active_logs = prog.get("active_logs", [])
                strat_prog = prog.get("strategy_progress", {})
                
                # 프로그레스 바 및 멀티 로그 업데이트
                p_bar.progress(pct / 100, text=f"분석 진행 중... {pct}%")
                
                # 전략별 미니 진행률 표시
                if strat_prog:
                    s_cols = st.columns(5)
                    s_names = {"pullback": "눌림목", "bottom_escape": "바닥탈출", "golden_cross": "골든크로스", "breakout": "박스권돌파", "convergence": "정배열초입"}
                    for i, (sk, sn) in enumerate(s_names.items()):
                        with s_cols[i]:
                            spct = strat_prog.get(sk, 0)
                            st.markdown(f'<div class="strat-label">{sn}</div>', unsafe_allow_html=True)
                            st.progress(spct / 100)

                log_html = "".join([f'<div style="font-size:0.85rem; margin-bottom:4px; color:#6366f1">{log}</div>' for log in active_logs])
                p_msg.markdown(f"""
                <div style="background:rgba(99, 102, 241, 0.05); padding:18px; border-radius:16px; border:1px solid rgba(99, 102, 241, 0.2); margin:10px 0">
                    <div style="font-size:0.75rem; color:#94a3b8; margin-bottom:8px; font-weight:800; text-transform:uppercase; letter-spacing:1px">실시간 병렬 분석 로그</div>
                    {log_html if log_html else '<div style="color:#94a3b8">엔진 가동 준비 중...</div>'}
                </div>
                """, unsafe_allow_html=True)
            except:
                pass
            time.sleep(0.8)

        st.success("✅ 심층 분석이 완료되었습니다!")
        st.cache_data.clear()
        st.rerun()

# ══════════════════════════════════════
# [2] 헤더: 시장 상태
# ══════════════════════════════════════

# 백엔드 서버 상태 체크
if not check_backend_status():
    st.error("⚠️ [알림] 분석 엔진 서버(8000)가 작동하지 않고 있습니다. 노트북에서 'server.py'를 실행해 주세요.")

if m_data:
    st.markdown("### 📊 실시간 증시 요약")
    
    # 🔍 시장 국면 한글화 (BULL/BEAR/NEUTRAL -> 한글)
    phase_map = {
        "BULL": "🚀 강력 상승 (매수 유리)",
        "BEAR": "📉 하락 위축 (리스크 관리)",
        "NEUTRAL": "☁️ 횡보 혼조 (종목 차별화)"
    }
    korean_phase = phase_map.get(m_data.market_phase, f"상태 확인 중 ({m_data.market_phase})")
    
    h1, h2, h3, h4 = st.columns(4)
    with h1: st.markdown(f'<div class="p-card"><div class="metric-title">KOSPI 지수</div><div class="metric-value">{m_data.kospi_value:,.1f}</div></div>', unsafe_allow_html=True)
    with h2: st.markdown(f'<div class="p-card"><div class="metric-title">KOSDAQ 지수</div><div class="metric-value">{m_data.kosdaq_value:,.1f}</div></div>', unsafe_allow_html=True)
    with h3: st.markdown(f'<div class="p-card"><div class="metric-title">시장 심리/국면</div><div class="metric-value" style="font-size:0.85rem !important">{korean_phase}</div></div>', unsafe_allow_html=True)
    with h4: st.markdown(f'<div class="p-card"><div class="metric-title">탐지된 신호</div><div class="metric-value">{len(raw_sigs)}건</div></div>', unsafe_allow_html=True)

# ══════════════════════════════════════
# [3] 초보 가이드 (Premium Table)
# ══════════════════════════════════════
with st.expander("📚 [초보자 필독] 시스템 사용법 및 전략 가이드", expanded=False):
    st.markdown("#### 📌 5대 핵심 전략 및 대응법")
    guide_table = """
    <table class="h-table">
        <tr><th>유형</th><th>의미</th><th>초보자 대응 팁</th></tr>
        <tr><td><b>눌림목</b></td><td>상승 도중 잠시 하락한 상태</td><td>가장 추천하는 입문 전략입니다. '싼 가격'에 살 수 있습니다.</td></tr>
        <tr><td><b>바닥탈출</b></td><td>하락이 멈추고 처음 오르는 상태</td><td>안전성이 높습니다. 느긋하게 수익을 보실 분께 좋습니다.</td></tr>
        <tr><td><b>골든크로스</b></td><td>강력한 상승 추세 전환</td><td>매우 유명한 지표입니다. 거래량이 같이 터지면 신뢰도가 높습니다.</td></tr>
        <tr><td><b>박스권돌파</b></td><td>매도 벽을 뚫고 신고가 도전</td><td>속도가 빠릅니다. 단기 수익을 원할 때 적격입니다.</td></tr>
        <tr><td><b>정배열초입</b></td><td>대세 우상향 항해 개시</td><td>안정적으로 길게 가져가기에 가장 좋습니다.</td></tr>
    </table>
    """
    st.markdown(guide_table, unsafe_allow_html=True)
    st.markdown("""
    - **실시간 수급**: '돈의 흐름'입니다. **정상/강력 유입**은 큰손들이 주식을 사고 있다는 증거입니다.
    - **손절가**: 주가가 이 가격 밑으로 내려가면 미련 없이 팔아 자산을 지키라는 경고등입니다.
    """)

# ══════════════════════════════════════
# [4] 공략 리스트 (High-Aesthetics)
# ══════════════════════════════════════
st.markdown("### 🚀 금일 최우선 공략 종목")

def format_price(v):
    try: return f"{int(float(v)):,}"
    except: return "—"

grouped = defaultdict(list)
for s in raw_sigs: grouped[s.get('ticker', '000000')].append(s)

if not grouped:
    st.info("현재 분석된 종목이 없습니다. 왼쪽 '분석 엔진 가동'을 눌러주세요.")
else:
    g_cols = st.columns(2)
    for idx, (ticker, signals) in enumerate(grouped.items()):
        main = signals[0]
        st_names = list(set([s.get('strategy', '—') for s in signals]))
        is_best = main.get('grade') in ('S', 'A')
        m_cap = main.get('market_cap', 0)
        m_cap_str = f"{format_price(m_cap // 100000000)}억" if m_cap > 0 else "—"
        
        with g_cols[idx % 2]:
            tags = " ".join([f'<span class="p-pill">{name}</span>' for name in st_names])
            
            # 전략별 초보자 팁 매핑
            tip_map = {
                "눌림목": "💡 상승 중 일시적 조정 구간입니다. <b>저가 매수</b> 후 반등을 노리세요.",
                "바닥탈출": "🌱 하락이 멈추고 반등이 시작되었습니다. <b>느긋하고 안정적인 투자</b>가 가능합니다.",
                "골든크로스": "⚡ 추세가 상향으로 전환되었습니다. <b>거래량이 터질 때 매수</b>가 유리합니다.",
                "박스권돌파": "🚀 저항 벽을 뚫었습니다. <b>빠른 속도로 수익</b>이 날 수 있는 구간입니다.",
                "정배열초입": "🌊 대세 우동향 항해의 시작입니다. <b>길게 보유하여 수익을 극대화</b>하세요."
            }
            # 첫 번째 전략의 팁을 대표로 노출
            current_tip = tip_map.get(st_names[0], "실시간 수급을 확인하며 분할 매수로 접근하세요.")

            # 분석 근거 (Reasons) 추출
            reason_list = main.get('reasons', [])
            reason_html = "".join([f'<div style="font-size:0.75rem; color:#94a3b8; margin-bottom:4px">◦ {r}</div>' for r in reason_list])
            
            card_html = f"""<div class="p-card" style="position:relative">
<div class="confidence-badge">{main.get('confidence', 0):.0f}%</div>
<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:15px">
<div>
<span style="font-size:1.5rem; font-weight:800">{main.get('name')}</span>
<span style="color:#94a3b8; font-size:1rem; margin-top:4px; display:block">{ticker}</span>
</div>
<div style="font-size:1.8rem; font-weight:800; color:#6366f1; font-family: Outfit; margin-right:60px">{format_price(main.get('current_price'))}원</div>
</div>
<div style="display:flex; gap:10px; margin-bottom:15px; flex-wrap:wrap">{tags}</div>

<div style="background:rgba(99, 102, 241, 0.05); border-radius:12px; padding:12px; margin-bottom:15px; border:1px dashed rgba(99, 102, 241, 0.2)">
    <div style="font-size:0.75rem; font-weight:800; color:#6366f1; margin-bottom:6px">📊 AI 분석 근거 (기술적 지표)</div>
    {reason_html if reason_html else '<div style="font-size:0.75rem; color:#94a3b8">주요 기술적 지표 밀집 구간 통과 중</div>'}
</div>

<div style="background:rgba(16, 185, 129, 0.05); padding:10px 14px; border-radius:12px; margin-bottom:15px; font-size:0.75rem; color:#10b981; border:1px solid rgba(16, 185, 129, 0.1)">
    <span style="font-weight:800; margin-right:5px">📢 초보자 팁:</span> {current_tip}
</div>

<div class="status-bar">
<svg style="width:20px;height:20px" fill="currentColor" viewBox="0 0 20 20"><path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1a1 1 0 112 0v1a1 1 0 11-2 0zM13.536 15.657a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM16.464 13.536a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707z"></path></svg>
수급: {main.get('supply_acceleration', '정상 유입 중')}
</div>
<div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:15px; margin-top:10px">
<div style="text-align:center; padding:12px; background:rgba(239, 68, 68, 0.05); border-radius:16px; border:1px solid rgba(239, 68, 68, 0.1)">
<div style="font-size:0.75rem; color:#ef4444; font-weight:700">손절가</div>
<div style="font-weight:800; color:#ef4444; font-size:1.2rem">{format_price(main.get('stop_loss'))}</div>
</div>
<div style="text-align:center; padding:12px; background:rgba(16, 185, 129, 0.05); border-radius:16px; border:1px solid rgba(16, 185, 129, 0.1)">
<div style="font-size:0.75rem; color:#10b981; font-weight:700">목표가</div>
<div style="font-weight:800; color:#10b981; font-size:1.2rem">{format_price(main.get('target_price_1'))}</div>
</div>
<div style="text-align:center; padding:12px; background:rgba(99, 102, 241, 0.05); border-radius:16px; border:1px solid rgba(99, 102, 241, 0.1)">
<div style="font-size:0.75rem; color:#6366f1; font-weight:700">시총</div>
<div style="font-weight:800; color:#6366f1; font-size:1.2rem">{m_cap_str}</div>
</div>
</div>
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)

# ══════════════════════════════════════
# [5] 리스트 섹션 (TOP 100)
# ══════════════════════════════════════
st.divider()
st.markdown("### 🔝 데이터 신뢰도 순위 (TOP 100)")
if raw_sigs:
    tops = sorted(raw_sigs, key=lambda x: x.get('confidence', 0), reverse=True)[:100]
    # 테마 변수 재로드 (for NameError 방지)
    t_colors = st.session_state.theme_colors
    l_cols = st.columns(4)
    for i, s in enumerate(tops):
        with l_cols[i % 4]:
            st.markdown(f"""
            <div style="padding:15px; border-bottom:1px solid {t_colors['border']}; display:flex; justify-content:space-between; font-size:0.9rem">
                <span><b>{i+1}. {s.get('name')}</b> <small style="color:{t_colors['text_dim']}"> {s.get('ticker')}</small></span>
                <span style="color:#6366f1; font-weight:800">{s.get('confidence', 0):.0f}%</span>
            </div>
            """, unsafe_allow_html=True)
else:
    st.caption("데이터가 없습니다. 분석 엔진을 실행해 주세요.")

st.divider()
st.caption("© 2026 ANTIGRAVITY Premium Portfolio | 노트북 전원을 켜두시면 모바일에서도 실시간 감시가 가능합니다.")
