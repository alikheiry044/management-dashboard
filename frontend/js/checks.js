// Requires js/api.js
(function () {
    const $ = (id) => document.getElementById(id);
    const setText = (id, t) => {
        const el = $(id);
        if (el) el.textContent = t;
    };

    let all = [];
    let filtered = [];

    const STATUS_FA = {
        spent: "خرج‌شده",
        passed: "پاس‌شده",
        open: "در جریان",
        returned: "برگشتی",
        unknown: "نامشخص",
    };

    function normalize(r) {
        return {
            check_number: r.check_number || "",
            party_name: r.party_name || "-",
            amount: Number(r.amount) || 0,
            due_date: r.due_date || "",
            bank_name: r.bank_name || "",
            status: r.status || "unknown",
            owner_name: r.owner_name || "",
        };
    }

    const norm = (s) =>
        String(s || "")
            .replace(/ي/g, "ی")
            .replace(/ك/g, "ک")
            .toLowerCase();

    function applyFilters() {
        const st = $("checkStatusFilter")?.value || "";
        const term = norm($("checkSearch")?.value).trim();
        filtered = all.filter((c) => {
            if (st && c.status !== st) return false;
            if (!term) return true;
            return norm(
                `${c.check_number} ${c.party_name} ${c.bank_name} ${c.owner_name}`
            ).includes(term);
        });
        render();
    }

    function render() {
        const spent = filtered.filter((c) => c.status === "spent");
        const other = filtered.filter((c) => c.status !== "spent");
        setText("kpiCheckCount", formatNumber(filtered.length));
        setText(
            "kpiCheckTotal",
            formatNumber(filtered.reduce((t, c) => t + c.amount, 0))
        );
        setText("kpiCheckSpent", formatNumber(spent.length));
        setText("kpiCheckOther", formatNumber(other.length));

        const tbody = $("checksBody");
        if (!tbody) return;

        if (!filtered.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align:center;padding:24px;color:#6b7280">
                        چکی یافت نشد. فایل را آپلود کنید.
                    </td>
                </tr>`;
            setText("checkCount", "");
            return;
        }

        tbody.innerHTML = filtered
            .map((c) => {
                const label = STATUS_FA[c.status] || c.status;
                const cls =
                    c.status === "spent"
                        ? "warning"
                        : c.status === "passed"
                          ? "success"
                          : "";
                return `
                <tr>
                    <td>${escapeHtml(toPersianDigits(c.check_number))}</td>
                    <td><b>${escapeHtml(c.party_name)}</b></td>
                    <td>${formatNumber(c.amount)}</td>
                    <td>${escapeHtml(toPersianDigits(c.due_date))}</td>
                    <td>${escapeHtml(c.bank_name)}</td>
                    <td><span class="badge ${cls}">${escapeHtml(label)}</span></td>
                    <td>${escapeHtml(c.owner_name)}</td>
                </tr>`;
            })
            .join("");

        setText("checkCount", `${formatNumber(filtered.length)} چک`);
    }

    async function loadChecks() {
        try {
            const data = await apiGet("/checks/?check_type=receivable_check");
            all = (Array.isArray(data) ? data : []).map(normalize);
            applyFilters();
        } catch (e) {
            const tbody = $("checksBody");
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="color:var(--danger);text-align:center;padding:20px">
                            ${escapeHtml(e.message || "خطا در دریافت چک‌ها")}
                        </td>
                    </tr>`;
            }
            console.error(e);
        }
    }

    $("checkStatusFilter")?.addEventListener("change", applyFilters);
    $("checkSearch")?.addEventListener("input", applyFilters);

    $("checkUploadBtn")?.addEventListener("click", async function () {
        const fileInput = $("checkFile");
        const file = fileInput?.files?.[0];
        const msg = $("checkUploadMsg");
        if (!file) {
            if (msg) msg.textContent = "فایل را انتخاب کنید";
            return;
        }

        const btn = this;
        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "در حال آپلود...";
        if (msg) msg.textContent = "پردازش...";

        try {
            let res;
            if (typeof apiUpload === "function") {
                res = await apiUpload("/checks/upload-receivable", file);
            } else {
                const form = new FormData();
                form.append("file", file);
                res = await apiRequest(
                    "/checks/upload-receivable",
                    { method: "POST", body: form },
                    "آپلود ناموفق بود"
                );
            }
            if (msg) {
                msg.textContent =
                    res.message || `ثبت شد: ${res.created || 0}`;
            }
            if (fileInput) fileInput.value = "";
            await loadChecks();
        } catch (e) {
            if (msg) msg.textContent = e.message || "آپلود ناموفق";
            console.error(e);
        } finally {
            btn.disabled = false;
            btn.textContent = original;
        }
    });

    // سوییچ تب حساب / چک
    document.querySelectorAll("#bankTabs [data-view]").forEach((btn) => {
        btn.addEventListener("click", () => {
            document
                .querySelectorAll("#bankTabs .tab")
                .forEach((t) => t.classList.remove("active"));
            btn.classList.add("active");
            const view = btn.getAttribute("data-view");
            const acc = $("accountsSection");
            const chk = $("checksSection");
            if (view === "checks") {
                if (acc) acc.hidden = true;
                if (chk) chk.hidden = false;
                loadChecks();
            } else {
                if (acc) acc.hidden = false;
                if (chk) chk.hidden = true;
            }
        });
    });

    window.reloadChecks = loadChecks;
})();
