"""결과 DataFrame → CSV/xlsx 바이트 export.

Streamlit `st.download_button` data 인자에 직접 전달하는 용도.
헤더 굵게, 컬럼 폭은 데이터 최대 길이 기준 auto-fit (최소 8, 최대 40).
"""

from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def to_csv(df: pd.DataFrame) -> bytes:
    """UTF-8 BOM 포함 — Excel 한글 깨짐 방지."""
    return df.to_csv(index=False).encode("utf-8-sig")


def to_xlsx(df: pd.DataFrame, sheet_name: str = "bl-eta") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    headers = list(df.columns)
    ws.append(headers)
    bold = Font(bold=True)
    for col_idx in range(1, len(headers) + 1):
        ws.cell(row=1, column=col_idx).font = bold

    for row in df.itertuples(index=False, name=None):
        ws.append([_cellify(v) for v in row])

    for col_idx, name in enumerate(headers, start=1):
        max_len = len(str(name))
        for v in df.iloc[:, col_idx - 1]:
            s = "" if v is None else str(v)
            if len(s) > max_len:
                max_len = len(s)
        width = min(max(max_len + 2, 8), 40)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cellify(v):
    """None/NaN → 빈 문자열. 나머지는 그대로."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return v
