// Backend manzili sahifa ochilgan hostdan olinadi:
// kompyuterda localhost, telefonda kompyuterning IP manzili (masalan 192.168.1.5)
const API_BASE = `http://${window.location.hostname}:8000/api/v1`;

const TOKEN_KEY = "ustabor_token";
const USER_KEY = "ustabor_user";

// ===== Sessiya =====
function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY));
  } catch (e) {
    return null;
  }
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function logout() {
  clearSession();
  window.location.replace("login.html");
}

// Rolga qarab bosh sahifa
function homeFor(user) {
  if (user && user.role === "admin") return "admin.html";
  if (user && user.role === "master") return "master-dashboard.html";
  return "index.html";
}

// Sahifani himoyalash: kirmagan -> login.html, noto'g'ri rol -> o'z sahifasi.
// Ruxsat bo'lsa foydalanuvchini qaytaradi, aks holda null.
function requireAuth(roles) {
  const user = getUser();
  if (!getToken() || !user) {
    clearSession();
    window.location.replace("login.html");
    return null;
  }
  if (roles && roles.length && !roles.includes(user.role)) {
    window.location.replace(homeFor(user));
    return null;
  }
  return user;
}

// ===== Xatolarni o'qiladigan matnga aylantirish =====
const FIELD_LABELS = {
  phone: "Telefon",
  password: "Parol",
  full_name: "Ism",
  role: "Rol",
};

function formatValidationItem(item) {
  const field = item.loc && item.loc[item.loc.length - 1];
  const label = FIELD_LABELS[field] || field || "Maydon";
  const ctx = item.ctx || {};
  let text;
  switch (item.type) {
    case "missing":
      text = "to'ldirilishi shart";
      break;
    case "string_too_short":
      text = `kamida ${ctx.min_length} ta belgidan iborat bo'lishi kerak`;
      break;
    case "string_too_long":
      text = `ko'pi bilan ${ctx.max_length} ta belgidan iborat bo'lishi kerak`;
      break;
    case "value_error":
      text = String(item.msg || "").replace(/^Value error,\s*/, "");
      break;
    default:
      text = "noto'g'ri qiymat";
  }
  return `${label}: ${text}`;
}

function formatError(data) {
  const detail = data && (data.detail || data.message);
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(formatValidationItem).join(". ");
  return "Xatolik yuz berdi";
}

function formatSom(n) {
  if (n === null || n === undefined || isNaN(n)) return "";
  const parts = String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${parts} so'm`;
}

// ===== So'rovlar =====
async function apiFetch(path, options = {}) {
  const { headers, ...rest } = options;
  const finalHeaders = { "Content-Type": "application/json", ...(headers || {}) };
  const token = getToken();
  if (token && !finalHeaders.Authorization) {
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  let res;
  try {
    res = await fetch(API_BASE + path, { ...rest, headers: finalHeaders });
  } catch (e) {
    throw new Error("Serverga ulanib bo'lmadi");
  }
  const data = await res.json().catch(() => null);

  if (!res.ok) {
    // Token yaroqsiz yoki muddati o'tgan: sessiyani tozalab, login sahifasiga
    if (res.status === 401 && path !== "/auth/login") {
      clearSession();
      window.location.replace("login.html");
    }
    throw new Error(formatError(data));
  }
  return data;
}
