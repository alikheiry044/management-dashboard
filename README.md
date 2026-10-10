# 🏢 سامانه هوشمند کنترل کسب‌وکار Rayad (Rayad Business Control)

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791.svg)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

سامانه‌ای جامع و سازمانی (Enterprise) برای کنترل، پایش و نظارت هوشمند بر فرآیندهای مالی و عملیاتی شرکت. این پروژه با الهام از استانداردهای جهانی کنترل داخلی طراحی شده و دارای **موتور ریسک هوشمند** برای تشخیص خودکار ناهنجاری‌ها است.

---

## ✨ ویژگی‌های کلیدی

- 🎯 **داشبورد مدیرعامل**: نمای لحظه‌ای از سلامت مالی، KPIهای کلیدی و نمودارهای تحلیلی زنده.
- 🧠 **موتور ریسک هوشمند (AI Risk Engine)**: تشخیص خودکار فاکتورهای تکراری، مبالغ غیرعادی و تغییرات مشکوک در حساب بانکی تأمین‌کنندگان.
- ✨ **آپلود هوشمند (Smart Upload)**: پردازش فایل‌های اکسل با **تشخیص خودکار ستون‌ها** (Fuzzy Matching) بدون نیاز به تنظیمات دستی.
- 💰 **کنترل مالی و تراکنش‌ها**: مدیریت چرخه پرداخت، تأیید چندمرحله‌ای و پایش وضعیت ریسک هر تراکنش.
- ▣ **کنترل فاکتورها (3-Way Match)**: تطبیق هوشمند سفارش خرید، رسید انبار و فاکتور برای تشخیص مغایرت.
- 🏦 **عملیات بانکی**: پایش حساب‌ها، گردش تراکنش‌ها و ابزار مغایرت‌گیری بانکی.
- 📦 **مدیریت تأمین‌کنندگان و انبار**: رصد امتیاز ریسک تأمین‌کنندگان و هشدار کالاهای کم‌موجودی.
- 📈 **گزارش‌های مدیریتی**: تولید خودکار گزارش‌های مالی، عملکردی و ریسک با قابلیت خروجی.

---

## 🛠 پشته فناوری (Tech Stack)

| بخش | تکنولوژی‌ها |
| :--- | :--- |
| **Backend** | Python, FastAPI, SQLAlchemy (Async), Pydantic, Pandas |
| **Database** | PostgreSQL (via Docker) |
| **Frontend** | HTML5, CSS3 (Custom Variables), Vanilla JavaScript, Chart.js |
| **AI / Logic** | موتور ریسک سفارشی (Rule-based + Heuristic Matching) |
| **DevOps** | Docker, Docker Compose, Uvicorn, Git |

---

## 🚀 راهنمای راه‌اندازی سریع (Quick Start)

### ۱. پیش‌نیازها
- Python 3.10+
- Docker & Docker Compose
- Git

### ۲. کلون کردن پروژه
```bash
git clone https://github.com/alikheiry044/management-dashboard.git
cd management-dashboard
