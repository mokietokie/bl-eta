# Todo: bl-eta

> 기반: plan.md v1.0 | 최종 업데이트: 2026-04-22
> 현재 진행: Phase 3 — SQLite 저장 + 변동 감지 (구현 완료, 연속 조회 검증 대기)

---

## 전체 진행 현황

| Phase | 목표 | 상태 | 완료율 | 시작 | 완료 |
|-------|------|------|--------|------|------|
| Phase 0 | 프로젝트 세팅 | 완료 | 6/6 | 2026-04-21 19:12 | 2026-04-21 19:17 |
| Phase 1 | track-trace PoC (BL 1건 조회+파싱) | 완료 | 5/5 | 2026-04-21 | 2026-04-22 |
| Phase 2 | 병렬 조회 + Streamlit UI | 완료 | 6/6 · Gate 통과 | 2026-04-22 | 2026-04-22 |
| Phase 3 | SQLite 저장 + 변동 감지 | 진행 | 0/4 | 2026-04-22 | - |
| Phase 4 | CSV/엑셀 export + 마감 | 대기 | 0/4 | - | - |

> 완료 / 진행중 / 대기 / 블로킹

---

## Phase 0: 프로젝트 세팅
> 목표: uv 기반 Python 프로젝트 + Streamlit 빈 앱 실행 확인
> 산출물: `uv run streamlit run app.py` → 빈 페이지 로딩 성공
> 시작: 2026-04-21 19:12 | 완료: 2026-04-21 19:17
> plan.md 참조: Section 4 (기술 스택), Section 9 (CLAUDE.md 초기값)

**이 Phase 주의사항**
- Playwright 설치 후 `uv run playwright install chromium` 반드시 실행 (브라우저 바이너리 별도 다운로드 필요)
- Python 3.11+ 필수 (Playwright async API 호환)

**시작 전 체크**
- [x] `@plan.md` 로드
- [x] 코어 md 필요 여부: **불필요** (세팅만)

**구현 태스크**
- [x] `uv init` (현재 디렉토리 `ship/`에서 `--name bl-eta --python 3.11`) + 가상환경 생성 _(19:13)_
- [x] 의존성 추가: `uv add streamlit playwright pandas openpyxl` _(19:14)_
- [x] `uv run playwright install chromium` 실행 → Chromium 145 + FFmpeg + headless-shell 설치 _(19:15)_
- [x] 프로젝트 구조 생성: `app.py`, `bl_eta/{__init__,tracker,parser,db,export}.py` 빈 파일, `.gitignore`(bl_eta.db 포함, 기본 `main.py` 제거) _(19:16)_
- [x] 빈 `app.py`에 `st.title("bl-eta")` 한 줄 → `uv run streamlit run app.py` 실행 확인 (health ok) _(19:16)_
- [x] `CLAUDE.md` 생성 (plan.md Section 9 복사 + 실제 버전/경로/명령 보완) _(19:17)_

**Gate**
- [x] 로컬 Streamlit 정상 로딩 확인 (http://localhost:8501/_stcore/health → `ok`)
- [x] CLAUDE.md 기술 스택 + 규칙 명시 완료
- [x] 인수인계 노트 작성 (Phase 0 → 1) — 아래 "인수인계 노트" 참조
- [x] Git 커밋: `chore: Phase 0 — 프로젝트 세팅` (5c8b46f, origin/main push 완료)

---

## Phase 1: track-trace PoC (BL 1건 조회+파싱)
> 목표: **최대 리스크 검증 Phase** — Bot 차단 유무, 선사별 HTML 구조 실측, 항구명 표기 수집
> 산출물: `python -m bl_eta.tracker <BL>` CLI 스크립트 + 선사 3~5건 샘플 HTML 구조 문서
> 시작: - | 완료: -
> plan.md 참조: Section 7.1 (ETA 파싱 동작 규칙)

**이 Phase 주의사항 (plan.md [RISK])**
- [RISK] **Bot 차단 가능성 (Cloudflare 등)** → 차단 확인되면 stealth 옵션/User-Agent 우회 시도, 그래도 실패 시 스택/소스 재검토
- [RISK] **선사별 HTML 구조 차이** → 실측 샘플 3~5건으로 `docs/carrier-samples.md` 작성 후 파서 분기 설계
- [RISK] **항구명 표기 다양성 (Busan/BUSAN/Pusan)** → 소문자 변환 후 `["busan","pusan","incheon"]` 부분 매칭
- [RISK] **track-trace 커버리지 미확정** → 미지원 선사 출력 패턴도 관찰해서 `status="not_found"` 조건 정의

**시작 전 체크**
- [x] `/clear` 후 `@plan.md` `@CLAUDE.md` `@todo.md` 로드
- [x] 사용자에게 실제 BL 샘플 3~5건 요청 (Maersk / KMTC / HMM 확보)
- [x] 코어 md 필요 여부: **필요** → `docs/carrier-samples.md` (선사별 HTML 구조 문서)

**구현 태스크**
- [x] Playwright async로 track-trace.com 접속 + BL 입력 + 제출 + 렌더링 대기 (max 30s) 스크립트 작성 → `bl_eta/tracker.py`
- [x] **샘플 BL 3건 실측** (Maersk / KMTC / HMM) → `docs/carrier-samples.md` 작성 + Bot 차단 결론 기록
- [x] `bl_eta/parser.py` 구현: 항구 소문자 매칭, ETA `YYYY-MM-DD` 정규화, 라벨 whitelist/blacklist 기반 분류 + 가장 늦은 ETA 선택
- [x] 파싱 실패 분기: `not_found`(항구 미발견) / `failed`(접속·로딩 실패)
- [x] CLI 진입점: `uv run python -m bl_eta.tracker <BL> [--headed] [--dump DIR]` 동작 확인

**Gate**
- [x] 샘플 BL 3건 실측 (Maersk=ok / KMTC=not_found(Akamai) / HMM=ok)
- [x] Bot 차단 여부 결론 기록 (`docs/carrier-samples.md` 상단 표)
- [x] CLAUDE.md 업데이트 (파서 분기 규칙, 실측 선사 목록)
- [x] 인수인계 노트 작성 (Phase 1 → 2) — 아래 섹션
- [ ] Git 커밋: `feat: Phase 1 — track-trace PoC 파서 구현` — Phase 2와 합쳐 커밋 예정

---

## Phase 2: 병렬 조회 + Streamlit UI
> 목표: BL 다중 입력 → 병렬 조회 → 결과 테이블. 진행률·Headless 토글까지.
> 산출물: 사용자가 실전 사용 가능한 UI (DB·비교 없이 단발 조회)
> 시작: - | 완료: -
> plan.md 참조: Section 3 (P0 대부분), Section 5 (화면 구성)

**이 Phase 주의사항 (plan.md [RISK])**
- [RISK] **Rate limit 미확인** → `asyncio.Semaphore(5)` 기본값. 실측 중 403/429 발생 시 사이드바 슬라이더로 즉시 축소

**시작 전 체크**
- [x] `/clear` 후 `@plan.md` `@CLAUDE.md` `@todo.md` `@docs/carrier-samples.md` 로드
- [x] 코어 md 필요 여부: **불필요** (Section 5 화면 구성으로 충분)

**구현 태스크**
- [x] `bl_eta/tracker.py`에 병렬 조회 함수 추가: `track_many()` = 단일 browser 공유 + BL별 context + `asyncio.Semaphore(N)` 롤링 큐 + `on_progress` 콜백 + 입력 순서 보존
- [x] `app.py` 사이드바: Headed 토글(**기본 ON** — Maersk headless 감지 회피), 동시성 슬라이더(1~10, 기본 5), DB 초기화 버튼(disabled placeholder)
- [x] `app.py` 메인: BL 입력 Textarea(줄바꿈 구분, 중복 제거) + `[조회 시작]` 버튼(빈 입력 시 disabled)
- [x] 진행률 표시: `threading.Thread`에서 `asyncio.run` → main이 `state["done"]` poll → `st.progress` + `st.empty()` 카운터
- [x] 결과 DataFrame 렌더링: BL / 선사 / 항구 / ETA / status 컬럼 + ok/not_found/failed 요약 배너 + raw_text expander
- [x] Headless=False 모드에서 브라우저 화면 실제로 뜨는지 확인 (사용자 실측 대기)

**Gate**
- [x] BL 병렬 조회 테스트 통과 (3개사 Maersk/KMTC/HMM 기준)
- [x] Headless/Headed 모드 둘 다 정상 동작
- [x] CLAUDE.md 업데이트 (병렬 패턴, UI 컴포넌트 배치)
- [x] 인수인계 노트 작성 (Phase 2 → 3)
- [ ] Git 커밋: `feat: Phase 2 — 병렬 조회 + Streamlit UI` — Phase 3과 합쳐 커밋 예정

---

## Phase 3: SQLite 저장 + 변동 감지
> 목표: 매 조회 시 DB 저장 + 전일 대비 변동 BL 하이라이트 (서비스 차별 기능)
> 산출물: CHANGED/NEW/UNCHANGED 3분류 + 변동 BL 상단 정렬
> 시작: - | 완료: -
> plan.md 참조: Section 6 (DB 스키마), Section 7.2 (변동 감지 동작 규칙)

**이 Phase 주의사항 (plan.md [RISK])**
- [RISK] **"어제"의 정의** → MVP는 직전 `queried_at` 1건 기준으로 비교 (당일 재조회 시에도). 전일자 기준 전환은 Post-MVP.
- [RISK] **ETA 변동 빈도 미측정** → 하이라이트 피로도는 1주 사용 후 조정 (색상 톤·정렬 순서)

**시작 전 체크**
- [x] `/clear` 후 `@plan.md` `@CLAUDE.md` `@todo.md` 로드
- [x] 코어 md 필요 여부: **불필요** (plan.md Section 6·7.2로 충분)

**구현 태스크**
- [x] `bl_eta/db.py` 구현: `init_db()` / `save_record()` / `get_previous()` / `reset()` / `compare()` — sqlite3 Row 반환, 쓰레드 안전(연결 per call)
- [x] 조회 파이프라인(`app.py`)에 연결: 각 BL마다 `get_previous(bl) → compare(prev, r) → save_record(r)` 순서
- [x] 변동 분류 `compare(prev, curr)` — prev None=NEW / eta 동일=UNCHANGED / 그 외=CHANGED. 이전 ETA는 DataFrame 컬럼으로 병기
- [x] DataFrame 하이라이트: `Styler.apply`로 CHANGED=빨강·굵게 / NEW=파랑 / UNCHANGED=회색. `change` 컬럼 기준 CHANGED→NEW→UNCHANGED 정렬

**Gate**
- [ ] BL을 2회 연속 조회하여 UNCHANGED 검증, ETA 수기 변조 후 CHANGED 검증
- [ ] 사이드바 "DB 초기화" 버튼 실제 동작 확인
- [ ] CLAUDE.md 업데이트 (DB 스키마 최종본, 변동 분류 규칙)
- [ ] 인수인계 노트 작성 (Phase 3 → 4)
- [ ] Git 커밋: `feat: Phase 3 — SQLite 저장 + 변동 감지 하이라이트`

---

## Phase 4: CSV/엑셀 export + 마감
> 목표: 고객사 이메일 첨부 가능한 export 완성 + MVP 성공 기준 최종 검증
> 산출물: 완성된 MVP + README
> 시작: - | 완료: -
> plan.md 참조: Section 1 (성공 기준), Section 3 (P0 export, P1 실패 플래그)

**이 Phase 주의사항**
- 실패 BL은 export에도 포함시킬 것 (고객사가 "조회 안 된 BL"도 알아야 함)
- xlsx 컬럼 너비 자동 조정 — 좁으면 ETA 날짜가 잘림

**시작 전 체크**
- [ ] `/clear` 후 `@plan.md` `@CLAUDE.md` `@todo.md` 로드
- [ ] 코어 md 필요 여부: **불필요**

**구현 태스크**
- [ ] `bl_eta/export.py` 구현: `to_csv(df) → bytes`, `to_xlsx(df) → bytes` (openpyxl, 헤더 굵게, 컬럼 폭 auto) _(HH:mm)_
- [ ] `app.py`에 `st.download_button` 2개 추가 (CSV / 엑셀) + 파일명 `bl_eta_YYYY-MM-DD.{csv,xlsx}` _(HH:mm)_
- [ ] 에러 케이스 UX 정리: 빈 입력 경고, 조회 중 버튼 비활성화, 실패 BL 개수 요약 배너 _(HH:mm)_
- [ ] README.md 작성: 설치·실행·일상 사용법·트러블슈팅(선사 파싱 실패 시 대응) _(HH:mm)_

**Gate (= MVP 성공 기준 최종 검증)**
- [ ] BL 10~20건 실제 조회 **5분 이내** 완료 측정
- [ ] 전일 대비 변동 BL 시각 하이라이트 + CHANGED 건 상단 정렬 확인
- [ ] Export 파일을 고객사 이메일 첨부 형식으로 열어보기 (Excel/Numbers)
- [ ] CLAUDE.md 최종 업데이트 (모든 결정사항 반영)
- [ ] Git 커밋: `feat: Phase 4 — export + MVP 완료`

---

## 블로킹 이슈

> 막히는 것 기록. 해결 후 삭제.

(없음)

---

## 인수인계 노트

> `/clear` 후에도 흐름이 끊기지 않도록. Phase 완료 시 작성.

**Phase 0 → 1** _(2026-04-21 19:17)_
- 환경: Python 3.11.15 (`.python-version`) + uv 0.10.12, venv `.venv/`. `uv sync`로 재현.
- 설치된 버전: streamlit 1.56.0 / playwright 1.58.0 / pandas 3.0.2 / openpyxl 3.1.5. Chromium 145.0.7632.6 + headless-shell + FFmpeg는 `~/Library/Caches/ms-playwright/`에 설치됨(프로젝트 외부).
- 구조: `app.py`(st.title만), `bl_eta/{__init__,tracker,parser,db,export}.py` 모두 빈 파일. `docs/` 폴더는 Phase 1에서 생성 예정.
- `.gitignore`: `bl_eta.db`, `.venv`, `__pycache__`, `.DS_Store`, IDE 폴더. `main.py`(uv init 기본 샘플)는 삭제함.
- 실행 확인: `uv run streamlit run app.py --server.headless true` → `/_stcore/health` = `ok`.
- **Phase 1 시작 전 필요한 것**: 실제 BL 샘플 **3~5건**(서로 다른 선사 섞어서). 사용자에게 요청 필요.
- **Phase 1 최우선 검증**: track-trace.com Bot 차단 유무. 차단 시 stealth/UA 우회 → 그래도 실패면 스택/소스 재검토 (plan.md Section 8 단서).
- 커밋 메시지 컨벤션: Phase별로 1커밋 (`chore:` 세팅 / `feat:` 기능). 커밋은 사용자 승인 후 진행.

**Phase 1 → 2** _(2026-04-22)_
- **Bot 차단 결론** (`docs/carrier-samples.md`):
  - track-trace.com: 차단 없음 (form POST + iframe 정상)
  - Maersk: **headless 감지** → Headed 필수
  - KMTC: Akamai Access Denied — track-trace 경로로 불가, `status="not_found"` 처리
  - HMM: 차단 없음. 단 iframe X-Frame-Options 차단 → outer 페이지 `Click here to show HMM results without frame` 링크로 새 탭 fallback
- **선사별 tracker 분기**: `CARRIERS_USE_FULLSCREEN_LINK = ("HMM",)`, `_handle_carrier_iframe`에서 `ekmtc.com` 감지 시 `_kmtc_resubmit` (실효는 없지만 구조 유지).
- **파서 라벨 분류** (`bl_eta/parser.py`): 항구 키워드 ±500자 창 → 각 날짜를 backward/forward 200자 내 whitelist(arrival/arrived/eta/etb) vs blacklist(departure/discharge/gate in·out/last movement/container returned/empty container/provided by 등) 최근접 라벨로 keep/drop. HMM 함정 `Rail ETD/ETA` 헤더 → `eta` 패턴에 regex 경계 `(?<![a-z/])eta(?![a-z/])` 적용해 배제.
- **자동화 흔적 제거**: `navigator.webdriver=undefined`, `languages=['en-US','en']`, `plugins=[1..5]` init script. 쿠키 배너 "Essential only" 자동 클릭.
- **Phase 2 착수 조건**: 위 모두 반영된 상태. 단일 `track()`과 병렬 `track_many()` 분리 필요 → Phase 2에서 완료.

**Phase 2 → 3** _(초안, 실측 수치 반영 전)_
- **병렬 구조**: `bl_eta/tracker.track_many(bl_list, *, headless, concurrency, dump_path, on_progress)`. 단일 playwright/browser 공유 + BL별 `BrowserContext` 격리(HMM fullscreen 새 탭용). `asyncio.Semaphore` 롤링 큐 — 빈 슬롯 생길 때마다 다음 BL 진입 (배치 X). 결과는 입력 인덱스 보존.
- **UI ↔ asyncio 브릿지**: Streamlit 메인 루프와 충돌 피하려 `threading.Thread` 내부에서 `asyncio.run`. main은 `state["done"]` poll(0.3s)로 `st.progress` 갱신.
- **사이드바 기본값**: Headed ON (Maersk 커버), 동시성 5 (Rate limit 미확인 안전값).
- **Phase 3 DB 연결 지점** (미구현 placeholder):
  - `app.py` 사이드바 `DB 초기화` 버튼 (`disabled=True` 해제 + `db.reset()` 연결)
  - `run_sync()` 조회 완료 직후 `db.save_record(rec)` 루프 추가
  - DataFrame 렌더 전에 `db.get_previous(bl)` 비교 → `NEW/UNCHANGED/CHANGED` 컬럼 생성, Styler 적용
- **실측 대기 항목** (Gate 2건):
  - BL 10~20건 5분 이내 완료 측정
  - Headed/Headless 모드 모두 정상 여부 (Maersk만 Headless에서 not_found 예상)
- **경고**: Streamlit `ScriptRunContext` WARNING이 bare `python -c "import app"`에서 다량 찍히지만 `streamlit run`에서는 정상. 무시.

**Phase 3 → 4** _(작성 전)_
