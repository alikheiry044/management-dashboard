// Requires js/api.js to be loaded before this file
// (requireLogin, getUser, logout, apiGet, apiUpload, formatNumber, toPersianDigits, escapeHtml)

if (!requireLogin()) throw new Error("not authenticated");

(function () {
    document.getElementById("logoutBtn")?.addEventListener("click", function (e) {
        e.preventDefault();
        logout();
    });

    const user = getUser();
    const welcome = document.getElementById("welcomeText");
    if (welcome && user) {
        welcome.textContent = user.full_name || user.email || "مدیر سیستم";
    }

    const MAX_UPLOAD_MB = 20;
    const ALLOWED_EXT = [".xlsx", ".xls", ".csv"];

    // شمارنده‌ی درخواست: فقط آخرین پاسخ نمایش داده شود
    let loadSeq = 0;

    async function loadSuppliers() {
        const message = document.getElementById("message");
        const tbody = document.getElementById("supplierBody");
        if (!tbody) return;

        const seq = ++loadSeq;

        if (message) {
            message.style.color = "";
            message.textContent = "در حال دریافت...";
        }
        tbody.innerHTML = "";

        try {
            const data = await apiGet("/suppliers/");
            if (seq !== loadSeq) return;

            // پشتیبانی از هر دو فرمت پاسخ (آرایه مستقیم یا پاسخ صفحه‌بندی‌شده)
            const items = Array.isArray(data) ? data : (data?.items || []);

            if (items.length === 0) {
                if (message) message.textContent = "تأمین‌کننده‌ای یافت نشد.";
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" style="text-align:center;color:#6b7280;padding:28px">
                            فایلی آپلود نشده است
                        </td>
                    </tr>`;
                return;
            }

            if (message) message.textContent = `${formatNumber(items.length)} تأمین‌کننده`;

            tbody.innerHTML = items.map((item) => `
                <tr>
                    <td>${escapeHtml(toPersianDigits(item.code || "-"))}</td>
                    <td><b>${escapeHtml(item.name || "-")}</b></td>
                    <td>${escapeHtml(formatNumber(item.debit_turnover))}</td>
                    <td>${escapeHtml(formatNumber(item.debit_balance))}</td>
                    <td>${escapeHtml(formatNumber(item.credit_balance))}</td>
                </tr>
            `).join("");
        } catch (error) {
            if (seq !== loadSeq) return;
            if (message) {
                message.style.color = "#d9343a";
                message.textContent = error.message || "خطا در دریافت تأمین‌کنندگان";
            }
            console.error("Suppliers load error:", error);
        }
    }

    function setUploadMsg(color, text) {
        const msg = document.getElementById("supplierUploadMsg");
        if (!msg) return;
        msg.style.color = color;
        msg.textContent = text;
    }

    function errorToText(e) {
        if (typeof e === "string") return e;
        if (e && typeof e === "object") return e.message || e.msg || e.error || JSON.stringify(e);
        return String(e);
    }

    document.getElementById("supplierUploadBtn")?.addEventListener("click", async function () {
        const fileInput = document.getElementById("supplierFile");
        const btn = this;
        const file = fileInput?.files?.[0];

        if (!file) return setUploadMsg("#d9343a", "لطفاً فایل را انتخاب کنید");

        const name = file.name.toLowerCase();
        if (!ALLOWED_EXT.some((ext) => name.endsWith(ext))) {
            return setUploadMsg("#d9343a", "فرمت فایل مجاز نیست (xlsx، xls یا csv)");
        }
        if (file.size === 0) return setUploadMsg("#d9343a", "فایل انتخاب‌شده خالی است");
        if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
            return setUploadMsg("#d9343a", `حجم فایل بیشتر از ${toPersianDigits(MAX_UPLOAD_MB)} مگابایت است`);
        }

        const originalText = btn.textContent;
        setUploadMsg("#6b7280", "در حال آپلود...");
        btn.disabled = true;
        btn.textContent = "در حال ارسال...";

        try {
            const result = await apiUpload("/suppliers/upload", file);

            // result ممکن است null باشد (پاسخ غیر JSON)؛ آپلود موفق را خطا نشان نده
            const parts = [result?.message || "آپلود انجام شد"];
            if (typeof result?.created === "number") {
                parts.push(`${toPersianDigits(result.created)} تأمین‌کننده ثبت شد`);
            }
            if (result?.skipped_duplicates) {
                parts.push(`${toPersianDigits(result.skipped_duplicates)} مورد تکراری رد شد`);
            }
            if (Array.isArray(result?.errors) && result.errors.length) {
                parts.push(`${toPersianDigits(result.errors.length)} ردیف خطا داشت (${errorToText(result.errors[0])})`);
            }

            // هیچ ردیفی ثبت نشده → موفقیت کامل نیست
            setUploadMsg(result?.created === 0 ? "#d97706" : "#15966f", parts.join(" — "));

            if (fileInput) fileInput.value = "";
            await loadSuppliers();
        } catch (error) {
            setUploadMsg("#d9343a", error.message || "آپلود ناموفق بود");
            console.error("Suppliers upload error:", error);
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", loadSuppliers);
    } else {
        loadSuppliers();
    }
})();
