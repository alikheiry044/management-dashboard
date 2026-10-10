import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Literal

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
# NOTE: adjust the name if your deps.py exposes the auth dependency differently
from app.core.deps import get_current_user
from app.models.report_snapshot import ReportSnapshot
from app.models.sales import SalesInvoice
from app.models.user import User

# Every route in this router requires a valid token
router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
    dependencies=[Depends(get_current_user)],
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

_EMPTY_AMOUNTS = {"", "-", "—", "nan", "none"}

# Matches summary rows such as "جمع", "جمع کل", "مجموع", "جمع:"
_TOTAL_ROW = re.compile(r"^(جمع|مجموع)(\s|:|$)")


def clean_amount(value):
    """
    Converts a cell value to Decimal.
    - empty / "-" / NaN  -> 0
    - "(1,000)"          -> -1000
    - Persian separators (٬ ٫) are handled
    - anything else unparsable raises ValueError (callers record it as a row error
      instead of silently turning it into 0)
    """
    if value is None or pd.isna(value):
        return Decimal("0")

    text = str(value).strip()
    if text.lower() in _EMPTY_AMOUNTS:
        return Decimal("0")

    negative = text.startswith("(") and text.endswith(")")
    text = (
        text.strip("()")
        .replace(",", "")
        .replace("،", "")
        .replace("٬", "")
        .replace("٫", ".")
        .replace(" ", "")
    )

    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"مبلغ نامعتبر: {value!r}")

    if not amount.is_finite():
        raise ValueError(f"مبلغ نامعتبر: {value!r}")

    return -amount if negative else amount


def normalize_persian(text: str) -> str:
    """تبدیل حروف عربی به معادل فارسی‌شان برای مقایسه‌ی درست نام ستون‌ها."""
    return (
        str(text).replace("ي", "ی")  # ي عربی -> ی فارسی
                 .replace("ك", "ک")  # ك عربی -> ک فارسی
    )


def is_total_row(name: str) -> bool:
    return bool(_TOTAL_ROW.match(normalize_persian(name).strip()))


def normalize_sale_date(value):
    """Real Excel dates -> YYYY-MM-DD; text dates are kept as-is; empty -> None."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):  # pd.Timestamp is a datetime subclass
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    return text or None


def read_ms_xml_spreadsheet(content: bytes) -> pd.DataFrame:
    """خواندن فایل‌های SpreadsheetML (XML اکسل ۲۰۰۳) که بعضی نرم‌افزارها با پسوند .xls تولید می‌کنند."""
    ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
    root = ET.fromstring(content)
    worksheet = root.find("ss:Worksheet", ns)
    table = worksheet.find("ss:Table", ns)
    rows = table.findall("ss:Row", ns)

    data = []
    for row in rows:
        cells = row.findall("ss:Cell", ns)
        values = []
        for cell in cells:
            data_el = cell.find("ss:Data", ns)
            values.append(data_el.text if data_el is not None else None)
        data.append(values)

    if not data:
        raise ValueError("جدولی در فایل پیدا نشد")

    header_idx = 0
    for i, r in enumerate(data):
        non_empty = [v for v in r if v not in (None, "")]
        if len(non_empty) > 1:
            header_idx = i
            break

    header = data[header_idx]
    body = data[header_idx + 1:]

    width = len(header)
    body = [r + [None] * (width - len(r)) for r in body]
    body = [r[:width] for r in body]

    return pd.DataFrame(body, columns=header)


async def read_uploaded_table(file: UploadFile) -> pd.DataFrame:
    """Shared reader (upload_finance.py can import this instead of keeping its own copy)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="فایل ارسال نشده است")

    filename = file.filename.lower()
    if not filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="فقط فایل Excel یا CSV مجاز است")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="حجم فایل بیشتر از ۲۰ مگابایت است")

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
        else:
            try:
                # calamine هم .xls و هم .xlsx واقعی را پشتیبانی می‌کند
                df = pd.read_excel(BytesIO(content), engine="calamine")
            except Exception:
                try:
                    # بعضی نرم‌افزارها خروجی .xls می‌دهند که در واقع XML اکسل ۲۰۰۳ است
                    df = read_ms_xml_spreadsheet(content)
                except Exception:
                    tables = pd.read_html(BytesIO(content))
                    if not tables:
                        raise ValueError("جدولی در فایل پیدا نشد")
                    df = tables[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خواندن فایل ناموفق بود: {str(e)}")

    df.columns = [normalize_persian(str(c).strip()) for c in df.columns]
    return df


def add_snapshot(db, *, report_type, total, row_count, filename, mode, user):
    """Adds a history row in the SAME transaction as the data (commit happens in the caller)."""
    db.add(ReportSnapshot(
        report_type=report_type,
        total_amount=total,
        row_count=row_count,
        mode=mode,
        filename=(filename or "")[:255],
        uploaded_by=getattr(user, "email", None),
    ))


@router.post("/sales-excel")
async def upload_sales_excel(
    file: UploadFile = File(...),
    mode: Literal["skip_duplicates", "append", "replace"] = Query(
        "skip_duplicates",
        description=(
            "skip_duplicates: فاکتورهای تکراری (مشتری+تاریخ+مبلغ) رد می‌شوند | "
            "append: همه اضافه می‌شوند | "
            "replace: همهٔ فاکتورهای قبلی حذف می‌شوند"
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    df = await read_uploaded_table(file)

    column_map = {
        "نوع تسویه": "settlement_type",
        "تاریخ": "sale_date",
        "نام مشتری": "customer_name",
        "خالص": "amount",
        "باقی مانده فاکتور": "remaining_amount",
        "باقی‌مانده فاکتور": "remaining_amount",
    }
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    missing = [c for c in ("sale_date", "customer_name", "amount") if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"ستون‌های ضروری یافت نشد: {missing}. ستون‌های فایل: {list(df.columns)}",
        )

    # Existing invoices as a multiset of (customer, date, amount) for duplicate detection
    existing = Counter()
    if mode == "skip_duplicates":
        result = await db.execute(
            select(SalesInvoice.customer_name, SalesInvoice.sale_date, SalesInvoice.amount)
        )
        for c, d, a in result.all():
            existing[(str(c).strip(), str(d).strip(), Decimal(str(a)))] += 1

    items = []
    errors = []
    skipped_totals = 0
    skipped_nonpositive = 0
    skipped_duplicates = 0

    for idx, row in df.iterrows():
        try:
            customer = row.get("customer_name")
            if pd.isna(customer) or str(customer).strip() == "":
                continue
            customer = str(customer).strip()

            if is_total_row(customer):
                skipped_totals += 1
                continue

            amount = clean_amount(row.get("amount"))
            remaining = (
                clean_amount(row.get("remaining_amount"))
                if "remaining_amount" in df.columns
                else Decimal("0")
            )

            if amount <= 0:
                skipped_nonpositive += 1  # e.g. sales returns; counted, not silent
                continue

            sale_date = normalize_sale_date(row.get("sale_date"))
            if sale_date is None:
                raise ValueError("تاریخ خالی است")

            if mode == "skip_duplicates":
                key = (customer, sale_date, amount)
                if existing[key] > 0:
                    existing[key] -= 1
                    skipped_duplicates += 1
                    continue

            settlement = row.get("settlement_type")
            description = f"نوع تسویه: {settlement}" if pd.notna(settlement) else None

            items.append(
                SalesInvoice(
                    customer_name=customer,
                    amount=amount,
                    remaining_amount=remaining,
                    sale_date=sale_date,
                    status="pending" if remaining > 0 else "completed",
                    description=description,
                )
            )
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {str(e)}")

    # Never wipe existing data when the file produced nothing usable
    if not items and (mode == "replace" or skipped_duplicates == 0):
        raise HTTPException(
            status_code=400,
            detail="هیچ ردیف معتبری در فایل پیدا نشد؛ داده‌های قبلی تغییری نکرد.",
        )

    if mode == "replace":
        await db.execute(delete(SalesInvoice))

    db.add_all(items)
    if items:
        add_snapshot(db, report_type="sales", total=sum((i.amount for i in items), Decimal(0)),
                     row_count=len(items), filename=file.filename, mode=mode, user=current_user)
    await db.commit()

    return {
        "message": "آپلود فاکتور فروش انجام شد",
        "created": len(items),
        "mode": mode,
        "skipped_duplicates": skipped_duplicates,
        "skipped_totals": skipped_totals,
        "skipped_nonpositive": skipped_nonpositive,
        "errors": errors[:30],
    }
