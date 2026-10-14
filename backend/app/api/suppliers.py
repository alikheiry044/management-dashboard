from decimal import Decimal
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.supplier import Supplier
from app.api.upload import normalize_persian, clean_amount

from app.api.upload_finance import _read_df as _read_uploaded_table, _is_total as _is_total_row
router = APIRouter(
    prefix="/suppliers",
    tags=["Suppliers"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/")
async def list_suppliers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Supplier).order_by(desc(Supplier.credit_balance))
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "debit_turnover": str(r.debit_turnover or 0),
            "debit_balance": str(r.debit_balance or 0),
            "credit_balance": str(r.credit_balance or 0),
        }
        for r in rows
    ]


@router.post("/upload")
async def upload_suppliers_excel(
    file: UploadFile = File(...),
    replace: bool = Query(True, description="حذف لیست قبلی قبل از ثبت"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    df = await _read_uploaded_table(file)

    column_map = {
        "کد": "code",
        "عنوان": "name",
        "گردش بدهکار": "debit_turnover",
        "مانده بدهکار": "debit_balance",
        "مانده بستانکار": "credit_balance",
    }
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    if "name" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"ستون عنوان پیدا نشد. ستون‌ها: {list(df.columns)}",
        )

    items = []
    errors = []
    skipped_totals = 0

    for idx, row in df.iterrows():
        try:
            name_raw = row.get("name")
            if pd.isna(name_raw) or str(name_raw).strip() == "":
                continue

            name = str(name_raw).strip()
            if _is_total_row(name):
                skipped_totals += 1
                continue

            code = row.get("code")
            code_text = None
            if pd.notna(code):
                if isinstance(code, float) and code.is_integer():
                    code_text = str(int(code))
                else:
                    code_text = str(code).strip()

            items.append(
                Supplier(
                    code=code_text,
                    name=name,
                    debit_turnover=clean_amount(row.get("debit_turnover")) if "debit_turnover" in df.columns else Decimal("0"),
                    debit_balance=clean_amount(row.get("debit_balance")) if "debit_balance" in df.columns else Decimal("0"),
                    credit_balance=clean_amount(row.get("credit_balance")) if "credit_balance" in df.columns else Decimal("0"),
                )
            )
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {str(e)}")

    if not items:
        raise HTTPException(
            status_code=400,
            detail="هیچ ردیف معتبری پیدا نشد؛ داده قبلی تغییر نکرد.",
        )

    if replace:
        await db.execute(delete(Supplier))

    db.add_all(items)
    await db.commit()

    return {
        "message": "آپلود تأمین‌کنندگان انجام شد",
        "created": len(items),
        "skipped_totals": skipped_totals,
        "errors": errors[:30],
    }
