"""SQLite CRUD + 변동 비교.

CLAUDE.md Rules: 다른 모듈에서 `import sqlite3` 금지. DB 접근은 반드시 이 모듈 경유.
스키마는 CLAUDE.md "데이터 스키마 (bl_eta.db)" 절의 eta_history 테이블.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

def _default_db_path() -> Path:
    """사용자 홈의 `~/.bl-eta/bl_eta.db`.

    코드는 배포 가능하되 DB는 각 사용자 로컬에만 존재. iCloud/OneDrive 동기화
    대상 아님 (사내 보안 관점). Windows는 `%USERPROFILE%\\.bl-eta\\bl_eta.db`.
    """
    base = Path.home() / ".bl-eta"
    base.mkdir(parents=True, exist_ok=True)
    new_path = base / "bl_eta.db"

    # 레거시 이관: 프로젝트 루트에 있던 기존 파일이 있으면 1회 이동
    legacy = Path(__file__).resolve().parent.parent / "bl_eta.db"
    if legacy.exists() and not new_path.exists():
        legacy.rename(new_path)

    return new_path


DB_PATH = _default_db_path()

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

CREATE TABLE IF NOT EXISTS shipments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    smelter             TEXT,
    origin              TEXT,
    carrier             TEXT,
    vessel              TEXT,
    bl_no               TEXT UNIQUE,
    supply_tons         REAL,
    initial_depart_date TEXT,
    cargo_location      TEXT
);
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
            _migrate_shipments_bl_nullable(conn)
            _migrate_shipments_add_cargo_location(conn)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


def _migrate_shipments_add_cargo_location(conn: sqlite3.Connection) -> None:
    """shipments.cargo_location 컬럼이 없으면 추가 (idempotent)."""
    cols = conn.execute("PRAGMA table_info(shipments)").fetchall()
    if any(c["name"] == "cargo_location" for c in cols):
        return
    conn.execute("ALTER TABLE shipments ADD COLUMN cargo_location TEXT")


def _migrate_shipments_bl_nullable(conn: sqlite3.Connection) -> None:
    """기존 DB의 `shipments.bl_no NOT NULL` 제약을 제거 (SQLite는 직접 수정 불가라 테이블 재생성)."""
    cols = conn.execute("PRAGMA table_info(shipments)").fetchall()
    bl_col = next((c for c in cols if c["name"] == "bl_no"), None)
    if bl_col is None or bl_col["notnull"] == 0:
        return
    conn.executescript(
        """
        CREATE TABLE shipments_new (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            smelter             TEXT,
            origin              TEXT,
            carrier             TEXT,
            vessel              TEXT,
            bl_no               TEXT UNIQUE,
            supply_tons         REAL,
            initial_depart_date TEXT
        );
        INSERT INTO shipments_new (id, smelter, origin, carrier, vessel, bl_no, supply_tons, initial_depart_date)
            SELECT id, smelter, origin, carrier, vessel, bl_no, supply_tons, initial_depart_date FROM shipments;
        DROP TABLE shipments;
        ALTER TABLE shipments_new RENAME TO shipments;
        """
    )


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
    """오늘(KST) 이전 날짜의 최신 queried_at 1건 반환. 없으면 None.

    당일 재조회 레코드를 제외해 "어제 대비 변동" 의미를 유지한다.
    queried_at은 UTC(CURRENT_TIMESTAMP)이므로 +9h로 KST 날짜 변환 후 비교.
    """
    _ensure_init()
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT bl_no, carrier, port, eta, raw_text, queried_at, status
            FROM eta_history
            WHERE bl_no = ?
              AND DATE(queried_at, '+9 hours') < DATE('now', '+9 hours')
            ORDER BY queried_at DESC, id DESC
            LIMIT 1
            """,
            (bl_no,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def get_latest_for_bl(bl_no: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """해당 BL의 최신 eta_history 1건 (날짜 필터 없음). `국내 도착일` 표시용."""
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


# ─── shipments (마스터) ────────────────────────────────────────────────

_SHIPMENT_FIELDS = (
    "smelter", "origin", "carrier", "vessel",
    "bl_no", "supply_tons", "initial_depart_date",
)


def shipments_all(db_path: Path | None = None) -> list[dict[str, Any]]:
    """마스터 전체, id 오름차순 (사용자 입력/업로드 순서 유지)."""
    _ensure_init()
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, smelter, origin, carrier, vessel, bl_no,
                   supply_tons, initial_depart_date, cargo_location
            FROM shipments
            ORDER BY id ASC
            """,
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def shipments_replace(rows: list[dict[str, Any]], db_path: Path | None = None) -> None:
    """DELETE 전체 + INSERT 새. 트랜잭션. bl_no 비어있는 행은 스킵.

    rows의 각 dict는 `_SHIPMENT_FIELDS` 키를 가진다고 가정 (없는 키는 None).
    UNIQUE(bl_no) 위반 시 IntegrityError 전파 — 호출자가 사용자에게 표시.
    """
    _ensure_init()
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM shipments")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='shipments'")
        for r in rows:
            bl = _clean_str(r.get("bl_no"))
            smelter = _clean_str(r.get("smelter"))
            origin = _clean_str(r.get("origin"))
            carrier = _clean_str(r.get("carrier"))
            vessel = _clean_str(r.get("vessel"))
            idd = _clean_str(r.get("initial_depart_date"))
            cargo_loc = _clean_str(r.get("cargo_location"))
            tons = _to_float(r.get("supply_tons"))
            conn.execute(
                """
                INSERT INTO shipments
                  (smelter, origin, carrier, vessel, bl_no, supply_tons, initial_depart_date, cargo_location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (smelter, origin, carrier, vessel, bl, tons, idd, cargo_loc),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _clean_str(v: Any) -> str | None:
    """None/NaN/공백 → None, 그 외 str(v).strip() (빈 문자열이면 None)."""
    if v is None or v != v:  # v != v → NaN
        return None
    s = str(v).strip()
    return s or None


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def update_cargo_locations(
    mapping: dict[str, str], db_path: Path | None = None
) -> int:
    """vessel 이름 → cargo_location 일괄 업데이트. 업데이트된 행 수 반환.

    동일 vessel로 여러 shipment 행이 있으면 모두 같은 값으로 갱신된다.
    """
    if not mapping:
        return 0
    _ensure_init()
    conn = _connect(db_path)
    total = 0
    try:
        for vessel, loc in mapping.items():
            if not vessel:
                continue
            cur = conn.execute(
                "UPDATE shipments SET cargo_location = ? WHERE vessel = ?",
                (loc, vessel),
            )
            total += cur.rowcount or 0
        conn.commit()
    finally:
        conn.close()
    return total


def get_recent(limit: int = 100, db_path: Path | None = None) -> list[dict[str, Any]]:
    """최근 queried_at 내림차순 레코드 목록. 사이드바 DB 뷰어용."""
    _ensure_init()
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, bl_no, carrier, port, eta, queried_at, status
            FROM eta_history
            ORDER BY queried_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


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
