// Requires js/api.js to be loaded before this file
if (!requireLogin()) throw new Error("not authenticated");

const txBody = document.getElementById("txBody");
const messageEl = document.getElementById("message");
const typeFilter = document.getElementById("typeFilter");
const statusFilter = document.getElementById("statusFilter");
const reloadBtn = document.getElementById("reloadBtn");

const STATUS_LABELS = {
    normal: "عادی",
    needs_review: "نیازمند بررسی",
    approved: "تأییدشده",
    stopped: "متوقف",
    settled: "تسویه‌شده"
};

const RISK_LABELS = {
    high: "بالا",
    medium: "متوسط",
    low: "پایین"
};

const TYPE_LABELS = {
    receivable: "مطالبات",
    payable: "بدهی‌ها",
    expense: "هزینه"
};

const UPLOAD_ENDPOINTS = {
    receivable: "/upload/receivables-excel",
    payable: "/upload/payables-excel",
    expense: "/upload/expense-report"
};

// پسوندهای مجاز برای آپلود (در صورت نیاز تغییر بده)
const ALLOWED_UPLOAD_EXT = /\.(xlsx|xls|csv)$/i;

function getRiskBadgeClass(level) {
    if (level === "high") return "bRed";
    if (level === "medium") return "bOrange";
    return "bGreen";
}

function getStatusBadgeClass(status) {
    if (status === "needs_review" || status === "stopped") return "bOrange";
    if (status === "approved" || status === "settled") return "bGreen";
    return "bBlue";
}

function getTypeLabel(type) {
    return TYPE_LABELS[type] || type || "-";
}

function buildActions(tx) {
    const id = escapeHtml(tx.id);
    const btn = (cls, status, text) =>
        `<button class="btn ${cls} sm" data-action="status" data-id="${id}" data-status="${status}">${text}</button>`;

    if (tx.status === "needs_review") {
        return btn("success", "approved", "تأیید") + btn("danger", "stopped", "رد");
    }
    if (tx.status === "stopped") {
        // تراکنش متوقف‌شده را دوباره «رد» کردن بی‌معنی است؛ فقط تأیید
        return btn("success", "approved", "تأیید");
    }
    if (tx.status === "normal") {
        return btn("warn", "needs_review", "بررسی");
    }
    return `<span class="bGray badge" style="padding: 4px 8px;">${escapeHtml(STATUS_LABELS[tx.status] || tx.status || "-")}</span>`;
}

// شمارنده‌ی درخواست: اگر کاربر سریع فیلتر را عوض کند، فقط آخرین پاسخ نمایش داده می‌شود
let loadSeq = 0;

async function loadTransactions() {
    if (!txBody || !messageEl) return;

    const seq = ++loadSeq;
    messageEl.textContent = "در حال دریافت داده‌ها...";
    txBody.innerHTML = "";

    let path = "/finance/";
    const params = new URLSearchParams();
    if (typeFilter?.value) params.append("type", typeFilter.value);
    if (statusFilter?.value) params.append("status", statusFilter.value);
    if (params.toString()) path += "?" + params.toString();

    try {
        const data = await apiGet(path);
        if (seq !== loadSeq) return; // پاسخ قدیمی است

        // پشتیبانی از هر دو فرمت پاسخ (آرایه مستقیم یا پاسخ صفحه‌بندی‌شده)
        const items = Array.isArray(data) ? data : (data?.items || []);

        messageEl.textContent = `نمایش ${toPersianDigits(items.length)} تراکنش`;

        if (items.length === 0) {
            txBody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--muted);">هیچ تراکنشی با این فیلترها یافت نشد.</td></tr>`;
            return;
        }

        txBody.innerHTML = items.map(tx => {
            const riskClass = getRiskBadgeClass(tx.risk_level);
            const statusClass = getStatusBadgeClass(tx.status);
            const noteText = tx.note || tx.description || "";

            const duplicateBadge = tx.is_duplicate
                ? '<span class="badge bRed" style="margin-right:4px; font-size:9px;" title="فاکتور تکراری">تکراری</span>'
                : "";
            const riskScoreText = (tx.risk_score !== null && tx.risk_score !== undefined)
                ? `<span style="font-size:10px; color:var(--muted); margin-right:4px;">(${escapeHtml(toPersianDigits(tx.risk_score))}%)</span>`
                : "";

            return `
                <tr>
                    <td><span class="badge bBlue">${escapeHtml(getTypeLabel(tx.type))}</span></td>
                    <td class="font-bold">${escapeHtml(tx.party_name || "-")}</td>
                    <td class="font-bold" dir="ltr" style="text-align:right;">${escapeHtml(formatNumber(tx.amount))}</td>
                    <td><span class="badge ${statusClass}">${escapeHtml(STATUS_LABELS[tx.status] || tx.status || "-")}</span></td>
                    <td>
                        <span class="badge ${riskClass}">${escapeHtml(RISK_LABELS[tx.risk_level] || tx.risk_level || "-")}</span>
                        ${riskScoreText}
                        ${duplicateBadge}
                    </td>
                    <td style="max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(noteText)}">
                        ${escapeHtml(noteText || "-")}
                    </td>
                    <td>
                        <div style="display:flex; gap:4px;">
                            ${buildActions(tx)}
                        </div>
                    </td>
                </tr>
            `;
        }).join("");

    } catch (error) {
        if (seq !== loadSeq) return;
        console.error("Load Transactions Error:", error);
        messageEl.textContent = "خطا در دریافت داده‌ها: " + error.message;
        txBody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--red);">خطا در بارگذاری</td></tr>`;
    }
}

async function updateTxStatus(id, newStatus, button) {
    const statusText = STATUS_LABELS[newStatus] || newStatus;
    if (!confirm(`آیا از تغییر وضعیت این تراکنش به «${statusText}» اطمینان دارید؟`)) return;

    if (button) button.disabled = true;

    try {
        // از apiRequest استفاده می‌کنیم تا timeout و مدیریت ۴۰۱ هم اعمال شود
        await apiRequest(
            `/finance/${encodeURIComponent(id)}/status`,
            {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    status: newStatus,
                    note: `تغییر وضعیت از طریق مرکز تراکنش‌ها در ${new Date().toLocaleString("fa-IR")}`
                })
            },
            "تغییر وضعیت ناموفق بود"
        );

        // بارگذاری مجدد جدول برای نمایش تغییرات
        await loadTransactions();

    } catch (error) {
        alert("خطا: " + error.message);
    } finally {
        if (button) button.disabled = false;
    }
}

// Event delegation: به‌جای onclick داخل HTML (امن‌تر و بدون تابع سراسری)
txBody?.addEventListener("click", (e) => {
    const button = e.target.closest("button[data-action='status']");
    if (!button) return;
    updateTxStatus(button.dataset.id, button.dataset.status, button);
});

// Event Listeners
reloadBtn?.addEventListener("click", loadTransactions);
typeFilter?.addEventListener("change", loadTransactions);
statusFilter?.addEventListener("change", loadTransactions);

// بارگذاری اولیه (اگر DOM از قبل آماده بود، مستقیم اجرا شود)
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadTransactions);
} else {
    loadTransactions();
}


// ===== منطق آپلود سریع در صفحه تراکنش‌ها =====

const txUploadBtn = document.getElementById("txUploadBtn");
const txFileInput = document.getElementById("txFile");
const txUploadType = document.getElementById("txUploadType");
const txUploadMsg = document.getElementById("txUploadMsg");

function setUploadMsg(color, text) {
    if (!txUploadMsg) return;
    txUploadMsg.style.color = color;
    txUploadMsg.textContent = text;
}

if (txUploadBtn && txFileInput && txUploadType) {
    txUploadBtn.addEventListener("click", async () => {
        const file = txFileInput.files[0];
        if (!file) {
            setUploadMsg("var(--red)", "⚠️ لطفاً ابتدا یک فایل انتخاب کنید.");
            return;
        }

        if (!ALLOWED_UPLOAD_EXT.test(file.name)) {
            setUploadMsg("var(--red)", "⚠️ فرمت فایل مجاز نیست. فقط فایل اکسل (xlsx / xls) یا csv انتخاب کنید.");
            return;
        }

        const endpoint = UPLOAD_ENDPOINTS[txUploadType.value];
        if (!endpoint) {
            setUploadMsg("var(--red)", "⚠️ نوع فایل را انتخاب کنید.");
            return;
        }

        const originalText = txUploadBtn.textContent;
        txUploadBtn.disabled = true;
        txUploadBtn.textContent = "در حال پردازش...";
        setUploadMsg("var(--blue)", "⏳ در حال آپلود و ارزیابی ریسک توسط موتور هوشمند...");

        try {
            const result = await apiUpload(endpoint, file);

            const created = toPersianDigits(result?.created ?? 0);
            const high = toPersianDigits(result?.risk_summary?.high ?? 0);
            setUploadMsg("var(--green)", `✅ موفق! ${created} ردیف ثبت شد. (ریسک بالا: ${high} مورد)`);

            // پاک کردن فایل و به‌روزرسانی خودکار جدول
            txFileInput.value = "";
            await loadTransactions();

        } catch (error) {
            setUploadMsg("var(--red)", `❌ خطا: ${error.message}`);
        } finally {
            txUploadBtn.disabled = false;
            txUploadBtn.textContent = originalText;
        }
    });
}