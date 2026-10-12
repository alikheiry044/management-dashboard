import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Literal
import tempfile
import os

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.report_snapshot import ReportSnapshot
from app.models.sales import SalesInvoice
from app.models.user import User
from app.models.inventory import InventoryItem

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
    dependencies=[Depends(get_current_user)],
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

_EMPTY_AMOUNTS = {"", "-", "—", "nan", "none"}
_TOTAL_ROW = re.compile(r"^(جمع|مجموع)(\s|:|$)")


def clean_amount(value):
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
    return (
        str(text).replace("ي", "ی")
        .replace("ك", "ک")
    )


def is_total_row(name: str) -> bool:
    return bool(_TOTAL_ROW.match(normalize_persian(name).strip()))


def normalize_sale_date(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    return text or None


def read_ms_xml_spreadsheet(content: bytes) -> pd.DataFrame:
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
    """خواندن فایل اکسل با پشتیبانی از همه فرمت‌ها"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="فایل ارسال نشده است")

    filename = file.filename.lower()
    if not filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="فقط فایل Excel یا CSV مجاز است")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="حجم فایل بیشتر از ۲۰ مگابایت است")

    # ✅ راه‌حل: ذخیره موقت فایل با پسوند صحیح
    ext = os.path.splitext(filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(tmp_path)
        elif filename.endswith(".xlsx"):
            df = pd.read_excel(tmp_path, engine="openpyxl")
        elif filename.endswith(".xls"):
            # تلاش با xlrd برای فایل‌های قدیمی
            try:
                df = pd.read_excel(tmp_path, engine="xlrd")
            except Exception:
                # اگر xlrd کار نکرد، تلاش با XML
                try:
                    df = read_ms_xml_spreadsheet(content)
                except Exception:
                    # آخرین تلاش: read_html
                    tables = pd.read_html(tmp_path)
                    if not tables:
                        raise ValueError("جدولی در فایل پیدا نشد")
                    df = tables[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خواندن فایل ناموفق بود: {str(e)}")
    finally:
        # پاک کردن فایل موقت
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    df.columns = [normalize_persian(str(c).strip()) for c in df.columns]
    return df


def add_snapshot(db, *, report_type, total, row_count, filename, mode, user):
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
            description="skip_duplicates: فاکتورهای تکراری رد می‌شوند | append: همه اضافه می‌شوند | replace: همه حذف و جایگزین می‌شوند",
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
                skipped_nonpositive += 1
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


# ===== آپلود انبار (Inventory Upload) =====

@router.post("/inventory-excel")
async def upload_inventory_excel(
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """آپلود فایل اکسل انبار (مرور تعدادی یا مبلغی)"""

    # ✅ استفاده از read_uploaded_table که حالا با فایل موقت کار می‌کند
    df = await read_uploaded_table(file)

    # نرمال‌سازی نام ستون‌ها
    df.columns = [str(c).strip() for c in df.columns]

    created = 0
    risk_high = 0
    risk_medium = 0
    risk_low = 0
    skipped_rows = 0

    for idx, row in df.iterrows():
        try:
            code = None
            name = None
            quantity = 0.0
            amount = 0.0
            unit_price = 0.0

            for col in df.columns:
                col_str = str(col).strip()

                if "کد کالا" in col_str or col_str == "کد":
                    code = str(row[col]).strip() if pd.notna(row[col]) else None
                elif "عنوان کالا" in col_str or "کالا عنوان" in col_str or col_str == "کالا":
                    name = str(row[col]).strip() if pd.notna(row[col]) else None
                elif col_str == "موجودی" or "موجودی-مقدار" in col_str:
                    try:
                        quantity = float(row[col]) if pd.notna(row[col]) else 0.0
                    except (ValueError, TypeError):
                        quantity = 0.0
                elif "موجودی-واحد فرعی" in col_str:
                    try:
                        if quantity == 0.0:
                            quantity = float(row[col]) if pd.notna(row[col]) else 0.0
                    except (ValueError, TypeError):
                        pass
                elif "موجودی-مبلغ" in col_str:
                    try:
                        amount = float(row[col]) if pd.notna(row[col]) else 0.0
                    except (ValueError, TypeError):
                        amount = 0.0
                elif "فی متوسط" in col_str or "موجودی-فی" in col_str:
                    try:
                        unit_price = float(row[col]) if pd.notna(row[col]) else 0.0
                    except (ValueError, TypeError):
                        unit_price = 0.0

            if not name:
                skipped_rows += 1
                continue

            if amount == 0.0 and unit_price > 0.0:
                amount = quantity * unit_price

            risk_level = "low"
            risk_score = 0
            status = "active"

            if quantity == 0:
                risk_level = "high"
                risk_score = 85
                risk_high += 1
                status = "out_of_stock"
            elif quantity < 10:
                risk_level = "medium"
                risk_score = 50
                risk_medium += 1
                status = "low_stock"
            else:
                risk_level = "low"
                risk_score = 10
                risk_low += 1
                status = "active"

            inventory_item = InventoryItem(
                code=code,
                name=name,
                category="محصول",
                quantity=quantity,
                unit_price=unit_price,
                total_value=amount,
                risk_level=risk_level,
                risk_score=risk_score,
                status=status
            )
            db.add(inventory_item)
            created += 1

        except Exception as e:
            print(f"خطا در پردازش ردیف {idx + 2}: {e}")
            skipped_rows += 1
            continue

    await db.commit()

    return {
        "message": "آپلود انبار با موفقیت انجام شد",
        "created": created,
        "skipped_rows": skipped_rows,
        "risk_summary": {
            "high": risk_high,
            "medium": risk_medium,
            "low": risk_low
        }
    }


# ===== آپلود مانده حساب‌ها (Financial Accounts Upload) =====

@router.post("/financial-accounts-excel")
async def upload_financial_accounts_excel(
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """آپلود فایل اکسل مانده حساب اشخاص (دریافتنی/پرداختنی)"""

    df = await read_uploaded_table(file)
    df.columns = [str(c).strip() for c in df.columns]

    created = 0
    risk_high = 0
    risk_medium = 0
    risk_low = 0
    skipped_rows = 0
    total_amount = Decimal("0")

    for idx, row in df.iterrows():
        try:
            code = None
            name = None
            amount = Decimal("0")

            # پیدا کردن ستون‌ها با نام‌های مختلف
            for col in df.columns:
                col_str = str(col).strip()

                # کد
                if col_str == "کد" or "کد" in col_str:
                    code = str(row[col]).strip() if pd.notna(row[col]) else None

                # عنوان/نام
                elif col_str == "عنوان" or "عنوان" in col_str or "نام" in col_str:
                    name = str(row[col]).strip() if pd.notna(row[col]) else None

                # مانده/مبلغ
                elif col_str == "مانده" or "مبلغ" in col_str or "مانده" in col_str:
                    try:
                        # پاک‌سازی مبلغ (حذف کاما و تبدیل به عدد)
                        amount_str = str(row[col]).replace(",", "").strip()
                        amount = Decimal(amount_str) if amount_str else Decimal("0")
                    except:
                        amount = Decimal("0")

            # اگر نام خالی بود، رد کن
            if not name:
                skipped_rows += 1
                continue

            # تشخیص نوع (دریافتنی یا پرداختنی) بر اساس علامت مبلغ
            tx_type = "receivable" if amount > 0 else "payable"
            amount = abs(amount)

            # محاسبه ریسک بر اساس مبلغ
            risk_level = "low"
            risk_score = 0
            status = "normal"

            if amount > 50_000_000_000:  # بالای ۵۰ میلیارد
                risk_level = "high"
                risk_score = 85
                risk_high += 1
                status = "needs_review"
            elif amount > 10_000_000_000:  # بالای ۱۰ میلیارد
                risk_level = "medium"
                risk_score = 50
                risk_medium += 1
                status = "normal"
            else:
                risk_level = "low"
                risk_score = 10
                risk_low += 1
                status = "normal"

            # ساخت رکورد تراکنش مالی
            finance_tx = FinanceTransaction(
                type=tx_type,
                amount=amount,
                transaction_date=date.today().strftime("%Y-%m-%d"),
                party_name=name,
                description=f"مانده حساب - کد {code}",
                reference_number=code,
                status=status,
                risk_level=risk_level,
                risk_score=risk_score,
                is_duplicate=False,
                has_bank_change=False,
                amount_anomaly=(amount > 50_000_000_000),
                needs_followup=(status == "needs_review"),
                created_at=datetime.now()
            )
            db.add(finance_tx)
            created += 1
            total_amount += amount

        except Exception as e:
            print(f"خطا در پردازش ردیف {idx + 2}: {e}")
            skipped_rows += 1
            continue

    await db.commit()

    return {
        "message": "آپلود مانده حساب‌ها با موفقیت انجام شد",
        "created": created,
        "total_amount": str(total_amount),
        "skipped_rows": skipped_rows,
        "risk_summary": {
            "high": risk_high,
            "medium": risk_medium,
            "low": risk_low
        }
    }
