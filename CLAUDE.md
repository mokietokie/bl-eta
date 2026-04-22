# CLAUDE.md

> 이 문서는 Claude Code가 bl-eta 코드를 작성/수정할 때 참조하는 유일한 프로젝트 맥락 문서다.
> plan.md·research.md·todo.md는 기획/진행 추적용, CLAUDE.md는 "지금 코드를 어떻게 짜야 하는가"의 기준.

---

## Project

**bl-eta** — track-trace.com(BL ETA) + vesselfinder.com(선박 위치)을 Playwright(async)로 병렬 자동 조회해, BL의 부산/인천 ETA와 선박 현재 위치(가까운 연안 국가)를 긁고, 전일 대비 변동을 감지·export하는 Streamlit **로컬 단독** RPA.

- 사용자: 트레이딩사업팀 실무자 본인 (로컬 1인)
- 목표: BL 10~20건 아침 루틴을 수작업 1시간 → **5분 이내**
- 차별점: **"변동 감지"** (전일 스냅샷 비교) + **선적 마스터 테이블** + **선명 → 한국어 연안 국가 자동 라벨링** (예: `"시에라리온 앞바다 (Freetown 인근)"`)

---

## Tech Stack

- Python **3.11** (uv 관리, `.python-version` 고정)
- **Playwright ≥1.58** (async API 전용) + Chromium
- **Streamlit ≥1.56** (`st.data_editor`, `st.dialog`, `st.popover` 사용)
- **SQLite** (로컬 파일 `~/.bl-eta/bl_eta.db`, 커밋 금지)
- **pandas ≥3.0 + openpyxl ≥3.1** (xlsx I/O)
- **reverse-geocoder ≥1.5** (오프라인 GeoNames cities1000 → 좌표→국가코드)
- 패키지 관리: **uv**

## Run Commands

```bash
uv sync
uv run playwright install chromium
uv run streamlit run app.py                        # http://localhost:8501
uv run python -m bl_eta.tracker <BL_NO> [--headed] # 단일 BL 조회 CLI
uv run python -m bl_eta.vesselfinder "<VESSEL>"    # 단일 선명 위치 조회 CLI
```

---

## Project Structure

```
ship/
├── app.py                    # Streamlit 진입점 (빠른조회 + 선적 마스터)
├── bl_eta/
│   ├── tracker.py            # track-trace.com 병렬 ETA 조회 (track_many)
│   ├── parser.py             # 부산/인천 ETA 파서 (선사별 분기)
│   ├── vesselfinder.py       # VesselFinder 병렬 위치 조회 (track_many_locations)
│   ├── db.py                 # SQLite CRUD (eta_history + shipments)
│   └── export.py             # xlsx/csv I/O + shipments 업로드 파싱
├── docs/carrier-samples.md   # 선사별 HTML 구조 샘플
└── pyproject.toml
```

---

## Rules

### 코드 규칙
- **Playwright는 async API만** 사용. sync API 금지.
- **DB 접근은 반드시 `bl_eta/db.py` 경유.** 다른 모듈에서 `import sqlite3` 금지.
- **ETA 파싱은 `bl_eta/parser.py`에 격리.** 선사별 분기는 여기서만.
- **위치 파싱은 `bl_eta/vesselfinder.py`에 격리.** VesselFinder 특화 로직(meta description 정규식, `_CC_KO` 국가명 맵)은 이 모듈에서만.
- **항구명 매칭**: 소문자 변환 후 `["busan","pusan","incheon"]` 부분 매칭.
- **ETA 정규화**: ISO `YYYY-MM-DD`. 파싱 실패 시 `None`.
- 여러 항구 Row 매칭 시 **가장 늦은 ETA** 선택.

### 동시성
- 기본 `asyncio.Semaphore(5)`, 사이드바 1~10. 403/429 시 즉시 축소.
- **병렬 패턴**: 단일 `browser` 공유 + **단위(BL/선명)마다 별도 `BrowserContext`**. 결과 인덱스 보존. 진행률은 `on_progress(done,total,key,rec)` 콜백. `tracker.track_many`, `vesselfinder.track_many_locations`가 동일 구조.
- **Streamlit ↔ asyncio 브릿지**: `threading.Thread` 내부에서 `asyncio.run(...)`. 메인 쓰레드는 `state["done"]` polling으로 `st.progress` 갱신.

### UI 레이아웃 (`app.py`)
- **우상단 `:material/settings:` popover**: Headed 토글(**기본 ON**, Maersk headless 감지 회피), 동시성 슬라이더, DB 초기화(`eta_history`만), DB 내역 expander.
- **1. BL 조회**: text_area + `조회 시작`. 결과 테이블·CSV/xlsx 다운로드. `st.session_state["quick_run"]`에 캐시.
- **2. 선박 자동화 관리양식 (선적 마스터)** — `st.data_editor` (num_rows="fixed").
  - 좌→우 컬럼: `선택` · 제련소 · 출항지 · 선사 · **선명** · BL · 공급물량(톤) · 최초출항일 · 국내 도착일 · 전일 대비 변동 · **화물 위치**
  - 파생 컬럼(disabled): 국내 도착일·전일 대비 변동. 화물 위치는 편집 가능하지만 새로고침 시 자동 덮어씀.
  - 빈 값은 빈칸 렌더 (`None`/`"None"` 금지). `공급물량(톤)`은 `pd.to_numeric(errors="coerce")`로 float64.
  - 헤더 우측 아이콘: 행 추가 / 선택 삭제 / 엑셀 업로드 popover / 엑셀 다운로드. `help=` 툴팁 필수.
  - 하단 버튼: **테이블 저장** / **ETA/위치 새로고침** (primary).
  - 새로고침 흐름 (2단계):
    ①편집 저장 → ②**BL→ETA** `track_many` → `run_master_refresh_inplace`가 data_editor 슬롯을 행별 진행 테이블로 인플레이스 교체 → ③**선명→위치** `track_many_locations` → `run_location_refresh_inplace`가 같은 슬롯을 재교체하며 `위치 진행` 컬럼에 `<국가 앞바다 (도시 인근)>` / `✗ 없음` / `✗ 실패` 표시 → ④`db.update_cargo_locations(mapping)` 일괄 UPDATE → ⑤`_refresh_done` 세션 저장 후 `st.rerun()` → ⑥상단 `@st.dialog`로 ETA·위치 각각의 ok/nf/failed 요약.

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
    cargo_location TEXT                   -- "<국가> 앞바다 (<도시> 인근)" 자동 라벨
);
```

### 전일 대비 변동 (`app.py:_delta_str`)
- **비교 기준**: `db.get_previous(bl)` = **KST 오늘 이전** 최신 1건 (`DATE(queried_at,'+9 hours') < DATE('now','+9 hours')`). 당일 재조회 기록은 prev 후보에서 제외.
- **현재 ETA**: `db.get_latest_for_bl(bl)` (날짜 필터 없음).
- **표기**: `""`(curr 없음) / `"신규"`(prev 없음) / `"변동없음"` / `"D±n"` / `""`(파싱 실패).

### VesselFinder 위치 파이프라인 (`bl_eta/vesselfinder.py`)
- 흐름: 선명 → 검색 URL `/vessels?name=...` → `<tr>` 중 `has-text("container ship")` 첫 행 → `/vessels/details/<IMO>` → `Track on Map` 클릭 → `/?imo=<IMO>` → HTML `<meta name="description">` 정규식으로 `lat N/S, lon E/W` 파싱 → `reverse_geocoder.search([(lat,lon)])` → `cc` → `_CC_KO[cc]`(한국어 국가명) + `name`(도시) → `"<국가> 앞바다 (<도시> 인근)"`.
- 좌표 파싱 실패 시 `~/.bl-eta/vf-map-dump.html`, 검색결과 miss 시 `~/.bl-eta/vf-search-dump.html` 자동 덤프.
- `_CC_KO`에 없는 ISO2는 코드 그대로 폴백. 신규 국가는 맵에 추가.

### Export (`bl_eta/export.py`)
- **빠른조회**: `to_csv(df)` (UTF-8 BOM) / `to_xlsx(df)` (헤더 굵게, 컬럼 폭 auto 8~40, A2 freeze). 파일명 `bl_eta_YYYY-MM-DD.{csv,xlsx}`.
- **마스터**: `shipments_to_xlsx(df)` / `shipments_from_xlsx(bytes) -> list[dict]`. 한글 헤더 ↔ DB 컬럼 매핑은 `SHIPMENT_COLS` 상수. 업로드는 전체 교체(`shipments_replace`). 빈 BL 행 스킵.

### 날짜 입력 정규화 (`app.py`)
- `_parse_date`: `%Y-%m-%d` / `%Y.%m.%d` / `%Y/%m/%d` / `%Y%m%d` 순서로 시도.
- `_date_to_iso`: 저장 직전 `최초출항일`을 `YYYY-MM-DD`로 정규화.

### 실패 처리
- ETA: 부산/인천 미발견 → `status="not_found"`. 접속 실패 → `status="failed"`. 둘 다 `eta=NULL`.
- 위치: 검색결과 0건 → `not_found`. 좌표 파싱/네트워크 실패 → `failed`. DB `cargo_location`은 **덮어쓰지 않음**(ok인 것만 UPDATE).
- **실패 건도 테이블·export에 포함**.

---

## 주의사항 (plan.md [RISK] 전환)

- [RISK] **track-trace.com Bot 차단** — Headed 기본 ON으로 회피 중.
- [RISK] **선사별 HTML 구조 차이** — 파서 분기 유지. 신규 선사는 `docs/carrier-samples.md`에 샘플 기록.
- [RISK] **병렬 Rate limit** — 기본 5, 403/429 시 축소.
- [RISK] **track-trace 커버리지 미확정** — 미지원 선사는 `not_found`. ESL/Wanhai/Cordelia는 수기 병행.
- [RISK] **MarineTraffic/Google 봇 차단** — 초기 시도 시 Cloudflare/reCAPTCHA로 차단됨. 현재 VesselFinder로 우회. VF가 Cloudflare 도입 시 `launch_persistent_context` + 실제 Chrome 프로필로 즉시 피벗.
- [RISK] **VesselFinder 좌표 정밀도** — meta description의 lat/lon이 정수 단위. 연안 국가 판별엔 충분하나 근접 도시명 정확도는 낮을 수 있음.
- [RISK] **동명이선(同名異船)** — 같은 이름의 비컨테이너 선박이 먼저 잡힐 가능성. 현재는 `Container Ship` 타입 첫 행으로 좁힘. IMO 검증 필요 시 추가.

---

## 금지사항

- **상용 배포 금지** — 로컬 단독 전제
- **조회 결과 외부 API 전송 금지** — 사내 BL 정보
- **Playwright sync API 금지**
- **`bl_eta.db` 커밋 금지** (사용자 홈에만 존재)
- **BL 번호 코드/테스트/커밋 메시지 하드코딩 금지** — 샘플은 `docs/carrier-samples.md`에 마스킹

---

## Phase 진행 상황

`todo.md`를 단일 출처로 삼는다. 현재: **Phase 4 + 선적 마스터 UI 개편 + VesselFinder 위치 자동화 구현 완료**.
