import re
from decimal import Decimal
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.finance import FinanceTransaction
from app.models.user import User

# اگر این توابع در upload.py هست از همان استفاده می‌شود
try:
    from app.api.upload import normalize_persian, clean_amount, add_snapshot, read_ms_xml_spreadsheet
except ImportError:
    def normalize_persian(text: str) -> str:
        if text is None:
            return ""
        t = str(text)
        t = t.replace("ي", "ی").replace("ك", "ک").replace("‌", " ").strip()
        return t

    def clean_amount(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return Decimal("0")
        text = str(value).strip().replace(",", "").replace("،", "").replace("٬", "")
        if text in ("", "-", "—", "nan", "None"):
            return Decimal("0")
        try:
            return Decimal(text)
        except Exception:
            return Decimal("0")

    def add_snapshot(*args, **kwargs):
        return None

    def read_ms_xml_spreadsheet(content: bytes):
        raise ValueError("xml reader not available")

# risk اختیاری
try:
    from app.services.risk_engine import assess_transaction_risk
except ImportError:
    async def assess_transaction_risk(db, data):
        amount = float(data.get("amount") or 0)
        if amount >= 20_000_000_000:
            level, score = "high", 90
        elif amount >= 5_000_000_000:
            level, score = "medium", 60
        else:
            level, score = "low", 10
        return {
            "risk_level": level,
            "risk_score": score,
            "is_duplicate": False,
            "amount_anomaly": level != "low",
            "requires_approval_from": "finance_manager" if level == "high" else None,
            "factors": [],
        }

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
    dependencies=[Depends(get_current_user)],
)

_TOTAL_ROW = re.compile(r"^(جمع|مجموع)(\s|:|$)")


def _is_total_row(name: str) -> bool:
    return bool(_TOTAL_ROW.match(normalize_persian(name)))


async def _read_uploaded_table(file: UploadFile) -> pd.DataFrame:
    if not file.filename:
        raise HTTPException(status_code=400, detail="فایل ارسال نشده است")

    filename = file.filename.lower()
    if not filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="فقط Excel یا CSV مجاز است")

    content = await file.read()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
        else:
            try:
                df = pd.read_excel(BytesIO(content), engine="calamine")
            except Exception:
                try:
                    df = read_ms_xml_spreadsheet(content)
                except Exception:
                    try:
                        tables = pd.read_html(BytesIO(content))
                        if not tables:
                            raise ValueError("جدولی پیدا نشد")
                        df = tables[0]
                    except Exception as e:
                        raise ValueError(str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خواندن فایل ناموفق بود: {e}")

    df.columns = [normalize_persian(str(c).strip()) for c in df.columns]
    return df


async def _import_balances(
    file: UploadFile,
    db: AsyncSession,
    *,
    tx_type: str,
    amount_header: str,
    label: str,
    replace: bool,
    user=None,
) -> dict:
    df = await _read_uploaded_table(file)

    column_map = {
        "کد": "code",
        "عنوان": "party_name",
        amount_header: "amount",
        "مانده": "amount",
        "مانده بستانکار": "amount",
    }
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    missing = [c for c in ("party_name", "amount") if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"ستون‌های ضروری یافت نشد: {missing}. ستون‌ها: {list(df.columns)}",
        )

    items = []
    errors = []
    skipped_totals = 0
    risk_summary = {"high": 0, "medium": 0, "low": 0}

    for idx, row in df.iterrows():
        try:
            party_name = row.get("party_name")
            if pd.isna(party_name) or str(party_name).strip() == "":
                continue

            name = str(party_name).strip()
            if _is_total_row(name):
                skipped_totals += 1
                continue

            code = row.get("code")
            description = f"کد: {code}" if pd.notna(code) else None
            amount = clean_amount(row.get("amount"))

            # مانده صفر را هم می‌توان رد کرد؛ اگر می‌خواهی صفرها ثبت شوند این if را بردار
            # if amount == 0:
            #     continue

            risk_result = await assess_transaction_risk(
                db,
                {
                    "amount": abs(amount),
                    "party_name": name,
                    "type": tx_type,
                    "description": description,
                },
            )

            risk_level = risk_result["risk_level"]
            risk_summary[risk_level] = risk_summary.get(risk_level, 0) + 1

            if risk_result.get("requires_approval_from") or risk_level in ("high", "medium"):
                status = "needs_review"
                approval_status = "pending" if risk_result.get("requires_approval_from") else "not_required"
            else:
                status = "normal"
                approval_status = "not_required"

            kwargs = dict(
                type=tx_type,
                amount=amount,
                transaction_date=None,
                party_name=name,
                description=description,
                status=status,
                risk_level=risk_level,
                needs_followup=(status == "needs_review"),
            )

            # فیلدهای اختیاری مدل
            for field, value in [
                ("risk_score", risk_result.get("risk_score", 0)),
                ("is_duplicate", risk_result.get("is_duplicate", False)),
                ("amount_anomaly", risk_result.get("amount_anomaly", False)),
                ("requires_approval_from", risk_result.get("requires_approval_from")),
                ("approval_status", approval_status),
                ("note", ", ".join(risk_result.get("factors") or []) or None),
            ]:
                if hasattr(FinanceTransaction, field):
                    kwargs[field] = value

            items.append(FinanceTransaction(**kwargs))
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {e}")

    if not items:
        raise HTTPException(status_code=400, detail="هیچ ردیف معتبری پیدا نشد")

    if replace:
        await db.execute(
            delete(FinanceTransaction).where(FinanceTransaction.type == tx_type)
        )

    db.add_all(items)
    try:
        add_snapshot(
            db,
            report_type="receivables" if tx_type == "receivable" else "payables",
            total=sum((abs(i.amount) for i in items), Decimal(0)),
            row_count=len(items),
            filename=file.filename,
            mode="replace" if replace else "append",
            user=user,
        )
    except Exception:
        pass

    await db.commit()

    return {
        "message": f"{label} انجام شد",
        "created": len(items),
        "skipped_totals": skipped_totals,
        "replaced_previous": replace,
        "errors": errors[:30],
        "risk_summary": risk_summary,
    }


@router.post("/receivables-excel")
async def upload_receivables_excel(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """مطالبات / مرور فروش / مانده مشتریان"""
    return await _import_balances(
        file, db,
        tx_type="receivable",
        amount_header="مانده",
        label="آپلود مطالبات / مانده مشتریان",
        replace=replace,
        user=current_user,
    )


@router.post("/payables-excel")
async def upload_payables_excel(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _import_balances(
        file, db,
        tx_type="payable",
        amount_header="مانده بستانکار",
        label="آپلود بدهی‌ها / بستانکاری",
        replace=replace,
        user=current_user,
    )


async def _import_movements(
    file: UploadFile,
    db: AsyncSession,
    *,
    tx_type: str,
    column_map: dict,
    amount_key: str,
    label: str,
    replace: bool,
    user=None,
):
    df = await _read_uploaded_table(file)
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    missing = [c for c in ("party_name", amount_key) if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"ستون‌های ضروری یافت نشد: {missing}. ستون‌ها: {list(df.columns)}",
        )

    items = []
    errors = []
    skipped_totals = 0

    for idx, row in df.iterrows():
        try:
            party = row.get("party_name")
            if pd.isna(party) or str(party).strip() == "":
                continue
            name = str(party).strip()
            if _is_total_row(name):
                skipped_totals += 1
                continue

            amount = clean_amount(row.get(amount_key))
            if amount <= 0:
                continue

            extra = row.get("extra_type")
            desc = row.get("description")
            ref = row.get("ref_no")
            tx_date = row.get("transaction_date")

            parts = []
            if pd.notna(extra):
                parts.append(f"نوع: {str(extra).strip()}")
            if pd.notna(desc) and str(desc).strip():
                parts.append(str(desc).strip())
            description = " | ".join(parts) if parts else None

            risk_result = await assess_transaction_risk(
                db,
                {
                    "amount": amount,
                    "party_name": name,
                    "type": tx_type,
                    "description": description,
                },
            )
            risk_level = risk_result["risk_level"]
            status = "needs_review" if risk_level in ("high", "medium") else "normal"

            kwargs = dict(
                type=tx_type,
                amount=amount,
                transaction_date=str(tx_date).strip() if pd.notna(tx_date) else None,
                party_name=name,
                description=description,
                status=status,
                risk_level=risk_level,
                needs_followup=(status == "needs_review"),
            )
            if hasattr(FinanceTransaction, "reference_number") and pd.notna(ref):
                kwargs["reference_number"] = str(ref).strip()
            if hasattr(FinanceTransaction, "risk_score"):
                kwargs["risk_score"] = risk_result.get("risk_score", 0)

            items.append(FinanceTransaction(**kwargs))
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {e}")

    if not items:
        raise HTTPException(status_code=400, detail="هیچ ردیف معتبری پیدا نشد")

    if replace:
        await db.execute(
            delete(FinanceTransaction).where(FinanceTransaction.type == tx_type)
        )

    db.add_all(items)
    await db.commit()

    return {
        "message": f"{label} انجام شد",
        "created": len(items),
        "skipped_totals": skipped_totals,
        "errors": errors[:30],
    }


@router.post("/payments-excel")
async def upload_payments_excel(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _import_movements(
        file, db,
        tx_type="payment",
        column_map={
            "نوع پرداخت": "extra_type",
            "طرف مقابل": "party_name",
            "شماره": "ref_no",
            "تاریخ": "transaction_date",
            "مبلغ پرداخت": "amount",
            "شرح": "description",
        },
        amount_key="amount",
        label="آپلود پرداخت‌ها",
        replace=replace,
        user=current_user,
    )


@router.post("/receipts-excel")
async def upload_receipts_excel(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _import_movements(
        file, db,
        tx_type="receipt",
        column_map={
            "نوع دریافت": "extra_type",
            "طرف مقابل": "party_name",
            "شماره": "ref_no",
            "تاریخ": "transaction_date",
            "مبلغ دریافت": "amount",
            "شرح": "description",
        },
        amount_key="amount",
        label="آپلود دریافت‌ها",
        replace=replace,
        user=current_user,
    )
