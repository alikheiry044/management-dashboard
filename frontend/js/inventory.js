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

// --- داده‌های نمونه (بعداً با داده واقعی از بک‌اند جایگزین می‌شود) ---
const mockInventoryData = [
    { code: "1001", name: "لپ‌تاپ Lenovo ThinkPad", category: "تجهیزات IT", qty: 45, price: 45000000, status: "normal" },
    { code: "1002", name: "مانیتور Samsung 24 inch", category: "تجهیزات IT", qty: 120, price: 8500000, status: "normal" },
    { code: "2001", name: "کاغذ A4 بسته 500 تایی", category: "ملزومات اداری", qty: 8, price: 1200000, status: "low" }, // کم‌موجودی
    { code: "2002", name: "خودکار آبی جعبه‌ای", category: "ملزومات اداری", qty: 0, price: 850000, status: "zero" }, // ناموجود
    { code: "3001", name: "میز مدیریت چوبی", category: "مبلمان", qty: 15, price: 12000000, status: "normal" },
    { code: "3002", name: "صندلی ارگونومیک", category: "مبلمان", qty: 3, price: 6500000, status: "low" },
    { code: "4001", name: "سرور HP ProLiant", category: "تجهیزات IT", qty: 2, price: 180000000, status: "normal" },
    { code: "5001", name: "کارتریج پرینتر HP", category: "ملزومات اداری", qty: 0, price: 3200000, status: "zero" }
];

function formatMoney(value) {
    return formatNumber(value) + " " + CURRENCY_LABEL;
}

async function loadInventoryDashboard() {
    // در آینده: const data = await apiGet("/inventory/stats");
    const data = mockInventoryData;

    // 1. محاسبه KPIها
    const totalItems = data.length;
    const totalValue = data.reduce((sum, item) => sum + (item.qty * item.price), 0);
    const lowStock = data.filter(item => item.status === "low").length;
    const zeroStock = data.filter(item => item.status === "zero").length;

    document.getElementById("kpi-total-items").textContent = toPersianDigits(totalItems) + " قلم";
    document.getElementById("kpi-total-value").textContent = formatMoney(totalValue);
    document.getElementById("kpi-low-stock").textContent = toPersianDigits(lowStock) + " قلم";
    document.getElementById("kpi-zero-stock").textContent = toPersianDigits(zeroStock) + " قلم";

    // 2. پر کردن جدول کالاهای نیازمند توجه (فقط low و zero)
    const tbody = document.getElementById("inventoryBody");
    const attentionItems = data.filter(item => item.status === "low" || item.status === "zero");

    if (attentionItems.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--green);">✅ همه کالاها در وضعیت مطلوبی هستند.</td></tr>';
    } else {
        tbody.innerHTML = attentionItems.map(item => {
            const statusBadge = item.status === "zero"
                ? '<span class="badge bRed">ناموجود</span>'
                : '<span class="badge bOrange">کم‌موجودی</span>';

            return `
                <tr>
                    <td style="font-family:monospace; font-weight:bold;">${toPersianDigits(item.code)}</td>
                    <td>${escapeHtml(item.name)}</td>
                    <td>${escapeHtml(item.category)}</td>
                    <td style="font-weight:bold;">${toPersianDigits(item.qty)}</td>
                    <td>${formatMoney(item.qty * item.price)}</td>
                    <td>${statusBadge}</td>
                </tr>
            `;
        }).join("");
    }

    // 3. رسم نمودار ارزش انبار به تفکیک دسته‌بندی
    renderInventoryChart(data);
}

function renderInventoryChart(data) {
    const canvas = document.getElementById("inventoryChart");
    if (!canvas) return;

    // گروه‌بندی ارزش بر اساس دسته‌بندی
    const categories = {};
    data.forEach(item => {
        const value = item.qty * item.price;
        categories[item.category] = (categories[item.category] || 0) + value;
    });

    const labels = Object.keys(categories);
    const values = Object.values(categories);
    const colors = ["#2563eb", "#c9a227", "#15966f", "#d9343a", "#8b5cf6"];

    new Chart(canvas, {
        type: "doughnut",
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 0,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "bottom", labels: { font: { family: "Tahoma", size: 12 }, padding: 15 } },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.label + ": " + formatMoney(context.raw);
                        }
                    }
                }
            }
        }
    });
}

// شبیه‌سازی خروجی اکسل
window.exportInventory = function() {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = "⏳ در حال تهیه...";
    setTimeout(() => {
        btn.textContent = "✅ دانلود شد";
        setTimeout(() => { btn.textContent = originalText; }, 2000);
    }, 1000);
};

// Initialize
document.addEventListener("DOMContentLoaded", loadInventoryDashboard);
