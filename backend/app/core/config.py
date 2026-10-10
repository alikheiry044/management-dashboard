from pathlib import Path

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env  (این فایل: backend/app/core/config.py)
# مسیر نسبت به همین فایل محاسبه می‌شود، پس از هر پوشه‌ای که اجرا کنی پیدا می‌شود.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8-sig",  # فایل با BOM (مثلاً ذخیره‌شده با Notepad) هم خوانده می‌شود
        extra="ignore",  # متغیرهای اضافه در .env خطا نمی‌دهند
    )

    # --- بدون مقدار پیش‌فرض: حتماً باید در .env باشند ---
    DATABASE_URL: str
    SECRET_KEY: str

    # --- تنظیمات عادی ---
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 ساعت

    # لاگ SQL در ترمینال (فقط برای عیب‌یابی روشن کن)
    SQL_ECHO: bool = False

    # آدرس‌های فرانتند که اجازهٔ صدا زدن API را دارند (با کاما جدا کن)
    CORS_ORIGINS: str = "http://127.0.0.1:5500,http://localhost:5500"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32 or "change-this" in v.lower():
            raise ValueError(
                "SECRET_KEY ضعیف است (حداقل ۳۲ نویسه و نباید مقدار نمونه باشد)"
            )
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


try:
    settings = Settings()
except ValidationError as e:
    problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
    raise SystemExit(
        f"\n❌ تنظیمات برنامه ناقص یا نامعتبر است -> {problems}\n"
        f"   فایل .env را اینجا بساز: {ENV_FILE}\n"
        f"   (نمونه: .env.example)\n"
    )
