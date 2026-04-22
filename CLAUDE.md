# CLAUDE.md

> 이 문서는 Claude Code가 bl-eta 코드를 작성/수정할 때 참조하는 유일한 프로젝트 맥락 문서다.
> plan.md·research.md·todo.md는 기획/진행 추적용, CLAUDE.md는 "지금 코드를 어떻게 짜야 하는가"의 기준.

---

## Project

**bl-eta** — track-trace.com을 Playwright(async)로 병렬 자동 조회해 BL의 부산/인천 ETA를 긁고, 전일 대비 변동을 감지·export하는 Streamlit **로컬 단독** RPA.

- 사용자: 트레이딩사업팀 실무자 본인 (로컬 1인)
- 목표: BL 10~20건 아침 루틴을 수작업 1시간 → **5분 이내**
- 차별점: **"변동 감지"** (전일 스냅샷 비교) + **선적 마스터 테이블** (제련소·출항지·선사·선명·BL·공급물량·최초출항일·국내 도착일·전일 대비 변동·화물 위치)

---

## Tech Stack

- Python **3.11** (uv 관리, `.python-version` 고정)
- **Playwright ≥1.58** (async API 전용) + Chromium
- **Streamlit ≥1.56** (`st.data_editor`, `st.dialog`, `st.popover` 사용)
- **SQLite** (로컬 파일 `~/.bl-eta/bl_eta.db`, 커밋 금지)
- **pandas ≥3.0 + openpyxl ≥3.1** (xlsx I/O)
- 패키지 관리: **uv**

## Run Commands

```bash
uv sync
uv run playwright install chromium
uv run streamlit run app.py             # http://localhost:8501
```

---

## Project Structure

```
ship/
├── app.py                    # Streamlit 진입점 (마스터 + 빠른조회 2섹션)
├── bl_eta/
│   ├── tracker.py            # Playwright 병렬 조회 (track_many)
│   ├── parser.py             # 부산/인천 ETA 파서 (선사별 분기)
│   ├── db.py                 # SQLite CRUD (eta_history + shipments)
│   └── export.py             # xlsx/csv I/O + shipments 업로드 파싱
├── docs/carrier-samples.md   # 선사별 HTML 구조 문서
└── pyproject.toml
```

---

## Rules

### 코드 규칙
- **Playwright는 async API만** 사용. sync API 금지.
- **DB 접근은 반드시 `bl_eta/db.py` 경유.** 다른 모듈에서 `import sqlite3` 금지.
- **파싱 로직은 `bl_eta/parser.py`에 격리.** 선사별 분기는 여기서만.
- **항구명 매칭**: 소문자 변환 후 `["busan","pusan","incheon"]` 부분 매칭.
- **ETA 정규화**: ISO `YYYY-MM-DD`. 파싱 실패 시 `None`.
- 여러 항구 Row 매칭 시 **가장 늦은 ETA** 선택 (최종 목적항 기준).

### 동시성
- 기본 `asyncio.Semaphore(5)`, 사이드바 1~10. 403/429 시 즉시 축소.
- **병렬 패턴**: 단일 `browser` 공유 + **BL마다 별도 `BrowserContext`** (HMM fullscreen 캡처가 context-scoped `expect_page` 의존). 결과 인덱스 보존. 진행률은 `on_progress(done,total,bl,rec)` 콜백.
- **Streamlit ↔ asyncio 브릿지**: `threading.Thread` 내부에서 `asyncio.run(track_many(...))`. 메인 쓰레드는 `state["done"]` polling으로 `st.progress` 갱신.

### UI 레이아웃 (`app.py`)
- **사이드바**: Headed 토글(**기본 ON**, Maersk headless 감지 회피), 동시성 슬라이더, DB 초기화(`eta_history`만), DB 내역 expander.
- **1. 선적 마스터** — `st.data_editor` (num_rows="fixed") 기반 마스터 테이블.
  - 좌→우 컬럼: `선택`(체크박스) · 제련소 · 출항지 · 선사 · 선명 · BL · 공급물량(톤) · 최초출항일 · 국내 도착일 · 전일 대비 변동 · 화물 위치
  - 파생 컬럼(disabled): 국내 도착일·전일 대비 변동. 그 외는 편집 가능.
  - 빈 값은 모두 빈칸 렌더 (`None`/`"None"` 표시 금지). `공급물량(톤)`은 `pd.to_numeric(errors="coerce")`로 float64 캐스팅해 NaN이 빈칸으로 보이게.
  - 헤더 우측 아이콘 버튼: `:material/add:` (행 추가) · `:material/remove:` (선택 삭제) · `:material/upload:` popover (엑셀 업로드) · `:material/download:` (엑셀 다운로드). 모두 `help=` 툴팁 제공.
  - 하단 버튼: **테이블 저장** / **ETA/위치 새로고침** (primary).
  - 새로고침 흐름: ①현재 편집 저장 → ②마스터 BL 전체로 `track_many` → ③`run_master_refresh_inplace`가 data_editor 슬롯을 행별 진행 테이블로 **인플레이스 교체**(진행중 → ✓ 완료 / ✗ 없음 / ✗ 실패) + 버튼 하단에 `st.progress`·`x/y 조회 중…` → ④완료 시 `st.session_state["_refresh_done"]` 저장 후 `st.rerun()` → ⑤상단 조건부 `@st.dialog`로 "새로고침 완료" 모달 표시.
- **2. 빠른 조회** — 기존 text_area + `조회 시작`. 결과 테이블·CSV/xlsx 다운로드. `st.session_state["quick_run"]`에 캐시.

### 데이터 스키마 (`~/.bl-eta/bl_eta.db`)
`bl_eta/db.py:_default_db_path` 경유. 레거시 `./bl_eta.db` 자동 이관. 스키마 변경은 `init_db()` 내부 migration 함수로 idempotent 처리.

```sql
CREATE TABLE eta_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bl_no TEXT NOT NULL,
    carrier TEXT, port TEXT,              -- port: "Busan" | "Incheon"
    eta TEXT,                             -- YYYY-MM-DD 또는 NULL
    raw_text TEXT,
    queried_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- UTC
    status TEXT NOT NULL                  -- "ok" | "not_found" | "failed"
);
CREATE INDEX idx_bl_queried ON eta_history(bl_no, queried_at DESC);

CREATE TABLE shipments (                  -- 선적 마스터
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    smelter TEXT, origin TEXT, carrier TEXT, vessel TEXT,
    bl_no TEXT UNIQUE,                    -- NULL 허용 (BL 미확정 행 저장 가능)
    supply_tons REAL,
    initial_depart_date TEXT,             -- YYYY-MM-DD
    cargo_location TEXT                   -- 현재 수기, 추후 외부 소스 연동
);
```

### 전일 대비 변동 (`app.py:_delta_str`)
- **비교 기준**: `db.get_previous(bl)` = **KST 오늘 이전** 최신 1건 (`DATE(queried_at,'+9 hours') < DATE('now','+9 hours')`). 당일 재조회 기록은 prev 후보에서 제외.
- **현재 ETA**: `db.get_latest_for_bl(bl)` (날짜 필터 없음).
- **표기 규칙**:
  - `curr` 없음 → `""`
  - `curr` 있고 `prev` 없음 → `"신규"`
  - 둘 다 있고 같음 → `"변동없음"`
  - 둘 다 있고 다름 → `"D±n"` (curr - prev 일수)
  - 파싱 실패 → `""`

### Export (`bl_eta/export.py`)
- **빠른조회**: `to_csv(df)` (UTF-8 BOM) / `to_xlsx(df)` (헤더 굵게, 컬럼 폭 auto 8~40, A2 freeze). 파일명 `bl_eta_YYYY-MM-DD.{csv,xlsx}`.
- **마스터**: `shipments_to_xlsx(df)` / `shipments_from_xlsx(bytes) -> list[dict]`. 한글 헤더 ↔ DB 컬럼 매핑은 `SHIPMENT_COLS` 상수. 업로드는 전체 교체(`shipments_replace`). 빈 BL 행은 업로드 파싱 단계에서 스킵.

### 날짜 입력 정규화 (`app.py`)
- `_parse_date`: `%Y-%m-%d` / `%Y.%m.%d` / `%Y/%m/%d` / `%Y%m%d` 순서로 시도. 실패 시 None.
- `_date_to_iso`: 저장 직전 `최초출항일`을 `YYYY-MM-DD`로 정규화. 사용자는 어떤 포맷이든 입력 가능.

### 실패 처리
- 부산/인천 미발견 → `status="not_found"`, `eta=NULL`
- 접속/로딩 실패 → `status="failed"`, `eta=NULL`
- **실패 BL도 테이블·export에 포함** (수동 판단 가능)

---

## 주의사항 (plan.md [RISK] 전환)

- [RISK] **track-trace.com Bot 차단** — Headed 기본 ON으로 회피 중. 차단 관찰 시 stealth/UA 검토.
- [RISK] **선사별 HTML 구조 차이** — 파서 분기 유지. 신규 선사는 `docs/carrier-samples.md`에 샘플 기록.
- [RISK] **병렬 Rate limit** — 기본 5, 403/429 시 축소.
- [RISK] **track-trace 커버리지 미확정** — 미지원 선사는 `not_found`. ESL/Wanhai/Cordelia는 수기 병행.
- [RISK] **화물 위치 자동화 미연동** — 현재 마스터 수기 입력. 외부 소스 확정 시 파생 컬럼으로 전환.

---

## 금지사항

- **상용 배포 금지** — 로컬 단독 전제
- **조회 결과 외부 API 전송 금지** — 사내 BL 정보
- **Playwright sync API 금지**
- **`bl_eta.db` 커밋 금지** (사용자 홈에만 존재)
- **BL 번호 코드/테스트/커밋 메시지 하드코딩 금지** — 샘플은 `docs/carrier-samples.md`에 마스킹

---

## Phase 진행 상황

`todo.md`를 단일 출처로 삼는다. 현재: **Phase 4 + 선적 마스터 UI 개편 구현 완료**.
