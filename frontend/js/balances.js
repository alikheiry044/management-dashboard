// Requires js/api.js — تب مانده مشتریان در sales.html
(function () {
    const $ = (id) => document.getElementById(id);
    const setText = (id, text) => {
        const el = $(id);
        if (el) el.textContent = text;
    };

    let all = [];
    let filtered = [];
    let filterMode = "all"; // all | receivable | payable

    function normalize(item) {
        return {
            code: item.detail_code || item.code || "",
            name: item.title || item.name || "-",
            balance: Number(item.balance) || 0,
        };
    }

    const norm = (s) =>
        String(s || "")
            .replace(/ي/g, "ی")
            .replace(/ك/g, "ک")
            .toLowerCase();

    function applyFilters() {
        const term = norm($("balanceSearch")?.value).trim();
        filtered = all.filter((s) => {
            if (filterMode === "receivable" && s.balance <= 0) return false;
            if (filterMode === "payable" && s.balance >= 0) return false;
            if (!term) return true;
            return norm(`${s.code} ${s.name}`).includes(term);
        });
        renderTable();
    }

    function renderKPIs(totals) {
        if (totals) {
            setText("kpiBalReceivable", formatNumber(totals.receivable_total || 0));
            setText("kpiBalPayable", formatNumber(Math.abs(totals.payable_total || 0)));
            setText("kpiBalNet", formatNumber(totals.net || 0));
            setText("kpiBalCount", formatNumber(totals.count || 0));
            return;
        }
        const recv = all.filter((s) => s.balance > 0);
        const pay = all.filter((s) => s.balance < 0);
        setText("kpiBalReceivable", formatNumber(recv.reduce((t, s) => t + s.balance, 0)));
        setText("kpiBalPayable", formatNumber(pay.reduce((t, s) => t + Math.abs(s.balance), 0)));
        setText("kpiBalNet", formatNumber(all.reduce((t, s) => t + s.balance, 0)));
        setText("kpiBalCount", formatNumber(all.length));
    }

    function renderTable() {
        const tbody = $("balanceBody");
        if (!tbody) return;

        if (!filtered.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align:center;padding:28px;color:#6b7280">
                        موردی یافت نشد. فایل مرور فروش را آپلود کنید.
                    </td>
                </tr>`;
            setText("balanceCount", "");
            return;
        }

        tbody.innerHTML = filtered
            .map((s) => {
                let status = "صفر";
                let cls = "badge";
                if (s.balance > 0) {
                    status = "بدهکار";
                    cls = "badge warning";
                } else if (s.balance < 0) {
                    status = "بستانکار";
                    cls = "badge danger";
                } else {
                    cls = "badge success";
                }

                return `
                <tr>
                    <td>${s.code ? escapeHtml(toPersianDigits(s.code)) : "-"}</td>
                    <td><b>${escapeHtml(s.name)}</b></td>
                    <td><span class="${cls}">${status}</span></td>
                    <td>${formatNumber(s.balance)}</td>
                </tr>`;
            })
            .join("");

        setText("balanceCount", `${formatNumber(filtered.length)} مورد`);
    }

    function renderTabs() {
        const nav = $("balanceTabs");
        if (!nav) return;
        const tabs = [
            { id: "all", label: "همه" },
            { id: "receivable", label: "بدهکاران" },
            { id: "payable", label: "بستانکاران" },
        ];
        nav.innerHTML = tabs
            .map(
                (t) =>
                    `<button type="button" class="tab ${filterMode === t.id ? "active" : ""}" data-bal="${t.id}">${t.label}</button>`
            )
            .join("");

        nav.querySelectorAll("[data-bal]").forEach((btn) => {
            btn.addEventListener("click", () => {
                filterMode = btn.getAttribute("data-bal");
                renderTabs();
                applyFilters();
            });
        });
    }

    async function loadBalances() {
        const info = $("balancesInfo");
        try {
            const data = await apiGet("/party-balances/");
            const items = data.items || [];
            all = items.map(normalize);
            renderKPIs(data.totals);

            if (info) {
                const period = data.period_label ? ` — دوره: ${data.period_label}` : "";
                info.textContent = all.length
                    ? `${formatNumber(all.length)} مشتری${period}`
                    : "هنوز مانده‌ای ثبت نشده.";
            }
            renderTabs();
            applyFilters();
        } catch (error) {
            if (info) info.textContent = error.message || "خطا در دریافت مانده مشتریان";
            console.error(error);
        }
    }

    $("balanceSearch")?.addEventListener("input", applyFilters);

    // تب‌های اصلی فروش
    document.querySelectorAll("#salesTabs [data-view]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const view = btn.getAttribute("data-view");
            document.querySelectorAll("#salesTabs .tab").forEach((t) => t.classList.remove("active"));
            btn.classList.add("active");

            const inv = $("invoicesSection");
            const bal = $("balancesSection");
            if (view === "balances") {
                if (inv) inv.hidden = true;
                if (bal) bal.hidden = false;
                loadBalances();
            } else {
                if (inv) inv.hidden = false;
                if (bal) bal.hidden = true;
            }
        });
    });


    window.reloadPartyBalances = loadBalances;
})();