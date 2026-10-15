// js/checks.js — مطابق banks.html فعلی
(function () {
    const $ = (id) => document.getElementById(id);
    const setText = (id, t) => { const el = $(id); if (el) el.textContent = t; };

    let all = [], filtered = [];

    // valueهای select#checkType در HTML تو
    const UPLOAD_MAP = {
        payable_check: "/checks/upload-payable",
        payable_check_passed: "/checks/upload-payable",
        receivable_check: "/checks/upload-receivable",
        receivable_check_spent: "/checks/upload-receivable",
    };

    const STATUS_FA = {
        spent: "خرج‌شده",
        passed: "پاس‌شده",
        open: "در جریان",
        returned: "برگشتی",
        unknown: "نامشخص",
    };

    function normalize(r) {
        return {
            check_type: r.check_type || "",
            check_number: r.check_number || "",
            party_name: r.party_name || "-",
            amount: Number(r.amount) || 0,
            due_date: r.due_date || "",
            bank_name: r.bank_name || "",
            status: r.status || "unknown",
            owner_name: r.owner_name || "",
            settle_date: r.settle_date || "",
        };
    }

    const norm = (s) =>
        String(s || "").replace(/ي/g, "ی").replace(/ك/g, "ک").toLowerCase();

    function applyFilters() {
        const st = $("checkStatusFilter")?.value || "";
        const kind = $("checkKindFilter")?.value || ""; // payable_check | receivable_check
        const term = norm($("checkSearch")?.value).trim();

        filtered = all.filter((c) => {
            if (st && c.status !== st) return false;
            if (kind && c.check_type !== kind) return false;
            if (!term) return true;
            return norm(
                `${c.check_number} ${c.party_name} ${c.bank_name} ${c.owner_name}`
            ).includes(term);
        });
        render();
    }

    function render() {
        const spent = filtered.filter((c) => c.status === "spent");
        setText("kpiCheckCount", formatNumber(filtered.length));
        setText("kpiCheckTotal", formatNumber(filtered.reduce((t, c) => t + c.amount, 0)));
        setText("kpiCheckSpent", formatNumber(spent.length));
        setText("kpiCheckOther", formatNumber(filtered.length - spent.length));

        const tbody = $("checksBody");
        if (!tbody) return;

        if (!filtered.length) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:#6b7280">چکی یافت نشد. فایل را آپلود کنید.</td></tr>`;
            setText("checkCount", "");
            return;
        }

        tbody.innerHTML = filtered.map((c) => {
            const label = STATUS_FA[c.status] || c.status;
            const cls = c.status === "spent" ? "warning" : c.status === "passed" ? "success" : "";
            return `<tr>
                <td>${escapeHtml(toPersianDigits(c.check_number))}</td>
                <td><b>${escapeHtml(c.party_name)}</b></td>
                <td>${formatNumber(c.amount)}</td>
                <td>${escapeHtml(toPersianDigits(c.due_date))}</td>
                <td>${escapeHtml(c.bank_name)}</td>
                <td><span class="badge ${cls}">${escapeHtml(label)}</span></td>
                <td>${escapeHtml(toPersianDigits(c.settle_date || "-"))}</td>
            </tr>`;
        }).join("");

        setText("checkCount", `${formatNumber(filtered.length)} چک`);
    }

    async function loadChecks() {
        try {
            const data = await apiGet("/checks/");
            all = (Array.isArray(data) ? data : []).map(normalize);
            applyFilters();
        } catch (e) {
            const tbody = $("checksBody");
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="7" style="color:var(--danger);text-align:center;padding:20px">${escapeHtml(e.message || "خطا")}</td></tr>`;
            }
        }
    }

    $("checkStatusFilter")?.addEventListener("change", applyFilters);
    $("checkKindFilter")?.addEventListener("change", applyFilters);
    $("checkSearch")?.addEventListener("input", applyFilters);

    $("checkUploadBtn")?.addEventListener("click", async function () {
        const fileInput = $("checkFile");
        const file = fileInput?.files?.[0];
        const msg = $("checkUploadMsg");
        const typeVal = $("checkType")?.value || "receivable_check_spent";

        if (!file) {
            if (msg) msg.textContent = "فایل را انتخاب کنید";
            return;
        }

        const endpoint = UPLOAD_MAP[typeVal] || "/checks/upload-receivable";
        const btn = this;
        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "در حال آپلود...";
        if (msg) msg.textContent = "پردازش...";

        try {
            let res;
            if (typeof apiUpload === "function") {
                res = await apiUpload(endpoint, file);
            } else {
                const form = new FormData();
                form.append("file", file);
                res = await apiRequest(endpoint, { method: "POST", body: form }, "آپلود ناموفق");
            }
            if (msg) msg.textContent = res.message || `ثبت شد: ${res.created || 0}`;
            if (fileInput) fileInput.value = "";
            await loadChecks();
        } catch (e) {
            if (msg) msg.textContent = e.message || "آپلود ناموفق";
        } finally {
            btn.disabled = false;
            btn.textContent = original;
        }
    });

    document.querySelectorAll("#bankTabs [data-view]").forEach((btn) => {
        btn.addEventListener("click", () => {
            document.querySelectorAll("#bankTabs .tab").forEach((t) => t.classList.remove("active"));
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
