// Requires js/api.js
// (requireLogin, getUser, logout, apiGet, apiUpload, formatNumber, toPersianDigits, escapeHtml)

if (!requireLogin()) throw new Error("not authenticated");

// کل کد داخل IIFE است تا نام ثابت‌ها (RISK_LABELS، TYPE_LABELS و ...) با فایل‌های دیگر تداخل نکند
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

    const MAX_ROWS = 300;
    const MAX_UPLOAD_MB = 20;
    const ALLOWED_EXT = [".xlsx", ".xls", ".csv"];

    const TYPE_LABELS = {
        receivable: { text: "مطالبات", cls: "bGreen" },
        payable: { text: "بدهی", cls: "bOrange" },
        payment: { text: "پرداخت", cls: "bOrange" },
        receipt: { text: "دریافت", cls: "bBlue" },
        expense: { text: "هزینه", cls: "bGray" },
    };

    const RISK_LABELS = {
        low: { text: "کم", cls: "bGreen" },
        medium: { text: "متوسط", cls: "bOrange" },
        high: { text: "بالا", cls: "bRed" },
    };

    const endpointMap = {
        receivable: "/upload/receivables-excel",
        payable: "/upload/payables-excel",
        payment: "/upload/payments-excel",
        receipt: "/upload/receipts-excel",
        expense: "/upload/expense-report",
    };

    function renderType(type) {
        const info = TYPE_LABELS[String(type || "").toLowerCase()];
        if (!info) return escapeHtml(type || "-");
        return `<span class="badge ${info.cls}">${info.text}</span>`;
    }

    function renderRisk(level) {
        const info = RISK_LABELS[String(level || "").toLowerCase()];
        if (!info) return escapeHtml(level || "-");
        return `<span class="badge ${info.cls}">${info.text}</span>`;
    }

    // شمارنده‌ی درخواست: فقط آخرین پاسخ نمایش داده شود
    let loadSeq = 0;

    async function loadFinanceData() {
        const message = document.getElementById("message");
        const tbody = document.getElementById("financeBody");
        if (!tbody) return;

        const seq = ++loadSeq;

        if (message) {
            message.style.color = "";
            message.textContent = "در حال دریافت اطلاعات...";
        }
        tbody.innerHTML = "";

        try {
            const data = await apiGet("/finance/");
            if (seq !== loadSeq) return;

            // پشتیبانی از هر دو فرمت پاسخ (آرایه مستقیم یا پاسخ صفحه‌بندی‌شده)
            const items = Array.isArray(data) ? data : (data?.items || []);

            if (items.length === 0) {
                if (message) message.textContent = "تراکنشی یافت نشد.";
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" style="text-align:center;color:#6b7280;padding:28px">
                            داده‌ای برای نمایش وجود ندارد. از بالا فایل آپلود کنید.
                        </td>
                    </tr>`;
                return;
            }

            const rows = items.slice(0, MAX_ROWS);

            tbody.innerHTML = rows.map((item) => {
                const party = item.party_name || item.party || "-";
                const amount = item.amount != null ? formatNumber(item.amount) : "۰";
                let description = item.description || item.note || "-";
                if (item.reference_number) {
                    description = `شماره: ${item.reference_number} | ${description}`;
                }

                return `
                    <tr>
                        <td>${renderType(item.type)}</td>
                        <td><b>${escapeHtml(party)}</b></td>
                        <td>${escapeHtml(amount)}</td>
                        <td>${renderRisk(item.risk_level || "low")}</td>
                        <td>${escapeHtml(String(description))}</td>
                    </tr>
                `;
            }).join("");

            if (message) {
                message.textContent = items.length > MAX_ROWS
                    ? `نمایش ${formatNumber(MAX_ROWS)} ردیف اول از ${formatNumber(items.length)} مورد`
                    : `${formatNumber(items.length)} مورد`;
            }
        } catch (error) {
            if (seq !== loadSeq) return;
            if (message) {
                message.style.color = "#d9343a";
                message.textContent = error.message || "خطا در دریافت لیست مالی";
            }
            console.error("Finance load error:", error);
        }
    }

    function setUploadMsg(color, text) {
        const box = document.getElementById("uploadResult");
        if (!box) return;
        box.style.color = color;
        box.textContent = text;
    }

    function errorToText(e) {
        if (typeof e === "string") return e;
        if (e && typeof e === "object") return e.message || e.msg || e.error || JSON.stringify(e);
        return String(e);
    }

    async function uploadFinanceFile() {
        const type = document.getElementById("uploadType")?.value;
        const fileInput = document.getElementById("uploadFile");
        const btn = document.getElementById("uploadBtn");
        const file = fileInput?.files?.[0];

        if (!file) return setUploadMsg("#d9343a", "لطفاً فایل را انتخاب کنید");

        const endpoint = endpointMap[type];
        if (!endpoint) return setUploadMsg("#d9343a", "نوع فایل نامعتبر است");

        const name = file.name.toLowerCase();
        if (!ALLOWED_EXT.some((ext) => name.endsWith(ext))) {
            return setUploadMsg("#d9343a", "فرمت فایل مجاز نیست (xlsx، xls یا csv)");
        }
        if (file.size === 0) return setUploadMsg("#d9343a", "فایل انتخاب‌شده خالی است");
        if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
            return setUploadMsg("#d9343a", `حجم فایل بیشتر از ${toPersianDigits(MAX_UPLOAD_MB)} مگابایت است`);
        }

        const originalText = btn?.textContent;
        setUploadMsg("#6b7280", "در حال آپلود و پردازش...");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "در حال ارسال...";
        }

        try {
            const result = await apiUpload(endpoint, file);

            // result ممکن است null باشد (پاسخ غیر JSON)؛ آپلود موفق را خطا نشان نده
            const parts = [result?.message || "آپلود با موفقیت انجام شد"];
            if (typeof result?.created === "number") {
                parts.push(`${toPersianDigits(result.created)} ردیف ثبت شد`);
            }
            if (result?.risk_summary?.high) {
                parts.push(`ریسک بالا: ${toPersianDigits(result.risk_summary.high)} مورد`);
            }
            if (result?.skipped_duplicates) {
                parts.push(`${toPersianDigits(result.skipped_duplicates)} مورد تکراری رد شد`);
            }
            if (Array.isArray(result?.errors) && result.errors.length) {
                parts.push(`${toPersianDigits(result.errors.length)} ردیف خطا داشت (${errorToText(result.errors[0])})`);
            }

            // هیچ ردیفی ثبت نشده → موفقیت کامل نیست
            const color = result?.created === 0 ? "#d97706" : "#15966f";
            setUploadMsg(color, parts.join(" — "));

            if (fileInput) fileInput.value = "";
            await loadFinanceData();
        } catch (error) {
            setUploadMsg("#d9343a", error.message || "آپلود ناموفق بود");
            console.error("Finance upload error:", error);
        } finally {
            if (btn) {
                btn.disabled = false;
                if (originalText) btn.textContent = originalText;
            }
        }
    }

    document.getElementById("uploadBtn")?.addEventListener("click", uploadFinanceFile);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", loadFinanceData);
    } else {
        loadFinanceData();
    }
})();
