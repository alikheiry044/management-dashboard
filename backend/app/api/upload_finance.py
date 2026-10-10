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
from app.api.upload import normalize_persian, read_ms_xml_spreadsheet, clean_amount, add_snapshot
from app.models.user import User
from app.services.risk_engine import assess_transaction_risk

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
        raise HTTPException(status_code=400, detail="فقط فایل Excel یا CSV مجاز است")

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
                    tables = pd.read_html(BytesIO(content))
                    if not tables:
                        raise ValueError("جدولی در فایل پیدا نشد")
                    df = tables[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خواندن فایل ناموفق بود: {str(e)}")

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

    column_map = {"کد": "code", "عنوان": "party_name", amount_header: "amount"}
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    missing = [c for c in ("party_name", "amount") if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"ستون‌های ضروری یافت نشد: {missing}. ستون‌های فایل: {list(df.columns)}",
        )

    items = []
    errors = []
    skipped_totals = 0
    risk_summary = {"high": 0, "medium": 0, "low": 0, "duplicates": 0}

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

            # ===== ارزیابی ریسک هوشمند =====
            transaction_data = {
                "amount": amount,
                "party_name": name,
                "type": tx_type,
                "description": description,
            }

            risk_result = await assess_transaction_risk(db, transaction_data)

            risk_level = risk_result["risk_level"]
            risk_score = risk_result["risk_score"]
            is_duplicate = risk_result["is_duplicate"]
            amount_anomaly = risk_result["amount_anomaly"]
            requires_approval = risk_result["requires_approval_from"]

            risk_summary[risk_level] = risk_summary.get(risk_level, 0) + 1
            if is_duplicate:
                risk_summary["duplicates"] += 1

            if requires_approval:
                status = "needs_review"
                approval_status = "pending"
            elif risk_level in ("high", "medium"):
                status = "needs_review"
                approval_status = "not_required"
            else:
                status = "normal"
                approval_status = "not_required"

            items.append(
                FinanceTransaction(
                    type=tx_type,
                    amount=amount,
                    transaction_date=None,
                    party_name=name,
                    description=description,
                    status=status,
                    risk_level=risk_level,
                    risk_score=risk_score,
                    is_duplicate=is_duplicate,
                    amount_anomaly=amount_anomaly,
                    requires_approval_from=requires_approval,
                    approval_status=approval_status,
                    needs_followup=(status == "needs_review"),
                    note=", ".join(risk_result["factors"]) if risk_result["factors"] else None,
                )
            )

        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {str(e)}")

    if not items:
        raise HTTPException(
            status_code=400,
            detail="هیچ ردیف معتبری در فایل پیدا نشد؛ داده‌های قبلی تغییری نکرد.",
        )

    if replace:
        await db.execute(
            delete(FinanceTransaction).where(FinanceTransaction.type == tx_type)
        )

    db.add_all(items)
    add_snapshot(
        db,
        report_type="receivables" if tx_type == "receivable" else "payables",
        total=sum((i.amount for i in items), Decimal(0)),
        row_count=len(items),
        filename=file.filename,
        mode="replace" if replace else "append",
        user=user,
    )
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
        replace: bool = Query(True, description="حذف مطالبات قبلی قبل از ثبت فایل جدید"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    return await _import_balances(
        file, db,
        tx_type="receivable",
        amount_header="مانده",
        label="آپلود حساب‌های دریافتنی",
        replace=replace,
        user=current_user,
    )


@router.post("/payables-excel")
async def upload_payables_excel(
        file: UploadFile = File(...),
        replace: bool = Query(True, description="حذف بدهی‌های قبلی قبل از ثبت فایل جدید"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    return await _import_balances(
        file, db,
        tx_type="payable",
        amount_header="مانده بستانکار",
        label="آپلود مانده بستانکاری",
        replace=replace,
        user=current_user,
    )