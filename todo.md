# Todo: bl-eta

> 기반: plan.md v1.0 | 최종 업데이트: 2026-04-21 19:17
> 현재 진행: Phase 1 — track-trace PoC (대기, 샘플 BL 수집 필요)

---

## 전체 진행 현황

| Phase | 목표 | 상태 | 완료율 | 시작 | 완료 |
|-------|------|------|--------|------|------|
| Phase 0 | 프로젝트 세팅 | 완료 | 6/6 | 2026-04-21 19:12 | 2026-04-21 19:17 |
| Phase 1 | track-trace PoC (BL 1건 조회+파싱) | 대기 | 0/5 | - | - |
| Phase 2 | 병렬 조회 + Streamlit UI | 대기 | 0/6 | - | - |
| Phase 3 | SQLite 저장 + 변동 감지 | 대기 | 0/4 | - | - |
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
- [ ] Git 커밋: `chore: Phase 0 — 프로젝트 세팅`

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
- [ ] `/clear` 후 `@plan.md` `@CLAUDE.md` `@todo.md` 로드
- [ ] 사용자에게 실제 BL 샘플 3~5건 요청 (서로 다른 선사 섞어서)
- [ ] 코어 md 필요 여부: **필요** → `docs/carrier-samples.md` (선사별 HTML 구조 문서)

**구현 태스크**
- [ ] Playwright async로 track-trace.com 접속 + BL 입력 + 제출 + 렌더링 대기 (max 30s) 스크립트 작성 → `bl_eta/tracker.py` _(HH:mm)_
- [ ] **샘플 BL 3~5건 실측** → HTML 구조·항구명 표기·ETA 위치 관찰 → `docs/carrier-samples.md` 작성 _(HH:mm)_
- [ ] `bl_eta/parser.py` 구현: 항구명 소문자 매칭(`busan/pusan/incheon`), ETA 정규화(`YYYY-MM-DD`), 여러 매칭 시 가장 늦은 ETA 선택 _(HH:mm)_
- [ ] 파싱 실패 분기: `not_found`(항구 미발견) / `failed`(접속·로딩 실패) _(HH:mm)_
- [ ] CLI 진입점: `python -m bl_eta.tracker <BL>` → dict 출력 확인 _(HH:mm)_

**Gate**
- [ ] 샘플 BL 3건 이상 파싱 성공 (ok/not_found/failed 분기 모두 재현)
- [ ] Bot 차단 여부 결론 기록 (`docs/carrier-samples.md` 상단)
- [ ] CLAUDE.md 업데이트 (파서 분기 규칙, 실측 선사 목록)
- [ ] 인수인계 노트 작성 (Phase 1 → 2)
- [ ] Git 커밋: `feat: Phase 1 — track-trace PoC 파서 구현`

---

## Phase 2: 병렬 조회 + Streamlit UI
> 목표: BL 다중 입력 → 병렬 조회 → 결과 테이블. 진행률·Headless 토글까지.
> 산출물: 사용자가 실전 사용 가능한 UI (DB·비교 없이 단발 조회)
> 시작: - | 완료: -
> plan.md 참조: Section 3 (P0 대부분), Section 5 (화면 구성)

**이 Phase 주의사항 (plan.md [RISK])**
- [RISK] **Rate limit 미확인** → `asyncio.Semaphore(5)` 기본값. 실측 중 403/429 발생 시 사이드바 슬라이더로 즉시 축소

**시작 전 체크**
- [ ] `/clear` 후 `@plan.md` `@CLAUDE.md` `@todo.md` `@docs/carrier-samples.md` 로드
- [ ] 코어 md 필요 여부: **불필요** (Section 5 화면 구성으로 충분)

**구현 태스크**
- [ ] `bl_eta/tracker.py`에 병렬 조회 함수 추가: `asyncio.gather` + `Semaphore(N)` (N은 인자) _(HH:mm)_
- [ ] `app.py` 사이드바: Headless 토글, 동시성 슬라이더(1~10, 기본 5), DB 초기화 버튼(자리만, Phase 3에서 연결) _(HH:mm)_
- [ ] `app.py` 메인: BL 입력 Textarea(줄바꿈 구분) + `[조회 시작]` 버튼 _(HH:mm)_
- [ ] 진행률 표시: `st.progress` + `st.empty()`로 "N/M 조회 중: {BL}" 실시간 갱신 _(HH:mm)_
- [ ] 결과 DataFrame 렌더링: BL / 선사 / 항구 / ETA / status 컬럼 — 실패 BL도 표시 (P1 "실패 플래그" 여기서 겸사) _(HH:mm)_
- [ ] Headless=False 모드에서 브라우저 화면 실제로 뜨는지 확인 _(HH:mm)_

**Gate**
- [ ] BL 10~20건 병렬 조회 성공 + 전체 소요 시간 기록 (성공 기준 "5분 이내" 검증)
- [ ] Headless/Headed 모드 둘 다 정상 동작
- [ ] CLAUDE.md 업데이트 (병렬 패턴, UI 컴포넌트 배치)
- [ ] 인수인계 노트 작성 (Phase 2 → 3)
- [ ] Git 커밋: `feat: Phase 2 — 병렬 조회 + Streamlit UI`

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
- [ ] `/clear` 후 `@plan.md` `@CLAUDE.md` `@todo.md` 로드
- [ ] 코어 md 필요 여부: **불필요** (plan.md Section 6·7.2로 충분)

**구현 태스크**
- [ ] `bl_eta/db.py` 구현: `init_db()`(CREATE TABLE + INDEX), `save_record(rec)`, `get_previous(bl_no)` → 직전 1건 반환 _(HH:mm)_
- [ ] 조회 파이프라인에 DB 저장 연결: 각 결과를 `eta_history`에 INSERT _(HH:mm)_
- [ ] 변동 분류 로직: `compare(prev, curr) → "NEW" | "UNCHANGED" | "CHANGED"` + 이전 ETA 병기 _(HH:mm)_
- [ ] DataFrame 하이라이트: `pandas.Styler`로 CHANGED=빨강 / NEW=파랑 / UNCHANGED=회색, CHANGED 상단 정렬 _(HH:mm)_

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

**Phase 1 → 2** _(작성 전)_
- Bot 차단 결론, 사용 가능 선사 목록, 파싱 성공률 기록 예정

**Phase 2 → 3** _(작성 전)_

**Phase 3 → 4** _(작성 전)_
