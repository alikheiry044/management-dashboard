import xml.etree.ElementTree as ET
from typing import Any
import re

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_AR2FA = str.maketrans({"ك": "ک", "ي": "ی", "ى": "ی", "ة": "ه", "ۀ": "ه"})
_INVISIBLE = re.compile(r"[\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u206f]")


def norm(value):
    if value is None:
        return ""
    s = str(value).translate(_AR2FA).translate(_DIGITS)
    s = _INVISIBLE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _rows_spreadsheetml(data: bytes):
    root = ET.fromstring(data.lstrip(b"\xef\xbb\xbf"))
    ws = next(root.iter("{urn:schemas-microsoft-com:office:spreadsheet}Worksheet"))
    rows = []
    for r in ws.iter("{urn:schemas-microsoft-com:office:spreadsheet}Row"):
        cells, col = [], 0
        for c in r.findall("{urn:schemas-microsoft-com:office:spreadsheet}Cell"):
            idx = c.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
            if idx:
                col = int(idx) - 1
            while len(cells) < col:
                cells.append(None)
            d = c.find("{urn:schemas-microsoft-com:office:spreadsheet}Data")
            cells.append(d.text if d is not None else None)
            col += 1
        rows.append(cells)
    return rows


def read_rows(data: bytes, filename: str = ""):
    head = data[:200].lstrip(b"\xef\xbb\xbf").lstrip()
    if head.startswith(b"<?xml") or head.startswith(b"<Workbook"):
        return _rows_spreadsheetml(data)
    import io
    import pandas as pd
    bio = io.BytesIO(data)
    df = pd.read_excel(bio, header=None, dtype=str, engine="openpyxl" if data[:2] == b"PK" else "xlrd")
    return df.where(df.notna(), None).values.tolist()


HEADER_ALIASES = {
    "party_code": ["تفصیلی", "کد تفصیلی", "کد تفصيلي", "کد", "تفصيلي"],
    "party": ["طرف مقابل", "طرف حساب", "نام", "نام تفصیلی", "طرف"],
    "due_date": ["تاریخ سررسید", "سررسید", "تاريخ سررسيد"],
    "check_no": ["شماره اعلامیه", "شماره چک", "شماره", "شماره سند", "سریال چک", "شماره چك", "شماره اعلاميه"],
    "issue_date": ["تاریخ اعلامیه", "تاریخ چک", "تاريخ اعلاميه"],
    "clear_date": ["تاریخ وصول", "تاریخ وصول، واخواست", "تاریخ پاس", "تاريخ وصول"],
    "receive_date": ["تاریخ رسید", "تاريخ رسيد"],
    "owner": ["صاحب چک", "صاحب چك"],
    "description": ["شرح", "توضیحات"],
    "bank": ["حساب بانکی", "بانک", "بانك", "حساب بانكي"],
    "type": ["نوع"],
    "amount": ["مبلغ", "مبلغ چک", "مبلغ چك", "مبلغ سند", "مبلغ (ريال)", "مبلغ (ریال)"],
    "status": ["وضعیت", "وضعيت"],
}


def find_header(rows, max_scan=15):
    for i, row in enumerate(rows[:max_scan]):
        cells = [norm(c) for c in row]
        mapping = {}
        for field, aliases in HEADER_ALIASES.items():
            for j, text in enumerate(cells):
                if text in aliases and j not in mapping.values():
                    mapping[field] = j
                    break
        # اگر حداقل یکی از فیلدهای کلیدی پیدا شد، هدر معتبر است
        if "due_date" in mapping or "check_no" in mapping or "amount" in mapping or "party" in mapping:
            return i, mapping
    return None, {}


def _to_number(v):
    s = norm(v).replace(",", "").replace("٬", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_checks_file(source, kind: str, filename: str = ""):
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        with open(source, "rb") as fh:
            data = fh.read()

    rows = read_rows(data, filename)
    h, col = find_header(rows)
    if h is None:
        raise ValueError("ردیف هدر (شامل ستون‌های اطلاعاتی چک) در فایل پیدا نشد.")

    def get(row, field):
        j = col.get(field)
        return row[j] if j is not None and j < len(row) else None

    checks, skipped, warnings = [], [], []
    for i, row in enumerate(rows[h + 1:], start=h + 2):
        if not any(norm(c) for c in row):
            continue

        ctype = norm(get(row, "type"))
        if ctype in ["تضمین", "تضمين"]:
            skipped.append({"row": i, "reason": "تضمین (وثیقه)"})
            continue

        party = norm(get(row, "party"))
        if not party or party.startswith(("جمع", "مجموع", "تعداد رکورد", "ارز:")):
            skipped.append({"row": i, "reason": "ردیف جمع یا اطلاعات غیرچک"})
            continue

        due = norm(get(row, "due_date"))
        no = norm(get(row, "check_no"))
        amount = _to_number(get(row, "amount"))

        clear = norm(get(row, "clear_date"))
        status_text = norm(get(row, "status"))
        status = status_text or ("passed" if clear else "open")

        checks.append({
            "kind": kind,
            "party_code": norm(get(row, "party_code")),
            "party": party,
            "due_date": due,
            "check_no": no,
            "issue_date": norm(get(row, "issue_date")),
            "clear_date": clear or None,
            "bank_account": norm(get(row, "bank")),
            "type": ctype,
            "receive_date": norm(get(row, "receive_date")) or None,
            "owner": norm(get(row, "owner")) or None,
            "description": norm(get(row, "description")) or None,
            "status_raw": status_text or None,
            "amount": amount if amount is not None else 0,
            "status": status,
        })

    if not checks:
        warnings.append("هیچ چک معتبری در فایل پیدا نشد")

    return {
        "checks": checks,
        "skipped": skipped,
        "warnings": warnings,
        "header_row": h + 1,
        "columns": col
    }
