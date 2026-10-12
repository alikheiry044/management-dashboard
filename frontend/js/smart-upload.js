// js/smart-upload.js
// آپلود هوشمند با تشخیص خودکار ستون‌ها
// Requires js/api.js to be loaded before this file
// (requireLogin, getUser, logout, apiRequest, UPLOAD_TIMEOUT, escapeHtml, toPersianDigits)

if (!requireLogin()) throw new Error("not authenticated");

// کل کد داخل IIFE است تا متغیرهای سراسری (selectedFile، fileInput و ...) با فایل‌های دیگر تداخل نکنند
(function () {
    const $ = (id) => document.getElementById(id);

    const user = getUser();
    const welcome = $("welcomeText");
    if (welcome && user) {
        welcome.textContent = user.full_name || user.email || "مدیر سیستم";
    }

    $("logoutBtn")?.addEventListener("click", function (e) {
        e.preventDefault();
        logout();
    });

    // ===== State =====
    let selectedFile = null;
    let previewData = null;
    let detectedMapping = {};
    let allFileColumns = [];

    const MAX_MB = 20;
    const VALID_EXT = [".xlsx", ".xls", ".csv"];
    const PREVIEW_BTN_TEXT = "🔍 بررسی و پیش‌نمایش";
    const CONFIRM_BTN_TEXT = "✅ تأیید و import نهایی";

    // ===== Elements =====
    const uploadArea = $("uploadArea");
    const fileInput = $("fileInput");
    const previewBtn = $("previewBtn");
    const confirmBtn = $("confirmBtn");
    const backBtn = $("backBtn");

    // اگر المان‌های اصلی در صفحه نبودند، کل فایل کرش نکند
    if (!uploadArea || !fileInput || !previewBtn) {
        console.warn("smart-upload: required elements not found");
        return;
    }

    const getFileType = () => $("fileType")?.value || "";

    // ===== Upload Area =====
    uploadArea.addEventListener("click", () => fileInput.click());

    uploadArea.addEventListener("dragover", function (e) {
        e.preventDefault();
        uploadArea.classList.add("dragover");
    });

    uploadArea.addEventListener("dragleave", function () {
        uploadArea.classList.remove("dragover");
    });

    uploadArea.addEventListener("drop", function (e) {
        e.preventDefault();
        uploadArea.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", function (e) {
        if (e.target.files && e.target.files.length) {
            handleFile(e.target.files[0]);
        }
        // مقدار را خالی کن تا انتخاب دوباره‌ی همان فایل هم رویداد change بدهد
        fileInput.value = "";
    });

    function handleFile(file) {
        const dot = file.name.lastIndexOf(".");
        const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";

        if (!VALID_EXT.includes(ext)) {
            alert("❌ فرمت فایل نامعتبر است. فقط .xlsx, .xls, .csv مجاز است.");
            return;
        }
        if (file.size === 0) {
            alert("❌ فایل انتخاب‌شده خالی است.");
            return;
        }
        if (file.size > MAX_MB * 1024 * 1024) {
            alert(`❌ حجم فایل بیش از ${toPersianDigits(MAX_MB)} مگابایت است.`);
            return;
        }

        selectedFile = file;

        const uploadText = uploadArea.querySelector(".upload-text");
        const uploadHint = uploadArea.querySelector(".upload-hint");
        const uploadIcon = uploadArea.querySelector(".upload-icon");

        if (uploadIcon) uploadIcon.textContent = "✅";
        if (uploadText) uploadText.textContent = file.name;
        if (uploadHint) uploadHint.textContent = toPersianDigits((file.size / 1024 / 1024).toFixed(2)) + " مگابایت — آماده بررسی";

        previewBtn.disabled = false;
        previewBtn.textContent = PREVIEW_BTN_TEXT;
    }

    // ===== Preview =====
    previewBtn.addEventListener("click", async function () {
        if (!selectedFile) return;

        previewBtn.disabled = true;
        previewBtn.textContent = "⏳ در حال بررسی و تشخیص ستون‌ها...";

        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("file_type", getFileType());

        try {
            // apiRequest: هدر Authorization، timeout، مدیریت ۴۰۱ و خواندن امن خطای ۴۲۲
            const data = await apiRequest(
                "/smart-upload/preview",
                { method: "POST", body: formData, timeout: UPLOAD_TIMEOUT },
                "خطا در بررسی فایل"
            );

            previewData = data;
            showPreview(data || {});
        } catch (error) {
            alert("❌ " + error.message);
        } finally {
            // دکمه همیشه دوباره فعال شود (وگرنه بعد از «بازگشت» برای فایل قبلی قفل می‌ماند)
            previewBtn.disabled = false;
            previewBtn.textContent = PREVIEW_BTN_TEXT;
        }
    });

    function setStep(id, className, html) {
        const el = $(id);
        if (!el) return;
        if (className === "active") {
            el.classList.add("active");
            el.classList.remove("completed");
        } else if (className === "completed") {
            el.classList.remove("active");
            el.classList.add("completed");
        } else {
            el.classList.remove("active", "completed");
        }
        if (html !== undefined) el.innerHTML = html;
    }

    function showPreview(data) {
        $("uploadSection")?.classList.add("hidden");
        $("previewSection")?.classList.remove("hidden");
        setStep("step1", "completed", "✓ انتخاب فایل");
        setStep("step2", "active");

        // هشدارها
        const warningsBox = $("warningsBox");
        if (warningsBox) {
            warningsBox.innerHTML = "";
            if (data.warnings && data.warnings.length) {
                const warningHtml = data.warnings.map((w) => "<div>" + escapeHtml(w) + "</div>").join("");
                warningsBox.innerHTML = '<div class="alert alert-warning">⚠️ ' + warningHtml + "</div>";
            }
        }

        allFileColumns = data.columns || [];

        const fieldLabels = {
            party_name: "نام طرف حساب",
            amount: "مبلغ",
            code: "کد",
            date: "تاریخ",
            description: "توضیحات",
            customer_name: "نام مشتری",
            remaining_amount: "مانده بدهی",
            product_name: "نام کالا",
            quantity: "تعداد",
            unit_price: "قیمت واحد",
            category: "دسته‌بندی",
            bank_name: "نام بانک",
            account_number: "شماره حساب",
            phone: "شماره تماس",
            invoice_number: "شماره فاکتور"
        };

        const mappingBody = $("mappingBody");
        const detected = data.detected || {};
        detectedMapping = {};
        if (mappingBody) mappingBody.innerHTML = "";

        Object.keys(detected).forEach(function (field) {
            const det = detected[field] || {};
            // فقط ستون‌های واقعاً تشخیص‌داده‌شده وارد نگاشت شوند (نه null)
            if (det.column) detectedMapping[field] = det.column;

            const confidence = det.confidence || 0;
            const confidenceClass = confidence >= 0.8 ? "high" : confidence >= 0.6 ? "medium" : "low";
            const confidenceText = toPersianDigits((confidence * 100).toFixed(0)) + "٪";
            const label = fieldLabels[field] || field;

            const row = document.createElement("tr");

            const td1 = document.createElement("td");
            td1.innerHTML = "<strong>" + escapeHtml(label) + '</strong><br><small style="color:var(--muted);">' + escapeHtml(field) + "</small>";
            row.appendChild(td1);

            const td2 = document.createElement("td");
            td2.textContent = det.column || "—";
            td2.style.fontWeight = "600";
            row.appendChild(td2);

            const td3 = document.createElement("td");
            td3.innerHTML = '<span class="confidence ' + confidenceClass + '">' + confidenceText + "</span>";
            row.appendChild(td3);

            const td4 = document.createElement("td");
            const select = document.createElement("select");
            select.className = "form-control";
            select.style.padding = "6px 10px";
            select.style.fontSize = "12px";

            const noneOption = document.createElement("option");
            noneOption.value = "";
            noneOption.textContent = "— بدون نگاشت —";
            select.appendChild(noneOption);

            allFileColumns.forEach(function (col) {
                const option = document.createElement("option");
                option.value = col;
                option.textContent = col;
                if (col === det.column) option.selected = true;
                select.appendChild(option);
            });

            select.addEventListener("change", function () {
                updateMapping(field, this.value);
            });

            td4.appendChild(select);
            row.appendChild(td4);

            mappingBody?.appendChild(row);
        });

        if (mappingBody && Object.keys(detected).length === 0) {
            mappingBody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--orange);">⚠️ هیچ ستونی به صورت خودکار تشخیص داده نشد. لطفاً نوع فایل را در مرحله قبل مشخص کنید.</td></tr>';
        }

        // پیش‌نمایش جدول
        const previewTable = $("previewTable");
        if (previewTable) {
            if (data.preview && data.preview.length) {
                const headers = Object.keys(data.preview[0]);
                let html = "<thead><tr>";
                headers.forEach((h) => { html += "<th>" + escapeHtml(h) + "</th>"; });
                html += "</tr></thead><tbody>";

                data.preview.forEach(function (row) {
                    html += "<tr>";
                    headers.forEach((h) => {
                        // ?? تا مقدار 0 هم نمایش داده شود (قبلاً با || خالی می‌شد)
                        html += "<td>" + escapeHtml(row[h] ?? "") + "</td>";
                    });
                    html += "</tr>";
                });
                html += "</tbody>";
                previewTable.innerHTML = html;
            } else {
                previewTable.innerHTML = '<tr><td style="text-align:center;padding:20px;color:var(--muted);">پیش‌نمایشی در دسترس نیست</td></tr>';
            }
        }

        const totalRows = $("totalRows");
        if (totalRows) totalRows.textContent = toPersianDigits(data.row_count || 0);
    }

    function updateMapping(field, newColumn) {
        if (newColumn === "") {
            delete detectedMapping[field];
        } else {
            detectedMapping[field] = newColumn;
        }
    }

    // ===== Back Button =====
    backBtn?.addEventListener("click", function () {
        $("uploadSection")?.classList.remove("hidden");
        $("previewSection")?.classList.add("hidden");
        setStep("step1", "active", "۱. انتخاب فایل");
        setStep("step2", "reset");
    });

    // ===== Confirm Import =====
    function errorToText(e) {
        if (typeof e === "string") return e;
        if (e && typeof e === "object") return e.message || e.msg || e.error || JSON.stringify(e);
        return String(e);
    }

    confirmBtn?.addEventListener("click", async function () {
        if (!selectedFile) {
            alert("⚠️ ابتدا یک فایل انتخاب کنید.");
            return;
        }
        if (Object.keys(detectedMapping).length === 0) {
            alert("⚠️ حداقل یک فیلد باید نگاشت شود.");
            return;
        }

        confirmBtn.disabled = true;
        confirmBtn.textContent = "⏳ در حال import و پردازش...";

        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("file_type", getFileType());
        formData.append("column_mapping", JSON.stringify(detectedMapping));

        try {
            const data = await apiRequest(
                "/smart-upload/confirm",
                { method: "POST", body: formData, timeout: UPLOAD_TIMEOUT },
                "خطا در import"
            );

            $("previewSection")?.classList.add("hidden");
            $("successSection")?.classList.remove("hidden");
            setStep("step2", "completed", "✓ بررسی تشخیص");
            setStep("step3", "active");

            // نام فیلد تعداد ردیف در پاسخ بک‌اند ممکن است متفاوت باشد
            const rowCount = data?.row_count ?? data?.created ?? data?.inserted ?? data?.imported ?? 0;

            let html =
                '<strong style="font-size:18px;color:var(--green);">' + escapeHtml(toPersianDigits(rowCount)) + " ردیف</strong> با موفقیت وارد سیستم شد.<br>" +
                '<small style="color:var(--muted);">موتور ریسک به صورت خودکار داده‌ها را تحلیل کرد.</small>';

            // نمایش ردیف‌های ردشده/خطادار (قبلاً کاملاً نادیده گرفته می‌شد)
            const notes = [];
            if (data?.skipped_duplicates) notes.push(escapeHtml(toPersianDigits(data.skipped_duplicates)) + " مورد تکراری رد شد");
            if (Array.isArray(data?.errors) && data.errors.length) {
                notes.push(escapeHtml(toPersianDigits(data.errors.length)) + " ردیف خطا داشت: " +
                    data.errors.slice(0, 5).map((e) => escapeHtml(errorToText(e))).join("، "));
            }
            if (notes.length) {
                html += '<br><small style="color:var(--orange);">⚠️ ' + notes.join(" — ") + "</small>";
            }

            const successMessage = $("successMessage");
            if (successMessage) successMessage.innerHTML = html;

        } catch (error) {
            alert("❌ " + error.message);
            confirmBtn.disabled = false;
            confirmBtn.textContent = CONFIRM_BTN_TEXT;
        }
    });
})();