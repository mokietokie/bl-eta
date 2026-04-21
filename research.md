# Research: bl-eta

> 작성일: 2026-04-21 | 상태: Draft | 인터뷰 기반 작성

---

## 1. 문제 정의 (Why)

**핵심 문제**
전쟁 여파로 해상 선복(船腹) 스케줄이 타이트해지면서, 재고 여유 없이 입항 즉시 고객사로 납품되는 구조가 일상화되었다. 이 상황에서 선사가 공지하는 **최종 목적항 ETA가 하루 단위로 변동(D+1, D+2...)** 되는데, 이를 놓치면 고객사 생산라인 스톱 위기로 이어진다. 담당자가 매일 아침 BL을 수작업으로 일일이 조회·비교해야 하는 구조는 휴먼 에러와 시간 소모가 크다.

**현재 해결 방식 (As-Is)**
- 매일 오전, 트레이딩사업팀 담당자가 [www.track-trace.com/bol](https://www.track-trace.com/bol)에 BL 번호를 **하나씩 수동 입력**
- 결과 화면에서 부산(Busan) 또는 인천(Incheon) ETA를 육안으로 확인
- 엑셀 파일에 수기 업데이트 → 외부 고객사에 이메일 첨부 발송
- **약 1시간** 소요 (10~20건 기준)

**문제의 빈도 & 크기**
- 하루 평균 10~20건 BL 조회 (매일 발생)
- [가정] 담당자 1인 기준 연간 약 250영업일 × 1시간 = **250시간 수작업** 소모
- 라인스톱 사례는 아직 발생하지 않았으나, 선복 타이트 상황에서 **예방이 핵심 동기**
- [검증 필요] ETA 변동 발생 빈도 (전체 BL 중 몇 %가 일별로 변경되는지)

---

## 2. 타겟 유저

**Primary User**
- 트레이딩사업팀 실무자 본인 (현 BL 수작업 트래킹 담당)
- 매일 아침 출근 직후 BL 조회 루틴을 수행
- 엑셀·이메일 기반 고객 커뮤니케이션에 익숙
- Streamlit 로컬 실행 수준의 IT 환경 사용 가능

**Secondary Stakeholder (간접 수혜자)**
- 외부 거래처(고객사)의 자재/생산 담당자 — 갱신된 ETA 엑셀을 이메일로 수신

**User Goal**
- 매일 아침 **5분 이내**에 BL 10~20건의 부산/인천 ETA를 확인하고, **어제 대비 변동된 BL만 빠르게 식별**하여 고객사에 전달

**Pain Point**
- 1시간에 걸쳐 BL을 하나씩 사이트에 입력 → 반복 작업
- 변동 여부 비교도 수기 (엑셀 전일자와 눈으로 대조)
- 여러 선사 사이트가 혼재되어 있어 track-trace.com 한 곳으로도 못 끝남 (ESL, Wanhai, Cordelia 별도 조회 필요)

---

## 3. 시장 & 경쟁사

| 서비스 | 핵심 기능 | 한계 / 우리가 더 나은 점 |
|--------|-----------|----------------------|
| track-trace.com (기준 소스) | 다수 선사 BL 통합 조회 UI | 사람이 하나씩 입력해야 함, 어제/오늘 비교 기능 없음 |
| ShipsGo / SeaRates (대체 후보) | 통합 트래킹 + API | 유료 구독 전제 가능성, MVP 우선순위 낮음 |
| 선사 개별 사이트 (Maersk, CMA 등) | 가장 정확한 1차 소스 | 선사마다 UI/로그인/지역 포맷 제각각 → 통합 불가 |

**차별점 가설**
- [가정] track-trace.com을 **Playwright로 자동화**하여 "수동 조회 → 병렬 자동 조회 + 어제 대비 변동 하이라이트 + CSV/엑셀 export"를 한 번에 제공하는 **개인용 RPA 도구**. 상용 서비스가 아닌 내부 업무용이라 단순하고 빠르게 반복 루틴을 제거하는 것이 가치.
- **핵심은 "변동 감지"** — 단순 조회가 아닌, 전일 대비 달라진 BL을 놓치지 않고 잡아내는 것

---

## 4. 솔루션 가설

**핵심 아이디어**
Streamlit UI에 BL 번호 리스트를 입력하면, Playwright(async)가 track-trace.com에 **병렬 접속**하여 각 BL의 최종 부산/인천 ETA를 파싱한다. 결과를 SQLite에 저장하고, 전일 결과와 비교하여 변동된 BL을 하이라이트한다. 결과는 테이블 표시 + CSV/엑셀 export로 고객사 이메일 첨부에 바로 사용 가능.

**핵심 가치 제안**
- **1시간 → 5분** 수작업 시간 단축
- **ETA 변동 BL 누락 제로** → 생산라인 리스크 예방

**검증해야 할 핵심 가정**
- [검증 필요] track-trace.com이 Playwright 자동 접속을 차단하는지 (CAPTCHA, Cloudflare 등)
- [검증 필요] 조회 결과 HTML 구조가 선사별로 얼마나 다른지 → 부산/인천 ETA 파싱 로직의 안정성
- [검증 필요] 동시 병렬 조회 시 사이트가 허용하는 동시성 한계 (Rate limit)
- [검증 필요] 실제 사용하는 선사 중 track-trace 커버리지 (사용자 확인 예정)
- [가정] BL 1건당 조회 + 파싱 평균 10~15초, 병렬 5개 기준 20건 = 약 1분 예상

---

## 5. MVP 범위

**Must Have (없으면 MVP가 아님)**
1. **BL 다중 입력 + track-trace.com 병렬 자동 조회 + 부산/인천 ETA 파싱**
   → 핵심 자동화. 이게 없으면 프로젝트 자체가 성립 안 됨.
2. **어제 vs 오늘 결과 자동 비교 → 변동 BL 하이라이트**
   → 단순 조회가 아닌 변동 감지가 주목적이므로 필수.
3. **결과 테이블 화면 표시 + CSV/엑셀 export**
   → 고객사 이메일 첨부가 최종 산출물이므로 export 없이는 업무 루프가 안 닫힘.

**부가 기능 (Must Have 내 포함)**
- Headless/Headed 토글 (진행상황 확인용)
- 진행률 바 + BL별 실시간 상태 로그

**Out of Scope (이번엔 안 함)**
- **조회 이력 스택/추이 차트** → Post-MVP (사용자 명시 합의)
- **ESL / Wanhai / Cordelia 직접 조회 자동화** → MVP는 track-trace만. 해당 3개 선사는 수기 병행
- **매일 아침 자동 스케줄 실행 (cron)** → MVP는 사람이 버튼 누르는 구조
- **고객사별 자동 이메일 발송** → MVP는 CSV export 후 수동 첨부
- **로그인 / 다중 유저 / 권한 관리** → 본인 로컬 사용만 가정

**MVP 성공 기준**
- 10~20건 BL을 **5분 이내**에 조회·파싱·비교 완료
- 전일 대비 ETA 변동 BL을 **누락 없이 100% 감지**하여 시각적으로 구분 표시
- CSV/엑셀 export 파일이 **고객사 이메일 첨부 형식에 바로 사용 가능**

---

## 6. 기술 레퍼런스

**확정 스택**
- **언어**: Python 3.11+
- **자동화**: Playwright (async API, 병렬 조회용)
- **UI**: Streamlit (로컬 실행)
- **저장소**: SQLite (어제/오늘 비교용 이력 저장, 파일 1개로 관리 간편)
- **Export**: pandas + openpyxl (CSV / xlsx)
- **패키지 관리**: uv (설치 속도 + 2026년 현재 사실상 표준)
- **실행 모드**: Headless 기본, Streamlit 사이드바 토글로 Headed 전환 가능

**참고 서비스 / 레퍼런스**
- [www.track-trace.com/bol](https://www.track-trace.com/bol) — MVP 기준 조회 소스 (Bill of Lading Tracking 입력창)
- [www.emiratesline.com](https://www.emiratesline.com) — ESL 직접 조회 (Post-MVP)
- [www.wanhai.com/views/Main.xhtml](https://www.wanhai.com/views/Main.xhtml) — Wanhai 직접 조회 (Post-MVP)
- [cordelialine.com/digital-information](https://cordelialine.com/digital-information/) — Cordelia 직접 조회 (Post-MVP)
- Playwright 공식 문서 async API (`playwright.async_api`) — 병렬 조회 패턴
- Streamlit `st.progress`, `st.empty`, `st.toggle` — 실시간 상태 표시 컴포넌트

**기술적 리스크**
- [검증 필요] track-trace.com의 Bot 차단 정책 (Cloudflare, User-Agent 필터링 등)
- [검증 필요] 선사별 HTML 구조 차이로 인한 파싱 분기 복잡도 (머스크 / CMA / KCTC / 기타)
- [검증 필요] 부산/인천 항구명 매칭 로직 (Busan, BUSAN, PUSAN 등 표기 다양성)
- [가정] 동시 병렬 조회 5~10개가 안전선. 초과 시 Rate limit 대응 로직 필요

---

## 7. 다음 단계

- [ ] **plan.md 작성** (본 research 기반으로 PRD + TRD 통합 설계)
- [ ] [검증 필요] **1순위 검증**: track-trace.com에 Playwright로 실제 BL 1건 조회 PoC — Bot 차단 유무 및 파싱 가능성 확인
- [ ] [검증 필요] **선사 커버리지 리스트** 사용자 확인 (ESL/Wanhai/Cordelia 외에 track-trace로 커버 안 되는 선사 목록)
- [ ] [검증 필요] **부산/인천 표기 규칙** 샘플 확보 (선사별로 어떻게 출력되는지)
- [ ] MVP 성공 기준 중 "5분 이내" 수치 — PoC 결과 기준으로 현실적 수치로 재조정 가능
