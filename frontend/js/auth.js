// Requires js/api.js to be loaded before this file (API_URL, getToken, getUser, extractError)

// Already logged in? Skip the login page.
if (getToken() && getUser()) {
    window.location.href = "dashboard.html";
}

const loginForm = document.getElementById("loginForm");
const loginErrorBox = document.getElementById("errorMessage");

// ظاهر پیام خطا از کلاس .error در style.css می‌آید (پس‌زمینه‌ی قرمز ملایم)
if (loginErrorBox) loginErrorBox.setAttribute("role", "alert");

function showLoginError(element, message) {
    if (!element) return;
    element.textContent = message;
    element.style.display = "block";
}

function hideLoginError(element) {
    if (!element) return;
    element.textContent = "";
    element.style.display = "none";
}

// با شروع تایپ دوباره، پیام خطای قبلی پاک شود
["email", "password"].forEach((id) => {
    document.getElementById(id)?.addEventListener("input", () => hideLoginError(loginErrorBox));
});

loginForm?.addEventListener("submit", async function (e) {
    e.preventDefault();

    const emailInput = document.getElementById("email");
    const passwordInput = document.getElementById("password");
    const submitBtn = this.querySelector("button[type=submit]");

    if (!emailInput || !passwordInput || !submitBtn) return;

    const email = emailInput.value.trim();
    const password = passwordInput.value;

    hideLoginError(loginErrorBox);

    if (!email || !password) {
        showLoginError(loginErrorBox, "ایمیل و رمز عبور را وارد کنید");
        (email ? passwordInput : emailInput).focus();
        return;
    }

    // Disable button to prevent double-click
    submitBtn.disabled = true;
    const originalBtnText = submitBtn.textContent;
    submitBtn.textContent = "در حال ورود...";

    try {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });

        let data = null;
        try {
            data = await response.json();
        } catch {
            // non-JSON body (e.g. HTML error page)
        }

        if (!response.ok) {
            showLoginError(loginErrorBox, extractError(data, "ورود ناموفق بود"));
            passwordInput.select();
            return;
        }

        if (!data || !data.access_token) {
            showLoginError(loginErrorBox, "پاسخ سرور نامعتبر است");
            return;
        }

        // If the login response has no user object, fetch it from /auth/me
        let user = data.user;
        if (!user) {
            const meResponse = await fetch(`${API_URL}/auth/me`, {
                headers: { "Authorization": `Bearer ${data.access_token}` }
            });
            if (meResponse.ok) {
                user = await meResponse.json();
            }
        }

        if (!user) {
            showLoginError(loginErrorBox, "اطلاعات کاربر دریافت نشد");
            return;
        }

        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("user", JSON.stringify(user));

        window.location.href = "dashboard.html";

    } catch (error) {
        showLoginError(loginErrorBox, "خطا در اتصال به سرور. مطمئن شوید Backend روشن است.");
        console.error("Login Error:", error);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalBtnText;
    }
});