# bl-eta

track-trace.com을 Playwright로 병렬 자동 조회해 BL의 **부산/인천 ETA**를 긁고, 전일 대비 변동을 감지·export하는 Streamlit 로컬 RPA.

- 대상: 트레이딩사업팀 실무자 로컬 1인
- 목표: BL 10~20건 아침 루틴을 수작업 1시간 → **5분 이내**
- 차별점: "조회"가 아니라 **"변동 감지"** (전일 스냅샷 대비 CHANGED/NEW/UNCHANGED 하이라이트)

---

## 설치

```bash
# 1) 의존성 동기화
uv sync

# 2) Playwright 브라우저 바이너리 (최초 1회)
uv run playwright install chromium
```

Python 3.11.15 (`.python-version` 고정), uv 0.10+.

## 실행

```bash
uv run streamlit run app.py
# → http://localhost:8501
```

단일 BL CLI 조회:

```bash
uv run python -m bl_eta.tracker <BL_NO> [--headed] [--dump DIR]
```

---

## 일상 사용법

1. BL 번호를 줄바꿈으로 구분해 입력창에 붙여넣기 (중복 자동 제거).
2. 사이드바 설정 확인:
   - **Headed 모드**: 기본 ON — Maersk는 headless 감지로 "No results found" 반환. 끄지 말 것.
   - **동시성**: 기본 5. 403/429가 보이면 즉시 낮추기.
3. `조회 시작` → 진행률 확인 → 결과 테이블.
4. **CHANGED 행이 테이블 상단**에 빨갛게 뜸. `변동일수` 컬럼의 `D+3`/`D-2`로 며칠 밀렸는지 확인.
5. `CSV 다운로드` / `엑셀 다운로드`로 고객사 이메일용 파일 생성.

### 결과 컬럼

| 컬럼 | 의미 |
|------|------|
| change | NEW(최초 조회) / UNCHANGED / CHANGED |
| 변동일수 | CHANGED일 때 `D±n` (ETA 차이 일수) |
| BL / 선사 / 항구 | 조회 결과 |
| 이전 ETA / ETA | 직전 스냅샷과 이번 조회 |
| status | ok / not_found / failed |

---

## 트러블슈팅

**Maersk가 모두 `not_found`로 나옴**
→ Headed 모드가 꺼져 있지 않은지 사이드바 확인. Maersk는 headless 브라우저를 감지해 결과를 비움.

**KMTC가 `not_found`로 나옴**
→ track-trace 경로에서 KMTC는 Akamai Access Denied로 막혀 있음 (알려진 한계). MVP에서는 수기 병행.

**HMM 결과가 안 보임**
→ HMM은 iframe X-Frame-Options 차단 때문에 outer 페이지의 `Click here to show HMM results without frame` 링크로 새 탭을 열어 캡처한다. Headed 모드에서 새 탭이 잠깐 뜨는 건 정상.

**403/429 에러**
→ 사이드바 동시성 슬라이더를 1~2로 낮추고 재시도.

**선사 파싱이 이상함 (Rail ETD를 ETA로 잡는 등)**
→ `docs/carrier-samples.md`에 해당 선사 HTML 패턴을 기록하고 `bl_eta/parser.py`에서 라벨 whitelist/blacklist 조정. `--dump DIR`로 raw HTML 덤프.

**DB 초기화하고 싶음**
→ 사이드바 `DB 초기화` 버튼 (되돌릴 수 없음). 파일 직접 삭제는 `bl_eta.db`.

---

## 프로젝트 구조

```
ship/
├── app.py              # Streamlit 진입점
├── bl_eta/
│   ├── tracker.py      # Playwright 조회 + 병렬 파이프라인
│   ├── parser.py       # 부산/인천 ETA 파서 (선사별 분기)
│   ├── db.py           # SQLite CRUD + 변동 비교
│   └── export.py       # CSV/xlsx export
├── docs/carrier-samples.md
├── bl_eta.db           # 로컬 SQLite (gitignore)
└── CLAUDE.md / plan.md / research.md / todo.md
```

자세한 설계·규칙은 [CLAUDE.md](./CLAUDE.md) 참조.
