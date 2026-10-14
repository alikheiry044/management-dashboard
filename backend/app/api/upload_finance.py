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

# ---------- helpers (با fallback) ----------
try:
    from app.api.upload import clean_amount, normalize_persian, add_snapshot, read_ms_xml_spreadsheet
except Exception:
    def normalize_persian(text):
        if text is None:
            return ""
        t = str(text)
        return t.replace("ي", "ی").replace("ك", "ک").replace("‌", " ").strip()

    def clean_amount(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return Decimal("0")
        text = str(value).strip().replace(",", "").replace("،", "").replace("٬", "")
        if text.lower() in ("", "-", "—", "nan", "none"):
            return Decimal("0")
        try:
            return Decimal(text)
        except Exception:
            return Decimal("0")

    def add_snapshot(*a, **k):
        return None

    def read_ms_xml_spreadsheet(content):
        raise ValueError("xml reader missing")

try:
    from app.services.risk_engine import assess_transaction_risk
except Exception:
    async def assess_transaction_risk(db, data):
        amount = float(data.get("amount") or 0)
        if amount >= 20_000_000_000:
            return {
                "risk_level": "high",
                "risk_score": 90,
                "requires_approval_from": "finance_manager",
                "factors": [],
            }
        if amount >= 5_000_000_000:
            return {
                "risk_level": "medium",
                "risk_score": 60,
                "requires_approval_from": None,
                "factors": [],
            }
        return {
            "risk_level": "low",
            "risk_score": 10,
            "requires_approval_from": None,
            "factors": [],
        }

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
    dependencies=[Depends(get_current_user)],
)

_TOTAL = re.compile(r"^(جمع|مجموع)(\s|:|$)")


def _is_total(name: str) -> bool:
    return bool(_TOTAL.match(normalize_persian(name or "")))


def _ensure_amount(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    """اگر ستون amount نباشد، ستونی که کلیدواژه مبلغ دارد را پیدا می‌کند (فاصله اضافی هم OK)."""
    if "amount" in df.columns:
        return df
    for c in df.columns:
        cleaned = str(c).replace(" ", "").replace("\u200c", "")
        for k in keywords:
            if k.replace(" ", "") in cleaned:
                return df.rename(columns={c: "amount"})
    return df


async def _read_df(file: UploadFile) -> pd.DataFrame:
    if not file.filename:
        raise HTTPException(status_code=400, detail="فایل ارسال نشده")
    name = file.filename.lower()
    if not name.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="فقط Excel یا CSV مجاز است")

    content = await file.read()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
        else:
            try:
                df = pd.read_excel(BytesIO(content), engine="calamine")
            except Exception:
                try:
                    df = read_ms_xml_spreadsheet(content)
                except Exception:
                    tables = pd.read_html(BytesIO(content))
                    if not tables:
                        raise ValueError("جدولی پیدا نشد")
                    df = tables[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خواندن فایل ناموفق: {e}")

    # نرمال‌سازی نام ستون + حذف فاصله‌های اضافی
    df.columns = [normalize_persian(str(c)).strip() for c in df.columns]
    return df


def _mk_tx(tx_type, amount, party, date=None, desc=None, ref=None, risk=None):
    risk = risk or {}
    level = risk.get("risk_level", "low")
    status = "needs_review" if level in ("high", "medium") else "normal"
    kw = dict(
        type=tx_type,
        amount=amount,
        transaction_date=date,
        party_name=party,
        description=desc,
        status=status,
        risk_level=level,
        needs_followup=(status == "needs_review"),
    )
    if hasattr(FinanceTransaction, "reference_number") and ref:
        kw["reference_number"] = str(ref).strip()
    if hasattr(FinanceTransaction, "risk_score"):
        kw["risk_score"] = risk.get("risk_score", 0)
    if hasattr(FinanceTransaction, "requires_approval_from"):
        kw["requires_approval_from"] = risk.get("requires_approval_from")
    if hasattr(FinanceTransaction, "approval_status"):
        kw["approval_status"] = (
            "pending" if risk.get("requires_approval_from") else "not_required"
        )
    return FinanceTransaction(**kw)


# ==================== پرداخت ====================
@router.post("/payments-excel")
async def upload_payments(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    df = await _read_df(file)
    cmap = {
        "نوع پرداخت": "pay_type",
        "طرف مقابل": "party_name",
        "شماره": "ref",
        "تاریخ": "date",
        "مبلغ پرداخت": "amount",
        "شرح": "desc",
    }
    df = df.rename(columns={c: cmap[c] for c in df.columns if c in cmap})
    df = _ensure_amount(df, ["مبلغ پرداخت"])

    if "party_name" not in df.columns or "amount" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"ستون طرف مقابل/مبلغ پرداخت لازم است. ستون‌ها: {list(df.columns)}",
        )

    items, errors, skipped = [], [], 0
    for idx, row in df.iterrows():
        try:
            party = row.get("party_name")
            if pd.isna(party) or not str(party).strip():
                continue
            name = str(party).strip()
            if _is_total(name):
                skipped += 1
                continue
            amount = clean_amount(row.get("amount"))
            if amount <= 0:
                continue

            parts = []
            if pd.notna(row.get("pay_type")):
                parts.append(f"نوع: {row.get('pay_type')}")
            if pd.notna(row.get("desc")) and str(row.get("desc")).strip():
                parts.append(str(row.get("desc")).strip())

            date = str(row.get("date")).strip() if pd.notna(row.get("date")) else None
            ref = str(row.get("ref")).strip() if pd.notna(row.get("ref")) else None
            risk = await assess_transaction_risk(
                db, {"amount": float(amount), "party_name": name, "type": "payment"}
            )
            items.append(
                _mk_tx("payment", amount, name, date, " | ".join(parts) or None, ref, risk)
            )
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {e}")

    if not items:
        raise HTTPException(status_code=400, detail="هیچ ردیف معتبری پیدا نشد")

    if replace:
        await db.execute(
            delete(FinanceTransaction).where(FinanceTransaction.type == "payment")
        )
    db.add_all(items)
    await db.commit()
    return {
        "message": "آپلود پرداخت‌ها انجام شد",
        "created": len(items),
        "skipped_totals": skipped,
        "errors": errors[:20],
    }


# ==================== دریافت ====================
@router.post("/receipts-excel")
async def upload_receipts(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    df = await _read_df(file)
    cmap = {
        "نوع دریافت": "rec_type",
        "طرف مقابل": "party_name",
        "شماره": "ref",
        "تاریخ": "date",
        "مبلغ دریافت": "amount",
        "شرح": "desc",
    }
    df = df.rename(columns={c: cmap[c] for c in df.columns if c in cmap})
    df = _ensure_amount(df, ["مبلغ دریافت"])

    if "party_name" not in df.columns or "amount" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"ستون طرف مقابل/مبلغ دریافت لازم است. ستون‌ها: {list(df.columns)}",
        )

    items, errors, skipped = [], [], 0
    for idx, row in df.iterrows():
        try:
            party = row.get("party_name")
            if pd.isna(party) or not str(party).strip():
                continue
            name = str(party).strip()
            if _is_total(name):
                skipped += 1
                continue
            amount = clean_amount(row.get("amount"))
            if amount <= 0:
                continue

            parts = []
            if pd.notna(row.get("rec_type")):
                parts.append(f"نوع: {row.get('rec_type')}")
            if pd.notna(row.get("desc")) and str(row.get("desc")).strip():
                parts.append(str(row.get("desc")).strip())

            date = str(row.get("date")).strip() if pd.notna(row.get("date")) else None
            ref = str(row.get("ref")).strip() if pd.notna(row.get("ref")) else None
            risk = await assess_transaction_risk(
                db, {"amount": float(amount), "party_name": name, "type": "receipt"}
            )
            items.append(
                _mk_tx("receipt", amount, name, date, " | ".join(parts) or None, ref, risk)
            )
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {e}")

    if not items:
        raise HTTPException(status_code=400, detail="هیچ ردیف معتبری پیدا نشد")

    if replace:
        await db.execute(
            delete(FinanceTransaction).where(FinanceTransaction.type == "receipt")
        )
    db.add_all(items)
    await db.commit()
    return {
        "message": "آپلود دریافت‌ها انجام شد",
        "created": len(items),
        "skipped_totals": skipped,
        "errors": errors[:20],
    }


# ==================== مطالبات / بدهی ====================
async def _import_balance(file, db, tx_type, amount_keywords, label, replace, user):
    df = await _read_df(file)
    cmap = {"کد": "code", "عنوان": "party_name", "مانده": "amount", "مانده بستانکار": "amount"}
    df = df.rename(columns={c: cmap[c] for c in df.columns if c in cmap})
    df = _ensure_amount(df, amount_keywords)

    if "party_name" not in df.columns or "amount" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"ستون عنوان/مانده لازم است. ستون‌ها: {list(df.columns)}",
        )

    items, errors, skipped = [], [], 0
    for idx, row in df.iterrows():
        try:
            party = row.get("party_name")
            if pd.isna(party) or not str(party).strip():
                continue
            name = str(party).strip()
            if _is_total(name):
                skipped += 1
                continue
            amount = clean_amount(row.get("amount"))
            code = row.get("code")
            desc = f"کد: {code}" if pd.notna(code) else None
            risk = await assess_transaction_risk(
                db,
                {
                    "amount": float(abs(amount)),
                    "party_name": name,
                    "type": tx_type,
                },
            )
            items.append(_mk_tx(tx_type, amount, name, None, desc, None, risk))
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
        "skipped_totals": skipped,
        "errors": errors[:20],
    }


@router.post("/receivables-excel")
async def upload_receivables(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _import_balance(
        file, db, "receivable", ["مانده"], "آپلود مطالبات", replace, current_user
    )


@router.post("/payables-excel")
async def upload_payables(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _import_balance(
        file,
        db,
        "payable",
        ["مانده بستانکار", "مانده"],
        "آپلود بدهی‌ها",
        replace,
        current_user,
    )


# سازگاری با suppliers.py و کدهای قدیمی
_read_uploaded_table = _read_df
_is_total_row = _is_total
