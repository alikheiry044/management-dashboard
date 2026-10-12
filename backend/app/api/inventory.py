from decimal import Decimal

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.inventory import InventoryItem
from app.api.upload import read_uploaded_table, is_total_row, clean_amount, add_snapshot
from app.models.user import User

router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
    dependencies=[Depends(get_current_user)],
)


def _normalize_code(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@router.post("/upload")
async def upload_inventory(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    df = await read_uploaded_table(file)

    column_map = {
        "کد کالا": "code",
        "عنوان کالا": "title",
        "موجودی": "quantity",
        "موجودی-مقدار": "quantity",
        "موجودی-مبلغ": "total_value",
    }
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    missing = [c for c in ("code", "title", "quantity") if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"ستون‌های ضروری یافت نشد: {missing}. ستون‌ها: {list(df.columns)}",
        )

    items = []
    errors = []
    skipped = 0

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
                skipped += 1
                continue

            item = InventoryItem(
                code=code_text,
                title=title_text,
                quantity=clean_amount(row.get("quantity")),
            )
            if "total_value" in df.columns:
                item.total_value = clean_amount(row.get("total_value"))
            items.append(item)
        except Exception as e:
            errors.append(f"ردیف {idx + 2}: {e}")

    if not items:
        raise HTTPException(status_code=400, detail="هیچ ردیف معتبری پیدا نشد")

    if replace:
        await db.execute(delete(InventoryItem))

    db.add_all(items)
    try:
        add_snapshot(
            db,
            report_type="inventory",
            total=None,
            row_count=len(items),
            filename=file.filename,
            mode="replace" if replace else "append",
            user=current_user,
        )
    except Exception:
        pass

    await db.commit()
    return {
        "message": "آپلود تعدادی انجام شد",
        "created": len(items),
        "skipped_totals": skipped,
        "errors": errors[:20],
    }


@router.post("/upload-value")
async def upload_inventory_value(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    df = await read_uploaded_table(file)

    column_map = {
        "کد کالا": "code",
        "کد": "code",
        "موجودی-مبلغ": "total_value",
        "مبلغ": "total_value",
    }
    df = df.rename(columns={c: column_map[c] for c in df.columns if c in column_map})

    if "code" not in df.columns or "total_value" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"ستون کد یا مبلغ پیدا نشد. ستون‌ها: {list(df.columns)}",
        )

    existing = {
        i.code: i for i in (await db.execute(select(InventoryItem))).scalars().all()
    }

    matched = 0
    unmatched = 0
    total = Decimal("0")

    for idx, row in df.iterrows():
        code = row.get("code")
        if pd.isna(code):
            continue
        code_text = _normalize_code(code)
        if not code_text or is_total_row(code_text):
            continue

        item = existing.get(code_text)
        if not item:
            unmatched += 1
            continue

        value = clean_amount(row.get("total_value"))
        item.total_value = value
        total += value
        matched += 1

    if matched == 0:
        raise HTTPException(
            status_code=400,
            detail="هیچ کدی تطبیق نخورد. اول فایل تعدادی را آپلود کن.",
        )

    await db.commit()
    return {
        "message": "آپلود مبلغی انجام شد",
        "created": matched,
        "matched": matched,
        "unmatched": unmatched,
        "total_value": str(total),
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
            "name": i.title,
            "quantity": str(i.quantity),
            "total_value": str(i.total_value) if i.total_value is not None else None,
        }
        for i in items
    ]