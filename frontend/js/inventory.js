// Requires js/api.js (و Chart.js در صورت نیاز)
// requireLogin, getUser, logout, apiGet, apiUpload, formatNumber, toPersianDigits, escapeHtml, CURRENCY_LABEL

if (!requireLogin()) throw new Error("not authenticated");

(function () {
    const $ = (id) => document.getElementById(id);

    const LOW_STOCK_DEFAULT = 10;
    const MAX_UPLOAD_MB = 20;
    const ALLOWED_EXT = [".xlsx", ".xls", ".csv"];
    const CHART_COLORS = ["#2563eb", "#c9a227", "#15966f", "#d9343a", "#8b5cf6", "#0891b2", "#ea580c", "#64748b"];

    let inventoryChart = null;
    let currentItems = [];

    const user = getUser();
    const welcome = $("welcomeText");
    if (welcome && user) {
        welcome.textContent = user.full_name || user.email || "مدیر سیستم";
    }

    $("logoutBtn")?.addEventListener("click", function (e) {
        e.preventDefault();
        logout();
    });

    function formatMoney(value) {
        return formatNumber(Number(value || 0)) + " " + (typeof CURRENCY_LABEL !== "undefined" ? CURRENCY_LABEL : "ریال");
    }

    function setText(id, text) {
        const el = $(id);
        if (el) el.textContent = text;
    }

    function itemTitle(item) {
        return item.title || item.name || "-";
    }

    function stockState(item) {
        const qty = Number(item.quantity) || 0;
        if (qty <= 0) return "zero";
        const threshold =
            Number(item.reorder_point) || Number(item.min_quantity) || LOW_STOCK_DEFAULT;
        return qty < threshold ? "low" : "ok";
    }

    function setBodyMessage(html) {
        const tbody = $("inventoryBody");
        if (tbody) tbody.innerHTML = html;
    }

    function destroyChart() {
        if (inventoryChart) {
            inventoryChart.destroy();
            inventoryChart = null;
        }
    }

    async function loadInventoryDashboard() {
        try {
            const data = await apiGet("/inventory/");
            const items = Array.isArray(data) ? data : (data?.items || []);
            currentItems = items;

            if (items.length === 0) {
                setText("kpi-total-items", "۰ قلم");
                setText("kpi-total-value", formatMoney(0));
                setText("kpi-low-stock", "۰ قلم");
                setText("kpi-zero-stock", "۰ قلم");
                destroyChart();
                setBodyMessage(
                    '<tr><td colspan="6" style="text-align:center;padding:30px;color:var(--muted);">' +
                    "هنوز داده‌ای وارد نشده. اول فایل تعدادی، بعد فایل مبلغی را آپلود کنید." +
                    "</td></tr>"
                );
                return;
            }

            const totalValue = items.reduce((sum, item) => sum + (Number(item.total_value) || 0), 0);
            const states = items.map(stockState);
            const lowStock = states.filter((s) => s === "low").length;
            const zeroStock = states.filter((s) => s === "zero").length;

            setText("kpi-total-items", toPersianDigits(items.length) + " قلم");
            setText("kpi-total-value", formatMoney(totalValue));
            setText("kpi-low-stock", toPersianDigits(lowStock) + " قلم");
            setText("kpi-zero-stock", toPersianDigits(zeroStock) + " قلم");

            // اگر جدول کامل می‌خواهی همه را نشان بده؛ اگر فقط نیازمند توجه:
            const showAll = true;
            const rows = showAll
                ? items.map((item) => ({ item, state: stockState(item) }))
                : items
                    .map((item) => ({ item, state: stockState(item) }))
                    .filter((x) => x.state !== "ok")
                    .sort((a, b) => (a.state === "zero" ? 0 : 1) - (b.state === "zero" ? 0 : 1));

            if (rows.length === 0) {
                setBodyMessage(
                    '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--green);">همه کالاها در وضعیت مطلوب هستند.</td></tr>'
                );
            } else {
                setBodyMessage(rows.map(({ item, state }) => {
                    const qty = Number(item.quantity) || 0;
                    let badge = '<span class="badge bGreen">عادی</span>';
                    if (state === "zero") badge = '<span class="badge bRed">ناموجود</span>';
                    else if (state === "low") badge = '<span class="badge bOrange">کم‌موجودی</span>';

                    return `
                        <tr>
                            <td style="font-family:monospace;font-weight:bold;">${escapeHtml(toPersianDigits(item.code || "-"))}</td>
                            <td>${escapeHtml(itemTitle(item))}</td>
                            <td>${escapeHtml(item.category || "محصول")}</td>
                            <td style="font-weight:bold;">${escapeHtml(toPersianDigits(qty))}</td>
                            <td>${escapeHtml(formatMoney(item.total_value))}</td>
                            <td>${badge}</td>
                        </tr>`;
                }).join(""));
            }

            renderInventoryChart(items);
        } catch (error) {
            console.error("Inventory Load Error:", error);
            setText("kpi-total-items", "خطا");
            setText("kpi-total-value", "-");
            setText("kpi-low-stock", "-");
            setText("kpi-zero-stock", "-");
            setBodyMessage(
                '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--red);">' +
                escapeHtml("خطا در دریافت اطلاعات: " + (error.message || "")) +
                "</td></tr>"
            );
        }
    }

    function renderInventoryChart(items) {
        const canvas = $("inventoryChart");
        if (!canvas || typeof Chart === "undefined") return;

        const categories = {};
        items.forEach((item) => {
            const cat = item.category || "دسته‌بندی نشده";
            categories[cat] = (categories[cat] || 0) + (Number(item.total_value) || 0);
        });

        const labels = Object.keys(categories);
        const values = Object.values(categories);

        destroyChart();
        inventoryChart = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
                    borderWidth: 0,
                    hoverOffset: 10,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { font: { family: "Tahoma", size: 12 }, padding: 15 },
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => context.label + ": " + formatMoney(context.raw),
                        },
                    },
                },
            },
        });
    }

    function csvCell(value) {
        if (typeof value === "number") return String(value);
        let s = String(value ?? "");
        if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
        return '"' + s.replace(/"/g, '""') + '"';
    }

    window.exportInventory = function () {
        if (!currentItems.length) {
            alert("داده‌ای برای خروجی وجود ندارد.");
            return;
        }

        const statusText = { zero: "ناموجود", low: "کم‌موجودی", ok: "عادی" };
        const header = ["کد کالا", "نام کالا", "دسته‌بندی", "موجودی", "ارزش کل", "وضعیت"];
        const rows = currentItems.map((item) => [
            item.code ?? "",
            itemTitle(item),
            item.category ?? "",
            Number(item.quantity) || 0,
            Number(item.total_value) || 0,
            statusText[stockState(item)],
        ]);

        const csv = [header, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n");
        const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "inventory-" + new Date().toISOString().slice(0, 10) + ".csv";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    };

    // ===== آپلود =====
    function setMsg(id, color, text) {
        const box = $(id);
        if (!box) return;
        box.style.color = color;
        box.textContent = text;
    }

    async function handleInventoryUpload({ fileInputId, msgId, btn, endpoint, successText }) {
        const fileInput = $(fileInputId);
        const file = fileInput?.files?.[0];

        if (!file) {
            return setMsg(msgId, "var(--red)", "لطفاً فایل را انتخاب کنید");
        }

        const name = file.name.toLowerCase();
        if (!ALLOWED_EXT.some((ext) => name.endsWith(ext))) {
            return setMsg(msgId, "var(--red)", "فرمت مجاز: xlsx، xls یا csv");
        }
        if (file.size === 0) {
            return setMsg(msgId, "var(--red)", "فایل خالی است");
        }
        if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
            return setMsg(msgId, "var(--red)", "حجم فایل زیاد است");
        }

        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "در حال پردازش...";
        setMsg(msgId, "var(--blue)", "در حال آپلود...");

        try {
            const data = await apiUpload(endpoint, file);
            const count = toPersianDigits(data?.created ?? data?.matched ?? 0);
            setMsg(msgId, "var(--green)", `${successText} — ${count} مورد`);
            fileInput.value = "";
            await loadInventoryDashboard();
        } catch (error) {
            setMsg(msgId, "var(--red)", error.message || "آپلود ناموفق بود");
        } finally {
            btn.disabled = false;
            btn.textContent = original;
        }
    }

    $("inventoryQtyBtn")?.addEventListener("click", function () {
        handleInventoryUpload({
            fileInputId: "inventoryQtyFile",
            msgId: "inventoryQtyMsg",
            btn: this,
            endpoint: "/inventory/upload",
            successText: "✅ آپلود تعدادی انجام شد",
        });
    });

    $("inventoryValueBtn")?.addEventListener("click", function () {
        handleInventoryUpload({
            fileInputId: "inventoryValueFile",
            msgId: "inventoryValueMsg",
            btn: this,
            endpoint: "/inventory/upload-value",
            successText: "✅ آپلود مبلغی انجام شد",
        });
    });

    // جستجو (اگر input با id=searchInput داری)
    $("searchInput")?.addEventListener("input", function () {
        const q = (this.value || "").trim().toLowerCase();
        if (!q) {
            loadInventoryDashboard();
            return;
        }
        const filtered = currentItems.filter((item) => {
            const code = String(item.code || "").toLowerCase();
            const title = String(itemTitle(item)).toLowerCase();
            return code.includes(q) || title.includes(q);
        });
        setBodyMessage(filtered.map((item) => {
            const state = stockState(item);
            const qty = Number(item.quantity) || 0;
            let badge = '<span class="badge bGreen">عادی</span>';
            if (state === "zero") badge = '<span class="badge bRed">ناموجود</span>';
            else if (state === "low") badge = '<span class="badge bOrange">کم‌موجودی</span>';
            return `
                <tr>
                    <td>${escapeHtml(toPersianDigits(item.code || "-"))}</td>
                    <td>${escapeHtml(itemTitle(item))}</td>
                    <td>${escapeHtml(item.category || "محصول")}</td>
                    <td>${escapeHtml(toPersianDigits(qty))}</td>
                    <td>${escapeHtml(formatMoney(item.total_value))}</td>
                    <td>${badge}</td>
                </tr>`;
        }).join("") || '<tr><td colspan="6" style="text-align:center;padding:20px;">موردی پیدا نشد</td></tr>');
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", loadInventoryDashboard);
    } else {
        loadInventoryDashboard();
    }
})();
