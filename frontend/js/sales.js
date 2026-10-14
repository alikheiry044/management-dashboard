// Requires js/api.js
requireLogin();

document.getElementById("logoutBtn")?.addEventListener("click", function (e) {
    e.preventDefault();
    logout();
});

(function () {
    const PAGE = 100;
    const $ = (id) => document.getElementById(id);
    const setText = (id, text) => {
        const el = $(id);
        if (el) el.textContent = text;
    };

    let all = [];
    let filtered = [];
    let shown = PAGE;

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
        const term = norm($("saleSearch")?.value).trim();
        const onlyDebt = $("saleOnlyDebt")?.checked;

        filtered = all.filter((s) => {
            if (onlyDebt && s.balance <= 0) return false;
            if (!term) return true;
            return norm(`${s.code} ${s.name}`).includes(term);
        });
        shown = PAGE;
        render();
    }

    $("saleSearch")?.addEventListener("input", applyFilters);
    $("saleOnlyDebt")?.addEventListener("change", applyFilters);
    $("saleClear")?.addEventListener("click", () => {
        if ($("saleSearch")) $("saleSearch").value = "";
        if ($("saleOnlyDebt")) $("saleOnlyDebt").checked = false;
        applyFilters();
    });
    $("saleMore")?.addEventListener("click", () => {
        shown += PAGE;
        renderTable();
    });

    function render() {
        const debtors = filtered.filter((s) => s.balance > 0);
        const totalRecv = debtors.reduce((t, s) => t + s.balance, 0);
        const totalCredit = filtered
            .filter((s) => s.balance < 0)
            .reduce((t, s) => t + Math.abs(s.balance), 0);

        setText("kpiSaleTotal", formatNumber(totalRecv));
        setText("kpiSaleOpen", formatNumber(totalCredit));
        setText("kpiSaleCount", formatNumber(filtered.length));
        setText("kpiSaleOpenCount", formatNumber(debtors.length));
        renderTable();
    }

    function renderTable() {
        const tbody = $("salesBody") || document.querySelector("#salesTable tbody");
        if (!tbody) return;

        if (!filtered.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align:center;padding:28px;color:#6b7280">
                        مشتری‌ای یافت نشد. فایل مرور فروش را آپلود کنید.
                    </td>
                </tr>`;
            setText("saleCount", "");
            const more = $("saleMore");
            if (more) more.hidden = true;
            return;
        }

        tbody.innerHTML = filtered
            .slice(0, shown)
            .map((s) => {
                let badge = '<span class="badge success">صفر</span>';
                let balHtml = formatNumber(s.balance);
                if (s.balance > 0) {
                    badge = '<span class="badge warning">بدهکار</span>';
                    balHtml = `<strong>${formatNumber(s.balance)}</strong>`;
                } else if (s.balance < 0) {
                    badge = '<span class="badge danger">بستانکار</span>';
                    balHtml = `<span class="neg">${formatNumber(s.balance)}</span>`;
                }

                return `
                <tr>
                    <td>${s.code ? escapeHtml(toPersianDigits(s.code)) : '<span class="muted">-</span>'}</td>
                    <td><b>${escapeHtml(s.name)}</b></td>
                    <td>${balHtml}</td>
                    <td>${badge}</td>
                </tr>`;
            })
            .join("");

        setText(
            "saleCount",
            `نمایش ${formatNumber(Math.min(shown, filtered.length))} از ${formatNumber(filtered.length)} مشتری`
        );
        const more = $("saleMore");
        if (more) more.hidden = shown >= filtered.length;
    }

    async function loadSales() {
        const message = $("message");
        try {
            const data = await apiGet("/party-balances/");
            const items = data.items || data || [];
            all = (Array.isArray(items) ? items : []).map(normalize);

            // KPI از totals سرور اگر بود
            if (data.totals && $("kpiSaleTotal")) {
                // بعداً با applyFilters هم آپدیت می‌شود
            }

            if (message) {
                message.style.color = "";
                message.textContent = all.length
                    ? `${formatNumber(all.length)} مشتری — مبالغ به ${typeof CURRENCY_LABEL !== "undefined" ? CURRENCY_LABEL : "ریال"}`
                    : "هنوز داده‌ای نیست. فایل مرور فروش را آپلود کنید.";
            }
            applyFilters();
        } catch (error) {
            if (message) {
                message.style.color = "var(--danger)";
                message.textContent = error.message || "خطا در دریافت لیست فروش";
            }
            console.error(error);
        }
    }

    // آپلود
    $("salesUploadBtn")?.addEventListener("click", async function () {
        const fileInput = $("salesFile");
        const msg = $("salesUploadMsg");
        const file = fileInput?.files?.[0];
        const btn = this;

        if (!file) {
            if (msg) {
                msg.style.color = "var(--danger)";
                msg.textContent = "فایل را انتخاب کنید";
            }
            return;
        }

        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "در حال آپلود...";
        if (msg) {
            msg.style.color = "";
            msg.textContent = "در حال پردازش...";
        }

        try {
            const result = await apiUpload("/party-balances/upload", file);
            if (msg) {
                msg.style.color = "var(--success, #15966f)";
                msg.textContent =
                    result.message ||
                    `آپلود انجام شد — ${result.inserted ?? result.created ?? 0} مورد`;
            }
            if (fileInput) fileInput.value = "";
            await loadSales();
        } catch (error) {
            if (msg) {
                msg.style.color = "var(--danger)";
                msg.textContent = error.message || "آپلود ناموفق بود";
            }
        } finally {
            btn.disabled = false;
            btn.textContent = original;
        }
    });

    loadSales();
})();