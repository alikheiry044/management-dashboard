// Requires js/api.js to be loaded before this file in banks.html
// (requireLogin, logout, apiGet, formatNumber, toPersianDigits, escapeHtml, CURRENCY_LABEL)

if (!requireLogin()) throw new Error("not authenticated");

// کل کد داخل IIFE است تا نام توابع (renderTable، setText و ...) با banking.js تداخل نکند
(function () {
    document.getElementById("logoutBtn")?.addEventListener("click", function (e) {
        e.preventDefault();
        logout();
    });

    let bankItems = [];

    // صفر / مقدار نامعتبر به‌صورت «-» و منفی قرمز نشان داده می‌شود
    // (مقدار ممکن است رشته باشد، مثلاً "1250.50" از Decimal بک‌اند)
    function moneyCell(value) {
        const n = Number(value);
        if (!Number.isFinite(n) || n === 0) return `<span class="muted">-</span>`;
        const cls = n < 0 ? ' class="neg"' : "";
        return `<span${cls}>${escapeHtml(formatNumber(n))}</span>`;
    }

    function setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    // ارقام فارسی/عربی را به لاتین تبدیل می‌کند تا جست‌وجو با هر دو نوع رقم کار کند
    function normalizeDigits(text) {
        return String(text)
            .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06F0))
            .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
    }

    function renderTable() {
        const tbody = document.getElementById("bankBody");
        if (!tbody) return;

        const term = normalizeDigits(document.getElementById("searchInput")?.value || "")
            .trim()
            .toLowerCase();

        const rows = term
            ? bankItems.filter((b) =>
                `${b.detail_code ?? ""} ${b.title ?? ""} ${b.account_number ?? ""}`
                    .toLowerCase()
                    .includes(term))
            : bankItems;

        if (rows.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--muted);">موردی یافت نشد.</td></tr>`;
        } else {
            tbody.innerHTML = rows.map((b) => `
                <tr>
                    <td>${escapeHtml(toPersianDigits(b.detail_code))}</td>
                    <td>${escapeHtml(b.title)}</td>
                    <td>${b.account_number ? escapeHtml(toPersianDigits(b.account_number)) : '<span class="muted">-</span>'}</td>
                    <td>${moneyCell(b.opening_balance)}</td>
                    <td>${moneyCell(b.receipts)}</td>
                    <td>${moneyCell(b.payments)}</td>
                    <td><strong>${moneyCell(b.balance)}</strong></td>
                </tr>`).join("");
        }

        setText(
            "countText",
            term ? `${toPersianDigits(rows.length)} از ${toPersianDigits(bankItems.length)} حساب` : ""
        );
    }

    function sumField(field) {
        return bankItems.reduce((acc, b) => acc + (Number(b[field]) || 0), 0);
    }

    async function loadBanks() {
        const message = document.getElementById("message");
        try {
            const data = await apiGet("/banks/");
            bankItems = Array.isArray(data?.items) ? data.items : [];

            if (!bankItems.length) {
                if (message) message.textContent = "هنوز گزارشی بارگذاری نشده. فایل را از بالای صفحه آپلود کنید.";
                return;
            }

            // اگر بک‌اند totals نفرستاد، از روی ردیف‌ها حساب می‌شود
            const t = data.totals || {
                count: bankItems.length,
                receipts: sumField("receipts"),
                payments: sumField("payments"),
                balance: sumField("balance"),
            };

            setText("kpiCount", formatNumber(t.count));
            setText("kpiReceipts", formatNumber(t.receipts));
            setText("kpiPayments", formatNumber(t.payments));
            setText("kpiBalance", formatNumber(t.balance));

            const cards = document.getElementById("bankCards");
            if (cards) cards.style.display = "";

            if (message) {
                message.style.color = "";
                const d = data.uploaded_at ? new Date(data.uploaded_at) : null;
                const when = d && !Number.isNaN(d.getTime()) ? d.toLocaleString("fa-IR") : "";
                message.textContent =
                    `مبالغ به ${CURRENCY_LABEL}` +
                    (when ? ` — آخرین به‌روزرسانی: ${when}` : "") +
                    (data.source_file ? ` (${data.source_file})` : "");
            }
            renderTable();
        } catch (error) {
            if (message) {
                message.style.color = "var(--red)";
                message.textContent = error.message || "خطا در دریافت اطلاعات بانک‌ها";
            }
            console.error("Banks load error:", error);
        }
    }

    document.getElementById("searchInput")?.addEventListener("input", renderTable);

    loadBanks();
})();