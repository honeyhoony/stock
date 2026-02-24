-- ═══════════════════════════════════════════════════
-- Supabase 테이블 생성 SQL (v2.1 - Public Schema 전용)
-- Supabase SQL Editor에 복사하여 실행하세요.
-- ═══════════════════════════════════════════════════

-- 1. my_holdings 테이블 (public 스키마 사용으로 404 오류 방지)
CREATE TABLE IF NOT EXISTS public.my_holdings (
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
    monitoring_mode VARCHAR(30) DEFAULT '손절 중심', 
    highest_price NUMERIC(12, 2) DEFAULT 0,          
    trailing_stop_pct NUMERIC(5, 2) DEFAULT 5.0,     
    
    stop_loss_price NUMERIC(12, 2) DEFAULT 0, 
    ma20_price NUMERIC(12, 2) DEFAULT 0,      
    status VARCHAR(20) DEFAULT '정상',         
    last_reason TEXT DEFAULT '',               
    
    -- 타임스탬프
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_holdings_ticker_pub ON public.my_holdings(ticker);
CREATE INDEX IF NOT EXISTS idx_holdings_status_pub ON public.my_holdings(status);

-- 3. RLS (Row Level Security) 설정
-- 테스트 편의를 위해 모든 접근 허용 (보안 필요 시 Policy 조정 필요)
ALTER TABLE public.my_holdings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all" ON public.my_holdings
    FOR ALL USING (true) WITH CHECK (true);

-- 4. 권한 부여
GRANT ALL ON TABLE public.my_holdings TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;
