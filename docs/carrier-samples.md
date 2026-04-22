# Carrier Samples (Phase 1 실측)

> 작성: 2026-04-21 | 최종 업데이트: 2026-04-22 | 샘플 3건 실측 (Maersk / KMTC / HMM) | BL 번호는 마스킹 (CLAUDE.md 금지사항 준수)

---

## Bot 차단 결론

| 대상 | 결과 | 비고 |
|------|------|------|
| track-trace.com | **차단 없음** | form POST·iframe 로딩 정상 |
| Maersk (maersk.com) | **Headless 감지** | headless 실행 시 "No results found" 반환. **Headed 모드에서 정상 동작** |
| KMTC (ekmtc.com) | **Akamai Access Denied** | track-trace 자체도 "cannot integrate completely" 경고 |
| HMM (hmm21.com) | **차단 없음** | iframe 대신 새 탭 fallback (X-Frame-Options 차단). `Click here to show HMM results without frame` 링크 클릭 필요 |
| COSCO (elines.coscoshipping.com) | **차단 없음** | HMM과 동일한 fullscreen link fallback. track-trace가 BL prefix를 부분적으로 strip(`COSUS` → `S<digits>`)해 쿼리 파라미터가 잘못 전달되므로 **10자리 숫자로 URL 재작성 필수**. 실제 결과는 외부 페이지 안의 `iframe#scctCargoTracking` 내부에 렌더링 |

**결론**: Phase 2 Streamlit 사이드바 "Headless/Headed 토글"의 **기본값은 Headed로** 설정 필요 (Maersk 커버리지 확보 목적). 자동화 흔적 제거를 위한 init script(`navigator.webdriver=undefined` 등) 기본 주입.

---

## 구조: track-trace = iframe aggregator

- track-trace 결과 페이지 HTML에는 **선사명 + iframe src**만 존재
- 실제 ETA는 `<iframe class="track_res_frame" src="<carrier-site>/...">` 내부에 렌더링
- 파싱 대상은 **각 선사 사이트** — 선사별 분리 구현 필요
- 추출 경로:
  - 선사명: `wc-multi-track-tab[data-tab-active="true"] @data-text`
  - iframe src: `iframe.track_res_frame @src`

---

## 샘플 1: `MAEU26693***` (Maersk Line) — **파싱 성공**

| 항목 | 값 |
|------|-----|
| iframe src | `https://www.maersk.com/tracking/<9자리>` (MAEU prefix 제거) |
| 실행 모드 | **Headed 필수** (headless 감지 → "No results found" 반환) |
| 감지된 항구 | BUSAN (From: VISAKHAPATNAM) |
| 파싱된 ETA | `2026-04-25` (원본 "25 Apr 2026 03:00") |

**innerText 구조**:
- 상단 카드: `Bill of Lading number\n<9자리>\nFrom\n<출발항>\nTo\nBUSAN`
- 컨테이너 카드 (요약 뷰): `<컨테이너번호>\n|\n<타입>\nLast updated: ...\nEstimated arrival date\n25 Apr 2026 03:00\nLatest event\nVessel departure • <항구>, <국가> • <날짜>`
- Transport plan (전개 뷰): 항구별 섹션 `<항구>\n<터미널>\nVessel arrival (<선박>/<항차>)\n<날짜>`

**파싱 전략 (`bl_eta/parser.py`)**:
1. 항구 키워드 매칭: 소문자 변환 후 `busan/pusan/incheon` 단어 경계 매칭
2. ETA 후보 수집 (둘 다):
   - "Estimated arrival date" 라벨 뒤 `DD MMM YYYY`
   - 각 항구 키워드 **앞뒤 500자** 창 내 **모든** 날짜 (`DD MMM YYYY` / `YYYY.MM.DD` 등)
3. 후보 중 **가장 늦은 날짜** 선택 (plan.md 7.1)
4. 날짜 포맷: `%d %b %Y` / `%d %B %Y` → ISO `YYYY-MM-DD`

**부가 관찰**:
- Cookie 배너 ("Essential only" / "Allow all") 존재 — 데이터 로드 차단하지는 않으나 tracker가 "Essential only" 자동 클릭
- 다중 컨테이너 BL이면 컨테이너 카드가 N개 출력됨 (각자 동일 ETA) — 파서는 max 선택하므로 무관
- Container 번호(HASU/MRKU/...)는 화주용 컨테이너 ID — BL 번호와 별개. 현 파서는 이를 무시

## 샘플 2: `KMTCVTG00674**` (Korea Marine Transport) — **미지원 확정**

| 항목 | 값 |
|------|-----|
| iframe src | `https://www.ekmtc.com/index.html#/cargo-tracking` |
| iframe 렌더 | `Access Denied` (Akamai/edgesuite) |
| track-trace 경고 | "Please reenter the number … as we can not integrate Korea Marine Transport completely due to technical reasons" |

**상태**: track-trace 경로로는 조회 불가. MVP에서는 **`status="not_found"` 처리 + 수기 병행** (ESL/Wanhai/Cordelia와 동일 취급).

**track-trace 홈페이지에서 "Can not be completely integrated" 경고 아이콘이 달린 선사 목록** (수기 병행 후보):
Interasia Lines · Korea Marine Transport · Marfret · MSC · MOL ACE · Namsung · Nirint · OOCL · Pan Ocean · RCL · Samudera · 외.

## 샘플 3: `HDMUDOHA626081**` (HMM) — **파싱 성공**

| 항목 | 값 |
|------|-----|
| iframe src | `https://www.hmm21.com/...` (X-Frame-Options로 iframe 차단) |
| 실행 모드 | Headless 가능 (헤드리스 감지 없음) |
| Fallback 경로 | outer 결과 페이지의 `Click here to show HMM results without frame` 링크 → 새 탭 로딩 → 선사 사이트 innerText 수집 |
| 감지된 항구 | BUSAN, KOREA (From: MESAIEED, QATAR) |
| 파싱된 ETA | `2026-03-06` (원본 Arrival(ETB) `2026-03-06 06:47`) |

**innerText 구조 (HMM 자체 페이지)**:
- **Arrival(ETB) 테이블** (요약): `Origin / Loading Port / T/S Port / Discharging Port / Destination` 5열 × (Location / Terminal / Arrival(ETB) / Departure) 행. BUSAN 도착은 Discharging/Destination 컬럼의 Arrival(ETB) 값.
- **Vessel Movement 테이블**: 선박별 `Loading Port / Departure / Discharging Port / Arrival` 행. Arrival 컬럼에 도착일자.
- **Shipment Progress 타임라인**: `Date / Time / Location / Status Description / Mode` — "Vessel Arrival at POD", "Vessel Berthing at POD", "Vessel Discharged at POD", "Import Empty Container Returned" 등 이벤트별 dated row.

**파서 함정 (실측 수정 내역)**:
- `Shipment Progress` 상단 헤더에 `Rail ETD/ETA` 토큰이 있어 whitelist의 "eta"에 매칭 → 이후 `2026-03-09 Import Empty Container Returned` 행까지 keep되어 잘못된 ETA 선정됐음.
- 수정: `_LABEL_WHITELIST`의 "eta"/"etb"를 regex 경계 패턴(`(?<![a-z/])eta(?![a-z/])`)으로 변경해 `ETD/ETA`·`ETA/ETD` 결합 헤더 배제.
- Blacklist 확장 (HMM 전용 이벤트): `last movement`, `container returned`, `empty container`, `provided by` (페이지 타임스탬프 `Tracking results are provided by HMM ... : 2026-04-22` 오매칭 방지).

**Fallback 로직 (`bl_eta/tracker.py`)**:
- `CARRIERS_USE_FULLSCREEN_LINK = ("HMM",)` — 선사 탭이 HMM이면 iframe 대신 outer 페이지에서 "show ... results without frame" 링크 클릭 → 새 탭에서 선사 사이트 직접 렌더.
- 새 탭 `domcontentloaded` + `networkidle` + 3s 여유 대기로 SPA 렌더 보장.

## 샘플 4: `COSUS644284****` (COSCO SHIPPING Lines) — **파싱 성공**

| 항목 | 값 |
|------|-----|
| iframe src | `https://elines.coscoshipping.com/ebusiness/cargoTracking?...` (X-Frame-Options로 outer iframe 차단) |
| 실행 모드 | Headless 가능 (차단 없음) |
| Fallback 경로 | `Click here to show COSCO SHIPPING Lines results without frame` 링크 → 새 탭 → **쿼리 재작성** → 내부 `iframe#scctCargoTracking` innerText 수집 |
| 감지된 항구 | Incheon (POR: Mesaieed, QA → POD/FND: Inchon, KR) |
| 파싱된 ETA | `2026-04-28` (원본 Selected Service의 `Inchon ETA 2026-04-28 02:00:00 KST`) |

**track-trace 쿼리 전달 버그**:
- track-trace는 COSCO로 redirect할 때 URL에 `number=S6442845940`을 넣음 — `COSUS` 중 `COSU` 4글자만 strip한 결과. COSCO 사이트는 이 값으로 조회 시 **"No results found (ongoing shipments or completed shipments within the last 6 months)"** 반환.
- 해결: carrier 사이트 로드 후 URL 쿼리를 **BL의 순수 digit 부분**(`6442845940`, 10자리)로 재작성해 `goto()` 재 navigate.
- 플랫폼(Mac/Windows) 또는 UA 별로 prefix strip 동작이 달라질 수 있다는 보고가 있었음 — 방어적으로 항상 digit-only로 재작성.

**innerText 수집 위치 (이중 iframe 구조)**:
- 외부 페이지 `elines.coscoshipping.com/ebusiness/cargoTracking`은 COSCO 포털 chrome(네비게이션, 쿠키 배너)만 렌더.
- 실제 tracking 결과는 내부 `<iframe id="scctCargoTracking" src="…/scct/public/ct/base?...">`에서 렌더링 → 이 frame의 innerText를 채택해야 함.
- 쿠키 배너(`Allow All` / `Accept All`)를 닫아야 내부 iframe이 안정적으로 렌더됨 — outer page에 대해 `_dismiss_cookie_banner()` 호출 필요.

**innerText 구조 (scctCargoTracking 내부)**:
- 상단: `POR / First POL / Transshipment / Last POD / FND` 5단계 타임라인. 각 단계마다 `ATD` / `ATA` / `ETA` 라벨 + `YYYY-MM-DD HH:MM:SS TZ` 날짜.
- `Inchon ETA 2026-04-28 02:00:00 KST` 행이 목적항 ETA.
- Transport Detail 테이블: 다수 컨테이너(CSNU/OOLU/OOCU/...)별 `Terminal Transfer Arrival` 이벤트 (대부분 Shanghai 경유지).

**파서 주의**:
- 날짜 포맷 `YYYY-MM-DD`로 현행 `_DATE_NEAR_PORT` 패턴 매칭 가능 → parser 분기 불필요.
- Shanghai 컨테이너 이벤트는 Incheon window 밖에 있어 현재 규칙으로도 영향 없음.
- 라벨 `ETA`가 regex 경계 패턴으로 whitelist에 포함돼 있어 Incheon 직전 `ETA` 라벨 매칭 정상.

## 추가 실측: `tracker.py` `CARRIERS_USE_FULLSCREEN_LINK` 튜플

```python
CARRIERS_USE_FULLSCREEN_LINK = ("HMM", "COSCO")
```
- 선사 탭 이름 부분매칭: "COSCO SHIPPING Lines" 안에 "COSCO" 포함 → 매칭.
- COSCO 분기는 `_follow_fullscreen_link` 내부에서 호스트(`elines.coscoshipping.com`) 기준으로 URL 재작성 + 내부 iframe 선택.

---

## 미수집 (추가 샘플 필요)

- [ ] 경고 아이콘 없는 선사의 BL 샘플 (Evergreen/ONE/CMA CGM 등) — innerText 구조 확인, 파서 분기 여부 판단
- [ ] Incheon 도착 BL 샘플 — 현재 Busan만 검증됨
- [ ] 다중 항구 경유 BL — "가장 늦은 ETA 선택" 규칙 재확인용
