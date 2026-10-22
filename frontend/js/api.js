// Backend manzili sahifa ochilgan hostdan olinadi:
// kompyuterda localhost, telefonda kompyuterning IP manzili (masalan 192.168.1.5)
const API_BASE = `http://${window.location.hostname}:8000/api/v1`;

const TOKEN_KEY = "ustabor_token";
const USER_KEY = "ustabor_user";

// ===== Umumiy holat va rol lug'atlari =====
const ORDER_STATUS_LABELS = {
  searching: "Qidirilmoqda",
  assigned: "Biriktirildi",
  in_progress: "Jarayonda",
  completed: "Yakunlandi",
  cancelled: "Bekor qilindi",
};

const ROLE_LABELS = {
  customer: "Mijoz",
  master: "Usta",
  admin: "Admin",
};

const PAYMENT_STATUS_LABELS = {
  paid: "To'langan",
  pending: "Kutilmoqda",
};

function formatOrderStatus(status) {
  return ORDER_STATUS_LABELS[status] || status || "";
}

function formatRole(role) {
  return ROLE_LABELS[role] || role || "";
}

function formatPaymentStatus(status) {
  return PAYMENT_STATUS_LABELS[status] || status || "To'langan";
}

function formatDate(dtStr) {
  if (!dtStr) return "—";
  const d = new Date(dtStr);
  if (isNaN(d.getTime())) return "—";
  const pad = (n) => String(n).padStart(2, "0");
  return (
    pad(d.getDate()) +
    "." +
    pad(d.getMonth() + 1) +
    "." +
    d.getFullYear() +
    " " +
    pad(d.getHours()) +
    ":" +
    pad(d.getMinutes())
  );
}

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

// 403 / ruxsat yo'q holatini sahifada ko'rsatish
function renderForbidden(message) {
  const main = document.querySelector("main.container");
  if (!main) return;
  main.replaceChildren();

  const card = document.createElement("div");
  card.className = "card empty-state";

  const title = document.createElement("h1");
  title.textContent = "Ruxsat yo'q";

  const desc = document.createElement("p");
  desc.className = "muted";
  desc.textContent = message || "Bu sahifani ko'rish uchun sizda ruxsat yo'q.";

  const homeLink = document.createElement("a");
  homeLink.className = "btn";
  homeLink.style.marginTop = "12px";
  homeLink.href = homeFor(getUser());
  homeLink.textContent = "Bosh sahifaga qaytish";

  card.append(title, desc, homeLink);
  main.appendChild(card);
  renderNav("");
}

// Sahifani himoyalash: kirmagan -> login.html, noto'g'ri rol -> "Ruxsat yo'q" va bosh sahifaga havola.
// Ruxsat bo'lsa foydalanuvchini qaytaradi, aks holda null.
function requireAuth(roles) {
  const user = getUser();
  if (!getToken() || !user) {
    clearSession();
    window.location.replace("login.html");
    return null;
  }
  if (roles && roles.length && !roles.includes(user.role)) {
    renderForbidden("Bu sahifa faqat " + roles.map(formatRole).join(", ") + " uchun mo'ljallangan.");
    return null;
  }
  return user;
}

// ===== Xatolarni o'qiladigan matnga aylantirish =====
const FIELD_LABELS = {
  phone: "Telefon",
  password: "Parol",
  current_password: "Joriy parol",
  new_password: "Yangi parol",
  full_name: "Ism",
  role: "Rol",
  bio: "Ma'lumot",
  city: "Shahar",
  district: "Tuman",
  address: "Manzil",
  description: "Tavsif",
  category_id: "Xizmat turi",
  selection_mode: "Tanlash usuli",
  master_id: "Usta",
  pricing_type: "Narxlash turi",
  base_price: "Narx",
  price: "Narx",
  note: "Izoh",
  rating: "Baho",
  comment: "Sharh",
  is_available: "Holat",
  is_active: "Faollik holati",
  is_approved: "Tasdiqlash holati",
  date_from: "Boshlanish sanasi",
  date_to: "Tugash sanasi",
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
    case "greater_than":
      text = `${ctx.gt} dan katta bo'lishi kerak`;
      break;
    case "greater_than_equal":
      text = `kamida ${ctx.ge} bo'lishi kerak`;
      break;
    case "less_than_equal":
      text = `ko'pi bilan ${ctx.le} bo'lishi kerak`;
      break;
    case "int_parsing":
    case "int_type":
      text = "butun son bo'lishi kerak";
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
    const err = new Error(formatError(data));
    err.status = res.status;
    throw err;
  }
  return data;
}

// ===== Umumiy navigatsiya =====
function renderNav(activeKey) {
  let nav = document.querySelector("nav.bottom-nav");
  if (!nav) {
    nav = document.createElement("nav");
    nav.className = "bottom-nav";
    document.body.appendChild(nav);
  }
  nav.replaceChildren();

  const user = getToken() ? getUser() : null;
  let items;

  if (user && user.role === "master") {
    items = [
      { key: "dashboard", href: "master-dashboard.html", icon: "📋", label: "Takliflar" },
      { key: "profile", href: "master-profile.html", icon: "👤", label: "Profil" },
      { key: "logout", href: "login.html", icon: "🚪", label: "Chiqish", onClick: logout },
    ];
  } else if (user && user.role === "customer") {
    items = [
      { key: "home", href: "index.html", icon: "🏠", label: "Asosiy" },
      { key: "orders", href: "my-orders.html", icon: "📋", label: "Buyurtmalar" },
      { key: "profile", href: "profile.html", icon: "👤", label: "Profil" },
    ];
  } else if (user && user.role === "admin") {
    items = [
      { key: "home", href: "index.html", icon: "🏠", label: "Asosiy" },
      { key: "admin", href: "admin.html", icon: "⚙️", label: "Admin" },
      { key: "logout", href: "login.html", icon: "🚪", label: "Chiqish", onClick: logout },
    ];
  } else {
    items = [
      { key: "home", href: "index.html", icon: "🏠", label: "Asosiy" },
      { key: "login", href: "login.html", icon: "🔑", label: "Kirish" },
      { key: "register", href: "register.html", icon: "📝", label: "Ro'yxatdan o'tish" },
    ];
  }

  items.forEach((item) => {
    const a = document.createElement("a");
    a.href = item.href;
    if (item.key === activeKey) {
      a.className = "active";
    }
    const iconSpan = document.createElement("span");
    iconSpan.className = "icon";
    iconSpan.textContent = item.icon;
    const labelNode = document.createTextNode(item.label);
    a.append(iconSpan, labelNode);

    if (item.onClick) {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        item.onClick();
      });
    }
    nav.appendChild(a);
  });
}
