"""bl-eta Streamlit app (Phase 4 — 병렬 조회 + SQLite 변동 감지 + export)."""

from __future__ import annotations

import asyncio
import threading
from datetime import date, datetime

import pandas as pd
import streamlit as st

from bl_eta import db, export, tracker

db.init_db()

st.set_page_config(page_title="bl-eta", layout="wide")
st.title("bl-eta")
st.caption("track-trace.com 병렬 BL 조회 — 부산/인천 ETA + 전일 대비 변동 감지")


# ─── 사이드바 ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("설정")
    # docs/carrier-samples.md: Maersk headless 감지 → 기본 Headed
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


# ─── 메인: 입력 ──────────────────────────────────────────────────────────
st.subheader("1. BL 번호 입력")
raw = st.text_area(
    "BL 번호를 줄바꿈으로 구분해 붙여넣기",
    height=180,
    placeholder="MAEU266930123\nHDMUDOHA62608100\n...",
)
run_clicked = st.button("조회 시작", type="primary", disabled=not raw.strip())


# ─── 병렬 조회 + 진행률 ─────────────────────────────────────────────────
def parse_bls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        bl = line.strip()
        if bl and bl not in seen:
            seen.add(bl)
            out.append(bl)
    return out


def run_sync(bl_list: list[str], headless: bool, concurrency: int) -> list[dict]:
    """Streamlit은 동기 컨텍스트 → 별도 쓰레드에서 asyncio.run.

    Streamlit 쓰레드가 이미 이벤트 루프를 들고 있을 수 있어 nested loop 방지.
    """
    progress_bar = st.progress(0.0)
    status_slot = st.empty()
    total = len(bl_list)
    state = {"done": 0}

    def on_progress(done: int, total_: int, bl: str, rec: dict) -> None:
        state["done"] = done
        # 콜백은 worker 쓰레드에서 호출 — Streamlit 위젯 직접 갱신 대신 상태만 저장.
        # progress 갱신은 poll 루프에서.

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
    if not prev_eta or not curr_eta:
        return ""
    try:
        p = datetime.strptime(prev_eta, "%Y-%m-%d").date()
        c = datetime.strptime(curr_eta, "%Y-%m-%d").date()
    except ValueError:
        return ""
    d = (c - p).days
    return f"D{d:+d}" if d else "D0"


def _row_style(row: pd.Series) -> list[str]:
    """plan.md 7.2: CHANGED 빨강 / NEW 파랑 / UNCHANGED 회색."""
    color_map = {
        "CHANGED": "background-color: #ffe5e5; color: #a40000; font-weight: 600",
        "NEW": "background-color: #e5f0ff; color: #1a4b8c",
        "UNCHANGED": "color: #888",
    }
    return [color_map.get(row["change"], "")] * len(row)


# ─── 실행 ────────────────────────────────────────────────────────────────
if run_clicked:
    bl_list = parse_bls(raw)
    if not bl_list:
        st.warning("유효한 BL이 없습니다.")
        st.stop()

    st.subheader("2. 진행률")
    t0 = datetime.now()
    try:
        results = run_sync(bl_list, headless=not headed, concurrency=concurrency)
    except Exception as e:
        st.error(f"조회 실패: {type(e).__name__}: {e}")
        st.stop()
    elapsed = (datetime.now() - t0).total_seconds()

    # ─── 변동 분류 + DB 저장 ──────────────────────────────────────────
    # 순서: prev 조회(이전 스냅샷) → compare → save(현재 조회 레코드 기록)
    rows: list[dict] = []
    for r in results:
        prev = db.get_previous(r["bl_no"])
        change = db.compare(prev, r)
        prev_eta = (prev.get("eta") if prev else "") or ""
        curr_eta = r.get("eta") or ""
        rows.append({
            "change": change,
            "변동일수": _delta_str(prev_eta, curr_eta) if change == "CHANGED" else "",
            "BL": r["bl_no"],
            "선사": r.get("carrier") or "",
            "항구": r.get("port") or "",
            "이전 ETA": prev_eta,
            "ETA": curr_eta,
            "status": r["status"],
        })
        db.save_record(r)

    # 다운로드 버튼 클릭 시 Streamlit rerun이 발생해도 결과가 사라지지 않도록 session_state에 캐시
    st.session_state["last_run"] = {
        "rows": rows,
        "results": results,
        "elapsed": elapsed,
    }


# ─── 결과 렌더링 (session_state 기반) ──────────────────────────────────
last = st.session_state.get("last_run")
if last:
    rows = last["rows"]
    results = last["results"]
    elapsed = last["elapsed"]

    st.subheader("3. 결과")
    ok = sum(1 for r in results if r["status"] == "ok")
    nf = sum(1 for r in results if r["status"] == "not_found")
    failed = sum(1 for r in results if r["status"] == "failed")
    changed = sum(1 for row in rows if row["change"] == "CHANGED")
    new_cnt = sum(1 for row in rows if row["change"] == "NEW")
    st.write(
        f"**{len(results)}건** · ok {ok} · not_found {nf} · failed {failed} · "
        f"CHANGED {changed} · NEW {new_cnt} · 소요 {elapsed:.1f}s"
    )
    if failed:
        st.warning(f"{failed}건 조회 실패 — 테이블 하단 status=failed 행 확인")

    df = pd.DataFrame(rows)
    # CHANGED 상단 정렬 (CHANGED → NEW → UNCHANGED)
    order = {"CHANGED": 0, "NEW": 1, "UNCHANGED": 2}
    df = df.sort_values(
        by="change", key=lambda s: s.map(order).fillna(3), kind="stable"
    ).reset_index(drop=True)

    styled = df.style.apply(_row_style, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ─── Export ────────────────────────────────────────────────────────
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
