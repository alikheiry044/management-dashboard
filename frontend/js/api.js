const API_URL = "http://127.0.0.1:8000";

// Currency unit shown on dashboard cards and table headers (change here only)
const CURRENCY_LABEL = "ریال";

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

function requireLogin() {
    if (!getToken() || !getUser()) {
        window.location.href = "index.html";
    }
}

function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    window.location.href = "index.html";
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

// Shared request helper: auth header, 401 handling, safe JSON parsing, readable errors
async function apiRequest(path, options = {}, fallbackError = "درخواست ناموفق بود") {
    let response;
    const token = getToken();

    const headers = {
        ...(options.headers || {}),
    };

    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }

    try {
        response = await fetch(`${API_URL}${path}`, {
            ...options,
            headers,
        });
    } catch {
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
        // non-JSON body (e.g. HTML error page)
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
    return apiRequest(path, { method: "POST", body: formData }, "آپلود ناموفق بود");
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

        const current = window.location.pathname.split("/").pop() || "index.html";
        document.querySelectorAll(".sidebar a").forEach(function (a) {
            const href = a.getAttribute("href");
            if (href === current) {
                a.classList.add("active");
            }
        });
    });
}
