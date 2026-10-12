// Requires js/api.js to be loaded before this file (API_URL, getToken, extractError, formatNumber)
//
// پنل آپلود بالای صفحه‌ها (فروش، مالی). HTML لازم:
//   <section id="uploadPanel" data-kind="sales"> ... </section>
//   داخلش: #uploadFile ، #uploadBtn ، #uploadResult و در صورت نیاز #uploadType (لیست نوع فایل)

// ⚠️ این مسیرها باید با مسیرهای آپلود در بک‌اند یکی باشند.
// برای دیدنشان: http://localhost:8000/docs  ← بخش‌های upload
// اگر بک‌اند یک مسیر واحد دارد، همه را همان مسیر بگذارید (نوع فایل در فیلد file_type هم ارسال می‌شود).
const UPLOAD_ENDPOINTS = {
    sales: "/upload/sales",
    receivable: "/upload/receivables",
    payable: "/upload/payables",
    expense: "/upload/expenses",
    bank: "/banks/upload",
};

const UPLOAD_ALLOWED_EXT = [".xlsx", ".xls", ".csv"];
const UPLOAD_MAX_MB = 10;

function initUploader() {
    const panel = document.getElementById("uploadPanel");
    if (!panel) return;

    const fileInput = document.getElementById("uploadFile");
    const button = document.getElementById("uploadBtn");
    const result = document.getElementById("uploadResult");
    const typeSelect = document.getElementById("uploadType");
    if (!fileInput || !button) return;

    function setResult(text, ok) {
        if (!result) return;
        result.textContent = text;
        result.className = "upload-result" + (ok === true ? " ok" : ok === false ? " fail" : "");
    }

    function summarize(data) {
        const message = (data && data.message) || "فایل با موفقیت بارگذاری شد";
        const keys = ["inserted", "imported", "saved", "processed", "rows", "count"];
        const key = data && keys.find((k) => typeof data[k] === "number");
        return key ? `${message} (${formatNumber(data[key])} ردیف)` : message;
    }

    fileInput.addEventListener("change", () => setResult("", null));
    typeSelect?.addEventListener("change", () => setResult("", null));

    button.addEventListener("click", async function () {
        const kind = typeSelect ? typeSelect.value : panel.dataset.kind;
        const path = UPLOAD_ENDPOINTS[kind];
        const file = fileInput.files[0];

        if (!path) return setResult("نوع فایل نامشخص است", false);
        if (!file) return setResult("ابتدا یک فایل انتخاب کنید", false);

        const name = file.name.toLowerCase();
        if (!UPLOAD_ALLOWED_EXT.some((ext) => name.endsWith(ext))) {
            return setResult("فرمت فایل مجاز نیست (xlsx، xls یا csv)", false);
        }
        if (file.size > UPLOAD_MAX_MB * 1024 * 1024) {
            return setResult(`حجم فایل بیشتر از ${formatNumber(UPLOAD_MAX_MB)} مگابایت است`, false);
        }

        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = "در حال ارسال...";
        setResult("در حال ارسال و پردازش فایل...", null);

        try {
            const form = new FormData();
            form.append("file", file);
            form.append("file_type", kind);

            const response = await fetch(`${API_URL}${path}`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${getToken()}` },
                body: form,
            });

            let data = null;
            try { data = await response.json(); } catch { /* non-JSON body */ }

            if (response.status === 401) {
                return setResult("نشست شما منقضی شده؛ دوباره وارد شوید", false);
            }
            if (!response.ok) {
                return setResult(extractError(data, "آپلود ناموفق بود"), false);
            }

            setResult(summarize(data), true);
            fileInput.value = "";
            // جدول با داده‌ی جدید دوباره بارگذاری شود
            setTimeout(() => window.location.reload(), 1200);
        } catch (error) {
            setResult("خطا در اتصال به سرور. مطمئن شوید Backend روشن است.", false);
            console.error("Upload error:", error);
        } finally {
            button.disabled = false;
            button.textContent = originalText;
        }
    });
}

initUploader();