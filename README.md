# 🚀 퀀트 트레이딩 스캐너 v1.0

> 5대 전략 기반 실시간 매수 기회 탐색 시스템

## 📊 5대 전략

| 전략 | 핵심 로직 | 판별 조건 |
|------|----------|----------|
| **🔵 눌림목** | 기준봉 중심값 지지 | 거래량 절벽 + 기관 보유 유지 |
| **🟢 바닥 탈출** | 20일선 돌파 | 매물대 벽 없음 + 매집봉 존재 |
| **🟡 골든 크로스** | MA5↑MA20 교차 | 20일선 기울기 양(+) + RSI>50 |
| **🔴 박스권 돌파** | 전고점 돌파 | 매도호가/매수호가 2배↑ + 프로그램 순매수 |
| **🟣 정배열 초입** | 이평선 밀집→발산 | 5-20-60-120일선 3%내 + 업종 상승 |

## 🏗️ 아키텍처

```
Scanner ──┬── DataCollector (KRX + KIS API)
          ├── TechnicalIndicators (MA/RSI/ATR/피보나치)
          ├── StrategyEngine (5대 전략 판별)
          ├── RiskManager (시장 필터 + 손절 자동화)
          ├── ReportGenerator (콘솔/텔레그램/JSON)
          └── FastAPI Dashboard (웹 UI)
```

## ⚡ 빠른 시작

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정
```bash
copy .env.example .env
# .env 파일에서 KIS API 키를 입력하세요
```

### 3. 대시보드 서버 실행
```bash
python server.py
# → http://localhost:8501 접속
```

### 4. CLI 스캔 실행
```bash
python scanner.py
```

## 🖥️ 대시보드

웹 대시보드는 `http://localhost:8501`에서 접속 가능합니다.

- **🚀 스캔 실행**: 상위 300종목에 대해 5대 전략 판별
- **📈 시장 상태**: 코스피/코스닥 5일선 기준 강세/약세 판단
- **🎯 전략 필터**: 전략별, 매수승인/관망 별 필터링
- **✅/⏸️ 승인 버튼**: 종목별 매수 승인 또는 관망 처리

## 🛡️ 리스크 관리

| 규칙 | 내용 |
|------|------|
| 시장 필터 | 코스피+코스닥 5일선 이탈 시 비중 30% 이하 |
| 전략 제한 | 약세장 시 바닥 탈출 전략만 운용 |
| 손절 자동화 | ATR 기반 손절가 + 20일선 이탈 시 매도 리포트 |
| 포지션 관리 | 단일 종목 10% / 최대 10종목 동시 보유 |

## 📡 API 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| `GET` | `/api/scan` | 전체 스캔 실행 |
| `GET` | `/api/results` | 최근 결과 조회 |
| `GET` | `/api/market` | 시장 상태 |
| `GET` | `/api/stock/{ticker}` | 개별 종목 분석 |
| `POST` | `/api/approve/{ticker}` | 매수 승인/관망 |

## 📋 보고서 양식

```
📊 삼성전자(005930) / 71,500원 / 눌림목

🔍 핵심 근거:
  1. 기준봉 중심값(70,200원) 지지 확인
  2. 거래량 절벽 감지 (현재 거래량 = 평균의 28%)
  3. 기관 보유 수량 유지 확인

🎯 매수 타점:
  • 1차 매수가: 70,000원
  • 2차 매수가: 68,500원

📈 목표가 / 📉 손절가:
  • 1차 목표가: 78,000원
  • 2차 목표가: 85,000원
  • 손절가: 66,000원
  • R:R 비율: 2.0

⚡ 신뢰도: 82%
✅ 승인 여부: [매수 승인]
```

## 🔑 API 키 발급

### 한국투자증권 (KIS) Open API
1. [KIS Developers](https://apiportal.koreainvestment.com/) 접속
2. 회원가입 후 앱 등록
3. App Key / App Secret 발급
4. `.env` 파일에 입력

### 텔레그램 봇 (선택)
1. @BotFather에게 `/newbot` 명령
2. 봇 토큰 발급
3. 채팅방 ID 확인
4. `.env` 파일에 입력

## 📁 파일 구조

```
_stock/
├── config.py              # 전역 설정 (API 키, 전략 파라미터)
├── data_collector.py      # 데이터 수집 (KRX + KIS API)
├── indicators.py          # 기술적 지표 (14종)
├── strategies.py          # 5대 전략 판별 엔진
├── risk_manager.py        # 리스크 관리 (시장 필터, 손절)
├── report_generator.py    # 보고서 생성 (콘솔/텔레그램/JSON)
├── scanner.py             # 메인 스캐너 (CLI)
├── server.py              # FastAPI 대시보드 서버
├── dashboard/
│   ├── index.html         # 대시보드 UI
│   ├── style.css          # 프리미엄 다크 테마 CSS
│   └── app.js             # 프론트엔드 로직
├── requirements.txt
├── .env.example
└── README.md
```

---

> ⚠️ **면책**: 이 시스템은 투자 참고용이며, 실제 투자 판단은 사용자의 책임입니다.
> 과거 데이터 기반 분석은 미래 수익을 보장하지 않습니다.
