-- ═══════════════════════════════════════════════════
-- Supabase 테이블 생성 SQL
-- eers_chatbot 스키마에 my_holdings 테이블 생성
-- ═══════════════════════════════════════════════════

-- 1. 스키마가 없으면 생성
CREATE SCHEMA IF NOT EXISTS eers_chatbot;

-- 2. my_holdings 테이블
CREATE TABLE IF NOT EXISTS eers_chatbot.my_holdings (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL UNIQUE,      -- 종목코드
    name VARCHAR(100) NOT NULL,               -- 종목명
    buy_price NUMERIC(12, 2) NOT NULL,        -- 매수가
    quantity INTEGER DEFAULT 0,               -- 수량
    account_note VARCHAR(200) DEFAULT '',     -- 계좌 메모
    
    -- 실시간 갱신 필드
    current_price NUMERIC(12, 2) DEFAULT 0,   -- 현재가
    pnl_pct NUMERIC(8, 2) DEFAULT 0,          -- 수익률 (%)
    pnl_amount NUMERIC(14, 2) DEFAULT 0,      -- 손익 금액
    
    -- 리스크 관리 & 모니터링 모드 (v2 추가)
    monitoring_mode VARCHAR(30) DEFAULT '손절 중심', -- 손절 중심 / 익절 중심 / 추세 추종
    highest_price NUMERIC(12, 2) DEFAULT 0,          -- 상장 이후(또는 매수 이후) 최고가 (추적 손절용)
    trailing_stop_pct NUMERIC(5, 2) DEFAULT 5.0,     -- 고점 대비 하락 허용치 (%)
    
    stop_loss_price NUMERIC(12, 2) DEFAULT 0, -- 고정 손절가
    ma20_price NUMERIC(12, 2) DEFAULT 0,      -- 20일 이동평균
    status VARCHAR(20) DEFAULT '정상',         -- 정상/경고/손절임박/손절도달
    last_reason TEXT DEFAULT '',               -- 마지막 상태 사유
    
    -- 타임스탬프
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 인덱스
CREATE INDEX IF NOT EXISTS idx_holdings_ticker 
    ON eers_chatbot.my_holdings(ticker);

CREATE INDEX IF NOT EXISTS idx_holdings_status 
    ON eers_chatbot.my_holdings(status);

-- 4. RLS (Row Level Security) 정책 — 선택사항
ALTER TABLE eers_chatbot.my_holdings ENABLE ROW LEVEL SECURITY;

-- 서비스 키 사용 시 모든 접근 허용
CREATE POLICY "Allow all for service role" ON eers_chatbot.my_holdings
    FOR ALL USING (true) WITH CHECK (true);

-- 5. 스키마를 API에 노출 (Supabase 대시보드 → Settings → API → Exposed schemas에도 추가 필요)
GRANT USAGE ON SCHEMA eers_chatbot TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA eers_chatbot TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA eers_chatbot TO anon, authenticated, service_role;
