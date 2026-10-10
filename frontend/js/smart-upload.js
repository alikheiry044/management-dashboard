// js/smart-upload.js
// آپلود هوشمند با تشخیص خودکار ستون‌ها

requireLogin();

const user = getUser();
const welcome = document.getElementById("welcomeText");
if (welcome && user) {
    welcome.textContent = user.full_name || user.email || "مدیر سیستم";
}

document.getElementById("logoutBtn")?.addEventListener("click", function (e) {
    e.preventDefault();
    logout();
});

// ===== State =====
let selectedFile = null;
let previewData = null;
let detectedMapping = {};
let allFileColumns = [];

// ===== Upload Area =====
const uploadArea = document.getElementById("uploadArea");
const fileInput = document.getElementById("fileInput");
const previewBtn = document.getElementById("previewBtn");

uploadArea.addEventListener("click", function() {
    fileInput.click();
});

uploadArea.addEventListener("dragover", function(e) {
    e.preventDefault();
    uploadArea.classList.add("dragover");
});

uploadArea.addEventListener("dragleave", function() {
    uploadArea.classList.remove("dragover");
});

uploadArea.addEventListener("drop", function(e) {
    e.preventDefault();
    uploadArea.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener("change", function(e) {
    if (e.target.files && e.target.files.length) {
        handleFile(e.target.files[0]);
    }
});

function handleFile(file) {
    // اعتبارسنجی نوع فایل
    const validTypes = [".xlsx", ".xls", ".csv"];
    const ext = "." + file.name.split(".").pop().toLowerCase();

    if (!validTypes.includes(ext)) {
        alert(" فرمت فایل نامعتبر است. فقط .xlsx, .xls, .csv مجاز است.");
        return;
    }

    // اعتبارسنجی حجم (۲۰ مگابایت)
    if (file.size > 20 * 1024 * 1024) {
        alert("❌ حجم فایل بیش از ۲۰ مگابایت است.");
        return;
    }

    selectedFile = file;

    // به‌روزرسانی UI
    const uploadText = uploadArea.querySelector(".upload-text");
    const uploadHint = uploadArea.querySelector(".upload-hint");
    const uploadIcon = uploadArea.querySelector(".upload-icon");

    uploadIcon.textContent = "✅";
    uploadText.textContent = file.name;
    uploadHint.textContent = (file.size / 1024 / 1024).toFixed(2) + " مگابایت — آماده بررسی";

    previewBtn.disabled = false;
    previewBtn.textContent = "🔍 بررسی و پیش‌نمایش";
}

// ===== Preview =====
previewBtn.addEventListener("click", async function() {
    if (!selectedFile) return;

    previewBtn.disabled = true;
    previewBtn.textContent = "⏳ در حال بررسی و تشخیص ستون‌ها...";

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("file_type", document.getElementById("fileType").value);

    try {
        const token = getToken();
        const response = await fetch(API_URL + "/smart-upload/preview", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token },
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "خطا در بررسی فایل");
        }

        previewData = data;
        showPreview(data);

    } catch (error) {
        alert("❌ " + error.message);
        previewBtn.disabled = false;
        previewBtn.textContent = "🔍 بررسی و پیش‌نمایش";
    }
});

function showPreview(data) {
    // تغییر step
    document.getElementById("uploadSection").classList.add("hidden");
    document.getElementById("previewSection").classList.remove("hidden");
    document.getElementById("step1").classList.remove("active");
    document.getElementById("step1").classList.add("completed");
    document.getElementById("step1").innerHTML = "✓ انتخاب فایل";
    document.getElementById("step2").classList.add("active");

    // نمایش هشدارها
    const warningsBox = document.getElementById("warningsBox");
    warningsBox.innerHTML = "";

    if (data.warnings && data.warnings.length) {
        const warningHtml = data.warnings.map(function(w) {
            return '<div>' + escapeHtml(w) + '</div>';
        }).join("");
        warningsBox.innerHTML = '<div class="alert alert-warning">⚠️ ' + warningHtml + '</div>';
    }

    // ذخیره ستون‌های فایل
    allFileColumns = data.columns || [];

    // نمایش mapping
    const mappingBody = document.getElementById("mappingBody");
    mappingBody.innerHTML = "";
    detectedMapping = {};

    const fieldLabels = {
        "party_name": "نام طرف حساب",
        "amount": "مبلغ",
        "code": "کد",
        "date": "تاریخ",
        "description": "توضیحات",
        "customer_name": "نام مشتری",
        "remaining_amount": "مانده بدهی",
        "product_name": "نام کالا",
        "quantity": "تعداد",
        "unit_price": "قیمت واحد",
        "category": "دسته‌بندی",
        "bank_name": "نام بانک",
        "account_number": "شماره حساب",
        "phone": "شماره تماس",
        "invoice_number": "شماره فاکتور"
    };

    Object.keys(data.detected).forEach(function(field) {
        const det = data.detected[field];
        detectedMapping[field] = det.column;

        const confidence = det.confidence || 0;
        const confidenceClass = confidence >= 0.8 ? "high" :
                               confidence >= 0.6 ? "medium" : "low";
        const confidenceText = (confidence * 100).toFixed(0) + "%";

        const label = fieldLabels[field] || field;

        const row = document.createElement("tr");

        // ستون اول: نام فیلد
        const td1 = document.createElement("td");
        td1.innerHTML = '<strong>' + escapeHtml(label) + '</strong><br><small style="color:var(--muted);">' + escapeHtml(field) + '</small>';
        row.appendChild(td1);

        // ستون دوم: ستون تشخیص داده شده
        const td2 = document.createElement("td");
        td2.textContent = det.column;
        td2.style.fontWeight = "600";
        row.appendChild(td2);

        // ستون سوم: امتیاز اطمینان
        const td3 = document.createElement("td");
        td3.innerHTML = '<span class="confidence ' + confidenceClass + '">' + confidenceText + '</span>';
        row.appendChild(td3);

        // ستون چهارم: منوی کشویی برای تغییر
        const td4 = document.createElement("td");
        const select = document.createElement("select");
        select.className = "form-control";
        select.style.padding = "6px 10px";
        select.style.fontSize = "12px";

        // گزینه "بدون نگاشت"
        const noneOption = document.createElement("option");
        noneOption.value = "";
        noneOption.textContent = "— بدون نگاشت —";
        select.appendChild(noneOption);

        // همه ستون‌های فایل
        allFileColumns.forEach(function(col) {
            const option = document.createElement("option");
            option.value = col;
            option.textContent = col;
            if (col === det.column) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        select.addEventListener("change", function() {
            updateMapping(field, this.value);
        });

        td4.appendChild(select);
        row.appendChild(td4);

        mappingBody.appendChild(row);
    });

    // اگر هیچ فیلدی تشخیص داده نشد
    if (Object.keys(data.detected).length === 0) {
        mappingBody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--orange);">️ هیچ ستونی به صورت خودکار تشخیص داده نشد. لطفاً نوع فایل را در مرحله قبل مشخص کنید.</td></tr>';
    }

    // نمایش پیش‌نمایش جدول
    const previewTable = document.getElementById("previewTable");
    if (data.preview && data.preview.length) {
        const headers = Object.keys(data.preview[0]);
        let html = '<thead><tr>';
        headers.forEach(function(h) {
            html += '<th>' + escapeHtml(h) + '</th>';
        });
        html += '</tr></thead><tbody>';

        data.preview.forEach(function(row) {
            html += '<tr>';
            headers.forEach(function(h) {
                html += '<td>' + escapeHtml(row[h] || '') + '</td>';
            });
            html += '</tr>';
        });
        html += '</tbody>';

        previewTable.innerHTML = html;
    } else {
        previewTable.innerHTML = '<tr><td style="text-align:center;padding:20px;color:var(--muted);">پیش‌نمایشی در دسترس نیست</td></tr>';
    }

    document.getElementById("totalRows").textContent = toPersianDigits(data.row_count || 0);
}

function updateMapping(field, newColumn) {
    if (newColumn === "") {
        delete detectedMapping[field];
    } else {
        detectedMapping[field] = newColumn;
    }
}

// ===== Back Button =====
document.getElementById("backBtn").addEventListener("click", function() {
    document.getElementById("uploadSection").classList.remove("hidden");
    document.getElementById("previewSection").classList.add("hidden");
    document.getElementById("step1").classList.add("active");
    document.getElementById("step1").classList.remove("completed");
    document.getElementById("step1").innerHTML = "۱. انتخاب فایل";
    document.getElementById("step2").classList.remove("active");
});

// ===== Confirm Import =====
document.getElementById("confirmBtn").addEventListener("click", async function() {
    const confirmBtn = document.getElementById("confirmBtn");

    if (Object.keys(detectedMapping).length === 0) {
        alert("⚠️ حداقل یک فیلد باید نگاشت شود.");
        return;
    }

    confirmBtn.disabled = true;
    confirmBtn.textContent = " در حال import و پردازش...";

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("file_type", document.getElementById("fileType").value);
    formData.append("column_mapping", JSON.stringify(detectedMapping));

    try {
        const token = getToken();
        const response = await fetch(API_URL + "/smart-upload/confirm", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token },
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "خطا در import");
        }

        // نمایش صفحه موفقیت
        document.getElementById("previewSection").classList.add("hidden");
        document.getElementById("successSection").classList.remove("hidden");
        document.getElementById("step2").classList.remove("active");
        document.getElementById("step2").classList.add("completed");
        document.getElementById("step2").innerHTML = "✓ بررسی تشخیص";
        document.getElementById("step3").classList.add("active");

        const rowCount = data.row_count || 0;
        document.getElementById("successMessage").innerHTML =
            '<strong style="font-size:18px;color:var(--green);">' + toPersianDigits(rowCount) + ' ردیف</strong> با موفقیت وارد سیستم شد.<br>' +
            '<small style="color:var(--muted);">موتور ریسک به صورت خودکار داده‌ها را تحلیل کرد.</small>';

    } catch (error) {
        alert("❌ " + error.message);
        confirmBtn.disabled = false;
        confirmBtn.textContent = "✅ تأیید و import نهایی";
    }
});
