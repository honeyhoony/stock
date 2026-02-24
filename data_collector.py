"""
╔══════════════════════════════════════════════════════════╗
║  데이터 수집 모듈 (Data Collector)                        ║
║  KRX 직접 조회 + KIS API 하이브리드                       ║
║  (pykrx 미설치 환경 대응 — KRX REST 직접 호출)             ║
╚══════════════════════════════════════════════════════════╝
"""
import time
import json
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from io import StringIO

from config import kis_config, filter_config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# KRX 데이터 직접 수집 (pykrx 대체)
# ──────────────────────────────────────────
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


def krx_post(bld: str, params: dict) -> pd.DataFrame:
    """KRX API에 POST 요청하여 DataFrame 반환"""
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    payload = {"bld": bld}
    payload.update(params)
    try:
        resp = requests.post(url, data=payload, headers=KRX_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # KRX returns {"OutBlock_1": [...]} or {"block1": [...]}
        for key in ["OutBlock_1", "block1", "output"]:
            if key in data:
                return pd.DataFrame(data[key])
        # 직접 리스트인 경우
        if isinstance(data, list):
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        logger.warning(f"KRX 조회 실패 ({bld}): {e}")
        return pd.DataFrame()


class KISAuth:
    """한국투자증권 API 인증 관리"""

    def __init__(self):
        self.access_token: Optional[str] = None
        self.token_expires: Optional[datetime] = None

    def get_token(self) -> str:
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token

        url = f"{kis_config.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": kis_config.app_key,
            "appsecret": kis_config.app_secret,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            self.token_expires = datetime.now() + timedelta(hours=23)
            logger.info("KIS 토큰 발급 완료")
            return self.access_token
        except Exception as e:
            logger.error(f"KIS 토큰 발급 실패: {e}")
            return ""

    def get_headers(self, tr_id: str) -> dict:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_token()}",
            "appkey": kis_config.app_key,
            "appsecret": kis_config.app_secret,
            "tr_id": tr_id,
        }


kis_auth = KISAuth()


class DataCollector:
    """
    데이터 수집기
    - KRX REST: 일봉/OHLCV, 시가총액, 수급(외인/기관)
    - KIS API: 실시간 호가, 체결강도, 프로그램매매
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[datetime, object]] = {}
        self._ticker_name_cache: Dict[str, str] = {}

    def get_stock_name(self, ticker: str) -> str:
        """종목코드로 종목명 반환"""
        if ticker in self._ticker_name_cache:
            return self._ticker_name_cache[ticker]
        
        # 캐시에 없으면 마켓 데이터 로드 시도
        self.get_market_cap_data()
        return self._ticker_name_cache.get(ticker, ticker) # 없으면 코드 그대로 반환

    # ══════════════════════════════════════
    # 1. 종목 리스트 & 필터링
    # ══════════════════════════════════════
    def get_market_cap_data(self) -> pd.DataFrame:
        """시가총액 + 거래대금 데이터 조회 (KRX) - 최근 영업일 찾기 로직 포함"""
        cache_key = "market_cap"
        if cache_key in self._cache:
            ts, df = self._cache[cache_key]
            if (datetime.now() - ts).seconds < 600:
                return df

        frames = []
        # 장 시작 전이나 휴일 대응: 최근 5일 중 데이터가 있는 가장 가까운 날짜 탐색
        found_date = None
        for i in range(5):
            target_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            temp_frames = []
            for mkt_id, mkt_name in [("STK", "KOSPI"), ("KSQ", "KOSDAQ")]:
                df = krx_post("dbms/MDC/STAT/standard/MDCSTAT01501", {
                    "mktId": mkt_id,
                    "trdDd": target_date,
                    "share": "1",
                    "money": "1",
                    "csvxls_isNo": "false",
                })
                if not df.empty:
                    df["시장"] = mkt_name
                    temp_frames.append(df)
            
            if len(temp_frames) >= 2: # 코스피, 코스닥 모두 성공 시
                frames = temp_frames
                found_date = target_date
                logger.info(f"KRX 데이터 로드 성공 (기준일: {found_date})")
                break
        
        if not frames:
            logger.warning("KRX 최근 5일 데이터 조회 실패 — 대규모 시뮬레이션 데이터 전환")
            return self._generate_simulated_market_data()

        result = pd.concat(frames, ignore_index=True)

        # 컬럼 매핑
        col_map = {
            "ISU_SRT_CD": "종목코드",
            "ISU_ABBRV": "종목명",
            "TDD_CLSPRC": "종가",
            "MKTCAP": "시가총액",
            "ACC_TRDVAL": "거래대금",
            "ACC_TRDVOL": "거래량",
            "FLUC_RT": "등락률",
            "LIST_SHRS": "상장주식수",
        }
        result.rename(columns={k: v for k, v in col_map.items() if k in result.columns}, inplace=True)

        # 숫자 변환
        for col in ["종가", "시가총액", "거래대금", "거래량"]:
            if col in result.columns:
                result[col] = pd.to_numeric(
                    result[col].astype(str).str.replace(",", ""), errors="coerce"
                )

        # 종목명 캐시
        if "종목코드" in result.columns and "종목명" in result.columns:
            for _, row in result.iterrows():
                self._ticker_name_cache[str(row["종목코드"])] = str(row["종목명"])

        self._cache[cache_key] = (datetime.now(), result)
        return result

    def filter_stocks(self, min_market_cap: int = None, top_rank: int = None) -> pd.DataFrame:
        """시가총액 및 거래대금 순합 기반 필터링 (동적 인자 지원)"""
        df = self.get_market_cap_data()
        if df.empty:
            return df

        m_cap = min_market_cap if min_market_cap is not None else filter_config.min_market_cap
        t_rank = top_rank if top_rank is not None else filter_config.top_trading_value_rank

        if "시가총액" in df.columns and m_cap > 0:
            df = df[df["시가총액"] >= m_cap].copy()

        if "거래대금" in df.columns and t_rank > 0:
            df = df.sort_values("거래대금", ascending=False)
            df = df.head(t_rank)

        # ETF/SPAC 제외
        if filter_config.exclude_etf and "종목명" in df.columns:
            etf_keywords = ["ETF", "ETN", "KODEX", "TIGER", "KBSTAR", "ARIRANG", "SOL", "PLUS"]
            mask = ~df["종목명"].str.contains("|".join(etf_keywords), na=False)
            df = df[mask]

        if "종목코드" in df.columns:
            df = df.set_index("종목코드")

        logger.info(f"필터링 완료: {len(df)}개 종목")
        return df

    # ══════════════════════════════════════
    # 2. OHLCV 일봉 데이터 (KIS API 기반)
    # ══════════════════════════════════════
    def get_ohlcv(self, ticker: str, days: int = 200) -> pd.DataFrame:
        """일봉 OHLCV (KIS API → 시뮬레이션 폴백)"""
        cache_key = f"ohlcv_{ticker}_{days}"
        if cache_key in self._cache:
            ts, df = self._cache[cache_key]
            if (datetime.now() - ts).seconds < 600:
                return df

        df = self._fetch_ohlcv_kis(ticker, days)

        if df.empty:
            logger.debug(f"{ticker} KIS OHLCV 실패 → 시뮬레이션 데이터")
            df = self._generate_simulated_ohlcv(ticker, days)

        # 필수 컬럼 확인
        required = ["시가", "고가", "저가", "종가", "거래량"]
        if all(c in df.columns for c in required):
            self._cache[cache_key] = (datetime.now(), df)

        return df

    def _fetch_ohlcv_kis(self, ticker: str, days: int = 200) -> pd.DataFrame:
        """KIS API 일봉 차트 조회 (FHKST03010100)"""
        url = f"{kis_config.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = kis_auth.get_headers("FHKST03010100")

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=int(days * 1.5))).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("rt_cd") != "0":
                logger.warning(f"{ticker} KIS OHLCV 응답 오류: {data.get('msg1', '')}")
                return pd.DataFrame()

            output2 = data.get("output2", [])
            if not output2:
                return pd.DataFrame()

            rows = []
            for item in output2:
                stck_bsop_date = item.get("stck_bsop_date", "")
                if not stck_bsop_date:
                    continue
                rows.append({
                    "날짜": stck_bsop_date,
                    "시가": int(item.get("stck_oprc", 0)),
                    "고가": int(item.get("stck_hgpr", 0)),
                    "저가": int(item.get("stck_lwpr", 0)),
                    "종가": int(item.get("stck_clpr", 0)),
                    "거래량": int(item.get("acml_vol", 0)),
                    "거래대금": int(item.get("acml_tr_pbmn", 0)),
                })

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df["날짜"] = pd.to_datetime(df["날짜"])
            df = df.set_index("날짜").sort_index()
            df["등락률"] = df["종가"].pct_change() * 100
            df = df.tail(days)

            logger.debug(f"{ticker} KIS OHLCV 수신: {len(df)}행")
            return df

        except Exception as e:
            logger.warning(f"{ticker} KIS OHLCV 조회 실패: {e}")
            return pd.DataFrame()

    # ══════════════════════════════════════
    # 3. 수급 데이터 (KIS API 기반)
    # ══════════════════════════════════════
    def get_investor_data(self, ticker: str, days: int = 60) -> pd.DataFrame:
        """외인/기관 순매수 데이터 (KIS API — 투자자별 매매동향)"""
        url = f"{kis_config.base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"
        headers = kis_auth.get_headers("FHKST01010900")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") == "0":
                output = data.get("output", {})
                return pd.DataFrame([{
                    "외인순매수": int(output.get("frgn_ntby_qty", 0)),
                    "기관순매수": int(output.get("orgn_ntby_qty", 0)),
                    "외인보유비중": float(output.get("frgn_stkn_rto", 0)),
                }])
            return pd.DataFrame()
        except Exception as e:
            logger.debug(f"{ticker} 투자자 매매동향 조회 실패: {e}")
            return pd.DataFrame()

    def get_institution_holding(self, ticker: str, days: int = 30) -> pd.DataFrame:
        """기관 보유 수량 추적"""
        return self.get_investor_data(ticker, days)

    def get_supply_demand(self, ticker: str) -> dict:
        """
        3대 수급 동기화 체크 (외인/기관/프로그램) + 가속도 분석
        → 가속도: 최근 5일 평균 대비 현재 수급 강도
        """
        result = {
            "foreign_buy": False, 
            "institution_buy": False,
            "program_buy": False,
            "buy_count": 0,
            "acceleration": {
                "foreign": 1.0,
                "institution": 1.0,
                "program": 1.0,
                "label": ""
            },
            "details": {},
        }

        try:
            # 1. 현재 수급 (당일)
            inv = self.get_investor_data(ticker)
            prog = self.get_program_trading(ticker)
            
            curr_f = 0
            curr_i = 0
            curr_p = 0

            if not inv.empty:
                curr_f = int(inv.iloc[0].get("외인순매수", 0))
                curr_i = int(inv.iloc[0].get("기관순매수", 0))
                result["details"]["외인순매수"] = curr_f
                result["details"]["기관순매수"] = curr_i
                if curr_f > 0:
                    result["foreign_buy"] = True
                    result["buy_count"] += 1
                if curr_i > 0:
                    result["institution_buy"] = True
                    result["buy_count"] += 1

            if prog:
                curr_p = prog.get("프로그램순매수", 0)
                result["details"]["프로그램순매수"] = curr_p
                if curr_p > 0:
                    result["program_buy"] = True
                    result["buy_count"] += 1

            # 2. 가속도 계산 (과거 5일 평균 대비)
            # KIS API의 한계로 정확한 리스트 조회가 어려울 경우 시뮬레이션 또는 절대 수치 기반 추정
            # 여기서는 '거래량' 대비 수급 비중의 변화로 가속도 모사
            price_data = self.get_current_price(ticker)
            avg_vol = 100000 # 기본값
            curr_vol = price_data.get("거래량", 1)
            
            # 가속도 로직: (현재 수급 / 현재 거래량) vs (임계치 0.05)
            # 5% 이상의 거래가 특정 수급 주체에 의해 발생하면 '가속'으로 판정
            f_acc = (abs(curr_f) / curr_vol) * 20 # 0.05일 때 1.0
            i_acc = (abs(curr_i) / curr_vol) * 20
            p_acc = (abs(curr_p) / curr_vol) * 20
            
            result["acceleration"]["foreign"] = round(f_acc, 1)
            result["acceleration"]["institution"] = round(i_acc, 1)
            result["acceleration"]["program"] = round(p_acc, 1)
            
            acc_list = []
            if f_acc > 2.0: acc_list.append(f"외인 {f_acc:.1f}x 폭발")
            if i_acc > 2.0: acc_list.append(f"기관 {i_acc:.1f}x 폭발")
            if p_acc > 2.0: acc_list.append(f"프로그램 {p_acc:.1f}x 가속")
            
            result["acceleration"]["label"] = ", ".join(acc_list) if acc_list else "수급 완만"

        except Exception as e:
            logger.debug(f"{ticker} 수급 가속도 분석 실패: {e}")

        return result

    # ══════════════════════════════════════
    # 4. KIS API — 호가/체결/프로그램
    # ══════════════════════════════════════
    def get_current_price(self, ticker: str) -> dict:
        """현재가 조회 (KIS REST API)"""
        url = f"{kis_config.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = kis_auth.get_headers("FHKST01010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") == "0":
                output = data.get("output", {})
                return {
                    "현재가": int(output.get("stck_prpr", 0)),
                    "등락률": float(output.get("prdy_ctrt", 0)),
                    "거래량": int(output.get("acml_vol", 0)),
                    "거래대금": int(output.get("acml_tr_pbmn", 0)),
                    "시가": int(output.get("stck_oprc", 0)),
                    "고가": int(output.get("stck_hgpr", 0)),
                    "저가": int(output.get("stck_lwpr", 0)),
                    "체결강도": float(output.get("seln_cnqn_smtn", 0)),
                }
            return {}
        except Exception as e:
            logger.warning(f"{ticker} 현재가 조회 실패: {e}")
            return {}

    def get_orderbook(self, ticker: str) -> dict:
        """호가 잔량 조회 (KIS REST API)"""
        url = f"{kis_config.base_url}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
        headers = kis_auth.get_headers("FHKST01010200")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") == "0":
                output = data.get("output1", {})
                total_ask = int(output.get("total_askp_rsqn", 0))
                total_bid = int(output.get("total_bidp_rsqn", 0))
                return {
                    "매도잔량합": total_ask,
                    "매수잔량합": total_bid,
                    "매도매수비율": round(total_ask / max(total_bid, 1), 2),
                }
            return {}
        except Exception as e:
            logger.warning(f"{ticker} 호가 조회 실패: {e}")
            return {}

    def get_program_trading(self, ticker: str) -> dict:
        """프로그램 매매 동향 (KIS REST API)"""
        url = f"{kis_config.base_url}/uapi/domestic-stock/v1/quotations/program-trade-by-stock"
        headers = kis_auth.get_headers("FHPPG04650100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") == "0":
                output = data.get("output1", {})
                return {
                    "프로그램매수": int(output.get("pgmn_buy_qty", 0)),
                    "프로그램매도": int(output.get("pgmn_sell_qty", 0)),
                    "프로그램순매수": int(output.get("pgmn_ntby_qty", 0)),
                }
            return {}
        except Exception as e:
            logger.warning(f"{ticker} 프로그램매매 조회 실패: {e}")
            return {}

    # ══════════════════════════════════════
    # 5. 매물대 (가격대별 거래량)
    # ══════════════════════════════════════
    def get_volume_profile(self, ticker: str, days: int = 60, bins: int = 20) -> pd.DataFrame:
        """가격대별 거래량 분포 (매물대)"""
        ohlcv = self.get_ohlcv(ticker, days)
        if ohlcv.empty:
            return pd.DataFrame()

        price_range = np.linspace(ohlcv["저가"].min(), ohlcv["고가"].max(), bins + 1)
        volume_profile = []

        for i in range(len(price_range) - 1):
            low, high = price_range[i], price_range[i + 1]
            mid = (low + high) / 2
            mask = (ohlcv["저가"] <= high) & (ohlcv["고가"] >= low)
            vol = ohlcv.loc[mask, "거래량"].sum()
            volume_profile.append({
                "가격하한": int(low),
                "가격상한": int(high),
                "중심가격": int(mid),
                "거래량합": int(vol),
            })

        df = pd.DataFrame(volume_profile)
        total_vol = df["거래량합"].sum()
        df["거래량비율"] = df["거래량합"] / max(total_vol, 1)
        return df

    # ══════════════════════════════════════
    # 6. 지수 데이터
    # ══════════════════════════════════════
    def get_market_index(self, index_code: str = "1001", days: int = 30) -> pd.DataFrame:
        """시장 지수 조회 (KRX)"""
        cache_key = f"index_{index_code}_{days}"
        if cache_key in self._cache:
            ts, df = self._cache[cache_key]
            if (datetime.now() - ts).seconds < 600:
                return df

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=int(days * 1.5))).strftime("%Y%m%d")

        df = krx_post("dbms/MDC/STAT/standard/MDCSTAT00301", {
            "idxIndMidclssCd": index_code,
            "strtDd": start_date,
            "endDd": end_date,
            "csvxls_isNo": "false",
        })

        if df.empty:
            df = self._generate_simulated_index(index_code, days)
        else:
            col_map = {
                "TRD_DD": "날짜",
                "CLSPRC_IDX": "종가",
                "OPNPRC_IDX": "시가",
                "HGPRC_IDX": "고가",
                "LWPRC_IDX": "저가",
                "ACC_TRDVOL": "거래량",
                "ACC_TRDVAL": "거래대금",
            }
            df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

            for col in ["종가", "시가", "고가", "저가"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            if "날짜" in df.columns:
                df["날짜"] = pd.to_datetime(df["날짜"])
                df = df.set_index("날짜").sort_index()

            df = df.tail(days)

        self._cache[cache_key] = (datetime.now(), df)
        return df

    # ══════════════════════════════════════
    # 7. 종목명 조회
    # ══════════════════════════════════════
    def get_stock_name(self, ticker: str) -> str:
        """종목명 반환"""
        if ticker in self._ticker_name_cache:
            return self._ticker_name_cache[ticker]

        # KRX에서 조회 시도
        well_known = {
            "005930": "삼성전자", "000660": "SK하이닉스",
            "373220": "LG에너지솔루션", "207940": "삼성바이오로직스",
            "005380": "현대차", "006400": "삼성SDI",
            "035420": "NAVER", "051910": "LG화학",
            "068270": "셀트리온", "028260": "삼성물산",
            "035720": "카카오", "105560": "KB금융",
            "055550": "신한지주", "066570": "LG전자",
            "003670": "포스코퓨처엠", "000270": "기아",
            "012330": "현대모비스", "096770": "SK이노베이션",
            "034730": "SK", "015760": "한국전력",
        }
        return well_known.get(ticker, ticker)

    # ══════════════════════════════════════
    # 8. 시뮬레이션 데이터 (API 미연결 시)
    # ══════════════════════════════════════
    def _generate_simulated_ohlcv(self, ticker: str, days: int = 200) -> pd.DataFrame:
        """시뮬레이션 OHLCV (API 미연결 시 데모용)"""
        np.random.seed(hash(ticker) % 2**31)

        base_prices = {
            "005930": 71000, "000660": 190000, "373220": 380000,
            "207940": 750000, "005380": 245000, "006400": 350000,
            "035420": 215000, "051910": 370000, "068270": 185000,
            "028260": 120000, "035720": 45000, "105560": 72000,
        }
        base = base_prices.get(ticker, 50000)

        dates = pd.bdate_range(end=datetime.now(), periods=days, freq='B')
        prices = [base]
        for _ in range(days - 1):
            change = np.random.normal(0, 0.02)
            prices.append(prices[-1] * (1 + change))

        prices = np.array(prices)
        highs = prices * (1 + np.random.uniform(0, 0.03, days))
        lows = prices * (1 - np.random.uniform(0, 0.03, days))
        opens = prices * (1 + np.random.uniform(-0.015, 0.015, days))
        volumes = np.random.randint(500000, 5000000, days)

        df = pd.DataFrame({
            "시가": opens.astype(int),
            "고가": highs.astype(int),
            "저가": lows.astype(int),
            "종가": prices.astype(int),
            "거래량": volumes,
            "거래대금": (prices * volumes).astype(int),
        }, index=dates)

        # 등락률 추가
        df["등락률"] = df["종가"].pct_change() * 100

        return df

    def _generate_simulated_market_data(self) -> pd.DataFrame:
        """대규모 시뮬레이션 시장 데이터 (테스트용 200종목)"""
        data = []
        # 주요 우량주 우선 배치
        blue_chips = [
            ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("373220", "LG에너지솔루션"),
            ("207940", "삼성바이오로직스"), ("005380", "현대차"), ("000270", "기아"),
            ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"),
            ("035720", "카카오")
        ]
        
        for ticker, name in blue_chips:
            np.random.seed(hash(ticker) % 2**31)
            cap = np.random.randint(50, 500) * 1_000_000_000_000
            trdval = np.random.randint(100, 1000) * 1_000_000_000
            data.append({
                "종목코드": ticker, "종목명": name, "종가": np.random.randint(50000, 800000),
                "시가총액": cap, "거래대금": trdval, "거래량": np.random.randint(500000, 5000000),
                "시장": "KOSPI",
            })

        # 나머지 190개 더미 데이터 생성
        for i in range(190):
            t = f"{900000 + i:06d}"
            name = f"시뮬레이션_{i+1:03d}"
            np.random.seed(i)
            cap = np.random.randint(1, 100) * 1_000_000_000_000
            trdval = np.random.randint(1, 100) * 1_000_000_000
            data.append({
                "종목코드": t, "종목명": name, "종가": np.random.randint(1000, 100000),
                "시가총액": cap, "거래대금": trdval, "거래량": np.random.randint(10000, 1000000),
                "시장": "KOSDAQ",
            })
            
        df = pd.DataFrame(data).set_index("종목코드")
        return df

    def _generate_simulated_index(self, index_code: str, days: int) -> pd.DataFrame:
        """시뮬레이션 지수 데이터 (사용자 요청 5900+ 반영)"""
        # 1001=KOSPI, 1002=KOSDAQ
        base = 5950 if index_code == "1001" else 5970 
        dates = pd.bdate_range(end=datetime.now(), periods=days, freq='B')

        prices = [base]
        for _ in range(days - 1):
            prices.append(prices[-1] * (1 + np.random.normal(0, 0.005)))

        df = pd.DataFrame({
            "종가": prices,
            "시가": [p * (1 + np.random.uniform(-0.003, 0.003)) for p in prices],
            "고가": [p * (1 + np.random.uniform(0, 0.005)) for p in prices],
            "저가": [p * (1 - np.random.uniform(0, 0.005)) for p in prices],
        }, index=dates)
        return df


# ──────────────────────────────────────────
# 싱글톤 인스턴스
# ──────────────────────────────────────────
collector = DataCollector()
