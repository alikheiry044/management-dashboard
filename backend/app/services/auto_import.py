# app/services/auto_import.py
"""
موتور تشخیص خودکار ستون‌های اکسل
"""

import re
from typing import Dict, List, Optional
import pandas as pd

COLUMN_MAPPINGS = {
    "party_name": {
        "names": ["نام طرف حساب", "عنوان حساب", "شرح حساب", "نام مشتری", "نام تأمین‌کننده", "طرف حساب", "حساب", "عنوان",
                  "customer_name", "supplier_name", "party", "title", "شرح", "نام", "مشتری", "تأمین‌کننده"],
        "keywords": ["نام", "عنوان", "حساب", "طرف", "مشتری", "تأمین"]
    },
    "amount": {
        "names": ["مبلغ", "مانده", "مبلغ کل", "جمع", "مبلغ فاکتور", "amount", "total", "balance", "قیمت", "مبلغ ریال",
                  "مبلغ (ریال)", "مبلغ (تومان)", "مانده بدهکار", "مانده بستانکار", "گردش بدهکار", "گردش بستانکار",
                  "خالص", "جمع کل"],
        "keywords": ["مبلغ", "مانده", "جمع", "قیمت", "amount", "total", "balance"]
    },
    "code": {
        "names": ["کد", "کد حساب", "کد کالا", "کد تأمین‌کننده", "کد مشتری", "code", "id", "number", "شماره", "کد ملی",
                  "شناسه"],
        "keywords": ["کد", "code", "شماره", "id"]
    },
    "date": {
        "names": ["تاریخ", "تاریخ سند", "تاریخ فاکتور", "تاریخ رسید", "date", "transaction_date", "invoice_date"],
        "keywords": ["تاریخ", "date"]
    },
    "description": {
        "names": ["توضیحات", "شرح", "شرح سند", "توضیح", "بابت", "description", "note", "remark"],
        "keywords": ["توضیح", "شرح", "بابت", "description"]
    },
    "customer_name": {
        "names": ["نام مشتری", "مشتری", "خریدار", "customer", "client"],
        "keywords": ["مشتری", "خریدار", "customer"]
    },
    "remaining_amount": {
        "names": ["مانده", "باقی مانده", "باقی‌مانده فاکتور", "مانده بدهی", "remaining", "outstanding", "balance_due"],
        "keywords": ["باقی", "مانده بدهی", "remaining"]
    },
    "product_name": {
        "names": ["نام کالا", "شرح کالا", "کالا", "محصول", "نام محصول", "product", "item", "goods"],
        "keywords": ["کالا", "محصول", "product", "item"]
    },
    "quantity": {
        "names": ["تعداد", "موجودی", "تعداد موجودی", "qty", "quantity", "count"],
        "keywords": ["تعداد", "موجودی", "quantity"]
    },
    "unit_price": {
        "names": ["قیمت واحد", "بهای واحد", "نرخ", "unit_price", "price"],
        "keywords": ["قیمت", "نرخ", "price"]
    },
    "category": {
        "names": ["دسته‌بندی", "گروه", "دسته", "category", "group"],
        "keywords": ["دسته", "گروه", "category"]
    },
    "bank_name": {
        "names": ["نام بانک", "بانک", "bank", "bank_name"],
        "keywords": ["بانک", "bank"]
    },
    "account_number": {
        "names": ["شماره حساب", "شماره شبا", "شبا", "IBAN", "account_number"],
        "keywords": ["حساب", "شبا", "account"]
    },
    "phone": {
        "names": ["تلفن", "شماره تماس", "موبایل", "phone", "mobile", "tel"],
        "keywords": ["تلفن", "تماس", "phone"]
    },
    "invoice_number": {
        "names": ["شماره فاکتور", "شماره سند", "invoice_number", "invoice_no"],
        "keywords": ["شماره فاکتور", "invoice"]
    }
}


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("  ", " ")
    text = text.lower()
    return text


def fuzzy_match_score(col_name: str, possible_names: List[str]) -> float:
    col_normalized = normalize_text(col_name)
    best_score = 0.0

    for name in possible_names:
        name_normalized = normalize_text(name)

        if col_normalized == name_normalized:
            return 1.0

        if col_normalized in name_normalized or name_normalized in col_normalized:
            score = len(col_normalized) / max(len(col_normalized), len(name_normalized))
            best_score = max(best_score, score)

        col_words = set(col_normalized.split())
        name_words = set(name_normalized.split())
        if col_words and name_words:
            common = col_words.intersection(name_words)
            if common:
                score = len(common) / max(len(col_words), len(name_words))
                best_score = max(best_score, score)

    return best_score


def detect_columns(df: pd.DataFrame, file_type: str = "auto") -> Dict[str, Dict]:
    detected = {}
    columns = df.columns.tolist()

    expected_fields = {
        "receivable": ["party_name", "amount", "code"],
        "payable": ["party_name", "amount", "code"],
        "expense": ["code", "description", "amount"],
        "sales": ["customer_name", "amount", "invoice_number", "date"],
        "inventory": ["product_name", "quantity", "unit_price", "category"],
        "suppliers": ["party_name", "bank_name", "account_number", "phone"],
        "auto": ["party_name", "amount"]
    }

    fields_to_detect = expected_fields.get(file_type, expected_fields["auto"])

    for field in fields_to_detect:
        if field not in COLUMN_MAPPINGS:
            continue

        mapping = COLUMN_MAPPINGS[field]
        best_col = None
        best_score = 0.0

        for col in columns:
            if col in mapping["names"]:
                detected[field] = {"column": col, "confidence": 1.0}
                best_col = col
                break

            score = fuzzy_match_score(col, mapping["names"])

            for keyword in mapping["keywords"]:
                if keyword in normalize_text(col):
                    score = max(score, 0.7)

            if score > best_score and score >= 0.5:
                best_score = score
                best_col = col

        if best_col:
            detected[field] = {"column": best_col, "confidence": best_score}

    return detected


def preview_import(file_path: str, file_type: str = "auto", max_rows: int = 10) -> Dict:
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        detected = detect_columns(df, file_type)

        warnings = []
        required_fields = {
            "receivable": ["party_name", "amount"],
            "payable": ["party_name", "amount"],
            "sales": ["customer_name", "amount"],
            "inventory": ["product_name", "quantity"],
            "suppliers": ["party_name"]
        }

        required = required_fields.get(file_type, ["party_name", "amount"])
        for field in required:
            if field not in detected:
                warnings.append("فیلد '" + field + "' تشخیص داده نشد")
            elif detected[field]["confidence"] < 0.7:
                warnings.append(
                    "اطمینان کم برای '" + field + "' (" + str(int(detected[field]["confidence"] * 100)) + "%)")

        preview_data = []
        for _, row in df.head(max_rows).iterrows():
            preview_data.append({
                str(col): str(row[col]) if pd.notna(row[col]) else None
                for col in df.columns
            })

        return {
            "success": True,
            "columns": [str(c) for c in df.columns],
            "detected": detected,
            "preview": preview_data,
            "row_count": len(df),
            "warnings": warnings,
            "file_type": file_type
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_import(file_path: str, file_type: str, column_mapping: Dict[str, str]) -> Dict:
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        df = df.rename(columns=column_mapping)

        main_col = column_mapping.get("party_name", "party_name")
        if main_col in df.columns:
            df = df.dropna(subset=[main_col])

        amount_col = column_mapping.get("amount", "amount")
        if amount_col in df.columns:
            df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce').fillna(0)

        return {
            "success": True,
            "row_count": len(df),
            "columns_mapped": column_mapping,
            "preview": df.head(5).to_dict('records')
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
    