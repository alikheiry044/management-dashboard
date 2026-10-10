// Requires js/api.js to be loaded before this file
requireLogin();

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
    if (type === "receivable") return "مطالبات";
    if (type === "payable") return "بدهی‌ها";
    if (type === "expense") return "هزینه";
    return type;
}

async function loadTransactions() {
    messageEl.textContent = "در حال دریافت داده‌ها...";
    txBody.innerHTML = "";

    const type = typeFilter.value;
    const status = statusFilter.value;

    let path = "/finance/";
    const params = new URLSearchParams();
    if (type) params.append("type", type);
    if (status) params.append("status", status);
    if (params.toString()) path += "?" + params.toString();

    try {
        const data = await apiGet(path);
        // پشتیبانی از هر دو فرمت پاسخ (آرایه مستقیم یا پاسخ صفحه‌بندی‌شده)
        const items = Array.isArray(data) ? data : (data.items || []);

        messageEl.textContent = `نمایش ${toPersianDigits(items.length)} تراکنش`;

        if (items.length === 0) {
            txBody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--muted);">هیچ تراکنشی با این فیلترها یافت نشد.</td></tr>`;
            return;
        }

        txBody.innerHTML = items.map(tx => {
            const riskClass = getRiskBadgeClass(tx.risk_level);
            const statusClass = getStatusBadgeClass(tx.status);

            let actions = "";
            if (tx.status === "needs_review" || tx.status === "stopped") {
                actions = `
                    <button class="btn success sm" onclick="updateTxStatus(${tx.id}, 'approved')">تأیید</button>
                    <button class="btn danger sm" onclick="updateTxStatus(${tx.id}, 'stopped')">رد</button>
                `;
            } else if (tx.status === "normal") {
                actions = `<button class="btn warn sm" onclick="updateTxStatus(${tx.id}, 'needs_review')">بررسی</button>`;
            } else {
                actions = `<span class="bGray badge" style="padding: 4px 8px;">${STATUS_LABELS[tx.status]}</span>`;
            }

            // نمایش نشانگر تکراری بودن اگر موتور ریسک آن را تشخیص داده باشد
            const duplicateBadge = tx.is_duplicate ? '<span class="badge bRed" style="margin-right:4px; font-size:9px;" title="فاکتور تکراری">تکراری</span>' : '';
            const riskScoreText = tx.risk_score ? `<span style="font-size:10px; color:var(--muted); margin-right:4px;">(${toPersianDigits(tx.risk_score)}%)</span>` : "";

            return `
                <tr>
                    <td><span class="badge bBlue">${getTypeLabel(tx.type)}</span></td>
                    <td class="font-bold">${escapeHtml(tx.party_name || "-")}</td>
                    <td class="font-bold" dir="ltr" style="text-align:right;">${formatNumber(tx.amount)}</td>
                    <td><span class="badge ${statusClass}">${STATUS_LABELS[tx.status] || tx.status}</span></td>
                    <td>
                        <span class="badge ${riskClass}">${RISK_LABELS[tx.risk_level] || tx.risk_level}</span>
                        ${riskScoreText}
                        ${duplicateBadge}
                    </td>
                    <td style="max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(tx.note || tx.description || '')}">
                        ${escapeHtml(tx.note || tx.description || "-")}
                    </td>
                    <td>
                        <div style="display:flex; gap:4px;">
                            ${actions}
                        </div>
                    </td>
                </tr>
            `;
        }).join("");

    } catch (error) {
        console.error("Load Transactions Error:", error);
        messageEl.textContent = "خطا در دریافت داده‌ها: " + error.message;
        txBody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--red);">خطا در بارگذاری</td></tr>`;
    }
}

// تابع سراسری برای فراخوانی از onclick در HTML
window.updateTxStatus = async function(id, newStatus) {
    const statusText = STATUS_LABELS[newStatus] || newStatus;
    if (!confirm(`آیا از تغییر وضعیت این تراکنش به «${statusText}» اطمینان دارید؟`)) return;

    try {
        const token = getToken();
        const response = await fetch(`${API_URL}/finance/${id}/status`, {
            method: "PATCH",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                status: newStatus,
                note: `تغییر وضعیت از طریق مرکز تراکنش‌ها در ${new Date().toLocaleString('fa-IR')}`
            })
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(extractError(data, "تغییر وضعیت ناموفق بود"));
        }

        // بارگذاری مجدد جدول برای نمایش تغییرات
        await loadTransactions();

    } catch (error) {
        alert("خطا: " + error.message);
    }
};

// Event Listeners
reloadBtn.addEventListener("click", loadTransactions);
typeFilter.addEventListener("change", loadTransactions);
statusFilter.addEventListener("change", loadTransactions);

// بارگذاری اولیه
document.addEventListener("DOMContentLoaded", loadTransactions);


// ===== منطق آپلود سریع در صفحه تراکنش‌ها =====

const txUploadBtn = document.getElementById("txUploadBtn");
const txFileInput = document.getElementById("txFile");
const txUploadType = document.getElementById("txUploadType");
const txUploadMsg = document.getElementById("txUploadMsg");

if (txUploadBtn) {
    txUploadBtn.addEventListener("click", async () => {
        const file = txFileInput.files[0];
        if (!file) {
            txUploadMsg.style.color = "var(--red)";
            txUploadMsg.textContent = "⚠️ لطفاً ابتدا یک فایل انتخاب کنید.";
            return;
        }

        txUploadBtn.disabled = true;
        txUploadBtn.textContent = "در حال پردازش...";
        txUploadMsg.style.color = "var(--blue)";
        txUploadMsg.textContent = "⏳ در حال آپلود و ارزیابی ریسک توسط موتور هوشمند...";

        try {
            const type = txUploadType.value;
            let endpoint = "";

            if (type === "receivable") endpoint = "/upload/receivables-excel";
            else if (type === "payable") endpoint = "/upload/payables-excel";
            else if (type === "expense") endpoint = "/upload/expense-report";

            // استفاده از تابع apiUpload که در api.js تعریف کردیم
            const result = await apiUpload(endpoint, file);

            txUploadMsg.style.color = "var(--green)";
            txUploadMsg.textContent = `✅ موفق! ${toPersianDigits(result.created)} ردیف ثبت شد. (ریسک بالا: ${toPersianDigits(result.risk_summary?.high || 0)} مورد)`;

            // پاک کردن فایل و به‌روزرسانی خودکار جدول
            txFileInput.value = "";
            await loadTransactions();

        } catch (error) {
            txUploadMsg.style.color = "var(--red)";
            txUploadMsg.textContent = `❌ خطا: ${error.message}`;
        } finally {
            txUploadBtn.disabled = false;
            txUploadBtn.textContent = "آپلود و پردازش";
        }
    });
}
