// آپلود فایل انبار (فقط برای Inventory.html)
// Requires js/api.js to be loaded before this file
// (requireLogin, apiUpload, formatNumber)

(function () {
    const fileInput = document.getElementById("inventoryFile");
    const button = document.getElementById("uploadBtn");
    const result = document.getElementById("inventoryResult");
    if (!fileInput || !button) return;

    // بدون توکن اصلاً ادامه نده (به صفحه‌ی ورود می‌رود)
    if (!requireLogin()) return;

    const ENDPOINT = "/upload/inventory-excel";
    const ALLOWED_EXT = [".xlsx", ".xls", ".csv"];
    const MAX_MB = 20;

    function setResult(text, ok) {
        if (!result) return;
        result.textContent = text;
        result.className = "upload-result" + (ok === true ? " ok" : ok === false ? " fail" : "");
    }

    fileInput.addEventListener("change", () => setResult("", null));

    button.addEventListener("click", async function () {
        const file = fileInput.files[0];
        if (!file) return setResult("ابتدا یک فایل انتخاب کنید", false);

        const name = file.name.toLowerCase();
        if (!ALLOWED_EXT.some((ext) => name.endsWith(ext))) {
            return setResult("فرمت فایل مجاز نیست (xlsx، xls یا csv)", false);
        }
        if (file.size === 0) {
            return setResult("فایل انتخاب‌شده خالی است", false);
        }
        if (file.size > MAX_MB * 1024 * 1024) {
            return setResult(`حجم فایل بیشتر از ${formatNumber(MAX_MB)} مگابایت است`, false);
        }

        const originalText = button.textContent;
        let reloading = false;

        button.disabled = true;
        button.textContent = "در حال ارسال...";
        setResult("در حال ارسال و پردازش فایل...", null);

        try {
            // apiUpload: هدر Authorization، timeout، و مدیریت ۴۰۱ (خروج خودکار) را انجام می‌دهد
            const data = await apiUpload(ENDPOINT, file);

            const created = data && typeof data.created === "number" ? data.created : null;
            const skipped = data && data.skipped_rows
                ? (Array.isArray(data.skipped_rows) ? data.skipped_rows.length : Number(data.skipped_rows))
                : 0;

            const parts = [(data && data.message) || "فایل انبار بارگذاری شد"];
            if (created !== null) parts.push(`${formatNumber(created)} کالا ثبت شد`);
            if (skipped) parts.push(`${formatNumber(skipped)} ردیف رد شد`);

            // اگر هیچ کالایی ثبت نشده، موفقیت کامل نیست؛ صفحه را رفرش نکن تا پیام دیده شود
            if (created === 0) {
                return setResult(parts.join(" — "), false);
            }

            setResult(parts.join(" — "), true);
            fileInput.value = "";

            // دکمه تا رفرش غیرفعال می‌ماند تا آپلود دوباره‌ی ناخواسته انجام نشود
            reloading = true;
            setTimeout(() => window.location.reload(), 1500);
        } catch (error) {
            setResult(error.message || "آپلود ناموفق بود", false);
            console.error("Inventory upload error:", error);
        } finally {
            if (!reloading) {
                button.disabled = false;
                button.textContent = originalText;
            }
        }
    });
})();