from decimal import Decimal

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
# NOTE: adjust the name if your deps.py exposes the auth dependency differently
from app.core.deps import get_current_user
from app.models.accounting_expense import AccountingExpense
# Shared helpers live in upload.py (see the updated version)
from app.api.upload import read_uploaded_table, is_total_row, clean_amount, add_snapshot
from app.models.user import User

# Every route in this router requires a valid token
router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
    dependencies=[Depends(get_current_user)],
)


def _normalize_code(value) -> str:
    """Excel numeric codes often arrive as floats: 1101.0 -> "1101"."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@router.post("/expense-report")
async def upload_expense_report(
    file: UploadFile = File(...),
    replace: bool = Query(True, description="حذف گزارش قبلی قبل از ثبت فایل جدید"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    df = await read_uploaded_table(file)

    column_map = {
        "کد": "code",
        "عنوان": "title",
        "گردش بدهکار": "debit_turnover",
        "گردش بستانکار": "credit_turnover",
        "مانده بدهکار": "debit_balance",
        "مانده بستانکار": "credit_balance",
    }
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    missing = [c for c in ("code", "title") if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"ستون‌های ضروری یافت نشد: {missing}. ستون‌های فایل: {list(df.columns)}",
        )

    items = []
    errors = []
    skipped_totals = 0

    for idx, row in df.iterrows():
        try:
            code = row.get("code")
            title = row.get("title")
            if pd.isna(code) or pd.isna(title):
                continue  # empty row

            code_text = _normalize_code(code)
            title_text = str(title).strip()
            if not code_text or not title_text:
                continue

            if is_total_row(title_text) or is_total_row(code_text):
                skipped_totals += 1
                continue

            items.append(
                AccountingExpense(
                    code=code_text,
                    title=title_text,
                    debit_turnover=clean_amount(row.get("debit_turnover")),
                    credit_turnover=clean_amount(row.get("credit_turnover")),
                    debit_balance=clean_amount(row.get("debit_balance")),
                    credit_balance=clean_amount(row.get("credit_balance")),
                )
            )
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {str(e)}")

    # Never wipe existing data when the file produced nothing usable
    if not items:
        raise HTTPException(
            status_code=400,
            detail="هیچ ردیف معتبری در فایل پیدا نشد؛ داده‌های قبلی تغییری نکرد.",
        )

    if replace:
        await db.execute(delete(AccountingExpense))

    db.add_all(items)
    add_snapshot(
        db,
        report_type="expense",
        total=sum((i.debit_balance for i in items), Decimal(0)),
        row_count=len(items),
        filename=file.filename,
        mode="replace" if replace else "append",
        user=current_user,
    )
    await db.commit()

    return {
        "message": "آپلود گزارش هزینه انجام شد",
        "created": len(items),
        "skipped_totals": skipped_totals,
        "replaced_previous": replace,
        "errors": errors[:30],
    }
