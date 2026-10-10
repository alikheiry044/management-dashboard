// js/uploader.js
document.addEventListener("DOMContentLoaded", function () {
    const uploadBtn = document.getElementById("uploadBtn");
    const uploadFile = document.getElementById("uploadFile");
    const uploadType = document.getElementById("uploadType");
    const uploadResult = document.getElementById("uploadResult");

    if (!uploadBtn) return;

    uploadBtn.addEventListener("click", async function () {
        const file = uploadFile.files[0];
        if (!file) {
            uploadResult.style.color = "#b4232a";
            uploadResult.textContent = "⚠️ لطفاً ابتدا یک فایل انتخاب کنید.";
            return;
        }

        uploadBtn.disabled = true;
        uploadBtn.textContent = "⏳ در حال پردازش...";
        uploadResult.style.color = "#2563eb";
        uploadResult.textContent = "⏳ در حال آپلود و ارزیابی ریسک...";

        try {
            const type = uploadType.value;
            let endpoint = "";

            if (type === "receivable") endpoint = "/upload/receivables-excel";
            else if (type === "payable") endpoint = "/upload/payables-excel";
            else if (type === "expense") endpoint = "/upload/expense-report";

            const result = await apiUpload(endpoint, file);

            const highRisk = result.risk_summary?.high || 0;
            const dups = result.risk_summary?.duplicates || 0;

            uploadResult.style.color = "#107a5a";
            uploadResult.textContent = `✅ موفق! ${toPersianDigits(result.created)} ردیف ثبت شد. (ریسک بالا: ${toPersianDigits(highRisk)} | تکراری: ${toPersianDigits(dups)})`;

            uploadFile.value = "";

            if (typeof loadFinanceData === "function") {
                await loadFinanceData();
            }

        } catch (error) {
            uploadResult.style.color = "#b4232a";
            uploadResult.textContent = `❌ خطا: ${error.message}`;
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.textContent = "آپلود و پردازش";
        }
    });
});
