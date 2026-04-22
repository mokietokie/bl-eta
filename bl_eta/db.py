"""SQLite CRUD + 변동 비교.

CLAUDE.md Rules: 다른 모듈에서 `import sqlite3` 금지. DB 접근은 반드시 이 모듈 경유.
스키마는 CLAUDE.md "데이터 스키마 (bl_eta.db)" 절의 eta_history 테이블.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "bl_eta.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS eta_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bl_no       TEXT NOT NULL,
    carrier     TEXT,
    port        TEXT,
    eta         TEXT,
    raw_text    TEXT,
    queried_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bl_queried ON eta_history(bl_no, queried_at DESC);
"""

# sqlite3 connection은 쓰레드별. Streamlit은 쓰레드에서 호출되므로 _connect()마다 새 연결.
_init_lock = threading.Lock()
_initialized = False


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    """테이블·인덱스 생성 (idempotent). 프로세스당 한번만 실제 실행."""
    global _initialized
    with _init_lock:
        conn = _connect(db_path)
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


def _ensure_init() -> None:
    if not _initialized:
        init_db()


def save_record(rec: dict[str, Any], db_path: Path | None = None) -> int:
    """tracker 결과 dict를 eta_history에 INSERT. 삽입된 id 반환."""
    _ensure_init()
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO eta_history (bl_no, carrier, port, eta, raw_text, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                rec.get("bl_no") or "",
                rec.get("carrier"),
                rec.get("port"),
                rec.get("eta"),
                rec.get("raw_text"),
                rec.get("status") or "failed",
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def get_previous(bl_no: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """직전 queried_at 1건 반환. 없으면 None.

    "어제 vs 오늘" 비교는 plan.md 7.2 규칙대로 **직전 1건** 기준 (MVP).
    """
    _ensure_init()
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT bl_no, carrier, port, eta, raw_text, queried_at, status
            FROM eta_history
            WHERE bl_no = ?
            ORDER BY queried_at DESC, id DESC
            LIMIT 1
            """,
            (bl_no,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def reset(db_path: Path | None = None) -> None:
    """모든 레코드 삭제 (사이드바 'DB 초기화' 버튼). 테이블 구조는 유지."""
    _ensure_init()
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM eta_history")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='eta_history'")
        conn.commit()
    finally:
        conn.close()


# ─── 변동 분류 ──────────────────────────────────────────────────────────

def compare(prev: dict[str, Any] | None, curr: dict[str, Any]) -> str:
    """plan.md 7.2: NEW / UNCHANGED / CHANGED 3분류.

    - prev 없음 → NEW
    - prev.eta == curr.eta (둘 다 None 포함) → UNCHANGED
    - 그 외 → CHANGED
    """
    if prev is None:
        return "NEW"
    if (prev.get("eta") or None) == (curr.get("eta") or None):
        return "UNCHANGED"
    return "CHANGED"
