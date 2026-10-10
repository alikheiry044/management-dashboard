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

function formatMoney(value) {
    return formatNumber(value) + " " + CURRENCY_LABEL;
}

// Render AI Risk Alerts (Rayad Style)
function renderAlerts(alerts) {
    const list = document.getElementById("alertsList");
    const empty = document.getElementById("alertsEmpty");
    if (!list) return;

    if (!alerts || alerts.length === 0) {
        list.innerHTML = "";
        if (empty) empty.style.display = "block";
        return;
    }
    if (empty) empty.style.display = "none";

    list.innerHTML = alerts.slice(0, 5).map(function(a) {
        const level = a.risk_level === "high" ? "high" : "medium";
        const riskLabel = a.risk_level === "high" ? "ریسک بالا" : "ریسک متوسط";
        const reason = a.note || (a.is_duplicate ? "فاکتور تکراری" : "مبلغ غیرعادی");
        const score = a.risk_score ? toPersianDigits(a.risk_score) + "/100" : "";
        const party = a.party_name || "نامشخص";

        return '<div class="alert-item alert-' + level + '">' +
            '<span class="alert-badge">' + riskLabel + ' ' + score + '</span>' +
            '<div style="flex:1">' +
                '<div class="alert-text">' + escapeHtml(party) + '</div>' +
                '<div class="alert-reason">' + escapeHtml(reason) + '</div>' +
            '</div>' +
            '<span class="alert-amount">' + formatMoney(a.amount) + '</span>' +
            '</div>';
    }).join("");
}

// Compose Management Report
var reportText = "";

function composeReport(summary, riskOverview) {
    var sections = [];
    var healthScore = Math.max(0, 100 - Math.round(riskOverview.average_risk_score || 0));

    sections.push({
        title: "📊 خلاصه وضعیت مالی",
        lines: [
            "مجموع تراکنش‌های ثبت‌شده: " + formatNumber(summary.total_transactions) + " مورد.",
            "مجموع مبلغ تراکنش‌ها: " + formatMoney(summary.total_amount) + ".",
            "تأییدشده: " + formatNumber(summary.approved) + " مورد | تسویه‌شده: " + formatNumber(summary.settled) + " مورد."
        ]
    });

    sections.push({
        title: "🛡 ارزیابی ریسک و سلامت کنترل",
        lines: [
            "امتیاز سلامت کنترل سازمان: " + toPersianDigits(healthScore) + " از ۱۰۰.", // ✅ اصلاح شد
            "تعداد تراکنش‌های پرریسک (High): " + formatNumber(riskOverview.high_risk_count) + " مورد.",
            "مجموع مبلغ در معرض ریسک: " + formatMoney(riskOverview.total_at_risk_amount) + "."
        ]
    });

    sections.push({
        title: "🔴 اقدامات فوری مورد نیاز",
        lines: [
            formatNumber(summary.pending_review) + " تراکنش در صف بررسی نیازمند تصمیم‌گیری.",
            formatNumber(summary.stopped) + " تراکنش به دلیل ریسک بالا متوقف شده‌اند."
        ]
    });

    return sections;
}

async function loadExecutiveDashboard() {
    var errorBox = document.getElementById("errorText");
    if (errorBox) errorBox.style.display = "none";

    try {
        var results = await Promise.all([
            apiGet("/finance/summary/overview"),
            apiGet("/finance/risk/overview"),
            apiGet("/finance/review-queue?risk_level=high")
        ]);

        var summary = results[0];
        var riskOverview = results[1];
        var queue = results[2];

        // 1. Update KPI Cards (Rayad Style Mapping)
        document.getElementById("kpi-total-amount").textContent = formatMoney(summary.total_amount);
        document.getElementById("kpi-total-tx-sub").textContent = "در " + formatNumber(summary.total_transactions) + " تراکنش";

        document.getElementById("kpi-stopped-count").textContent = formatNumber(summary.stopped) + " مورد";

        document.getElementById("kpi-pending-review").textContent = formatNumber(summary.pending_review) + " مورد";
        document.getElementById("kpi-high-risk-sub").textContent = formatNumber(riskOverview.high_risk_count) + " مورد پرریسک";

        var healthScore = Math.max(0, 100 - Math.round(riskOverview.average_risk_score));
        document.getElementById("kpi-health-score").textContent = toPersianDigits(healthScore);

        // 2. Update Manager Focus Section
        document.getElementById("focus-high-risk").textContent = formatNumber(riskOverview.high_risk_count) + " مورد";
        document.getElementById("focus-duplicates").textContent = "در حال تحلیل..."; // می‌تواند از یک API جداگانه بیاید
        document.getElementById("focus-at-risk").textContent = formatMoney(riskOverview.total_at_risk_amount);
        document.getElementById("focus-approved").textContent = formatNumber(summary.approved) + " مورد";

        // 3. Render Alerts
        renderAlerts(queue);

        // 4. Render Report
        var sections = composeReport(summary, riskOverview);
        var reportBody = document.getElementById("reportBody");
        var reportHTML = '<p style="font-size:11px;color:var(--muted);margin:0 0 12px 0;">تولید شده در: ' + toPersianDigits(new Date().toLocaleString('fa-IR')) + '</p>';

        sections.forEach(function(sec) {
            reportHTML += '<h4>' + sec.title + '</h4><ul>';
            sec.lines.forEach(function(line) {
                reportHTML += '<li>' + escapeHtml(line) + '</li>';
            });
            reportHTML += '</ul>';
        });

        reportBody.innerHTML = reportHTML;

        reportText = "گزارش مدیریتی هوشمند - " + new Date().toLocaleString('fa-IR') + "\n\n";
        sections.forEach(function(sec) {
            reportText += sec.title + "\n";
            sec.lines.forEach(function(l) {
                reportText += "- " + l + "\n";
            });
            reportText += "\n";
        });

        // 5. Load Charts
        loadAllCharts();

    } catch (error) {
        console.error("Dashboard Load Error:", error);
        if (errorBox) {
            errorBox.textContent = "⚠️ " + (error.message || "خطا در دریافت اطلاعات. مطمئن شوید بک‌اند در حال اجراست.");
            errorBox.style.display = "block";
        }
    }
}

// Copy Report
document.getElementById("copyReportBtn")?.addEventListener("click", async function () {
    try {
        await navigator.clipboard.writeText(reportText);
        var original = this.textContent;
        this.textContent = "✅ کپی شد";
        setTimeout(function() { this.textContent = original; }.bind(this), 2000);
    } catch (e) {
        this.textContent = "❌ کپی ممکن نشد";
    }
});

document.getElementById("printReportBtn")?.addEventListener("click", function() { window.print(); });

// Chart Loader (بدون eval)
async function loadSimpleChart(canvasId, apiPath, label, type) {
    type = type || "line";
    try {
        var data = await apiGet(apiPath);
        var canvas = document.getElementById(canvasId);
        if (!canvas) return;

        var key = canvasId + "Instance";
        if (window[key]) {
            window[key].destroy();
        }

        window[key] = new Chart(canvas, {
            type: type,
            data: {
                labels: data.labels || [],
                datasets: [{
                    label: label,
                    data: data.values || [],
                    borderColor: type === "bar" ? "#c9a227" : "#2563eb",
                    backgroundColor: type === "bar" ? "rgba(201,162,39,0.55)" : "rgba(37,99,235,0.1)",
                    borderWidth: 2,
                    tension: 0.3,
                    fill: type === "line",
                    pointRadius: 3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: true, position: "top" } },
                scales: { y: { beginAtZero: true } }
            }
        });
    } catch (error) {
        console.warn("Chart " + canvasId + " skipped:", error.message);
    }
}

async function loadAllCharts() {
    await loadSimpleChart("salesTrendChart", "/dashboard/sales-trend", "فروش", "line");
    await loadSimpleChart("receivablesTrendChart", "/dashboard/receivables-trend", "مطالبات", "bar");
}

// Initialize
document.addEventListener("DOMContentLoaded", loadExecutiveDashboard);
