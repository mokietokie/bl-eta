"""bl-eta Streamlit app — 선적 마스터 + 병렬 조회 + SQLite 변동 감지 + export."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from datetime import date, datetime

import pandas as pd
import streamlit as st

from bl_eta import db, export, tracker, vesselfinder

db.init_db()

st.set_page_config(page_title="bl-eta", layout="wide", initial_sidebar_state="collapsed")

_title_cols = st.columns([10, 1])
with _title_cols[0]:
    st.title("선박 ETA 자동화 시스템")
    st.caption("track-trace.com 병렬 BL 조회 — 부산/인천 ETA + 전일 대비 변동 감지")
with _title_cols[1]:
    _settings_popover = st.popover(":material/settings:", help="설정", use_container_width=True)


# ─── 새로고침 완료 모달 ─────────────────────────────────────────────────
if "_refresh_done" in st.session_state:
    _info = st.session_state["_refresh_done"]

    @st.dialog("새로고침 완료")
    def _done_dialog():
        st.markdown(f"**ETA {_info['n']}건** 갱신 완료")
        st.write(f"- ✓ 완료: {_info['ok']}")
        st.write(f"- ✗ 없음(not_found): {_info['nf']}")
        st.write(f"- ✗ 실패: {_info['failed']}")
        _bl_nf = _info.get("bl_nf_list") or []
        _bl_failed = _info.get("bl_failed_list") or []
        if _bl_nf or _bl_failed:
            with st.expander(f"실패 BL {len(_bl_nf) + len(_bl_failed)}건", expanded=True):
                for item in _bl_nf:
                    st.write(f"- `{item}` — 없음")
                for item in _bl_failed:
                    st.write(f"- `{item}` — 실패")
        if "loc_n" in _info:
            st.markdown(f"**위치 {_info['loc_n']}건** 갱신 완료")
            st.write(f"- ✓ 완료: {_info['loc_ok']}")
            st.write(f"- ✗ 없음: {_info['loc_nf']}")
            st.write(f"- ✗ 실패: {_info['loc_failed']}")
            if _info.get("loc_retried"):
                st.caption(f"↻ 재시도로 구제: {_info['loc_retried']}건")
            if _info.get("loc_imo_backfill"):
                st.caption(f"⊕ IMO 자동 백필: {_info['loc_imo_backfill']}행")
            _loc_nf = _info.get("loc_nf_list") or []
            _loc_failed = _info.get("loc_failed_list") or []
            if _loc_nf or _loc_failed:
                with st.expander(f"실패 선명 {len(_loc_nf) + len(_loc_failed)}건", expanded=True):
                    for item in _loc_nf:
                        st.write(f"- `{item}` — 없음")
                    for item in _loc_failed:
                        st.write(f"- `{item}` — 실패")
        if st.button("확인", type="primary", use_container_width=True):
            del st.session_state["_refresh_done"]
            st.rerun()

    _done_dialog()


# ─── 설정 (우상단 톱니바퀴 popover) ──────────────────────────────────────
with _settings_popover:
    st.header("설정")
    headed = st.toggle(
        "Headed 모드 (브라우저 창 표시)",
        value=True,
        help="Maersk는 headless 감지로 'No results found' 반환 — Headed 권장.",
    )
    concurrency = st.slider("동시성", min_value=1, max_value=10, value=5, step=1)
    st.divider()
    if st.button("DB 초기화", help="eta_history 전체 삭제 (되돌릴 수 없음)"):
        db.reset()
        st.success("DB 초기화 완료")
    st.caption(f"DB 파일: `{db.DB_PATH}`")

    with st.expander("DB 내역 (최근 100건)"):
        recent = db.get_recent(limit=100)
        if recent:
            st.caption(f"{len(recent)}건")
            st.dataframe(
                pd.DataFrame(recent),
                use_container_width=True,
                hide_index=True,
                height=320,
            )
        else:
            st.caption("아직 조회 기록이 없습니다.")


# ─── 공용 유틸 ───────────────────────────────────────────────────────────
def run_sync(bl_list: list[str], headless: bool, concurrency: int) -> list[dict]:
    """Streamlit은 동기 컨텍스트 → 별도 쓰레드에서 asyncio.run."""
    progress_bar = st.progress(0.0)
    status_slot = st.empty()
    total = len(bl_list)
    state = {"done": 0}

    def on_progress(done: int, total_: int, bl: str, rec: dict) -> None:
        state["done"] = done

    results_holder: dict[str, list[dict]] = {}
    err_holder: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            results_holder["r"] = asyncio.run(
                tracker.track_many(
                    bl_list,
                    headless=headless,
                    concurrency=concurrency,
                    on_progress=on_progress,
                )
            )
        except BaseException as e:
            err_holder["e"] = e

    th = threading.Thread(target=runner, daemon=True)
    th.start()
    while th.is_alive():
        done = state["done"]
        progress_bar.progress(done / total if total else 1.0)
        status_slot.text(f"{done}/{total} 조회 중…")
        th.join(timeout=0.3)
    done = state["done"]
    progress_bar.progress(1.0)
    status_slot.text(f"{done}/{total} 완료")

    if "e" in err_holder:
        raise err_holder["e"]
    return results_holder.get("r", [])


def _delta_str(prev_eta: str, curr_eta: str) -> str:
    """D±n (차이) / '변동없음' (동일) / '신규' (prev 없고 curr 있음) / '' (그 외)."""
    if not curr_eta:
        return ""
    if not prev_eta:
        return "신규"
    try:
        p = datetime.strptime(prev_eta, "%Y-%m-%d").date()
        c = datetime.strptime(curr_eta, "%Y-%m-%d").date()
    except ValueError:
        return ""
    d = (c - p).days
    return f"D{d:+d}" if d else "변동없음"


_REFRESH_STATUS_MAP = {"ok": "✓ 완료", "not_found": "✗ 없음", "failed": "✗ 실패"}


def run_master_refresh_inplace(slot, bl_list: list[str], headless: bool, concurrency: int) -> list[dict]:
    """새로고침 중 `slot`(데이터 에디터 자리)을 행별 진행 테이블로 교체하고,
    호출 위치(보통 버튼 아래)에 프로그레스 바와 `x/y 조회 중…` 캡션을 렌더.
    """
    base = build_master_df().drop(columns=[SELECT_HEADER]).copy()
    base.insert(0, "진행", "진행중")
    slot.dataframe(base, use_container_width=True, hide_index=True)

    progress_bar = st.progress(0.0)
    status_slot = st.empty()
    total = len(bl_list)
    state: dict = {"done": 0, "per_bl": {}}

    def on_progress(done: int, total_: int, bl: str, rec: dict) -> None:
        state["done"] = done
        state["per_bl"][bl] = _REFRESH_STATUS_MAP.get(rec.get("status", ""), "✓ 완료")

    results_holder: dict[str, list[dict]] = {}
    err_holder: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            results_holder["r"] = asyncio.run(
                tracker.track_many(
                    bl_list,
                    headless=headless,
                    concurrency=concurrency,
                    on_progress=on_progress,
                )
            )
        except BaseException as e:
            err_holder["e"] = e

    def redraw() -> None:
        for bl, status in state["per_bl"].items():
            base.loc[base["BL"] == bl, "진행"] = status
        slot.dataframe(base, use_container_width=True, hide_index=True)
        done = state["done"]
        progress_bar.progress(done / total if total else 1.0)
        status_slot.text(f"{done}/{total} 조회 중…")

    th = threading.Thread(target=runner, daemon=True)
    th.start()
    while th.is_alive():
        redraw()
        th.join(timeout=0.4)
    redraw()
    progress_bar.progress(1.0)
    status_slot.text(f"{state['done']}/{total} 완료")

    if "e" in err_holder:
        raise err_holder["e"]
    return results_holder.get("r", [])


def run_location_refresh_inplace(
    slot, items: list[dict], headless: bool, concurrency: int
) -> list[dict]:
    """items: [{"vessel": str, "imo": str|None, "prev_label": str|None}].

    실패한 항목은 prev_label이 있으면 `<라벨> (이번 조회 실패/없음)` 형태로 표시 —
    DB에는 이전 성공값이 남아있다는 사실을 사용자가 한눈에 보게 한다.
    """
    base = build_master_df().drop(columns=[SELECT_HEADER]).copy()
    base.insert(0, "위치 진행", "진행중")
    slot.dataframe(base, use_container_width=True, hide_index=True)

    progress_bar = st.progress(0.0)
    status_slot = st.empty()
    total = len(items)
    prev_map = {it["vessel"]: (it.get("prev_label") or "") for it in items}
    state: dict = {"done": 0, "per_vessel": {}}

    def on_progress(done: int, total_: int, vessel: str, rec: dict) -> None:
        state["done"] = done
        status = rec.get("status", "")
        label = rec.get("location_label")
        prev = prev_map.get(vessel) or ""
        if status == "ok" and label:
            state["per_vessel"][vessel] = label
        elif prev:
            tag = "이번 조회 실패" if status == "failed" else "이번 조회 없음"
            state["per_vessel"][vessel] = f"{prev} ({tag})"
        elif status == "not_found":
            state["per_vessel"][vessel] = "✗ 없음"
        else:
            state["per_vessel"][vessel] = "✗ 실패"

    results_holder: dict[str, list[dict]] = {}
    err_holder: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            results_holder["r"] = asyncio.run(
                vesselfinder.track_many_locations(
                    items,
                    headless=headless,
                    concurrency=concurrency,
                    on_progress=on_progress,
                )
            )
        except BaseException as e:
            err_holder["e"] = e

    def redraw() -> None:
        for v, s in state["per_vessel"].items():
            base.loc[base["선명"] == v, "위치 진행"] = s
        slot.dataframe(base, use_container_width=True, hide_index=True)
        done = state["done"]
        progress_bar.progress(done / total if total else 1.0)
        status_slot.text(f"위치 {done}/{total} 조회 중…")

    th = threading.Thread(target=runner, daemon=True)
    th.start()
    while th.is_alive():
        redraw()
        th.join(timeout=0.4)
    redraw()
    progress_bar.progress(1.0)
    status_slot.text(f"위치 {state['done']}/{total} 완료")

    if "e" in err_holder:
        raise err_holder["e"]
    return results_holder.get("r", [])


def parse_bls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        bl = line.strip()
        if bl and bl not in seen:
            seen.add(bl)
            out.append(bl)
    return out


# ─── 마스터 테이블 렌더 파이프라인 ────────────────────────────────────────
KO_HEADERS = [ko for _, ko in export.SHIPMENT_COLS]
DB_FIELDS = [db_ for db_, _ in export.SHIPMENT_COLS]
DERIVED_HEADERS = export.SHIPMENT_DERIVED_KO
SELECT_HEADER = "선택"
CARGO_HEADER = "화물 위치"
DISPLAY_HEADERS = [SELECT_HEADER] + KO_HEADERS + DERIVED_HEADERS + [CARGO_HEADER]


def _parse_date(s) -> date | None:
    """여러 포맷의 날짜 문자열을 date로 파싱. 실패 시 None."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def build_master_df() -> pd.DataFrame:
    """shipments + eta_history 파생 컬럼(국내 도착일·전일 대비 변동) 합친 DF."""
    rows = db.shipments_all()
    out_rows: list[dict] = []
    for r in rows:
        latest = db.get_latest_for_bl(r["bl_no"])
        prev = db.get_previous(r["bl_no"])
        curr_eta = (latest or {}).get("eta") or ""
        prev_eta = (prev or {}).get("eta") or ""
        display: dict = {SELECT_HEADER: False}
        for db_, ko in export.SHIPMENT_COLS:
            v = r.get(db_)
            if db_ == "initial_depart_date":
                d = _parse_date(v)
                v = d.strftime("%Y-%m-%d") if d else ""
            elif db_ == "supply_tons":
                v = float(v) if v is not None else float("nan")
            else:
                v = v if v is not None else ""
            display[ko] = v
        display["국내 도착일"] = curr_eta
        display["전일 대비 변동"] = _delta_str(prev_eta, curr_eta)
        display[CARGO_HEADER] = r.get("cargo_location") or ""
        out_rows.append(display)
    if not out_rows:
        return pd.DataFrame(columns=DISPLAY_HEADERS)
    df = pd.DataFrame(out_rows)[DISPLAY_HEADERS]
    # 공급물량: 명시적 float64로 캐스팅해야 NumberColumn이 NaN을 빈칸으로 렌더
    df["공급물량(톤)"] = pd.to_numeric(df["공급물량(톤)"], errors="coerce")
    return df


def _date_to_iso(v) -> str | None:
    """date/Timestamp/str → 'YYYY-MM-DD'. 빈값/파싱실패 → None."""
    if v is None:
        return None
    if hasattr(v, "strftime"):  # datetime/date/Timestamp
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        return v.strftime("%Y-%m-%d")
    d = _parse_date(v)
    return d.strftime("%Y-%m-%d") if d else None


def edited_to_records(edited: pd.DataFrame) -> list[dict]:
    """data_editor 결과(한글 컬럼) → DB 컬럼 키 dict 리스트. 파생 컬럼은 버림."""
    ko_to_db = {ko: db_ for db_, ko in export.SHIPMENT_COLS}
    records: list[dict] = []
    for _, row in edited.iterrows():
        rec = {db_: row.get(ko) for ko, db_ in ko_to_db.items()}
        rec["initial_depart_date"] = _date_to_iso(rec.get("initial_depart_date"))
        if CARGO_HEADER in edited.columns:
            rec["cargo_location"] = row.get(CARGO_HEADER)
        records.append(rec)
    return records


# ─── 1. 빠른 조회 ────────────────────────────────────────────────────────
st.subheader("1. BL 조회")

_prev_raw = st.session_state.get("quick_raw", "")
_lines = max(1, _prev_raw.count("\n") + 1)
_h = max(68, min(600, 38 + 24 * _lines))
raw = st.text_area(
    "BL 번호 입력",
    height=_h,
    placeholder="BL 번호 입력 (여러 건은 줄바꿈)",
    key="quick_raw",
    label_visibility="collapsed",
)
quick_clicked = st.button("조회 시작", disabled=not raw.strip())


if quick_clicked:
    bl_list = parse_bls(raw)
    if not bl_list:
        st.warning("유효한 BL이 없습니다.")
        st.stop()

    t0 = datetime.now()
    try:
        results = run_sync(bl_list, headless=not headed, concurrency=concurrency)
    except Exception as e:
        st.error(f"조회 실패: {type(e).__name__}: {e}")
        st.stop()
    elapsed = (datetime.now() - t0).total_seconds()

    rows: list[dict] = []
    for r in results:
        prev = db.get_previous(r["bl_no"])
        prev_eta = (prev.get("eta") if prev else "") or ""
        curr_eta = r.get("eta") or ""
        rows.append({
            "BL": r["bl_no"],
            "선사": r.get("carrier") or "",
            "항구": r.get("port") or "",
            "이전 ETA": prev_eta,
            "ETA": curr_eta,
            "전일 대비 변동": _delta_str(prev_eta, curr_eta),
            "status": r["status"],
        })
        db.save_record(r)

    st.session_state["quick_run"] = {
        "rows": rows,
        "results": results,
        "elapsed": elapsed,
    }


last = st.session_state.get("quick_run")
if last:
    rows = last["rows"]
    results = last["results"]
    elapsed = last["elapsed"]

    ok = sum(1 for r in results if r["status"] == "ok")
    nf = sum(1 for r in results if r["status"] == "not_found")
    failed = sum(1 for r in results if r["status"] == "failed")
    st.write(
        f"**{len(results)}건** · ok {ok} · not_found {nf} · failed {failed} · 소요 {elapsed:.1f}s"
    )
    if failed:
        st.warning(f"{failed}건 조회 실패 — status=failed 행 확인")

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    today = date.today().isoformat()
    col_csv, col_xlsx, _ = st.columns([1, 1, 6])
    col_csv.download_button(
        "CSV 다운로드",
        data=export.to_csv(df),
        file_name=f"bl_eta_{today}.csv",
        mime="text/csv",
    )
    col_xlsx.download_button(
        "엑셀 다운로드",
        data=export.to_xlsx(df),
        file_name=f"bl_eta_{today}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    with st.expander("raw_text (디버깅용)"):
        for r in results:
            st.markdown(f"**{r['bl_no']}** · `{r['status']}`")
            st.code((r.get("raw_text") or "")[:1500], language="text")


# ─── 2. 선적 마스터 ──────────────────────────────────────────────────────
st.divider()
master_df = build_master_df()

# 헤더: 제목 + 우측 상단 아이콘(행 추가 / 선택 행 삭제 / 업로드 / 다운로드)
hdr_cols = st.columns([10, 1, 1, 1, 1])
with hdr_cols[0]:
    st.subheader("2. 선박 자동화 관리양식")
with hdr_cols[1]:
    add_clicked = st.button(
        ":material/add:",
        help="빈 행 추가",
        use_container_width=True,
    )
with hdr_cols[2]:
    delete_clicked = st.button(
        ":material/remove:",
        help="선택된 행 삭제",
        use_container_width=True,
    )
with hdr_cols[3]:
    with st.popover(":material/upload:", help="엑셀 업로드", use_container_width=True):
        upload = st.file_uploader("xlsx 파일 선택", type=["xlsx"], label_visibility="collapsed")
        if upload is not None:
            fp_key = f"_uploaded_{upload.name}_{upload.size}"
            if not st.session_state.get(fp_key):
                try:
                    recs = export.shipments_from_xlsx(upload.getvalue())
                    db.shipments_replace(recs)
                    st.session_state[fp_key] = True
                    st.success(f"{len(recs)}건 업로드 완료")
                    st.rerun()
                except sqlite3.IntegrityError as e:
                    st.error(f"업로드 실패 (BL 중복 등): {e}")
                except Exception as e:
                    st.error(f"업로드 실패: {type(e).__name__}: {e}")
with hdr_cols[4]:
    st.download_button(
        ":material/download:",
        data=export.shipments_to_xlsx(master_df.drop(columns=[SELECT_HEADER])),
        file_name=f"shipments_{date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="엑셀 다운로드 (저장된 마스터 기준)",
        use_container_width=True,
    )

master_slot = st.empty()
edited = master_slot.data_editor(
    master_df,
    num_rows="fixed",
    use_container_width=True,
    hide_index=True,
    column_config={
        SELECT_HEADER: st.column_config.CheckboxColumn(
            width=10,
            help="삭제할 행 선택 후 우측 상단 ➖ 클릭",
            default=False,
        ),
        "IMO": st.column_config.TextColumn(
            help="VesselFinder IMO (7자리 숫자). 있으면 선명 대신 이것을 키로 위치 추적 — 동명이선/항차 suffix 문제 해소.",
        ),
        "공급물량(톤)": st.column_config.NumberColumn(),
        "최초출항일": st.column_config.TextColumn(
            help="YYYY-MM-DD · 2026-04-20 / 2026.04.20 / 20260420 모두 가능 (저장 시 자동 YYYY-MM-DD)",
        ),
        "국내 도착일": st.column_config.TextColumn(
            disabled=True,
            help="track-trace 조회 결과 (YYYY-MM-DD)",
        ),
        "전일 대비 변동": st.column_config.TextColumn(disabled=True, help="D±n / 변동없음 (오늘 이전 최신 ETA 대비)"),
        CARGO_HEADER: st.column_config.TextColumn(
            help="새로고침 시 선명 기반 VesselFinder 조회 결과로 자동 갱신",
        ),
    },
    key="shipments_editor",
)

if add_clicked:
    # 현재 편집 상태 저장 + 빈 행 1개 추가
    current = edited_to_records(pd.DataFrame(edited))
    current.append({k: None for k in ("smelter","origin","carrier","imo","vessel","bl_no","supply_tons","initial_depart_date")})
    try:
        db.shipments_replace(current)
        st.rerun()
    except sqlite3.IntegrityError as e:
        st.error(f"행 추가 실패 (BL 중복): {e}")

if delete_clicked:
    df_edit = pd.DataFrame(edited)
    if SELECT_HEADER in df_edit.columns:
        mask = df_edit[SELECT_HEADER].fillna(False).astype(bool)
        if not mask.any():
            st.warning("삭제할 행을 먼저 체크박스로 선택하세요.")
        else:
            remaining = df_edit[~mask]
            try:
                db.shipments_replace(edited_to_records(remaining))
                st.success(f"{int(mask.sum())}건 삭제 완료")
                st.rerun()
            except sqlite3.IntegrityError as e:
                st.error(f"삭제 실패 (BL 중복): {e}")

btn_cols = st.columns(2)

with btn_cols[0]:
    if st.button("테이블 저장", use_container_width=True):
        try:
            db.shipments_replace(edited_to_records(pd.DataFrame(edited)))
            st.success("저장 완료")
            st.rerun()
        except sqlite3.IntegrityError as e:
            st.error(f"저장 실패 (BL 중복): {e}")

with btn_cols[1]:
    refresh_clicked = st.button("ETA/위치 새로고침", type="primary", use_container_width=True)

if refresh_clicked:
    # 저장 선행
    try:
        db.shipments_replace(edited_to_records(pd.DataFrame(edited)))
    except sqlite3.IntegrityError as e:
        st.error(f"저장 실패 (BL 중복): {e}")
        st.stop()

    shipments = db.shipments_all()
    bls = [r["bl_no"] for r in shipments if r.get("bl_no")]
    # 위치 조회 항목 dedup: IMO가 있으면 IMO를, 없으면 vessel을 키로.
    # IMO는 전 세계 유일한 선박 식별자(7자리)라 같은 배의 선명 표기 차이를 흡수한다.
    seen: set[str] = set()
    items: list[dict] = []
    for r in shipments:
        imo = (r.get("imo") or "").strip()
        v = (r.get("vessel") or "").strip()
        key = f"imo:{imo}" if imo else (f"vessel:{v}" if v else "")
        if not key or key in seen:
            continue
        seen.add(key)
        items.append({
            "vessel": v or None,
            "imo": imo or None,
            "prev_label": r.get("cargo_location"),
        })
    if not bls and not items:
        st.warning("마스터에 BL/선명이 없습니다.")
    else:
        # 1단계: BL → ETA 조회
        results: list[dict] = []
        if bls:
            try:
                results = run_master_refresh_inplace(
                    master_slot, bls, headless=not headed, concurrency=concurrency
                )
            except Exception as e:
                st.error(f"ETA 조회 실패: {type(e).__name__}: {e}")
                st.stop()
            for r in results:
                db.save_record(r)

        # 2단계: 선명/IMO → 위치 조회
        loc_results: list[dict] = []
        loc_imo_backfill = 0
        loc_updated = 0
        if items:
            try:
                loc_results = run_location_refresh_inplace(
                    master_slot, items, headless=not headed, concurrency=concurrency
                )
            except Exception as e:
                st.error(f"위치 조회 실패: {type(e).__name__}: {e}")
                st.stop()
            for r in loc_results:
                if r.get("status") != "ok" or not r.get("location_label"):
                    continue
                label = r["location_label"]
                imo = (r.get("imo") or "").strip() or None
                vessel = r.get("vessel") or None
                # IMO가 있으면 같은 vessel의 NULL 행에 IMO 백필 → 다음부터는 IMO 직접 조회
                if imo and vessel:
                    loc_imo_backfill += db.update_vessel_imo(vessel, imo)
                # 항상 UPDATE — 동일 결과여도 덮어써서 "최신 조회 반영" 의미 유지
                if imo:
                    loc_updated += db.update_cargo_location_by_imo(imo, label)
                elif vessel:
                    loc_updated += db.update_cargo_location_by_vessel(vessel, label)

        ok = sum(1 for r in results if r["status"] == "ok")
        nf = sum(1 for r in results if r["status"] == "not_found")
        failed = sum(1 for r in results if r["status"] == "failed")
        loc_ok = sum(1 for r in loc_results if r["status"] == "ok")
        loc_nf = sum(1 for r in loc_results if r["status"] == "not_found")
        loc_failed = sum(1 for r in loc_results if r["status"] == "failed")
        loc_retried = sum(1 for r in loc_results if r.get("retried"))
        bl_nf_list = [r["bl_no"] for r in results if r["status"] == "not_found"]
        bl_failed_list = [r["bl_no"] for r in results if r["status"] == "failed"]
        loc_nf_list = [r["vessel"] for r in loc_results if r["status"] == "not_found"]
        loc_failed_list = [r["vessel"] for r in loc_results if r["status"] == "failed"]
        st.session_state["_refresh_done"] = {
            "n": len(results), "ok": ok, "nf": nf, "failed": failed,
            "bl_nf_list": bl_nf_list, "bl_failed_list": bl_failed_list,
            "loc_n": len(loc_results), "loc_ok": loc_ok,
            "loc_nf": loc_nf, "loc_failed": loc_failed,
            "loc_nf_list": loc_nf_list, "loc_failed_list": loc_failed_list,
            "loc_retried": loc_retried, "loc_imo_backfill": loc_imo_backfill,
        }
        st.rerun()


