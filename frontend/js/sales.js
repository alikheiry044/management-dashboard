// Requires js/api.js to be loaded before this file
requireLogin();

const user = getUser();
const welcome = document.getElementById("welcomeText");
if (welcome && user) {
    welcome.textContent = user.full_name || user.email || "مدیر سیستم";
}

document.getElementById("logoutBtn")?.addEventListener("click", function (e) {
    e.preventDefault();
    logout();
});

// --- داده‌های نمونه فاکتورها ---
const mockInvoices = [
    { id: "F-8231", supplier: "شرکت فولاد مبارکه", amount: 850000000, matchStatus: "mismatch", risk: "high", reason: "مبلغ غیرعادی + مغایرت با سفارش" },
    { id: "F-8232", supplier: "پتروشیمی بندر امام", amount: 420000000, matchStatus: "matched", risk: "low", reason: "" },
    { id: "F-8233", supplier: "شرکت ملی مس", amount: 1250000000, matchStatus: "mismatch", risk: "high", reason: "تغییر حساب بانکی تأمین‌کننده" },
    { id: "F-8234", supplier: "ایران خودرو", amount: 320000000, matchStatus: "matched", risk: "low", reason: "" },
    { id: "F-8235", supplier: "سایپا", amount: 280000000, matchStatus: "pending", risk: "medium", reason: "در انتظار رسید انبار" },
    { id: "F-8236", supplier: "شرکت فولاد مبارکه", amount: 850000000, matchStatus: "mismatch", risk: "high", reason: "فاکتور تکراری (مبلغ و تاریخ یکسان)" },
    { id: "F-8237", supplier: "مپنا", amount: 670000000, matchStatus: "matched", risk: "low", reason: "" },
    { id: "F-8238", supplier: "ذوب‌آهن اصفهان", amount: 540000000, matchStatus: "pending", risk: "medium", reason: "مغایرت جزئی با سفارش خرید" }
];

function formatMoney(value) {
    return formatNumber(value) + " " + CURRENCY_LABEL;
}

async function loadSalesDashboard() {
    // در آینده: const data = await apiGet("/invoices/");
    const data = mockInvoices;

    // 1. محاسبه KPIها
    const totalInvoices = data.length;
    const matched = data.filter(inv => inv.matchStatus === "matched").length;
    const mismatch = data.filter(inv => inv.matchStatus === "mismatch").length;
    const highRisk = data.filter(inv => inv.risk === "high").length;
    const matchRate = Math.round((matched / totalInvoices) * 100);

    document.getElementById("kpi-total-invoices").textContent = toPersianDigits(totalInvoices) + " فاکتور";
    document.getElementById("kpi-matched").textContent = toPersianDigits(matched) + " فاکتور";
    document.getElementById("kpi-match-rate").textContent = toPersianDigits(matchRate) + "٪ تطابق کامل";
    document.getElementById("kpi-mismatch").textContent = toPersianDigits(mismatch) + " فاکتور";
    document.getElementById("kpi-high-risk").textContent = toPersianDigits(highRisk) + " فاکتور";

    // 2. پر کردن جدول فاکتورهای نیازمند توجه (فقط mismatch و high risk)
    const tbody = document.getElementById("invoiceBody");
    const attentionInvoices = data.filter(inv => inv.matchStatus === "mismatch" || inv.risk === "high");

    if (attentionInvoices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--green);">✅ همه فاکتورها بدون مغایرت هستند.</td></tr>';
    } else {
        tbody.innerHTML = attentionInvoices.map(inv => {
            const matchBadge = inv.matchStatus === "matched"
                ? '<span class="badge bGreen">تطبیق‌شده</span>'
                : inv.matchStatus === "mismatch"
                ? '<span class="badge bRed">مغایرت‌دار</span>'
                : '<span class="badge bOrange">در انتظار</span>';

            const riskBadge = inv.risk === "high"
                ? '<span class="badge bRed">پرریسک</span>'
                : inv.risk === "medium"
                ? '<span class="badge bOrange">متوسط</span>'
                : '<span class="badge bGreen">پایین</span>';

            return `
                <tr>
                    <td style="font-family:monospace; font-weight:bold;">${toPersianDigits(inv.id)}</td>
                    <td>${escapeHtml(inv.supplier)}</td>
                    <td style="font-weight:bold;">${formatMoney(inv.amount)}</td>
                    <td>${matchBadge}</td>
                    <td>${riskBadge}</td>
                </tr>
            `;
        }).join("");
    }

    // 3. رسم نمودار روند فاکتورهای ماهانه
    renderInvoiceTrendChart();
}

function renderInvoiceTrendChart() {
    const canvas = document.getElementById("invoiceTrendChart");
    if (!canvas) return;

    new Chart(canvas, {
        type: "bar",
        data: {
            labels: ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور"],
            datasets: [{
                label: "تعداد فاکتورها",
                data: [280, 310, 295, 342, 328, 350],
                backgroundColor: "rgba(201, 162, 39, 0.55)",
                borderColor: "#c9a227",
                borderWidth: 2,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true, grid: { color: "#f3f4f6" } },
                x: { grid: { display: false } }
            }
        }
    });
}

// شبیه‌سازی خروجی اکسل
window.exportInvoices = function() {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = "⏳ در حال تهیه...";
    setTimeout(() => {
        btn.textContent = "✅ دانلود شد";
        setTimeout(() => { btn.textContent = originalText; }, 2000);
    }, 1000);
};

// Initialize
document.addEventListener("DOMContentLoaded", loadSalesDashboard);
