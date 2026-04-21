# Plan: bl-eta

> 작성일: 2026-04-21 | 버전: v1.0 | 기반: research.md

---

## 1. Overview

**한 줄 정의**: track-trace.com을 Playwright로 병렬 자동 조회해 BL의 부산/인천 ETA를 긁어오고, 전일 대비 변동을 감지·export하는 Streamlit 로컬 RPA 도구.

**MVP 목표**: 매일 아침 BL 10~20건 조회 루틴을 수작업 1시간 → **5분 이내**로 단축하고, 전일 대비 ETA 변동을 누락 없이 감지한다.

**성공 기준**
- 10~20건 BL 조회·파싱·비교가 **5분 이내** 완료
- 전일 대비 ETA 변동 BL **100% 감지** 및 시각적 하이라이트
- CSV/엑셀 export가 **고객사 이메일 첨부에 바로 사용 가능**한 포맷

**핵심 가치**: 연간 ~250시간 수작업 제거 + 라인스톱 리스크 예방 (변동 누락 제로)

---

## 2. 타겟 & 문제

**유저**: 트레이딩사업팀 실무자 본인. 매일 아침 BL 수작업 트래킹 후 엑셀+이메일로 외부 고객사에 전달.

**문제**: 전쟁 여파로 선복 타이트 + 재고 없이 입항 즉시 납품 → ETA D+1 변동 누락 시 고객사 라인스톱 위기. 현재는 BL 10~20건을 하나씩 사이트에 수동 입력 (약 1시간 소요).

**해결**: BL 리스트 입력 → Playwright async 병렬 조회 → 부산/인천 ETA 파싱 → 전일 비교 → 하이라이트 테이블 + CSV/엑셀 export.

**차별점**: 상용 서비스가 아닌 **개인 업무용 RPA**. "조회"가 아니라 **"변동 감지"**가 주 기능이라는 점이 다르다. 전일 스냅샷과 자동 비교하여 달라진 BL만 하이라이트한다.

---

## 3. 기능 범위

### In Scope

| 기능 | 설명 | 우선순위 |
|------|------|---------|
| BL 다중 입력 UI | Textarea에 BL 번호 여러 개 붙여넣기 (줄바꿈 구분) | P0 |
| 병렬 자동 조회 | Playwright async, 동시 5개 병렬 | P0 |
| 부산/인천 ETA 파싱 | track-trace 결과에서 Busan/Incheon 항목만 추출 | P0 |
| 전일 대비 변동 감지 | SQLite에 저장된 전일 스냅샷과 비교, 변동 BL 하이라이트 | P0 |
| 결과 테이블 표시 | Streamlit DataFrame, 변동 셀은 색상 구분 | P0 |
| CSV/엑셀 export | pandas → xlsx/csv 다운로드 버튼 | P0 |
| Headless/Headed 토글 | 사이드바 스위치로 브라우저 표시 on/off | P0 |
| 진행률 표시 | st.progress + BL별 실시간 상태 로그 | P0 |
| 실패 BL 플래그 | 조회 실패/부산·인천 미발견 BL을 별도 표시 | P1 |

### Out of Scope
- 조회 이력 스택 / 추이 차트 → Post-MVP (사용자 합의)
- ESL / Wanhai / Cordelia 직접 조회 자동화 → MVP는 track-trace만, 3개사는 수기 병행
- 매일 아침 자동 스케줄 실행 (cron) → 사람이 버튼 누르는 구조
- 고객사별 자동 이메일 발송 → export 후 수동 첨부
- 로그인 / 다중 유저 → 본인 로컬 단독 사용

---

## 4. 기술 스택 (확정)

```
언어       : Python 3.11+
자동화      : Playwright (async API)
UI         : Streamlit
저장소      : SQLite (로컬 파일 bl_eta.db)
Export     : pandas + openpyxl
패키지 관리  : uv
실행 모드   : Headless 기본, Streamlit 사이드바 토글로 Headed 전환
동시성      : asyncio.Semaphore(5) — 안전 기본값 (사이트 Rate limit 미확인)
```

---

## 5. 화면 구성

Streamlit 단일 페이지 + 사이드바 구성 (페이지 분리 없음 — MVP 원칙).

```
┌─ 사이드바 ─────────────────────────┐
│ - Headless/Headed 토글            │
│ - 동시성 슬라이더 (1~10, 기본 5)    │
│ - DB 초기화 버튼                   │
└───────────────────────────────────┘
┌─ 메인 영역 ────────────────────────┐
│ 1. BL 입력 Textarea (줄바꿈 구분)  │
│ 2. [조회 시작] 버튼                │
│ 3. 진행률 바 + 실시간 상태 로그    │
│ 4. 결과 테이블 (변동 하이라이트)   │
│ 5. [CSV 다운로드] [엑셀 다운로드]  │
└───────────────────────────────────┘
```

---

## 6. 데이터 모델

SQLite 파일 1개 (`bl_eta.db`), 단일 테이블로 충분.

```sql
CREATE TABLE eta_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bl_no       TEXT NOT NULL,
    carrier     TEXT,           -- 선사명 (파싱 가능 시)
    port        TEXT,           -- "Busan" or "Incheon"
    eta         TEXT,           -- ISO 날짜 YYYY-MM-DD, 파싱 실패 시 NULL
    raw_text    TEXT,           -- 원본 파싱 텍스트 (디버깅용)
    queried_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status      TEXT NOT NULL   -- "ok" | "not_found" | "failed"
);
CREATE INDEX idx_bl_queried ON eta_history(bl_no, queried_at DESC);
```

> "어제 vs 오늘" 비교는 `SELECT * FROM eta_history WHERE bl_no=? ORDER BY queried_at DESC LIMIT 2` 한 줄로 수행. 별도 "변동 로그" 테이블 불필요 (실시간 계산으로 대체).

---

## 7. 핵심 기능 동작 규칙

### 7.1 ETA 파싱 동작 규칙

**입력**: BL 번호 문자열 (예: `MSCU1234567`)

**처리 흐름**:
1. Playwright로 `https://www.track-trace.com/bol` 접속
2. "Bill of Lading Tracking" 입력창에 BL 번호 입력 → 제출
3. 선사 결과 페이지 렌더링 완료 대기 (최대 30초)
4. 페이지 내에서 항구명이 **"Busan"** 또는 **"Incheon"**(대소문자 무관, "PUSAN" 표기도 매칭)인 Row 탐색
5. 해당 Row에서 **ETA 날짜 추출** → ISO 포맷(`YYYY-MM-DD`)으로 정규화
6. 여러 개 매칭 시 **가장 늦은 ETA** 선택 (= 최종 목적항 기준)

**출력 레코드**:
```python
{"bl_no": "MSCU1234567", "carrier": "Maersk", "port": "Busan",
 "eta": "2026-05-03", "status": "ok", "raw_text": "..."}
```

**파싱 실패 규칙**:
- Busan/Incheon 둘 다 없음 → `status="not_found"`, `eta=NULL`
- 사이트 접속/로딩 실패 → `status="failed"`, `eta=NULL`
- 실패 BL도 결과 테이블에 표시 (사용자가 수동 조회 판단 가능하도록)

- [RISK] 선사별 HTML 구조 차이: 머스크/CMA/KCTC 등 각 선사 결과 레이아웃이 다를 가능성. Phase 1 PoC에서 샘플 3~5건으로 구조 확인 후 파서 분기 결정.
- [RISK] 항구명 표기 다양성: `Busan / BUSAN / Pusan / 부산` — 소문자 변환 후 `["busan", "pusan", "incheon"]` 부분 매칭으로 커버.

### 7.2 변동 감지 동작 규칙

**입력**: 오늘 조회한 BL별 ETA 레코드

**규칙**:
1. 각 BL에 대해 직전 `queried_at`의 ETA를 SQLite에서 조회
2. 비교 결과를 3가지로 분류:
   - `NEW`: 이전 기록 없음 (신규 조회) → 파란색 표시
   - `UNCHANGED`: ETA 동일 → 회색
   - `CHANGED`: ETA 다름 → **빨간색 하이라이트 + 기존 ETA → 신규 ETA 병기**
3. CHANGED 건은 테이블 상단으로 정렬

**출력 테이블 예시**:
| BL | 선사 | 항구 | 이전 ETA | 오늘 ETA | 상태 |
|----|------|------|----------|----------|------|
| MSCU1234567 | Maersk | Busan | 2026-05-01 | 2026-05-03 | **CHANGED** |
| CMAU9876543 | CMA | Incheon | 2026-04-30 | 2026-04-30 | UNCHANGED |
| KMTC5555 | KCTC | Busan | — | 2026-05-05 | NEW |

- [RISK] "어제"의 정의: 당일 여러 번 조회 시 직전 스냅샷 기준으로 할지, 전일자 기준으로 할지. MVP는 **직전 `queried_at` 1건 기준**으로 구현 (단순성 우선).

---

## 8. Phase 구성

| Phase | 목표 | 산출물 |
|-------|------|--------|
| Phase 0 | 프로젝트 세팅 | `uv init` + Playwright 설치 + 빈 Streamlit 앱 실행 확인 |
| Phase 1 | **track-trace PoC** — BL 1건 조회+파싱 CLI 스크립트. Bot 차단 여부·HTML 구조 실측 | 단일 BL 입력 → ETA 출력 스크립트, 선사별 샘플 3~5건 구조 문서 |
| Phase 2 | 병렬 조회 + Streamlit UI | 다중 BL 입력 → 병렬 조회 → 결과 테이블 표시, Headless/Headed 토글, 진행률 바 |
| Phase 3 | SQLite 저장 + 변동 감지 | 매 조회 시 DB 저장, 전일 대비 변동 하이라이트 |
| Phase 4 | CSV/엑셀 export + 마감 | Export 버튼, 에러 케이스 UX 정리, README 작성 → MVP 완료 |

> **Phase 1이 최대 리스크 지점**. PoC 실패(Bot 차단 등) 시 스택 변경 또는 대체 소스 검토 필요.

---

## 9. CLAUDE.md 초기값

```markdown
## Project
bl-eta — track-trace.com 병렬 자동 조회로 BL의 부산/인천 ETA를 긁고 전일 대비 변동을 감지하는 Streamlit 로컬 RPA.

## Tech Stack
- Python 3.11+ / Playwright (async) / Streamlit / SQLite / pandas+openpyxl / uv
- 실행: `uv run streamlit run app.py`

## Project Structure
- app.py              : Streamlit 진입점
- bl_eta/tracker.py   : Playwright 조회+파싱 로직
- bl_eta/parser.py    : 부산/인천 ETA 파서 (선사별 분기)
- bl_eta/db.py        : SQLite CRUD + 변동 비교
- bl_eta/export.py    : CSV/엑셀 export
- bl_eta.db           : 로컬 SQLite (gitignore)

## Rules
- Playwright는 async API만 사용 (`playwright.async_api`)
- DB 접근은 반드시 `bl_eta/db.py` 경유 (직접 sqlite3 import 금지)
- 파싱 로직은 `bl_eta/parser.py`에 격리 — 선사별 분기 시 여기서만 수정
- 항구명 매칭은 소문자 변환 후 `["busan", "pusan", "incheon"]` 부분 매칭
- 동시성 기본값 5, 사이드바에서 1~10 조절

## 주의사항 (research.md [검증 필요] → 전환)
- [RISK] track-trace.com Bot 차단 가능성 (Cloudflare 등). Phase 1 PoC 최우선 검증.
- [RISK] 선사별 HTML 구조 차이. 파서는 분기 설계를 전제로 작성.
- [RISK] 동시 병렬 조회 Rate limit 미확인. 기본값 5에서 시작, 403/429 발생 시 축소.
- [RISK] 항구명 표기 다양성 (Busan/BUSAN/Pusan). 소문자+부분매칭으로 대응.
- [RISK] ETA 변동 빈도 미측정 — 하이라이트 피로도 과/부족 여부는 1주 사용 후 조정.
- [RISK] track-trace 커버리지 미확정 — 미지원 선사는 결과 테이블에 `not_found` 플래그 표시, ESL/Wanhai/Cordelia는 수기 병행 명시.

## 금지사항
- 상용 배포 금지 (로컬 단독 사용 전제)
- 조회 결과 외부 API 전송 금지 (사내 BL 정보)
- Playwright sync API 사용 금지 (성능상 병렬 필수)
```
