// آدرس Backend: همان hostname صفحه‌ی فعلی را استفاده می‌کند تا localhost و 127.0.0.1
// دچار مشکل CORS نشوند. اگر صفحه با file:// باز شده باشد، 127.0.0.1 استفاده می‌شود.
// هنگام دیپلوی فقط همین یک خط را عوض کن.
const API_URL = `http://${window.location.hostname || "127.0.0.1"}:8000`;

// Currency unit shown on dashboard cards and table headers (change here only)
const CURRENCY_LABEL = "ریال";

// زمان انتظار پیش‌فرض (میلی‌ثانیه)
const REQUEST_TIMEOUT = 30000;
const UPLOAD_TIMEOUT = 120000;

function getToken() {
    return localStorage.getItem("access_token");
}

function getUser() {
    try {
        const user = localStorage.getItem("user");
        return user ? JSON.parse(user) : null;
    } catch {
        return null;
    }
}

// مقدار true/false برمی‌گرداند. در بالای هر صفحه‌ی محافظت‌شده این‌طور استفاده کن:
//   if (!requireLogin()) throw new Error("not authenticated");
// تا بقیه‌ی کد صفحه بدون توکن اجرا نشود.
function requireLogin() {
    if (!getToken() || !getUser()) {
        window.location.replace("index.html");
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    window.location.replace("index.html");
}

// Turns FastAPI's `detail` (string or 422 array) into a readable message
function extractError(data, fallback) {
    if (!data || !data.detail) return fallback;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
        return data.detail.map((d) => d.msg || JSON.stringify(d)).join("، ");
    }
    return fallback;
}

// fetch با timeout؛ اگر سرور جواب ندهد درخواست قطع می‌شود
async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(url, { ...options, signal: controller.signal });
    } finally {
        clearTimeout(timer);
    }
}

// Shared request helper: auth header, timeout, 401 handling, safe JSON parsing, readable errors
async function apiRequest(path, options = {}, fallbackError = "درخواست ناموفق بود") {
    const { timeout, ...fetchOptions } = options;
    const token = getToken();

    const headers = { ...(fetchOptions.headers || {}) };
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }

    let response;
    try {
        response = await fetchWithTimeout(
            `${API_URL}${path}`,
            { ...fetchOptions, headers },
            timeout || REQUEST_TIMEOUT
        );
    } catch (err) {
        if (err && err.name === "AbortError") {
            throw new Error("سرور پاسخ نداد. دوباره تلاش کنید.");
        }
        throw new Error("اتصال به سرور برقرار نشد. مطمئن شوید Backend روشن است.");
    }

    if (response.status === 401) {
        logout();
        throw new Error("نشست شما منقضی شده است. لطفاً دوباره وارد شوید.");
    }

    let data = null;
    try {
        data = await response.json();
    } catch {
        // non-JSON body (e.g. HTML error page or 204 No Content)
    }

    if (!response.ok) {
        throw new Error(extractError(data, fallbackError));
    }
    return data;
}

async function apiGet(path) {
    return apiRequest(path, { method: "GET" }, "دریافت اطلاعات ناموفق بود");
}

async function apiPost(path, body) {
    return apiRequest(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    }, "ثبت اطلاعات ناموفق بود");
}

async function apiUpload(path, file) {
    const formData = new FormData();
    formData.append("file", file);
    // Do not set Content-Type: the browser adds the multipart boundary itself
    return apiRequest(
        path,
        { method: "POST", body: formData, timeout: UPLOAD_TIMEOUT },
        "آپلود ناموفق بود"
    );
}

function toPersianDigits(text) {
    if (text === null || text === undefined) return "";
    return String(text).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
}

function formatNumber(num) {
    if (num === null || num === undefined || num === "-" || num === "") return "-";
    const n = Number(num);
    if (Number.isNaN(n)) return "-";
    return n.toLocaleString("fa-IR");
}

// Escape text before putting it into innerHTML (data may come from uploaded Excel files)
function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// Highlight the current page's link in the sidebar & set currency units
if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".currency-unit").forEach(function (el) {
            el.textContent = CURRENCY_LABEL;
        });

        // فقط اسم فایل، بدون مسیر / query / hash
        const fileName = (p) => (p || "").split(/[?#]/)[0].split("/").pop();
        const current = fileName(window.location.pathname) || "index.html";

        document.querySelectorAll(".sidebar a").forEach(function (a) {
            if (fileName(a.getAttribute("href")) === current) {
                a.classList.add("active");
            }
        });
    });
}