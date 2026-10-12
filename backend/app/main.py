from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base
from app.models import User, FinanceTransaction, SalesInvoice
from app.api import suppliers
from app.api import auth, sales, finance, upload, dashboard
from app.api import banking, tasks, suppliers, smart_upload
from app.api.upload_finance import router as upload_finance_router
from app.api.upload_expense import router as expense_upload_router

from app.api import banks
from app.models.inventory import InventoryItem
from app.api.inventory import router as inventory_router
from app.models.bank_balance import BankBalance  # noqa: F401  (تا جدول ساخته شود)
from app.api import inventory
app = FastAPI(
    title="Management Dashboard API",
    description="سامانه گزارش‌دهی و داشبورد مدیریتی",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ جداول دیتابیس با موفقیت بررسی/ایجاد شدند")


app.include_router(auth.router)
app.include_router(sales.router)
app.include_router(finance.router)
app.include_router(upload.router)
app.include_router(expense_upload_router)
app.include_router(upload_finance_router)
app.include_router(inventory_router)
app.include_router(dashboard.router)
app.include_router(banking.router)
app.include_router(tasks.router)
app.include_router(suppliers.router)
app.include_router(smart_upload.router)
app.include_router(suppliers.router)
app.include_router(inventory.router)
app.include_router(banks.router)
app.include_router(inventory_router)
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "سیستم با موفقیت در حال اجرا است",
    }

from app.models.inventory import InventoryItem



from app.models.inventory import InventoryItem


