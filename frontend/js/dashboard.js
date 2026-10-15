// Requires js/api.js (و Chart.js) to be loaded before this file
// (requireLogin, getUser, logout, apiGet, formatNumber, toPersianDigits, escapeHtml, CURRENCY_LABEL)

if (!requireLogin()) throw new Error("not authenticated");

(function () {
    const $ = (id) => document.getElementById(id);

    const user = getUser();
    const welcome = $("welcomeText");
    if (welcome && user) {
        welcome.textContent = user.full_name || user.email || "مدیر سیستم";
    }

    $("logoutBtn")?.addEventListener("click", function (e) {
        e.preventDefault();
        logout();
    });

    function setText(id, text) {
        const el = $(id);
        if (el) el.textContent = text;
    }

    // مقدار نامعتبر به‌جای «- ریال» فقط «-» نشان داده می‌شود
    function formatMoney(value) {
        if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "-";
        return formatNumber(value) + " " + CURRENCY_LABEL;
    }

    function formatCount(value) {
        if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "-";
        return formatNumber(value);
    }

    // امتیاز سلامت یک‌جا محاسبه می‌شود (قبلاً در دو جا جدا بود و یکی NaN می‌داد)
    function calcHealthScore(riskOverview) {
        const avg = Number(riskOverview?.average_risk_score) || 0;
        return Math.max(0, 100 - Math.round(avg));
    }

    // ===== کارت‌های KPI که منبع جداگانه دارند =====
    // آدرس APIهای زیر را با endpoint واقعی بک‌اند خودتان پر کنید.
    // null = هنوز منبعی تعریف نشده و کارت «-» نشان می‌دهد.
    // پاسخ می‌تواند عدد ساده یا آبجکتی با total / total_amount / value باشد.
    const KPI_ENDPOINTS = {
        kpiReceivables: null,   // مثلاً "/finance/receivables/total"
        kpiPayables: null,      // مثلاً "/finance/payables/total"
        kpiBank: null,          // مثلاً "/banks/balance"
        kpiInventory: null      // مثلاً "/inventory/value"
    };

    // مقادیر KPI که برای گزارش لازم است (کارت‌ها هنگام بارگذاری آن را پر می‌کنند)
    const kpiData = {};

    function pickValue(d) {
        if (d === null || d === undefined) return null;
        if (typeof d === "number" || typeof d === "string") return d;
        return d.total ?? d.total_amount ?? d.value ?? null;
    }

    async function loadMoneyKpi(id, path) {
        if (!path) {
            setText(id, "-");
            return;
        }
        try {
            const value = pickValue(await apiGet(path));
            kpiData[id] = value;
            setText(id, formatMoney(value));
        } catch (err) {
            console.warn("KPI " + id + " skipped:", err.message);
            setText(id, "-");
        }
    }

    async function loadChecksKpi() {
        try {
            const data = await apiGet("/checks/summary");
            kpiData.checks = data || null;
            setText("kpiChecks", formatCount(data?.count));
        } catch (err) {
            console.warn("KPI kpiChecks skipped:", err.message);
            setText("kpiChecks", "-");
        }
    }

    // این کارت‌ها مستقل از خلاصه مالی و ریسک بارگذاری می‌شوند
    function loadIndependentKpis() {
        const jobs = [loadChecksKpi()];
        Object.keys(KPI_ENDPOINTS).forEach(function (id) {
            jobs.push(loadMoneyKpi(id, KPI_ENDPOINTS[id]));
        });
        return Promise.all(jobs);
    }

    // ===== هشدارهای ریسک =====
    function renderAlerts(alerts) {
        const list = $("alertsList");
        const empty = $("alertsEmpty");
        if (!list) return;

        if (!alerts || alerts.length === 0) {
            list.innerHTML = "";
            if (empty) empty.style.display = "block";
            return;
        }
        if (empty) empty.style.display = "none";

        list.innerHTML = alerts.slice(0, 5).map(function (a) {
            const level = a.risk_level === "high" ? "high" : "medium";
            const riskLabel = a.risk_level === "high" ? "ریسک بالا" : "ریسک متوسط";
            const reason = a.note || (a.is_duplicate ? "فاکتور تکراری" : "مبلغ غیرعادی");
            const score = a.risk_score ? toPersianDigits(a.risk_score) + "/100" : "";
            const party = a.party_name || "نامشخص";

            return '<div class="alert-item alert-' + level + '">' +
                '<span class="alert-badge">' + escapeHtml(riskLabel + " " + score) + "</span>" +
                '<div style="flex:1">' +
                    '<div class="alert-text">' + escapeHtml(party) + "</div>" +
                    '<div class="alert-reason">' + escapeHtml(reason) + "</div>" +
                "</div>" +
                '<span class="alert-amount">' + escapeHtml(formatMoney(a.amount)) + "</span>" +
                "</div>";
        }).join("");
    }

    // ===== گزارش مدیریتی =====
    let reportText = "";

    const CHECK_STATUS_LABEL = {
        open: "در جریان",
        passed: "پاس‌شده",
        spent: "خرج‌شده",
        returned: "برگشتی",
        unknown: "نامشخص"
    };

    function hasValue(v) {
        return v !== null && v !== undefined && v !== "" && !Number.isNaN(Number(v));
    }

    function moneyLine(label, value) {
        return hasValue(value)
            ? label + ": " + formatMoney(value) + "."
            : label + ": اطلاعات در دسترس نیست.";
    }

    // گزارش به ترتیب چرخهٔ کسب‌وکار: فروش ← مطالبات و چک ← بانک ← بدهی ← انبار ← ریسک ← اقدامات
    function composeReport(summary, riskOverview, alertsCount) {
        const healthScore = calcHealthScore(riskOverview);
        const checks = kpiData.checks || null;

        // --- چک‌ها ---
        const checkLines = [];
        if (checks) {
            checkLines.push(
                "تعداد چک‌های ثبت‌شده: " + formatCount(checks.count) +
                " فقره، به مبلغ کل " + formatMoney(checks.total_amount) + "."
            );
            const parts = Object.entries(checks.by_status || {}).map(function (entry) {
                return (CHECK_STATUS_LABEL[entry[0]] || entry[0]) + ": " + formatNumber(entry[1]);
            });
            if (parts.length) checkLines.push("وضعیت چک‌ها — " + parts.join(" | ") + ".");
        } else {
            checkLines.push("اطلاعات چک‌ها در دسترس نیست.");
        }

        // --- اقدامات فوری ---
        const urgent = [
            formatNumber(summary.pending_review) + " تراکنش در صف بررسی نیازمند تصمیم‌گیری.",
            formatNumber(summary.stopped) + " تراکنش به دلیل ریسک بالا متوقف شده‌اند."
        ];
        const returned = Number(checks?.by_status?.returned) || 0;
        if (returned > 0) urgent.push(formatNumber(returned) + " چک برگشتی نیازمند پیگیری است.");
        if (alertsCount > 0) urgent.push(formatNumber(alertsCount) + " هشدار ریسک فعال است.");

        return [
            {
                title: "1️⃣ فروش و درآمد",
                lines: [
                    "مجموع تراکنش‌های ثبت‌شده: " + formatNumber(summary.total_transactions) + " مورد.",
                    "مجموع مبلغ تراکنش‌ها: " + formatMoney(summary.total_amount) + ".",
                    "تأییدشده: " + formatNumber(summary.approved) + " مورد | تسویه‌شده: " + formatNumber(summary.settled) + " مورد.",
                    "فاکتورهای باز (در انتظار بررسی): " + formatNumber(summary.pending_review) + " مورد."
                ]
            },
            {
                title: "2️⃣ مطالبات و چک‌ها",
                lines: [moneyLine("مجموع مطالبات", kpiData.kpiReceivables)].concat(checkLines)
            },
            {
                title: "3️⃣ نقدینگی (بانک)",
                lines: [moneyLine("مانده حساب‌های بانکی", kpiData.kpiBank)]
            },
            {
                title: "4️⃣ بدهی‌ها",
                lines: [moneyLine("مجموع بدهی‌ها", kpiData.kpiPayables)]
            },
            {
                title: "5️⃣ انبار",
                lines: [moneyLine("ارزش موجودی انبار", kpiData.kpiInventory)]
            },
            {
                title: "6️⃣ ریسک و سلامت کنترل",
                lines: [
                    "امتیاز سلامت کنترل سازمان: " + toPersianDigits(healthScore) + " از ۱۰۰.",
                    "تعداد تراکنش‌های پرریسک (High): " + formatNumber(riskOverview.high_risk_count) + " مورد.",
                    "مجموع مبلغ در معرض ریسک: " + formatMoney(riskOverview.total_at_risk_amount) + "."
                ]
            },
            {
                title: "🔴 اقدامات فوری مورد نیاز",
                lines: urgent
            }
        ];
    }

    async function loadExecutiveDashboard() {
        const errorBox = $("errorText");
        if (errorBox) errorBox.style.display = "none";

        // کارت‌های مستقل (چک، مطالبات، بدهی، بانک، انبار)؛ خطایشان به بقیه سرایت نمی‌کند
        const independentKpis = loadIndependentKpis();

        try {
            // خلاصه و ریسک ضروری‌اند؛ صف بررسی اختیاری است (خطایش کل داشبورد را خراب نکند)
            const [summary, riskOverview, queueRaw] = await Promise.all([
                apiGet("/finance/summary/overview"),
                apiGet("/finance/risk/overview"),
                apiGet("/finance/review-queue?risk_level=high").catch((err) => {
                    console.warn("Review queue skipped:", err.message);
                    return null;
                })
            ]);

            if (!summary || !riskOverview) {
                throw new Error("پاسخ سرور نامعتبر است");
            }

            const queue = Array.isArray(queueRaw) ? queueRaw : (queueRaw?.items || []);

            // 1. کارت‌های KPI
            setText("kpiSales", formatMoney(summary.total_amount));
            setText("kpiPending", formatCount(summary.pending_review));
            setText(
                "kpiAlerts",
                formatCount(queueRaw === null ? riskOverview.high_risk_count : queue.length)
            );

            // 2. هشدارها
            renderAlerts(queue);

            // 3. گزارش جامع (ترتیب: فروش ← مطالبات ← بانک ← بدهی ← انبار ← ریسک ← اقدامات)
            await independentKpis;   // چک، مطالبات، بدهی، بانک و انبار برای گزارش لازم‌اند
            const sections = composeReport(summary, riskOverview, queue.length);
            const reportBody = $("reportBody");
            if (reportBody) {
                let html = '<p class="report-date">تولید شده در: ' +
                    escapeHtml(new Date().toLocaleString("fa-IR")) + "</p>";
                sections.forEach(function (sec) {
                    html += "<h3>" + escapeHtml(sec.title) + "</h3><ul>";
                    sec.lines.forEach((line) => { html += "<li>" + escapeHtml(line) + "</li>"; });
                    html += "</ul>";
                });
                reportBody.innerHTML = html;
            }

            reportText = "گزارش مدیریتی هوشمند - " + new Date().toLocaleString("fa-IR") + "\n\n";
            sections.forEach(function (sec) {
                reportText += sec.title + "\n";
                sec.lines.forEach((l) => { reportText += "- " + l + "\n"; });
                reportText += "\n";
            });

            // 4. نمودارها (مستقل از هم، موازی)
            loadAllCharts();

        } catch (error) {
            console.error("Dashboard Load Error:", error);
            if (errorBox) {
                errorBox.textContent = "⚠️ " + (error.message || "خطا در دریافت اطلاعات. مطمئن شوید بک‌اند در حال اجراست.");
                errorBox.style.display = "block";
            }
        }
    }

    // ===== کپی گزارش =====
    // navigator.clipboard فقط در https یا localhost کار می‌کند؛ برای بقیه روش جایگزین
    function legacyCopy(text) {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand("copy"); } catch { /* ignore */ }
        ta.remove();
        return ok;
    }

    $("copyReportBtn")?.addEventListener("click", async function () {
        const btn = this;
        const original = btn.textContent;

        if (!reportText) {
            btn.textContent = "⏳ گزارش هنوز آماده نیست";
            setTimeout(() => { btn.textContent = original; }, 2000);
            return;
        }

        let ok = false;
        try {
            await navigator.clipboard.writeText(reportText);
            ok = true;
        } catch {
            ok = legacyCopy(reportText);
        }

        btn.textContent = ok ? "✅ کپی شد" : "❌ کپی ممکن نشد";
        setTimeout(() => { btn.textContent = original; }, 2000);
    });

    $("printReportBtn")?.addEventListener("click", () => window.print());

    // ===== نمودارها =====
    const charts = {};   // نمونه‌ی هر نمودار؛ قبل از رسم دوباره destroy می‌شود

    async function loadSimpleChart(canvasId, apiPath, label, type) {
        type = type || "line";
        const canvas = $(canvasId);
        if (!canvas) return;

        if (typeof Chart === "undefined") {
            console.warn("Chart.js is not loaded; chart " + canvasId + " skipped");
            return;
        }

        try {
            const data = await apiGet(apiPath);

            if (charts[canvasId]) {
                charts[canvasId].destroy();
                delete charts[canvasId];
            }

            charts[canvasId] = new Chart(canvas, {
                type: type,
                data: {
                    labels: data?.labels || [],
                    datasets: [{
                        label: label,
                        data: data?.values || [],
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

    function loadAllCharts() {
        return Promise.all([
            loadSimpleChart("salesTrendChart", "/dashboard/sales-trend", "فروش", "line"),
            loadSimpleChart("receivablesTrendChart", "/dashboard/receivables-trend", "مطالبات", "bar")
        ]);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", loadExecutiveDashboard);
    } else {
        loadExecutiveDashboard();
    }
})();
