# CLAUDE.md

> 이 문서는 Claude Code가 bl-eta 코드를 작성/수정할 때 참조하는 유일한 프로젝트 맥락 문서다.
> plan.md·research.md·todo.md는 기획/진행 추적용, CLAUDE.md는 "지금 코드를 어떻게 짜야 하는가"의 기준.

---

## Project

**bl-eta** — track-trace.com을 Playwright(async)로 병렬 자동 조회해 BL의 부산/인천 ETA를 긁고, 전일 대비 변동을 감지·export하는 Streamlit **로컬 단독** RPA.

- 사용자: 트레이딩사업팀 실무자 본인 (로컬 1인)
- 목표: BL 10~20건 아침 루틴을 수작업 1시간 → **5분 이내**
- 차별점: "조회"가 아니라 **"변동 감지"** (전일 스냅샷 비교 하이라이트)

---

## Tech Stack

- Python **3.11.15** (uv 관리, `.python-version` 고정)
- **Playwright 1.58** (async API 전용) + Chromium 145
- **Streamlit 1.56**
- **SQLite** (로컬 파일 `bl_eta.db`, 커밋 금지)
- **pandas 3.0 + openpyxl 3.1** (CSV/xlsx export)
- 패키지 관리: **uv 0.10+**

## Run Commands

```bash
# 의존성 동기화 (pyproject.toml 기준)
uv sync

# Playwright 브라우저 바이너리 (최초 1회)
uv run playwright install chromium

# Streamlit 앱 실행
uv run streamlit run app.py
# → http://localhost:8501

# 단일 BL CLI 조회 (Phase 1 이후)
uv run python -m bl_eta.tracker <BL_NO>
```

---

## Project Structure

```
ship/
├── app.py                  # Streamlit 진입점
├── bl_eta/
│   ├── __init__.py
│   ├── tracker.py          # Playwright 조회 + 병렬 파이프라인
│   ├── parser.py           # 부산/인천 ETA 파서 (선사별 분기)
│   ├── db.py               # SQLite CRUD + 변동 비교
│   └── export.py           # CSV/xlsx export
├── bl_eta.db               # 로컬 SQLite (gitignore, 커밋 금지)
├── docs/
│   └── carrier-samples.md  # 선사별 HTML 구조 문서 (Phase 1에서 작성)
├── plan.md / research.md / todo.md / CLAUDE.md
└── pyproject.toml
```

---

## Rules

### 코드 규칙
- **Playwright는 async API만** 사용 (`from playwright.async_api import ...`). sync API 금지.
- **DB 접근은 반드시 `bl_eta/db.py` 경유.** 다른 모듈에서 `import sqlite3` 금지.
- **파싱 로직은 `bl_eta/parser.py`에 격리.** 선사별 분기가 생기면 이 파일에서만 수정.
- **항구명 매칭은 소문자 변환 후** `["busan", "pusan", "incheon"]` 부분 매칭. (Busan/BUSAN/Pusan 전부 동일 처리)
- **ETA 정규화는 ISO `YYYY-MM-DD`.** 파싱 실패 시 `None`.
- 여러 항구 Row 매칭 시 **가장 늦은 ETA** 선택 (최종 목적항 기준).

### 동시성
- 기본 `asyncio.Semaphore(5)`. 사이드바에서 1~10 조절.
- 403/429 관찰 시 즉시 축소.

### 데이터 스키마 (bl_eta.db)
```sql
CREATE TABLE eta_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bl_no       TEXT NOT NULL,
    carrier     TEXT,
    port        TEXT,          -- "Busan" | "Incheon"
    eta         TEXT,          -- YYYY-MM-DD, 실패 시 NULL
    raw_text    TEXT,          -- 원본 파싱 텍스트 (디버깅용)
    queried_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status      TEXT NOT NULL  -- "ok" | "not_found" | "failed"
);
CREATE INDEX idx_bl_queried ON eta_history(bl_no, queried_at DESC);
```

### 변동 분류
- `NEW` (이전 기록 없음) → 파랑
- `UNCHANGED` (ETA 동일) → 회색
- `CHANGED` (ETA 다름) → 빨강 + 이전/신규 ETA 병기, 테이블 **상단 정렬**
- "어제"의 정의는 **직전 `queried_at` 1건 기준** (MVP)

### 실패 처리
- 부산/인천 미발견 → `status="not_found"`, `eta=NULL`
- 접속/로딩 실패 → `status="failed"`, `eta=NULL`
- **실패 BL도 결과 테이블·export에 포함** (사용자가 수동 판단 가능하도록)

---

## 주의사항 (research.md·plan.md [RISK] 전환)

- [RISK] **track-trace.com Bot 차단 (Cloudflare 등)** — Phase 1에서 최우선 검증. 차단 확인 시 stealth/UA 우회 시도, 그래도 실패 시 스택 재검토.
- [RISK] **선사별 HTML 구조 차이** — 파서는 분기 설계 전제. Phase 1에서 샘플 3~5건으로 `docs/carrier-samples.md` 작성.
- [RISK] **병렬 Rate limit 미확인** — 기본 5, 403/429 시 축소.
- [RISK] **항구명 표기 다양성** — 소문자+부분매칭으로 커버.
- [RISK] **ETA 변동 빈도 미측정** — 1주 사용 후 하이라이트 톤 조정.
- [RISK] **track-trace 커버리지 미확정** — 미지원 선사는 `not_found`. ESL/Wanhai/Cordelia는 MVP에서 수기 병행.

---

## 금지사항

- **상용 배포 금지** — 로컬 단독 사용 전제
- **조회 결과 외부 API 전송 금지** — 사내 BL 정보
- **Playwright sync API 사용 금지** — 병렬 필수
- **`bl_eta.db` 커밋 금지** — .gitignore 등재
- **BL 번호를 코드/테스트/커밋 메시지에 하드코딩 금지** — 샘플은 `docs/carrier-samples.md`에 마스킹해서 기록

---

## Phase 진행 상황

진행 중인 Phase와 다음 태스크는 `todo.md`를 단일 출처로 삼는다.
현재: **Phase 0 — 프로젝트 세팅 (진행 중)**
