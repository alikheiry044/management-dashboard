from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# ساخت Engine (موتور اتصال به دیتابیس)
engine = create_async_engine(
    settings.DATABASE_URL,
    # لاگ SQL فقط وقتی SQL_ECHO=true باشد؛ در حالت عادی خاموش است
    echo=bool(getattr(settings, "SQL_ECHO", False)),
    # قبل از هر استفاده اتصال را چک می‌کند (بعد از sleep لپ‌تاپ یا قطع اتصال بیکار)
    pool_pre_ping=True,
)

# ساخت Session
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# پایه برای مدل‌ها
Base = declarative_base()


# وابستگی برای استفاده در APIها
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


