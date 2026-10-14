"""
خواندن فایل‌های «مرور چک» (پرداختنی / دریافتنی) از نرم‌افزار حسابداری.

نکته‌های مهم که در فایل‌های واقعی دیده شد:
  1) پسوند فایل .xls است ولی محتوایش XML (SpreadsheetML 2003) است، نه Excel باینری.
     xlrd و pandas.read_excel روی آن شکست می‌خورند → همین باعث «هیچ چک معتبری پیدا نشد» می‌شود.
  2) حروف عربی (ك ي) در هدر و داده‌ها؛ باید قبل از مقایسه به فارسی (ک ی) تبدیل شوند.
  3) ردیف اول عنوان گزارش است، هدر در ردیف دوم؛ بین داده‌ها ردیف خالی هست.
  4) ستون «مبلغ» در این فایل وجود ندارد (در فایل‌های دیگر ممکن است باشد).
  5) ردیف‌های نوع «تضمین» (وثیقه‌ی وام) چک واقعی نیستند.

استفاده:
    from check_parser import parse_checks_file
    result = parse_checks_file(path_or_bytes, kind="payable_check")
    result["checks"], result["warnings"], result["skipped"]
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

SS = "{urn:schemas-microsoft-com:office:spreadsheet}"

_AR2FA = str.maketrans({"ك": "ک", "ي": "ی", "ى": "ی", "ة": "ه", "ۀ": "ه"})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_INVISIBLE = re.compile(r"[\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u206f]")


def norm(value):
    """نرمال‌سازی متن: ك/ي عربی، رقم فارسی، کاراکترهای نامرئی، فاصله‌ی اضافه."""
    if value is None:
        return ""
    s = str(value).translate(_AR2FA).translate(_DIGITS)
    s = _INVISIBLE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- خواندن ردیف‌ها از هر نوع فایل ----------

def _rows_spreadsheetml(data: bytes):
    root = ET.fromstring(data.lstrip(b"\xef\xbb\xbf"))
    ws = next(root.iter(SS + "Worksheet"))
    rows = []
    for r in ws.iter(SS + "Row"):
        cells, col = [], 0
        for c in r.findall(SS + "Cell"):
            idx = c.get(SS + "Index")
            if idx:
                col = int(idx) - 1
            while len(cells) < col:
                cells.append(None)
            d = c.find(SS + "Data")
            cells.append(d.text if d is not None else None)
            col += 1
        rows.append(cells)
    return rows


def _rows_other(data: bytes, filename: str):
    import pandas as pd
    bio = io.BytesIO(data)
    name = (filename or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(bio, header=None, dtype=str, encoding="utf-8-sig")
    elif data[:2] == b"PK":                      # xlsx
        df = pd.read_excel(bio, header=None, dtype=str, engine="openpyxl")
    else:                                         # xls باینری واقعی
        df = pd.read_excel(bio, header=None, dtype=str, engine="xlrd")
    return df.where(df.notna(), None).values.tolist()


def read_rows(data: bytes, filename: str = ""):
    head = data[:200].lstrip(b"\xef\xbb\xbf").lstrip()
    if head.startswith(b"<?xml") or head.startswith(b"<Workbook"):
        return _rows_spreadsheetml(data)
    return _rows_other(data, filename)


# ---------- شناسایی ستون‌ها ----------

# هر فیلد: چند عبارت ممکن در هدر (بعد از نرمال‌سازی)
HEADER_ALIASES = {
    "party_code": ["تفصیلی", "کد تفصیلی", "کد"],
    "party":      ["طرف مقابل", "طرف حساب", "نام"],
    "due_date":   ["تاریخ سررسید", "سررسید"],
    "check_no":   ["شماره اعلامیه", "شماره چک", "شماره"],
    "issue_date": ["تاریخ اعلامیه", "تاریخ چک"],
    "clear_date": ["تاریخ وصول", "تاریخ وصول، واخواست", "تاریخ وصول، واخواست", "تاریخ پاس"],
    "receive_date": ["تاریخ رسید"],
    "owner":      ["صاحب چک"],
    "description": ["شرح", "توضیحات"],
    "bank":       ["حساب بانکی", "بانک"],
    "type":       ["نوع"],
    "amount":     ["مبلغ", "مبلغ چک"],
    "status":     ["وضعیت"],
}


def find_header(rows, max_scan=15):
    """ردیف هدر را پیدا می‌کند (نه الزاماً ردیف اول) و نقشه‌ی فیلد→ستون برمی‌گرداند."""
    for i, row in enumerate(rows[:max_scan]):
        cells = [norm(c) for c in row]
        mapping = {}
        for field, aliases in HEADER_ALIASES.items():
            for j, text in enumerate(cells):
                if text in aliases and j not in mapping.values():
                    mapping[field] = j
                    break
        if "due_date" in mapping and ("party" in mapping or "check_no" in mapping):
            return i, mapping
    return None, {}


def _to_number(v):
    s = norm(v).replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------- تابع اصلی ----------

def parse_checks_file(source, kind: str, filename: str = ""):
    """
    source : مسیر فایل یا bytes
    kind   : payable_check | receivable_check
    خروجی  : dict با checks / skipped / warnings
    """
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        filename = filename or str(source)
        with open(source, "rb") as fh:
            data = fh.read()

    rows = read_rows(data, filename)
    h, col = find_header(rows)
    if h is None:
        raise ValueError("ردیف هدر (شامل «تاریخ سررسید» و «طرف مقابل») در فایل پیدا نشد")

    def get(row, field):
        j = col.get(field)
        return row[j] if j is not None and j < len(row) else None

    checks, skipped, warnings = [], [], []
    for i, row in enumerate(rows[h + 1:], start=h + 2):
        if not any(norm(c) for c in row):
            continue                                  # ردیف خالی
        ctype = norm(get(row, "type"))
        if ctype == "تضمین":
            skipped.append({"row": i, "reason": "تضمین (وثیقه) - چک واقعی نیست"})
            continue
        due = norm(get(row, "due_date"))
        no = norm(get(row, "check_no"))
        if not due and not no:
            skipped.append({"row": i, "reason": "بدون سررسید و شماره"})
            continue
        clear = norm(get(row, "clear_date"))
        status_text = norm(get(row, "status"))
        # اگر ستون وضعیت نبود: در گزارش‌های پرداختنی داشتن «تاریخ وصول» یعنی پاس‌شده
        status = status_text or ("passed" if clear else "open")
        checks.append({
            "kind": kind,
            "party_code": norm(get(row, "party_code")),
            "party": norm(get(row, "party")),
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
            "amount": _to_number(get(row, "amount")),
            "status": status,
        })

    if checks and "amount" not in col:
        warnings.append("ستون «مبلغ» در این فایل نیست؛ مبلغ چک‌ها خالی ثبت می‌شود")
    if not checks:
        warnings.append("هیچ چک معتبری در فایل پیدا نشد")
    return {"checks": checks, "skipped": skipped, "warnings": warnings,
            "header_row": h + 1, "columns": col}


if __name__ == "__main__":
    import sys, json
    r = parse_checks_file(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "payable_check")
    print(json.dumps({k: v for k, v in r.items() if k != "checks"}, ensure_ascii=False, indent=2))
    print("تعداد چک:", len(r["checks"]))
    for c in r["checks"][:3]:
        print(c)