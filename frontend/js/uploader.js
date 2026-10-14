// Requires js/api.js to be loaded before this file
// (requireLogin, apiRequest, UPLOAD_TIMEOUT, formatNumber)
//
// پنل آپلود بالای صفحه‌ها (فروش، مالی). HTML لازم:
//   <section id="uploadPanel" data-kind="sales"> ... </section>
//   داخلش: #uploadFile ، #uploadBtn ، #uploadResult و در صورت نیاز #uploadType (لیست نوع فایل)
//
// کل کد داخل IIFE است تا نام ثابت‌ها (مثل UPLOAD_ENDPOINTS) با فایل‌های دیگر تداخل نکند.

(function () {
    // مسیرهای آپلود در بک‌اند.
    // ✅ sales و bank از کد بک‌اند تأیید شده‌اند.
    // ⚠️ receivable / payable / expense: همان مسیرهایی که transactions.js استفاده می‌کند.
    //    اگر ۴۰۴ گرفتی، مسیر واقعی را در http://localhost:8000/docs ببین.
    const UPLOAD_ENDPOINTS = {
        sales: "/upload/sales-excel",
        receivable: "/upload/receivables-excel",
        payable: "/upload/payables-excel",
        expense: "/upload/expense-report",
        bank: "/banks/upload",
        balances: "/party-balances/upload",   // مانده مشتریان (فایل «مرور فروش»)
        payment: "/upload/payments-excel",
        receipt: "/upload/receipts-excel",
    };

    const UPLOAD_ALLOWED_EXT = [".xlsx", ".xls", ".csv"];
    const UPLOAD_MAX_MB = 10;

    function initUploader() {
        const panel = document.getElementById("uploadPanel");
        if (!panel) return;

        const fileInput = document.getElementById("uploadFile");
        const button = document.getElementById("uploadBtn");
        const result = document.getElementById("uploadResult");
        const typeSelect = document.getElementById("uploadType");
        if (!fileInput || !button) return;

        // بدون ورود، ادامه نده (به صفحه‌ی ورود می‌رود)
        if (!requireLogin()) return;

        function setResult(text, ok) {
            if (!result) return;
            result.textContent = text;
            result.className = "upload-result" + (ok === true ? " ok" : ok === false ? " fail" : "");
        }

        function errorToText(e) {
            if (typeof e === "string") return e;
            if (e && typeof e === "object") return e.message || e.msg || e.error || JSON.stringify(e);
            return String(e);
        }

        // آیا نتیجه هشدار/خطای ردیفی دارد؟ (برای اینکه رفرش زود پیام را پاک نکند)
        function hasWarnings(data) {
            if (!data) return false;
            return (
                (Array.isArray(data.errors) && data.errors.length > 0) ||
                data.total_matches === false ||
                Boolean(data.skipped_duplicates)
            );
        }

        function summarize(data) {
            const parts = [(data && data.message) || "فایل با موفقیت بارگذاری شد"];
            if (!data) return parts[0];
            const keys = ["created", "inserted", "imported", "saved", "processed", "rows", "count"];
            const n = keys.map((k) => data[k]).find((v) => typeof v === "number");
            if (n !== undefined) parts.push(`${formatNumber(n)} ردیف ثبت شد`);
            if (data.skipped_zero) parts.push(`${formatNumber(data.skipped_zero)} ردیف با مانده‌ی صفر رد شد`);
            if (data.total_matches === false) parts.push("هشدار: جمع ردیف‌ها با ردیف جمع فایل نمی‌خواند");
            if (data.skipped_duplicates) parts.push(`${formatNumber(data.skipped_duplicates)} مورد تکراری رد شد`);
            if (Array.isArray(data.errors) && data.errors.length) {
                parts.push(`${formatNumber(data.errors.length)} ردیف خطا داشت (${errorToText(data.errors[0])})`);
            }
            return parts.join(" — ");
        }

        fileInput.addEventListener("change", () => setResult("", null));

        // عناصری که data-show-for دارند فقط برای همان نوع فایل نمایش داده می‌شوند
        function syncVisibility() {
            const kind = typeSelect ? typeSelect.value : panel.dataset.kind;
            panel.querySelectorAll("[data-show-for]").forEach((el) => {
                el.hidden = el.dataset.showFor !== kind;
            });
        }
        typeSelect?.addEventListener("change", () => { setResult("", null); syncVisibility(); });
        syncVisibility();

        button.addEventListener("click", async function () {
            const kind = typeSelect ? typeSelect.value : panel.dataset.kind;
            const path = UPLOAD_ENDPOINTS[kind];
            // پارامتر mode فقط برای فاکتورهای فروش معنی دارد
            const mode = kind === "sales" ? (document.getElementById("uploadMode")?.value || undefined) : undefined;
            const file = fileInput.files[0];

            if (!path) return setResult("نوع فایل نامشخص است", false);
            if (!file) return setResult("ابتدا یک فایل انتخاب کنید", false);

            const name = file.name.toLowerCase();
            if (!UPLOAD_ALLOWED_EXT.some((ext) => name.endsWith(ext))) {
                return setResult("فرمت فایل مجاز نیست (xlsx، xls یا csv)", false);
            }
            if (file.size === 0) {
                return setResult("فایل انتخاب‌شده خالی است", false);
            }
            if (file.size > UPLOAD_MAX_MB * 1024 * 1024) {
                return setResult(`حجم فایل بیشتر از ${formatNumber(UPLOAD_MAX_MB)} مگابایت است`, false);
            }

            if (mode === "replace" &&
                !confirm("همه‌ی داده‌های فعلی این بخش حذف و با این فایل جایگزین می‌شود. ادامه می‌دهید؟")) {
                return;
            }

            const originalText = button.textContent;
            let reloading = false;

            button.disabled = true;
            button.textContent = "در حال ارسال...";
            setResult("در حال ارسال و پردازش فایل...", null);

            try {
                const form = new FormData();
                form.append("file", file);
                form.append("file_type", kind);

                // apiRequest: هدر Authorization، timeout و مدیریت ۴۰۱ (خروج خودکار)
                // Content-Type را دستی نگذار؛ مرورگر boundary را خودش اضافه می‌کند.
                const data = await apiRequest(
                    `${path}${mode ? `?mode=${encodeURIComponent(mode)}` : ""}`,
                    { method: "POST", body: form, timeout: UPLOAD_TIMEOUT },
                    "آپلود ناموفق بود"
                );

                setResult(summarize(data), true);
                fileInput.value = "";
                if (typeSelect) window.location.hash = kind;   // بعد از رفرش، همان بخش باز بماند

                // دکمه تا رفرش غیرفعال می‌ماند (مخصوصاً مهم در حالت replace)
                // اگر هشدار یا خطا وجود دارد، زمان بیشتری برای خواندن پیام بگذار
                reloading = true;
                setTimeout(() => window.location.reload(), hasWarnings(data) ? 6000 : 1200);
            } catch (error) {
                setResult(errorToText(error) || "آپلود ناموفق بود", false);
                console.error("Upload error:", error);
            } finally {
                if (!reloading) {
                    button.disabled = false;
                    button.textContent = originalText;
                }
            }
        });
    }

    // اگر DOM هنوز آماده نیست، منتظر بمان (مثلاً وقتی اسکریپت در <head> است)
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initUploader);
    } else {
        initUploader();
    }
})();