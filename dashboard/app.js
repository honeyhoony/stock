/**
 * ╔══════════════════════════════════════════════════════════╗
 * ║  퀀트 트레이딩 대시보드 — 프론트엔드 로직 (app.js)         ║
 * ╚══════════════════════════════════════════════════════════╝
 */

// ─────────────────────────────────────────
// State
// ─────────────────────────────────────────
let allSignals = [];
let currentFilter = 'all';
let searchQuery = '';

// ─────────────────────────────────────────
// API Base
// ─────────────────────────────────────────
const API_BASE = window.location.origin;

// ─────────────────────────────────────────
// Clock
// ─────────────────────────────────────────
function updateClock() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('ko-KR', { hour12: false });
    const dateStr = now.toLocaleDateString('ko-KR', {
        year: 'numeric', month: '2-digit', day: '2-digit'
    });
    const el = document.getElementById('headerTime');
    if (el) el.textContent = `${dateStr} ${timeStr}`;
}
setInterval(updateClock, 1000);
updateClock();

// ─────────────────────────────────────────
// Toast Notifications
// ─────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

// ─────────────────────────────────────────
// Scanning Overlay
// ─────────────────────────────────────────
function showScanning(show, text = '전략 스캔 중...', sub = '잠시만 기다려주세요') {
    const overlay = document.getElementById('scanningOverlay');
    const textEl = document.getElementById('scanningText');
    const subEl = document.getElementById('scanningSub');

    if (textEl) textEl.textContent = text;
    if (subEl) subEl.textContent = sub;

    if (show) {
        overlay.classList.add('active');
    } else {
        overlay.classList.remove('active');
    }
}

// ─────────────────────────────────────────
// Market Condition
// ─────────────────────────────────────────
async function loadMarketCondition() {
    try {
        const resp = await fetch(`${API_BASE}/api/market`);
        const data = await resp.json();
        updateMarketUI(data);
    } catch (err) {
        console.error('Market condition error:', err);
        showToast('시장 상태 조회 실패', 'error');
    }
}

function updateMarketUI(data) {
    if (!data) return;

    // KOSPI
    const kospiCard = document.getElementById('marketKospi');
    const kospiBadge = document.getElementById('kospiBadge');
    const kospiValue = document.getElementById('kospiValue');
    const kospiDesc = document.getElementById('kospiDesc');

    if (data.kospi_above_ma5) {
        kospiCard.className = 'market-card bull';
        kospiBadge.className = 'market-card-badge badge-bull';
        kospiBadge.textContent = '5일선 ↑';
    } else {
        kospiCard.className = 'market-card bear';
        kospiBadge.className = 'market-card-badge badge-bear';
        kospiBadge.textContent = '5일선 ↓';
    }

    if (data.kospi_value) {
        kospiValue.textContent = Number(data.kospi_value).toLocaleString('ko-KR', {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        });
        kospiDesc.textContent = `MA5: ${Number(data.kospi_ma5).toLocaleString('ko-KR', {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        })}`;
    } else if (data.reasons && data.reasons[0]) {
        kospiDesc.textContent = data.reasons[0];
    }

    // KOSDAQ
    const kosdaqCard = document.getElementById('marketKosdaq');
    const kosdaqBadge = document.getElementById('kosdaqBadge');
    const kosdaqValue = document.getElementById('kosdaqValue');
    const kosdaqDesc = document.getElementById('kosdaqDesc');

    if (data.kosdaq_above_ma5) {
        kosdaqCard.className = 'market-card bull';
        kosdaqBadge.className = 'market-card-badge badge-bull';
        kosdaqBadge.textContent = '5일선 ↑';
    } else {
        kosdaqCard.className = 'market-card bear';
        kosdaqBadge.className = 'market-card-badge badge-bear';
        kosdaqBadge.textContent = '5일선 ↓';
    }

    if (data.kosdaq_value) {
        kosdaqValue.textContent = Number(data.kosdaq_value).toLocaleString('ko-KR', {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        });
        kosdaqDesc.textContent = `MA5: ${Number(data.kosdaq_ma5).toLocaleString('ko-KR', {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        })}`;
    } else if (data.reasons && data.reasons[1]) {
        kosdaqDesc.textContent = data.reasons[1];
    }

    // Market Phase
    const phaseCard = document.getElementById('marketPhase');
    const phaseBadge = document.getElementById('phaseBadge');
    const phaseValue = document.getElementById('phaseValue');
    const phaseDesc = document.getElementById('phaseDesc');

    const phaseMap = {
        'BULL': { class: 'bull', badge: 'badge-bull', emoji: '🟢', label: '강세장' },
        'BEAR': { class: 'bear', badge: 'badge-bear', emoji: '🔴', label: '약세장' },
        'NEUTRAL': { class: 'neutral', badge: 'badge-neutral', emoji: '🟡', label: '혼조세' },
    };

    const ph = phaseMap[data.market_phase] || phaseMap['NEUTRAL'];
    phaseCard.className = `market-card ${ph.class}`;
    phaseBadge.className = `market-card-badge ${ph.badge}`;
    phaseBadge.textContent = data.market_phase;
    phaseValue.textContent = `${ph.emoji} ${ph.label}`;
    phaseDesc.textContent = `최대 투자비중: ${(data.max_weight * 100).toFixed(0)}%`;

    // Allowed Strategies
    const strategyValue = document.getElementById('strategyValue');
    const strategyDesc = document.getElementById('strategyDesc');
    const strategyBadge = document.getElementById('strategyBadge');

    if (data.allowed_strategies) {
        const nameMap = {
            'pullback': '눌림목', 'bottom_escape': '바닥탈출',
            'golden_cross': '골든크로스', 'breakout': '박스권돌파',
            'convergence': '정배열초입'
        };
        const names = data.allowed_strategies.map(s => nameMap[s] || s);
        strategyValue.textContent = `${data.allowed_strategies.length}개 전략`;
        strategyDesc.textContent = names.join(' · ');
        strategyBadge.textContent = data.market_phase === 'BEAR' ? '제한' : '전체';
    }
}

// ─────────────────────────────────────────
// Run Scan
// ─────────────────────────────────────────
async function runScan() {
    const btn = document.getElementById('btnScan');
    btn.classList.add('loading');
    btn.disabled = true;
    showScanning(true, '🔍 전략 스캔 진행 중...', '거래대금 상위 종목을 분석하고 있습니다');
    showToast('스캔을 시작합니다...', 'info');

    try {
        const resp = await fetch(`${API_BASE}/api/scan`);
        const data = await resp.json();

        if (data.error) {
            showToast(`스캔 오류: ${data.error}`, 'error');
            return;
        }

        // Update market condition
        if (data.market_condition) {
            updateMarketUI(data.market_condition);
        }

        // Update signals
        allSignals = data.signals || [];
        renderSignals();

        // Update summary
        if (data.summary) {
            updateSummary(data.summary);
        }

        const approved = allSignals.filter(s => s.verdict === '매수 승인').length;
        showToast(
            `스캔 완료! ${allSignals.length}개 신호 감지, ${approved}개 매수 승인`,
            approved > 0 ? 'success' : 'warning'
        );

    } catch (err) {
        console.error('Scan error:', err);
        showToast('스캔 실행 중 오류가 발생했습니다', 'error');
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
        showScanning(false);
    }
}

// ─────────────────────────────────────────
// Load Previous Results
// ─────────────────────────────────────────
async function loadResults() {
    try {
        const resp = await fetch(`${API_BASE}/api/results`);
        const data = await resp.json();

        if (data.market_condition) {
            updateMarketUI(data.market_condition);
        }

        allSignals = data.signals || [];
        if (allSignals.length > 0) {
            renderSignals();
            if (data.summary) updateSummary(data.summary);
        }
    } catch (err) {
        console.log('No previous results found');
    }
}

// ─────────────────────────────────────────
// Summary
// ─────────────────────────────────────────
function updateSummary(summary) {
    const bar = document.getElementById('summaryBar');
    bar.style.display = 'flex';

    document.getElementById('statTotal').textContent = summary.total_signals || 0;
    document.getElementById('statApproved').textContent = summary.approved || 0;
    document.getElementById('statWatch').textContent = summary.watch || 0;
    document.getElementById('statScanned').textContent = summary.total_scanned || 0;
    document.getElementById('statTime').textContent = `${summary.elapsed_seconds || 0}s`;
}

// ─────────────────────────────────────────
// Render Signals
// ─────────────────────────────────────────
function renderSignals() {
    const grid = document.getElementById('signalsGrid');
    const empty = document.getElementById('emptyState');

    // Filter signals
    let filtered = [...allSignals];

    // Strategy filter
    if (currentFilter !== 'all') {
        if (currentFilter === 'approved') {
            filtered = filtered.filter(s => s.verdict === '매수 승인');
        } else {
            filtered = filtered.filter(s => s.strategy === currentFilter);
        }
    }

    // Search filter
    if (searchQuery) {
        const q = searchQuery.toLowerCase();
        filtered = filtered.filter(s =>
            s.name.toLowerCase().includes(q) ||
            s.ticker.includes(q)
        );
    }

    // Clear grid
    grid.innerHTML = '';

    if (filtered.length === 0) {
        if (allSignals.length === 0) {
            grid.innerHTML = `
        <div class="empty-state" id="emptyState">
          <div class="empty-state-icon">🎯</div>
          <h3>스캔 대기 중</h3>
          <p>상단의 <strong>"🚀 스캔 실행"</strong> 버튼을 클릭하면 시장을 분석하고 매수 기회를 탐색합니다.</p>
          <button class="btn btn-primary btn-lg" onclick="runScan()">🚀 스캔 시작하기</button>
        </div>`;
        } else {
            grid.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">🔍</div>
          <h3>검색 결과 없음</h3>
          <p>현재 필터 조건에 맞는 신호가 없습니다. 필터를 변경해 보세요.</p>
        </div>`;
        }
        return;
    }

    // Create cards
    filtered.forEach((signal, index) => {
        grid.appendChild(createSignalCard(signal, index));
    });
}

function createSignalCard(signal, index) {
    const card = document.createElement('div');
    card.className = 'signal-card';
    if (signal.grade === 'S') card.classList.add('grade-s');
    else if (signal.grade === 'A') card.classList.add('grade-a');
    card.style.animationDelay = `${index * 0.06}s`;

    const strategyMap = {
        '눌림목': { ribbon: 'ribbon-pullback', tag: 'tag-pullback', icon: '🔵' },
        '바닥탈출': { ribbon: 'ribbon-bottom-escape', tag: 'tag-bottom-escape', icon: '🟢' },
        '골든크로스': { ribbon: 'ribbon-golden-cross', tag: 'tag-golden-cross', icon: '🟡' },
        '박스권돌파': { ribbon: 'ribbon-breakout', tag: 'tag-breakout', icon: '🔴' },
        '정배열초입': { ribbon: 'ribbon-convergence', tag: 'tag-convergence', icon: '🟣' },
    };

    const sm = strategyMap[signal.strategy] || strategyMap['눌림목'];

    // Confidence level
    let confClass = 'low';
    let confColor = 'var(--red-600)';
    if (signal.confidence >= 75) {
        confClass = 'high';
        confColor = 'var(--green-600)';
    } else if (signal.confidence >= 55) {
        confClass = 'medium';
        confColor = 'var(--amber-600)';
    }

    // Grade badge HTML
    let gradeHTML = '';
    if (signal.grade === 'S') {
        gradeHTML = `<span class="grade-badge grade-badge-s">🏆 S급</span>`;
    } else if (signal.grade === 'A') {
        gradeHTML = `<span class="grade-badge grade-badge-a">⭐ A급</span>`;
    }

    // Multi strategy info
    let multiHTML = '';
    if (signal.multi_strategy_count >= 2) {
        const others = (signal.multi_strategies || [])
            .filter(s => s !== signal.strategy)
            .join(' + ');
        multiHTML = `
        <div class="multi-strategy-info">
          🔗 교집합: ${signal.strategy} + ${others}
          ${signal.confidence_bonus ? `(+${signal.confidence_bonus}점 보너스)` : ''}
        </div>`;
    }

    // Reasons HTML
    const reasonsHTML = (signal.reasons || []).map(r =>
        `<div class="reason-item"><span class="dot"></span><span>${escapeHtml(r)}</span></div>`
    ).join('');

    // Verdict buttons
    const isApproved = signal.verdict === '매수 승인';

    card.innerHTML = `
    <div class="signal-card-ribbon ${sm.ribbon}"></div>
    ${gradeHTML}
    <div class="signal-card-body">
      <div class="signal-card-top">
        <div class="signal-stock-info">
          <h3>${escapeHtml(signal.name)}</h3>
          <span class="signal-stock-ticker">${signal.ticker}</span>
        </div>
        <div class="signal-price">
          <div class="signal-price-value">${formatPrice(signal.current_price)}</div>
        </div>
      </div>

      <div class="signal-strategy-tag ${sm.tag}">
        ${sm.icon} ${escapeHtml(signal.strategy)}
      </div>
      ${multiHTML}

      <div class="signal-reasons">
        <h4>🔍 핵심 근거</h4>
        ${reasonsHTML}
      </div>

      <div class="signal-prices">
        <div class="price-box">
          <div class="price-box-label">1차 매수가</div>
          <div class="price-box-value buy">${formatPrice(signal.entry_price_1)}</div>
        </div>
        <div class="price-box">
          <div class="price-box-label">2차 매수가</div>
          <div class="price-box-value buy">${formatPrice(signal.entry_price_2)}</div>
        </div>
        <div class="price-box">
          <div class="price-box-label">1차 목표가</div>
          <div class="price-box-value target">${formatPrice(signal.target_price_1)}</div>
        </div>
        <div class="price-box">
          <div class="price-box-label">손절가</div>
          <div class="price-box-value stop">${formatPrice(signal.stop_loss)}</div>
        </div>
      </div>

      <div class="confidence-bar-container">
        <div class="confidence-label">
          <span>신뢰도${signal.confidence_bonus ? ` (보너스 +${signal.confidence_bonus})` : ''}</span>
          <strong style="color: ${confColor}">${signal.confidence.toFixed(0)}%</strong>
        </div>
        <div class="confidence-bar">
          <div class="confidence-fill ${confClass}" style="width: ${signal.confidence}%"></div>
        </div>
      </div>

      <div class="signal-actions">
        <button class="btn ${isApproved ? 'btn-success' : 'btn-outline'} btn-sm"
                onclick="handleApproval('${signal.ticker}', '매수 승인')"
                id="approveBtn_${signal.ticker}">
          ✅ 매수 승인
        </button>
        <button class="btn btn-outline btn-sm"
                onclick="handleApproval('${signal.ticker}', '관망')"
                id="watchBtn_${signal.ticker}">
          ⏸️ 관망
        </button>
      </div>
    </div>
  `;

    return card;
}

// ─────────────────────────────────────────
// Approval Handler
// ─────────────────────────────────────────
async function handleApproval(ticker, action) {
    try {
        const resp = await fetch(`${API_BASE}/api/approve/${ticker}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action }),
        });
        const data = await resp.json();

        if (action === '매수 승인') {
            showToast(`${ticker} 매수 승인 완료!`, 'success');
            const approveBtn = document.getElementById(`approveBtn_${ticker}`);
            if (approveBtn) {
                approveBtn.className = 'btn btn-success btn-sm';
            }
        } else {
            showToast(`${ticker} 관망 처리`, 'warning');
        }
    } catch (err) {
        showToast('처리 중 오류 발생', 'error');
    }
}

// ─────────────────────────────────────────
// Filters
// ─────────────────────────────────────────
function setFilter(filter, element) {
    currentFilter = filter;

    // Update pill state
    document.querySelectorAll('.filter-pill').forEach(pill => pill.classList.remove('active'));
    if (element) element.classList.add('active');

    renderSignals();
}

function filterSignals() {
    searchQuery = document.getElementById('searchInput').value.trim();
    renderSignals();
}

// ─────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────
function formatPrice(price) {
    if (!price || price === 0) return '—';
    return parseInt(price).toLocaleString('ko-KR') + '원';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ─────────────────────────────────────────
// Keyboard Shortcuts
// ─────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    // Ctrl+Enter: Run scan
    if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        runScan();
    }
    // Ctrl+M: Market condition
    if (e.ctrlKey && e.key === 'm') {
        e.preventDefault();
        loadMarketCondition();
    }
    // Escape: Close overlay
    if (e.key === 'Escape') {
        showScanning(false);
    }
});

// ─────────────────────────────────────────
// Demo Mode (when API is not available)
// ─────────────────────────────────────────
function loadDemoData() {
    const demoSignals = [
        {
            ticker: '000660', name: 'SK하이닉스', strategy: '골든크로스',
            triggered: true, confidence: 91,
            current_price: 192000, entry_price_1: 190000, entry_price_2: 185000,
            target_price_1: 215000, target_price_2: 230000, stop_loss: 178000,
            risk_reward_ratio: 2.1,
            reasons: [
                '골든크로스 발생 (MA5 ↑ MA20)',
                '20일선 기울기 양호 (+0.85%)',
                'RSI 50선 상향 돌파 (RSI: 55.3)',
            ],
            verdict: '매수 승인',
            grade: 'A', grade_label: 'A급 (2중 교집합)',
            confidence_bonus: 15, original_confidence: 76,
            multi_strategy_count: 2,
            multi_strategies: ['골든크로스', '바닥탈출'],
        },
        {
            ticker: '000660', name: 'SK하이닉스', strategy: '바닥탈출',
            triggered: true, confidence: 83,
            current_price: 192000, entry_price_1: 188000, entry_price_2: 184000,
            target_price_1: 210000, target_price_2: 225000, stop_loss: 176000,
            risk_reward_ratio: 1.8,
            reasons: [
                '20일선(187,200원) 상향 돌파 확인',
                '상방 5% 매물대 벽 없음',
                '매집봉 3개 감지 (최대 거래량 배수: 3.1x)',
            ],
            verdict: '매수 승인',
            grade: 'A', grade_label: 'A급 (2중 교집합)',
            confidence_bonus: 15, original_confidence: 68,
            multi_strategy_count: 2,
            multi_strategies: ['골든크로스', '바닥탈출'],
        },
        {
            ticker: '005930', name: '삼성전자', strategy: '눌림목',
            triggered: true, confidence: 82,
            current_price: 71500, entry_price_1: 70000, entry_price_2: 68500,
            target_price_1: 78000, target_price_2: 85000, stop_loss: 66000,
            risk_reward_ratio: 2.0,
            reasons: [
                '기준봉 중심값(70,200원) 지지 확인',
                '거래량 절벽 감지 (현재 거래량 = 평균의 28%)',
                '기관 보유 수량 유지 확인 (5일 변동 3.2% 이내)',
            ],
            verdict: '매수 승인',
            grade: 'B', grade_label: '단일 전략',
            confidence_bonus: 0, multi_strategy_count: 1, multi_strategies: ['눌림목'],
        },
        {
            ticker: '068270', name: '셀트리온', strategy: '박스권돌파',
            triggered: true, confidence: 71,
            current_price: 185000, entry_price_1: 183000, entry_price_2: 184850,
            target_price_1: 198000, target_price_2: 213000, stop_loss: 172000,
            risk_reward_ratio: 1.4,
            reasons: [
                '전고점(183,000원) 돌파 확인',
                '매도호가 잔량/매수호가 = 2.3배 (강한 돌파 신호)',
                '프로그램 순매수 45,200주 유입',
                '거래량 폭증 2.8배 (돌파 에너지 확인)',
            ],
            verdict: '매수 승인',
            grade: 'B', grade_label: '단일 전략',
            confidence_bonus: 0, multi_strategy_count: 1, multi_strategies: ['박스권돌파'],
        },
        {
            ticker: '035420', name: 'NAVER', strategy: '바닥탈출',
            triggered: true, confidence: 68,
            current_price: 215000, entry_price_1: 210000, entry_price_2: 205000,
            target_price_1: 240000, target_price_2: 260000, stop_loss: 195000,
            risk_reward_ratio: 2.0,
            reasons: [
                '20일선(208,500원) 상향 돌파 확인',
                '상방 5% 매물대 벽 없음 — 상승 여력 확보',
                '매집봉 2개 감지 (최대 거래량 배수: 2.8x)',
            ],
            verdict: '관망',
            grade: 'B', grade_label: '단일 전략',
            confidence_bonus: 0, multi_strategy_count: 1, multi_strategies: ['바닥탈출'],
        },
        {
            ticker: '051910', name: 'LG화학', strategy: '정배열초입',
            triggered: true, confidence: 64,
            current_price: 372000, entry_price_1: 372000, entry_price_2: 365000,
            target_price_1: 410000, target_price_2: 440000, stop_loss: 345000,
            risk_reward_ratio: 1.4,
            reasons: [
                '이평선 밀집 확인 (스프레드 2.45%)',
                '정배열 형성 (MA5 > MA20 > MA60 > MA120)',
                '밀집 후 발산 시작 감지',
                '시장 지수 5일선 위 — 업종 상승 추세 가중치 적용',
            ],
            verdict: '관망',
            grade: 'B', grade_label: '단일 전략',
            confidence_bonus: 0, multi_strategy_count: 1, multi_strategies: ['정배열초입'],
        },
    ];

    const demoMarket = {
        kospi_above_ma5: true,
        kosdaq_above_ma5: false,
        kospi_value: 2650.32,
        kospi_ma5: 2635.18,
        kosdaq_value: 845.60,
        kosdaq_ma5: 852.40,
        market_phase: 'NEUTRAL',
        max_weight: 0.7,
        allowed_strategies: ['pullback', 'bottom_escape', 'golden_cross', 'breakout', 'convergence'],
        reasons: [
            '코스피 5일선 위 (2,650 > MA5 2,635)',
            '⚠️ 코스닥 5일선 이탈 (845 < MA5 852)',
            '🟡 혼조세 — 투자비중 70% 이하 권고',
        ],
    };

    allSignals = demoSignals;
    updateMarketUI(demoMarket);
    renderSignals();
    updateSummary({
        total_signals: demoSignals.length,
        approved: demoSignals.filter(s => s.verdict === '매수 승인').length,
        watch: demoSignals.filter(s => s.verdict === '관망').length,
        total_scanned: 287,
        elapsed_seconds: 42.3,
    });
}

// ─────────────────────────────────────────
// Init
// ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // Try to load previous results, or fall back to demo
    try {
        const resp = await fetch(`${API_BASE}/api/results`, { signal: AbortSignal.timeout(3000) });
        if (resp.ok) {
            const data = await resp.json();
            if (data.signals && data.signals.length > 0) {
                allSignals = data.signals;
                renderSignals();
                if (data.market_condition) updateMarketUI(data.market_condition);
                if (data.summary) updateSummary(data.summary);
                loadWatchlist();
                return;
            }
        }
    } catch {
        // API not available
    }

    // Load demo data for visual presentation
    loadDemoData();
    showToast('데모 데이터를 표시합니다. 서버 연결 후 스캔을 실행하세요.', 'info', 5000);
});


// ─────────────────────────────────────────
// 관찰 리스트 (Watchlist)
// ─────────────────────────────────────────
async function loadWatchlist() {
    try {
        const resp = await fetch(`${API_BASE}/api/watchlist`);
        if (!resp.ok) return;
        const items = await resp.json();
        renderWatchlist(items);
    } catch {
        // pass
    }
}

async function addWatchlistItem() {
    const ticker = document.getElementById('wlTicker')?.value.trim();
    const buyPrice = parseFloat(document.getElementById('wlBuyPrice')?.value);
    const name = document.getElementById('wlName')?.value.trim() || '';
    const quantity = parseInt(document.getElementById('wlQuantity')?.value) || 0;

    if (!ticker || !buyPrice || buyPrice <= 0) {
        showToast('종목코드와 매수가를 입력하세요.', 'error');
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/watchlist/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker, buy_price: buyPrice, name, quantity }),
        });
        const data = await resp.json();
        if (data.error) {
            showToast(`등록 실패: ${data.error}`, 'error');
        } else {
            showToast(`${data.name || ticker} 관찰 등록 완료!`, 'success');
            document.getElementById('wlTicker').value = '';
            document.getElementById('wlBuyPrice').value = '';
            document.getElementById('wlName').value = '';
            document.getElementById('wlQuantity').value = '';
            loadWatchlist();
        }
    } catch (err) {
        showToast('서버 연결 실패', 'error');
    }
}

async function removeWatchlistItem(ticker) {
    try {
        const resp = await fetch(`${API_BASE}/api/watchlist/${ticker}`, { method: 'DELETE' });
        if (resp.ok) {
            showToast(`${ticker} 관찰 해제`, 'warning');
            loadWatchlist();
        }
    } catch (err) {
        showToast('삭제 실패', 'error');
    }
}

async function checkWatchlist() {
    showToast('종목 상태 체크 중...', 'info');
    try {
        const resp = await fetch(`${API_BASE}/api/watchlist/check`);
        const results = await resp.json();
        const items = results.map(r => r.item);
        renderWatchlist(items);

        const alerts = results.filter(r => r.alert);
        if (alerts.length > 0) {
            showToast(`⚠️ ${alerts.length}개 종목 알림 발생!`, 'error', 5000);
        } else {
            showToast('✅ 체크 완료 — 이상 없음', 'success');
        }
    } catch {
        showToast('체크 실패', 'error');
    }
}

async function startMonitoring() {
    try {
        await fetch(`${API_BASE}/api/watchlist/monitor/start`, { method: 'POST' });
        showToast('🔄 실시간 모니터링 시작 (1분 간격)', 'success');
        document.getElementById('monitorStatus').textContent = '🟢 모니터링 중';
    } catch {
        showToast('모니터링 시작 실패', 'error');
    }
}

async function stopMonitoring() {
    try {
        await fetch(`${API_BASE}/api/watchlist/monitor/stop`, { method: 'POST' });
        showToast('⏹️ 모니터링 중지', 'warning');
        document.getElementById('monitorStatus').textContent = '🔴 중지됨';
    } catch {
        showToast('모니터링 중지 실패', 'error');
    }
}

function renderWatchlist(items) {
    const section = document.getElementById('watchlistSection');
    if (!section) return;

    section.style.display = 'block';

    const tbody = document.getElementById('watchlistBody');
    if (!tbody) return;

    if (!items || items.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 2rem; color: var(--text-secondary);">
                    관찰 종목이 없습니다. 위에서 등록해 주세요.
                </td>
            </tr>`;
        return;
    }

    tbody.innerHTML = items.map(item => {
        const statusMap = {
            '정상': { emoji: '✅', cls: 'status-ok' },
            '경고': { emoji: '⚠️', cls: 'status-warn' },
            '손절임박': { emoji: '🚨', cls: 'status-danger' },
            '손절도달': { emoji: '💀', cls: 'status-critical' },
        };
        const st = statusMap[item.status] || statusMap['정상'];
        const pnlClass = item.pnl_pct >= 0 ? 'pnl-profit' : 'pnl-loss';
        const pnlSign = item.pnl_pct >= 0 ? '+' : '';

        return `
            <tr class="watchlist-row ${st.cls}">
                <td>
                    <div class="wl-stock-name">${escapeHtml(item.name || item.ticker)}</div>
                    <div class="wl-stock-ticker">${item.ticker}</div>
                </td>
                <td class="mono">${parseInt(item.buy_price).toLocaleString()}</td>
                <td class="mono">${item.current_price > 0 ? parseInt(item.current_price).toLocaleString() : '—'}</td>
                <td class="mono ${pnlClass}">${item.current_price > 0 ? `${pnlSign}${item.pnl_pct.toFixed(1)}%` : '—'}</td>
                <td class="mono">${parseInt(item.stop_loss_price).toLocaleString()}</td>
                <td>
                    <span class="wl-status ${st.cls}">${st.emoji} ${item.status}</span>
                    ${item.reasons && item.reasons.length ? `<div class="wl-reason">${item.reasons[0]}</div>` : ''}
                </td>
                <td>
                    <button class="btn btn-outline btn-xs" onclick="removeWatchlistItem('${item.ticker}')">🗑️</button>
                </td>
            </tr>`;
    }).join('');
}
