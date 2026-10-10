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

// --- داده‌های نمونه حساب‌های بانکی ---
const mockAccounts = [
    { id: 1, name: "بانک ملت - حساب جاری", bank: "ملت", number: "0123456789", balance: 2850000000, status: "clean" },
    { id: 2, name: "بانک صادرات - حساب سپرده", bank: "صادرات", number: "9876543210", balance: 1420000000, status: "clean" },
    { id: 3, name: "بانک پارسیان - حساب ارزی", bank: "پارسیان", number: "5551234567", balance: 680000000, status: "unmatched" },
    { id: 4, name: "بانک تجارت - حساب حقوق", bank: "تجارت", number: "7778889990", balance: 340000000, status: "clean" }
];

// --- داده‌های نمونه تراکنش‌ها ---
const mockTransactions = [
    { date: "1403/07/15", description: "واریز فروش - شرکت الف", amount: 450000000, type: "credit", status: "matched" },
    { date: "1403/07/15", description: "پرداخت حقوق - کارکنان", amount: -280000000, type: "debit", status: "matched" },
    { date: "1403/07/14", description: "خرید مواد اولیه - تأمین‌کننده ب", amount: -620000000, type: "debit", status: "unmatched" },
    { date: "1403/07/14", description: "واریز پیش‌فروش - مشتری ج", amount: 180000000, type: "credit", status: "matched" },
    { date: "1403/07/13", description: "پرداخت اجاره دفتر", amount: -45000000, type: "debit", status: "matched" },
    { date: "1403/07/13", description: "واریز سود سپرده", amount: 12000000, type: "credit", status: "matched" },
    { date: "1403/07/12", description: "خرید تجهیزات اداری", amount: -95000000, type: "debit", status: "unmatched" }
];

// --- داده‌های نمونه مغایرت‌ها ---
const mockReconciliations = [
    { account: "بانک پارسیان - حساب ارزی", amount: 45000000, reason: "تراکنش ثبت‌نشده در سیستم", status: "unmatched" },
    { account: "بانک ملت - حساب جاری", amount: 12000000, reason: "کارمزد بانکی کسر نشده", status: "unmatched" },
    { account: "بانک صادرات - حساب سپرده", amount: 0, reason: "تطابق کامل", status: "matched" }
];

function formatMoney(value) {
    return formatNumber(Math.abs(value)) + " " + CURRENCY_LABEL;
}

async function loadBankingDashboard() {
    // در آینده: const data = await apiGet("/banking/stats");
    const accounts = mockAccounts;
    const transactions = mockTransactions;
    const reconciliations = mockReconciliations;

    // 1. محاسبه KPIها
    const totalBalance = accounts.reduce((sum, acc) => sum + acc.balance, 0);
    const accountCount = accounts.length;
    const todayTransactions = transactions.filter(t => t.date === "1403/07/15").length;
    const todayAmount = transactions.filter(t => t.date === "1403/07/15").reduce((sum, t) => sum + Math.abs(t.amount), 0);
    const unmatchedCount = reconciliations.filter(r => r.status === "unmatched").length;
    const cleanAccounts = accounts.filter(a => a.status === "clean").length;

    document.getElementById("kpi-total-balance").textContent = formatMoney(totalBalance);
    document.getElementById("kpi-account-count").textContent = "در " + toPersianDigits(accountCount) + " حساب بانکی";
    document.getElementById("kpi-today-transactions").textContent = toPersianDigits(todayTransactions) + " تراکنش";
    document.getElementById("kpi-today-amount").textContent = "مبلغ: " + formatMoney(todayAmount);
    document.getElementById("kpi-reconciliations").textContent = toPersianDigits(unmatchedCount) + " مورد";
    document.getElementById("kpi-clean-accounts").textContent = toPersianDigits(cleanAccounts) + " حساب";

    // 2. نمایش لیست حساب‌ها
    const accountsList = document.getElementById("accountsList");
    accountsList.innerHTML = accounts.map(acc => {
        const statusBadge = acc.status === "clean"
            ? '<span class="badge bGreen">بدون مغایرت</span>'
            : '<span class="badge bOrange">مغایرت دارد</span>';

        return `
            <div class="account-card">
                <div class="account-header">
                    <div>
                        <div class="account-name">${escapeHtml(acc.name)}</div>
                        <div class="account-details">
                            <span>شماره: ${toPersianDigits(acc.number)}</span>
                            <span>بانک: ${escapeHtml(acc.bank)}</span>
                        </div>
                    </div>
                    <div style="text-align:left;">
                        <div class="account-balance">${formatMoney(acc.balance)}</div>
                        <div style="margin-top:4px;">${statusBadge}</div>
                    </div>
                </div>
            </div>
        `;
    }).join("");

    // 3. نمایش مغایرت‌ها
    const reconList = document.getElementById("reconciliationList");
    reconList.innerHTML = reconciliations.map(recon => {
        const statusClass = recon.status === "matched" ? "matched" : "unmatched";
        const statusText = recon.status === "matched" ? "✅ تطابق کامل" : "⚠️ مغایرت";

        return `
            <div class="recon-item">
                <div>
                    <div class="recon-label">${escapeHtml(recon.account)}</div>
                    <div style="font-size:11px;color:var(--muted);margin-top:4px;">${escapeHtml(recon.reason)}</div>
                </div>
                <div class="recon-value ${statusClass}">
                    ${recon.amount > 0 ? formatMoney(recon.amount) : statusText}
                </div>
            </div>
        `;
    }).join("");

    // 4. نمایش تراکنش‌ها
    const tbody = document.getElementById("transactionsBody");
    tbody.innerHTML = transactions.slice(0, 10).map(t => {
        const amountClass = t.type === "credit" ? "bGreen" : "bRed";
        const amountSign = t.type === "credit" ? "+" : "-";
        const statusBadge = t.status === "matched"
            ? '<span class="badge bGreen">تطبیق‌شده</span>'
            : '<span class="badge bOrange">مغایرت</span>';

        return `
            <tr>
                <td>${toPersianDigits(t.date)}</td>
                <td>${escapeHtml(t.description)}</td>
                <td style="font-weight:bold;" class="${amountClass}">${amountSign}${formatMoney(t.amount)}</td>
                <td>${statusBadge}</td>
            </tr>
        `;
    }).join("");

    // 5. رسم نمودار روند موجودی
    renderBalanceTrendChart();
}

function renderBalanceTrendChart() {
    const canvas = document.getElementById("balanceTrendChart");
    if (!canvas) return;

    new Chart(canvas, {
        type: "line",
        data: {
            labels: ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"],
            datasets: [{
                label: "موجودی کل (میلیارد تومان)",
                data: [4.8, 5.1, 4.9, 5.3, 5.0, 5.29, 5.29],
                borderColor: "#2563eb",
                backgroundColor: "rgba(37, 99, 235, 0.1)",
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointRadius: 5,
                pointBackgroundColor: "#fff",
                pointBorderColor: "#2563eb",
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y + " میلیارد تومان";
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: { color: "#f3f4f6" }
                },
                x: {
                    grid: { display: false }
                }
            }
        }
    });
}

// شبیه‌سازی مغایرت‌گیری
window.runReconciliation = function() {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = "⏳ در حال بررسی...";
    btn.disabled = true;

    setTimeout(() => {
        btn.textContent = "✅ مغایرت‌گیری انجام شد";
        setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
        }, 2000);
    }, 1500);
};

// شبیه‌سازی خروجی اکسل
window.exportTransactions = function() {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = "⏳ در حال تهیه...";
    setTimeout(() => {
        btn.textContent = "✅ دانلود شد";
        setTimeout(() => { btn.textContent = originalText; }, 2000);
    }, 1000);
};

// Initialize
document.addEventListener("DOMContentLoaded", loadBankingDashboard);

