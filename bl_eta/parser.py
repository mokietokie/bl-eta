"""선사 tracking 페이지 innerText → ETA 레코드 파서.

Phase 1 실측 기준 구현 — Maersk 우선 지원.
다른 선사는 docs/carrier-samples.md 기록 후 선사별 분기 추가 예정.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

PORT_KEYWORDS: dict[str, str] = {
    "busan": "Busan",
    "pusan": "Busan",
    "incheon": "Incheon",
}

# ETA가 innerText에 등장하는 형태 (실측):
#   Maersk  : "Estimated arrival date\n25 Apr 2026 03:00"  (DD MMM YYYY)
#   Maersk  : 전개된 transport plan "BUSAN\n...\nVessel arrival (…)\n25 Apr 2026 03:00"
#   KMTC    : 결과 테이블 "BUSAN NEW PORT(Hanjin New Port)\n2026.05.05 14:00"  (YYYY.MM.DD)
# 공통 전략: (1) 'Estimated arrival date' 라벨 매칭 + (2) 항구 키워드 앞뒤 500자 창 내 모든 날짜 수집
# → plan.md 규칙대로 가장 늦은 ETA 선택.
_ETA_LABEL_DATE = re.compile(
    r"estimated arrival date[\s\n]+(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
    re.IGNORECASE,
)
_DATE_NEAR_PORT = re.compile(
    r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"      # DD MMM YYYY (Maersk)
    r"|\d{4}[./\-]\d{1,2}[./\-]\d{1,2})"     # YYYY.MM.DD / YYYY-MM-DD (KMTC 등)
)
_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d")
_PORT_WINDOW_CHARS = 500

# 라벨 anchoring: 날짜 직전 ~200자 내 가장 가까운 라벨로 keep/drop 분류.
# - 양쪽 리스트에 해당 없으면 default=keep (KMTC처럼 명시 라벨 없는 선사 호환)
# - 기준: HMM 실측 — BUSAN 주변에 ETA·출발·컨테이너반납·페이지타임스탬프가 혼재,
#   Arrival/ETB가 근접한 날짜만 통과시키면 올바른 ETA만 남음.
# regex 경계 사용 이유: HMM "Rail ETD/ETA" 컬럼 헤더의 "eta"를 배제.
# `(?<![a-z/])eta(?![a-z/])` — "ETD/ETA" (앞에 /) 와 "ETA/ETD" (뒤에 /) 둘 다 스킵.
_LABEL_WHITELIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"arrival", re.IGNORECASE),
    re.compile(r"arrived", re.IGNORECASE),
    re.compile(r"(?<![a-z/])eta(?![a-z/])", re.IGNORECASE),
    re.compile(r"(?<![a-z])etb(?![a-z])", re.IGNORECASE),
)
_LABEL_BLACKLIST: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        r"departure",            # Vessel departure, Departure 컬럼
        r"departed",
        r"load on",              # "Load on VESSEL" 이벤트
        r"discharge",            # Discharge 이벤트
        r"gate in",              # Gate in Empty 등
        r"gate out",             # Gate out Empty 등
        r"last movement",        # HMM 컨테이너 테이블 Last Movement Date
        r"container returned",   # Import Empty Container Returned
        r"empty container",      # Empty Container Returned
        r"provided by",          # "Tracking results are provided by HMM ... : 2026-04-22" 페이지 타임스탬프
        r"last updated",         # Maersk "Last updated: 6 days ago"
        r"rollover",
    )
)
_LABEL_SCAN_CHARS = 200


def _closest_kind_in(segment: str, *, from_end: bool) -> str:
    """segment 내 가장 가까운 라벨 기준 keep/drop/default.

    from_end=True : 날짜 앞 backward 텍스트에서 segment 끝(=rfind 최대 인덱스)이 가깝다.
    from_end=False: 날짜 뒤 forward 텍스트에서 segment 시작(=find 최소 인덱스)이 가깝다.
    """
    best_pos = -1 if from_end else len(segment) + 1
    best_kind = "default"

    def consider(idx: int, kind: str) -> None:
        nonlocal best_pos, best_kind
        if idx < 0:
            return
        if from_end:
            if idx > best_pos:
                best_pos = idx
                best_kind = kind
        else:
            if idx < best_pos:
                best_pos = idx
                best_kind = kind

    def pattern_idx(pat: re.Pattern[str]) -> int:
        matches = list(pat.finditer(segment))
        if not matches:
            return -1
        return matches[-1].start() if from_end else matches[0].start()

    for pat in _LABEL_WHITELIST:
        consider(pattern_idx(pat), "keep")
    for pat in _LABEL_BLACKLIST:
        consider(pattern_idx(pat), "drop")
    return best_kind


def _classify_date_by_label(text_lower: str, date_start: int, date_end: int) -> str:
    """가장 가까운 라벨 기준 분류 — backward 우선, 없으면 forward fallback.

    실측 구조:
      (a) Maersk/HMM Arrival(ETB) 테이블 : "Arrival\n날짜\n날짜..." — backward 잡힘.
      (b) HMM Shipment Progress          : "날짜\n항구\n상태라벨" — backward엔 이전 이벤트 라벨이 잡혀
                                           오판 가능 → backward에 라벨 없을 때만 forward fallback.
    backward에 라벨이 있으면 forward는 보지 않음 — Arrival 테이블의 날짜들이 뒤따르는 'Departure' 행
    헤더에 잘못 매칭돼 drop되는 것 방지.

    반환: "keep" | "drop" | "default" (default는 caller가 keep으로 취급).
    """
    back_start = max(0, date_start - _LABEL_SCAN_CHARS)
    backward = text_lower[back_start:date_start]
    kind = _closest_kind_in(backward, from_end=True)
    if kind != "default":
        return kind

    forward = text_lower[date_end: date_end + _LABEL_SCAN_CHARS]
    return _closest_kind_in(forward, from_end=False)


def _truncate(text: str, limit: int = 2000) -> str:
    return text[:limit] if text else ""


def _to_iso(raw: str) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _find_port(text_lower: str) -> str | None:
    for keyword, canonical in PORT_KEYWORDS.items():
        if re.search(rf"\b{keyword}\b", text_lower):
            return canonical
    return None


def _find_latest_eta(text: str) -> str | None:
    """모든 ETA 후보 수집 → 가장 늦은 ISO 날짜 반환 (plan.md 7.1 규칙)."""
    candidates: list[str] = []

    for raw in _ETA_LABEL_DATE.findall(text):
        iso = _to_iso(raw)
        if iso:
            candidates.append(iso)

    text_lower = text.lower()
    for keyword in PORT_KEYWORDS:
        for match in re.finditer(rf"\b{keyword}\b", text_lower):
            start = max(0, match.start() - _PORT_WINDOW_CHARS)
            end = match.end() + _PORT_WINDOW_CHARS
            window = text[start:end]
            for date_match in _DATE_NEAR_PORT.finditer(window):
                date_pos = start + date_match.start()
                date_end_pos = start + date_match.end()
                kind = _classify_date_by_label(text_lower, date_pos, date_end_pos)
                if kind == "drop":
                    continue
                iso = _to_iso(date_match.group(1))
                if iso:
                    candidates.append(iso)

    return max(candidates) if candidates else None


def parse(bl_no: str, text: str, *, carrier: str | None = None) -> dict[str, Any]:
    """선사 iframe innerText에서 부산/인천 ETA 추출.

    반환: {bl_no, carrier, port, eta, status, raw_text}
      status: "ok" | "not_found"
    """
    if not text:
        return {
            "bl_no": bl_no, "carrier": carrier, "port": None, "eta": None,
            "status": "not_found", "raw_text": "",
        }

    port = _find_port(text.lower())
    if port is None:
        return {
            "bl_no": bl_no, "carrier": carrier, "port": None, "eta": None,
            "status": "not_found", "raw_text": _truncate(text),
        }

    eta = _find_latest_eta(text)
    if eta is None:
        return {
            "bl_no": bl_no, "carrier": carrier, "port": port, "eta": None,
            "status": "not_found", "raw_text": _truncate(text),
        }

    return {
        "bl_no": bl_no, "carrier": carrier, "port": port, "eta": eta,
        "status": "ok", "raw_text": _truncate(text),
    }
