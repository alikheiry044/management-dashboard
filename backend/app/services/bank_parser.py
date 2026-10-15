import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, List
import re

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class BankParseError(ValueError):
    """خطای اختصاصی پارسر بانک‌ها"""
    pass


@dataclass
class BankRow:
    detail_code: str
    title: str
    account_number: str | None
    opening_balance: int
    receipts: int
    payments: int
    balance: int


def fix_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()


def to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(round(value))
    text = fix_text(value).translate(_PERSIAN_DIGITS)
    text = text.replace(",", "").replace("٬", "").replace(" ", "")
    if text in {"", "-", "--"}:
        return 0
    try:
        return int(round(float(text)))
    except ValueError:
        return 0


def clean_code(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return fix_text(value).translate(_PERSIAN_DIGITS)


def _read_rows(content: bytes) -> list[list[Any]]:
    text_head = content[:100].decode("utf-8", errors="ignore").strip()
    if text_head.startswith("<?xml") or "<Workbook" in text_head:
        try:
            tree = ET.fromstring(content)
            ns = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
            rows = []
            for table in tree.findall('.//ss:Table', ns):
                for row in table.findall('ss:Row', ns):
                    row_data = []
                    for cell in row.findall('ss:Cell', ns):
                        data = cell.find('ss:Data', ns)
                        row_data.append(data.text if data is not None else "")
                    rows.append(row_data)
            if rows:
                return rows
        except Exception as e:
            raise BankParseError(f"خطا در خواندن ساختار XML فایل: {e}")

    raise BankParseError("فرمت فایل اکسل بانک‌ها نامعتبر است.")


def parse_bank_rows(rows: list[list[Any]]) -> list[BankRow]:
    result = []
    for row in rows[1:]:  # رد کردن هدر
        if not row or not row[0]:
            continue
        code = clean_code(row[0])
        title = fix_text(row[1]) if len(row) > 1 else ""
        if not code:
            continue

        result.append(BankRow(
            detail_code=code,
            title=title,
            account_number=None,
            opening_balance=to_int(row[2]) if len(row) > 2 else 0,
            receipts=to_int(row[3]) if len(row) > 3 else 0,
            payments=to_int(row[4]) if len(row) > 4 else 0,
            balance=to_int(row[5]) if len(row) > 5 else 0,
        ))
    if not result:
        raise BankParseError("هیچ ردیف معتبری در فایل بانک پیدا نشد.")
    return result


def parse_bank_accounts(content: bytes) -> list[BankRow]:
    """تابع اصلی مورد انتظار در API بانک‌ها"""
    rows = _read_rows(content)
    return parse_bank_rows(rows)
