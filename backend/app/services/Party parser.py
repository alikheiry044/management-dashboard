"""
پارسر گزارش «مرور فروش» (مانده‌ی اشخاص).

ستون‌ها: کد | عنوان | مانده
- بالای جدول ممکن است یک تیتر باشد (مثلاً «1405 شهریور»).
- آخرین ردیف (بدون کد و عنوان) جمع کل فایل است و برای صحت‌سنجی استفاده می‌شود.
- مانده‌ی صفر رد می‌شود. مثبت = بدهکار (مطالبات)، منفی = بستانکار (بدهی).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from app.services.bank_parser import clean_code, fix_text, to_int


class PartyParseError(ValueError):
    """خطای قابل نمایش به کاربر (پیام فارسی)."""


@dataclass
class PartyRow:
    detail_code: str
    title: str
    balance: int


@dataclass
class PartyResult:
    rows: list[PartyRow] = field(default_factory=list)
    skipped_zero: int = 0
    file_total: int | None = None

    @property
    def computed_total(self) -> int:
        return sum(r.balance for r in self.rows)

    @property
    def total_matches(self) -> bool:
        return self.file_total is None or self.file_total == self.computed_total


_CODE = {"کد", "کدحساب", "کدتفصیلی"}
_TITLE = {"عنوان", "نام", "شرح"}
_BALANCE = {"مانده"}


def _key(value: Any) -> str:
    return fix_text(value).replace(" ", "")


def _find_header(rows: list[list[Any]]) -> tuple[int, int, int, int]:
    for idx, row in enumerate(rows[:30]):
        keys = [_key(c) for c in row]
        code = next((i for i, k in enumerate(keys) if k in _CODE), None)
        title = next((i for i, k in enumerate(keys) if k in _TITLE), None)
        bal = next((i for i, k in enumerate(keys) if k in _BALANCE), None)
        if code is not None and title is not None and bal is not None:
            return idx, code, title, bal
    raise PartyParseError(
        "ستون‌های «کد، عنوان، مانده» پیدا نشد. مطمئن شوید فایل «مرور فروش» را انتخاب کرده‌اید."
    )


def parse_party_rows(rows: list[list[Any]]) -> PartyResult:
    header_idx, c_code, c_title, c_bal = _find_header(rows)
    result = PartyResult()
    seen: set[str] = set()

    def cell(row: list[Any], col: int) -> Any:
        return row[col] if col < len(row) else None

    for row in rows[header_idx + 1:]:
        code = clean_code(cell(row, c_code))
        title = fix_text(cell(row, c_title))
        raw = cell(row, c_bal)

        if not code and not title:
            if raw not in (None, ""):
                result.file_total = to_int(raw)   # ردیف جمع کل فایل
            continue
        if not code:
            continue

        balance = to_int(raw)
        if balance == 0:
            result.skipped_zero += 1
            continue
        if code in seen:
            raise PartyParseError(f"کد «{code}» در فایل تکراری است")
        seen.add(code)
        result.rows.append(PartyRow(code, title, balance))

    if not result.rows:
        raise PartyParseError("هیچ ردیف دارای مانده‌ای در فایل پیدا نشد")
    return result


def sniff_period(content: bytes) -> str | None:
    """اگر فایل XML اکسل است و ردیف اولش فقط یک تیتر دارد (مثل «1405 شهریور»)، همان را برگردان."""
    head = content[:4096].lstrip(b"\xef\xbb\xbf").lstrip()
    if not head.startswith(b"<"):
        return None
    try:
        ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
        root = ET.fromstring(content)
        first_row = root.find("ss:Worksheet/ss:Table/ss:Row", ns)
        texts = []
        for cell in first_row.findall("ss:Cell", ns):
            data = cell.find("ss:Data", ns)
            if data is not None and data.text and data.text.strip():
                texts.append(fix_text(data.text))
        return texts[0] if len(texts) == 1 else None
    except Exception:
        return None
    