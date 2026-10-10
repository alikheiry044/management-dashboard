import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.inventory import InventoryItem
# Shared helpers live in upload.py (see the updated version)
from app.api.upload import read_uploaded_table, is_total_row, clean_amount, add_snapshot
from app.models.user import User

# Every route in this router requires a valid token (upload included)
router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
    dependencies=[Depends(get_current_user)],
)


def _normalize_code(value) -> str:
    """Excel numeric codes often arrive as floats: 1101.0 -> "1101"."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@router.post("/upload")
async def upload_inventory(
    file: UploadFile = File(...),
    replace: bool = Query(True, description="حذف موجودی قبلی قبل از ثبت فایل جدید"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    df = await read_uploaded_table(file)

    column_map = {
        "کد کالا": "code",
        "عنوان کالا": "title",
        "موجودی": "quantity",
    }
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    missing = [c for c in ("code", "title", "quantity") if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"ستون‌های ضروری یافت نشد: {missing}. ستون‌های فایل: {list(df.columns)}",
        )

    items = []
    errors = []
    skipped_totals = 0
    negative_quantity = 0

    for idx, row in df.iterrows():
        try:
            code = row.get("code")
            title = row.get("title")
            if pd.isna(code) or pd.isna(title):
                continue

            code_text = _normalize_code(code)
            title_text = str(title).strip()
            if not code_text or not title_text:
                continue

            if is_total_row(title_text) or is_total_row(code_text):
                skipped_totals += 1
                continue

            quantity = clean_amount(row.get("quantity"))
            if quantity < 0:
                negative_quantity += 1  # kept, but reported: usually a bookkeeping problem

            items.append(
                InventoryItem(code=code_text, title=title_text, quantity=quantity)
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
        await db.execute(delete(InventoryItem))

    db.add_all(items)
    add_snapshot(
        db,
        report_type="inventory",
        total=None,
        row_count=len(items),
        filename=file.filename,
        mode="replace" if replace else "append",
        user=current_user,
    )
    await db.commit()

    return {
        "message": "آپلود موجودی انبار انجام شد",
        "created": len(items),
        "skipped_totals": skipped_totals,
        "negative_quantity": negative_quantity,
        "replaced_previous": replace,
        "errors": errors[:30],
    }


@router.get("/")
async def list_inventory(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InventoryItem).order_by(InventoryItem.title))
    items = result.scalars().all()
    return [
        {
            "id": i.id,
            "code": i.code,
            "title": i.title,
            "quantity": str(i.quantity),
        }
        for i in items
    ]
