# app/api/smart_upload.py
"""
APIهای آپلود هوشمند با تشخیص خودکار ستون‌ها
"""

import os
import json
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.auto_import import preview_import, execute_import

router = APIRouter(prefix="/smart-upload", tags=["Smart Upload"])


@router.post("/preview")
async def preview_file(
        file: UploadFile = File(...),
        file_type: str = Form("auto"),
        current_user: User = Depends(get_current_user),
):
    allowed_types = ["receivable", "payable", "expense", "sales", "inventory", "suppliers", "auto"]
    if file_type not in allowed_types:
        raise HTTPException(status_code=400, detail="نوع فایل نامعتبر")

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = preview_import(tmp_path, file_type)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/confirm")
async def confirm_import(
        file: UploadFile = File(...),
        file_type: str = Form(...),
        column_mapping: str = Form(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    try:
        mapping = json.loads(column_mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="فرمت column_mapping نامعتبر است")

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = execute_import(tmp_path, file_type, mapping)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "message": "import با موفقیت انجام شد",
            "row_count": result["row_count"],
            "preview": result["preview"]
        }

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
            