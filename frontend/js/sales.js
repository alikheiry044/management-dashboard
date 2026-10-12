// Requires js/api.js to be loaded before this file in sales.html
// بخش «فاکتورهای فروش»؛ داده از GET /sales/ (فیلدهای SalesInvoiceOut)
requireLogin();

document.getElementById("logoutBtn")?.addEventListener("click", function (e) {
    e.preventDefault();
    logout();
});

(function () {
    const PAGE = 100;
    const STATUS = {
        pending: { text: "در انتظار تسویه", cls: "warning" },
        completed: { text: "تسویه‌شده", cls: "success" },
    };

    let all = [];
    let filtered = [];
    let shown = PAGE;

    const $ = (id) => document.getElementById(id);
    const setText = (id, text) => { const el = $(id); if (el) el.textContent = text; };

    // Decimal از سرور به‌صورت رشته می‌آید؛ همه‌جا به عدد تبدیل می‌شود
    function normalize(item) {
        const description = String(item.description || "").replace(/^نوع تسویه\s*:\s*/, "").trim();
        return {
            invoice: item.invoice_number || "",
            customer: item.customer_name || "-",
            date: String(item.sale_date || ""),
            amount: Number(item.amount) || 0,
            remaining: Number(item.remaining_amount) || 0,
            description,
            status: item.status || (Number(item.remaining_amount) > 0 ? "pending" : "completed"),
        };
    }

    const norm = (s) => String(s || "").replace(/ي/g, "ی").replace(/ك/g, "ک").toLowerCase();

    function normDate(s) {
        const t = String(s || "").trim().replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d));
        const m = t.match(/^(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})$/);
        return m ? `${m[1]}/${m[2].padStart(2, "0")}/${m[3].padStart(2, "0")}` : "";
    }

    function applyFilters() {
        const status = $("saleStatus")?.value || "";
        const from = normDate($("saleFrom")?.value);
        const to = normDate($("saleTo")?.value);
        const term = norm($("saleSearch")?.value).trim();

        filtered = all.filter((s) =>
            (!status || s.status === status) &&
            (!from || s.date >= from) &&
            (!to || s.date <= to) &&
            (!term || norm(`${s.customer} ${s.invoice} ${s.description}`).includes(term)));
        shown = PAGE;
        render();
    }

    ["saleStatus"].forEach((id) => $(id)?.addEventListener("change", applyFilters));
    ["saleFrom", "saleTo", "saleSearch"].forEach((id) => $(id)?.addEventListener("input", applyFilters));
    $("saleClear")?.addEventListener("click", () => {
        ["saleFrom", "saleTo", "saleSearch"].forEach((id) => { if ($(id)) $(id).value = ""; });
        if ($("saleStatus")) $("saleStatus").value = "";
        applyFilters();
    });
    $("saleMore")?.addEventListener("click", () => { shown += PAGE; renderTable(); });

    function render() {
        const open = filtered.filter((s) => s.remaining > 0);
        setText("kpiSaleTotal", formatNumber(filtered.reduce((t, s) => t + s.amount, 0)));
        setText("kpiSaleOpen", formatNumber(open.reduce((t, s) => t + s.remaining, 0)));
        setText("kpiSaleCount", formatNumber(filtered.length));
        setText("kpiSaleOpenCount", formatNumber(open.length));
        renderTable();
    }

    function renderTable() {
        const tbody = $("salesBody") || document.querySelector("#salesTable tbody");
        if (!tbody) return;

        tbody.innerHTML = filtered.slice(0, shown).map((s) => {
            const st = STATUS[s.status] || { text: s.status, cls: "" };
            const remaining = s.remaining > 0
                ? `<strong class="neg">${formatNumber(s.remaining)}</strong>`
                : '<span class="muted">-</span>';
            return `
                <tr>
                    <td>${s.invoice ? escapeHtml(toPersianDigits(s.invoice)) : '<span class="muted">-</span>'}</td>
                    <td>${escapeHtml(s.customer)}</td>
                    <td>${escapeHtml(toPersianDigits(s.date))}</td>
                    <td>${formatNumber(s.amount)}</td>
                    <td>${remaining}</td>
                    <td class="clip" title="${escapeHtml(s.description)}">${s.description ? escapeHtml(toPersianDigits(s.description)) : '<span class="muted">-</span>'}</td>
                    <td><span class="badge ${st.cls}">${escapeHtml(st.text)}</span></td>
                </tr>`;
        }).join("");

        setText("saleCount", filtered.length
            ? `نمایش ${formatNumber(Math.min(shown, filtered.length))} از ${formatNumber(filtered.length)} فاکتور`
            : "فاکتوری یافت نشد");
        const more = $("saleMore");
        if (more) more.hidden = shown >= filtered.length;
    }

    async function loadSales() {
        const message = $("message");
        try {
            const data = await apiGet("/sales/");
            all = (Array.isArray(data) ? data : []).map(normalize);

            if (message) {
                message.textContent = all.length
                    ? `${formatNumber(all.length)} فاکتور — مبالغ به ${CURRENCY_LABEL}`
                    : "هنوز فاکتوری ثبت نشده. فایل فاکتورهای فروش را از بالای صفحه آپلود کنید.";
            }
            applyFilters();
        } catch (error) {
            if (message) {
                message.style.color = "var(--danger)";
                message.textContent = error.message || "خطا در دریافت لیست فروش";
            }
            console.error("Sales load error:", error);
        }
    }

    loadSales();
})();
