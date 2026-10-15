from decimal import Decimal
from io import BytesIO
import xml.etree.ElementTree as ET

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.bank_check import BankCheck
from app.models.user import User

_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

router = APIRouter(
    prefix="/checks",
    tags=["Checks"],
    dependencies=[Depends(get_current_user)],
)

STATUS_MAP = {
    "خرج شده": "spent",
    "خرج‌شده": "spent",
    "پاس شده": "passed",
    "پاس‌شده": "passed",
    "پاس": "passed",
    "در جریان": "open",
    "نزد صندوق": "open",
    "واخواست": "returned",
    "برگشتی": "returned",
}


def normalize_persian(text) -> str:
    if text is None:
        return ""
    return str(text).replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").strip()


def clean_amount(value) -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return Decimal("0")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().translate(_DIGITS)
    text = text.replace(",", "").replace("،", "").replace("٬", "").replace(" ", "")
    if text.lower() in ("", "-", "—", "nan", "none"):
        return Decimal("0")
    try:
        return Decimal(text)
    except Exception:
        return Decimal("0")


def is_total_row(name: str) -> bool:
    n = normalize_persian(name)
    if not n:
        return True
    if n.startswith("جمع") or n.startswith("مجموع"):
        return True
    if "ارز" in n or "رکورد" in n or "مرور" in n:
        return True
    return False


def map_status(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "unknown"
    text = normalize_persian(raw)
    for k, v in STATUS_MAP.items():
        if k in text:
            return v
    return "unknown"


async def read_df(file: UploadFile) -> pd.DataFrame:
    if not file.filename:
        raise HTTPException(400, "فایل ارسال نشده")
    name = file.filename.lower()
    if not name.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(400, "فقط Excel یا CSV")

    content = await file.read()

    if name.endswith(".csv"):
        df = pd.read_csv(BytesIO(content))
        df.columns = [normalize_persian(str(c)).strip() for c in df.columns]
        return df

    head = content[:200].decode("utf-8", errors="ignore")
    if "<?xml" in head or "Workbook" in head:
        try:
            tree = ET.fromstring(content)
            ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
            rows = []
            for row in tree.findall(".//ss:Row", ns):
                cells = []
                col_idx = 0
                for cell in row.findall("ss:Cell", ns):
                    idx_attr = cell.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
                    if idx_attr:
                        target = int(idx_attr) - 1
                        while col_idx < target:
                            cells.append("")
                            col_idx += 1
                    data = cell.find("ss:Data", ns)
                    cells.append(data.text if data is not None and data.text else "")
                    col_idx += 1
                if any(str(c).strip() for c in cells):
                    rows.append(cells)
            if len(rows) < 2:
                raise ValueError("داده کافی نیست")

            # اگر ردیف اول عنوان گزارش باشد، ردیف بعدی هدر است
            header_idx = 0
            first = " ".join(str(c) for c in rows[0])
            if "مرور" in first or len(rows[0]) <= 2:
                header_idx = 1

            header = [normalize_persian(str(c)).strip() for c in rows[header_idx]]
            data_rows = rows[header_idx + 1 :]
            max_len = max(len(header), max((len(r) for r in data_rows), default=0))
            header = header + [f"col_{i}" for i in range(len(header), max_len)]
            normalized = []
            for r in data_rows:
                r = list(r) + [""] * (max_len - len(r))
                normalized.append(r[:max_len])
            return pd.DataFrame(normalized, columns=header[:max_len])
        except Exception as e:
            raise HTTPException(400, f"خواندن XML ناموفق: {e}")

    try:
        df = pd.read_excel(BytesIO(content), engine="calamine")
    except Exception:
        try:
            df = pd.read_excel(BytesIO(content), engine="openpyxl")
        except Exception as e:
            raise HTTPException(400, f"خواندن فایل ممکن نشد: {e}")

    df.columns = [normalize_persian(str(c)).strip() for c in df.columns]
    return df


def cell(row, key):
    v = row.get(key)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    t = str(v).strip()
    return t or None


async def import_checks(file, db, check_type, default_status, replace):
    df = await read_df(file)

    cmap = {
        "تفصیلی": "detail_code",
        "طرف مقابل": "party_name",
        "نوع": "movement_type",
        "شماره": "check_number",
        "شماره اعلامیه": "check_number",
        "شماره چک": "check_number",
        "مبلغ": "amount",
        "مبلغ چک": "amount",
        "مبلغ اعلامیه": "amount",
        "تاریخ سررسید": "due_date",
        "سررسید": "due_date",
        "تاریخ رسید": "receive_date",
        "تاریخ اعلامیه": "receive_date",
        "بانک": "bank_name",
        "حساب بانکی": "bank_name",
        "وضعیت": "status_raw",
        "تاریخ وصول، واخواست": "settle_date",
        "تاریخ وصول": "settle_date",
        "صاحب چک": "owner_name",
        "شرح": "description",
    }
    df = df.rename(columns={c: cmap[c] for c in df.columns if c in cmap})

    # مبلغ اختیاری
    if "amount" not in df.columns:
        for c in list(df.columns):
            if "مبلغ" in str(c).replace(" ", ""):
                df = df.rename(columns={c: "amount"})
                break

    amount_missing = "amount" not in df.columns
    if amount_missing:
        df["amount"] = 0

    if "party_name" not in df.columns:
        raise HTTPException(400, f"ستون طرف مقابل یافت نشد. ستون‌ها: {list(df.columns)}")

    items, errors, skipped = [], [], 0

    for idx, row in df.iterrows():
        try:
            party = row.get("party_name")
            if party is None or (isinstance(party, float) and pd.isna(party)) or not str(party).strip():
                skipped += 1
                continue

            name = normalize_persian(party)
            if is_total_row(name):
                skipped += 1
                continue

            amount = clean_amount(row.get("amount")) if not amount_missing else Decimal("0")
            if not amount_missing and amount <= 0:
                continue

            status = map_status(row.get("status_raw"))
            if status == "unknown" and default_status:
                status = default_status

            items.append(
                BankCheck(
                    check_type=check_type,
                    status=status,
                    detail_code=cell(row, "detail_code"),
                    party_name=name,
                    movement_type=cell(row, "movement_type"),
                    check_number=cell(row, "check_number"),
                    amount=amount,
                    due_date=cell(row, "due_date"),
                    receive_date=cell(row, "receive_date"),
                    bank_name=cell(row, "bank_name"),
                    owner_name=cell(row, "owner_name"),
                    settle_date=cell(row, "settle_date"),
                    description=cell(row, "description"),
                    source_file=file.filename,
                )
            )
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {e}")

    if not items:
        raise HTTPException(400, "هیچ چک معتبری پیدا نشد")

    if replace:
        await db.execute(delete(BankCheck).where(BankCheck.check_type == check_type))

    db.add_all(items)
    await db.commit()

    return {
        "message": "آپلود چک انجام شد",
        "created": len(items),
        "check_type": check_type,
        "amount_missing": amount_missing,
        "skipped": skipped,
        "errors": errors[:20],
    }


@router.post("/upload-receivable")
async def upload_receivable(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await import_checks(file, db, "receivable_check", "spent", replace)


@router.post("/upload-payable")
async def upload_payable(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # پیش‌فرض open؛ اگر در فایل «پاس» باشد map_status آن را می‌گیرد
    return await import_checks(file, db, "payable_check", "open", replace)


@router.get("/")
async def list_checks(
    check_type: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(BankCheck)
    if check_type:
        q = q.where(BankCheck.check_type == check_type)
    if status:
        q = q.where(BankCheck.status == status)
    q = q.order_by(BankCheck.id.desc())
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "check_type": r.check_type,
            "status": r.status,
            "detail_code": r.detail_code,
            "party_name": r.party_name,
            "check_number": r.check_number,
            "amount": str(r.amount),
            "due_date": r.due_date,
            "receive_date": r.receive_date,
            "bank_name": r.bank_name,
            "owner_name": r.owner_name,
            "settle_date": r.settle_date,
            "description": r.description,
        }
        for r in rows
    ]


@router.get("/summary")
async def checks_summary(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(BankCheck))).scalars().all()
    total = sum((r.amount for r in rows), Decimal(0))
    by_status = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {"count": len(rows), "total_amount": str(total), "by_status": by_status}

