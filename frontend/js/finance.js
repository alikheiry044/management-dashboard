// Requires js/api.js to be loaded before this file in finance.html
requireLogin();

document.getElementById("logoutBtn")?.addEventListener("click", function (e) {
    e.preventDefault();
    logout();
});

const MAX_ROWS = 200;

const TYPE_LABELS = {
    receivable: { text: "مطالبات", cls: "bBlue" },
    payable: { text: "بدهی", cls: "bOrange" },
    expense: { text: "هزینه", cls: "bRed" },
};

const TABS = [
    { key: "all", label: "همه" },
    { key: "receivable", label: "مطالبات" },
    { key: "payable", label: "بدهی‌ها" },
    { key: "expense", label: "هزینه‌ها" },
];

let allRows = [];
let activeTab = "all";

function renderType(type) {
    const info = TYPE_LABELS[type];
    if (!info) return escapeHtml(type);
    return `<span class="badge ${info.cls}">${info.text}</span>`;
}

function getRiskBadge(riskLevel, riskScore) {
    if (!riskLevel) return '<span class="badge bGray">نامشخص</span>';
    const cls = riskLevel === "high" ? "bRed" : (riskLevel === "medium" ? "bOrange" : "bGreen");
    const label = riskLevel === "high" ? "بالا" : (riskLevel === "medium" ? "متوسط" : "پایین");
    const score = riskScore ? ` (${toPersianDigits(riskScore)}%)` : "";
    return `<span class="badge ${cls}">${label}${score}</span>`;
}

function normalize(item) {
    const rawType = item.type || item.transaction_type || (item.amount < 0 ? "payable" : "receivable");
    const amountNum = Math.abs(Number(item.amount) || 0);

    let description = item.description || item.note || "";
    if (item.code) {
        description = `کد: ${toPersianDigits(item.code)} ${description}`;
    } else if (!description) {
        description = "-";
    }

    return {
        id: item.id,
        type: String(rawType).toLowerCase(),
        party: item.party || item.customer_name || item.party_name || "-",
        amount: amountNum,
        hasAmount: item.amount !== undefined && item.amount !== null,
        description: description,
        riskLevel: item.risk_level || "low",
        riskScore: item.risk_score || 0,
        status: item.status || "normal"
    };
}

function renderTabs() {
    const nav = document.getElementById("financeTabs");
    if (!nav) return;

    nav.innerHTML = TABS.map((t) => {
        const count = t.key === "all"
            ? allRows.length
            : allRows.filter((r) => r.type === t.key).length;
        const active = t.key === activeTab ? " active" : "";
        return `<button type="button" class="tab${active}" data-tab="${t.key}">${t.label} (${formatNumber(count)})</button>`;
    }).join("");
}

function renderTable() {
    const tbody = document.getElementById("financeBody");
    const summary = document.getElementById("financeSummary");
    if (!tbody) return;

    const filtered = activeTab === "all"
        ? allRows
        : allRows.filter((r) => r.type === activeTab);

    if (!filtered.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px; color: var(--muted);">موردی برای این بخش یافت نشد. فایل مربوط را آپلود کنید.</td></tr>';
        if (summary) summary.textContent = "";
        return;
    }

    tbody.innerHTML = filtered.slice(0, MAX_ROWS).map((r) => `
        <tr>
            <td>${renderType(r.type)}</td>
            <td>${escapeHtml(r.party)}</td>
            <td style="font-weight:bold; direction:ltr; text-align:right;">${r.hasAmount ? formatNumber(r.amount) : "۰"}</td>
            <td>${getRiskBadge(r.riskLevel, r.riskScore)}</td>
            <td>${escapeHtml(toPersianDigits(r.description))}</td>
        </tr>
    `).join("");

    if (summary) {
        const total = filtered.reduce((sum, r) => sum + r.amount, 0);
        let text = `${formatNumber(filtered.length)} ردیف — جمع: ${formatNumber(total)} ${CURRENCY_LABEL}`;
        if (filtered.length > MAX_ROWS) {
            text += ` (نمایش ${formatNumber(MAX_ROWS)} ردیف اول)`;
        }
        summary.textContent = text;
    }
}

document.getElementById("financeTabs")?.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-tab]");
    if (!btn) return;
    activeTab = btn.dataset.tab;
    renderTabs();
    renderTable();
});

async function loadFinanceData() {
    const message = document.getElementById("message");
    const tbody = document.getElementById("financeBody");

    if (!tbody) return;

    if (message) {
        message.style.color = "";
        message.textContent = "در حال دریافت اطلاعات...";
    }
    tbody.innerHTML = "";

    try {
        const response = await apiGet("/finance/");

        // ✅ اصلاح مهم: پشتیبانی از هر دو فرمت پاسخ (آرایه مستقیم یا Paginated)
        const data = Array.isArray(response) ? response : (response.items || []);

        if (data.length === 0) {
            if (message) message.textContent = "تراکنشی یافت نشد. از بخش آپلود، فایل اکسل را بارگذاری کنید.";
            renderTabs();
            return;
        }

        allRows = data.map(normalize);
        if (message) message.textContent = "";

        renderTabs();
        renderTable();
    } catch (error) {
        if (message) {
            message.style.color = "var(--red)";
            message.textContent = error.message || "خطا در دریافت لیست تراکنش‌ها";
        }
        console.error("Finance load error:", error);
    }
}

// اجرای اولیه
document.addEventListener("DOMContentLoaded", loadFinanceData);
