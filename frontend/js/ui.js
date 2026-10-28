// Umumiy UI yordamchilari: toast, tasdiqlash modali, avtomatik yangilanish (polling).
// Barcha sahifalarda api.js dan keyin yuklanadi.

function toast(message, type) {
  type = type === "success" || type === "error" ? type : "info";
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const el = document.createElement("div");
  el.className = "toast toast-" + type;
  el.setAttribute("role", "status");
  el.textContent = message;
  container.appendChild(el);

  requestAnimationFrame(() => el.classList.add("show"));

  const remove = () => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 200);
  };
  setTimeout(remove, 4000);
  el.addEventListener("click", remove);
}

// Natija: Promise<boolean> — "Ha" bosilsa true, "Yo'q"/Esc/tashqariga bosilsa false.
function confirmModal(message, options) {
  options = options || {};
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";

    const box = document.createElement("div");
    box.className = "modal-content";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");

    const text = document.createElement("p");
    text.style.margin = "0 0 16px";
    text.style.fontWeight = "600";
    text.textContent = message;

    const row = document.createElement("div");
    row.className = "modal-actions";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-outline";
    cancelBtn.style.flex = "1";
    cancelBtn.textContent = options.cancelLabel || "Yo'q";

    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = "btn " + (options.danger ? "btn-danger" : "btn-accent");
    okBtn.style.flex = "1";
    okBtn.textContent = options.okLabel || "Ha";

    function close(result) {
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      resolve(result);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") close(false);
    }

    cancelBtn.addEventListener("click", () => close(false));
    okBtn.addEventListener("click", () => close(true));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(false);
    });

    row.append(cancelBtn, okBtn);
    box.append(text, row);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    document.addEventListener("keydown", onKeyDown);
    okBtn.focus();
  });
}

// fn har `ms` millisoniyada chaqiriladi, lekin faqat tab ko'rinib turganda.
// Qaytaradi: stop() — pollingni to'xtatish uchun.
function startPolling(fn, ms) {
  let stopped = false;
  let timer = null;

  function schedule() {
    timer = setTimeout(tick, ms);
  }
  function isEditingForm() {
    const el = document.activeElement;
    return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA");
  }

  function tick() {
    if (stopped) return;
    // Foydalanuvchi forma to'ldirayotgan bo'lsa, fon yangilanishi uni o'chirib
    // qo'ymasligi uchun shu safar o'tkazib yuboriladi.
    if (document.visibilityState === "visible" && !isEditingForm()) {
      fn();
    }
    schedule();
  }
  function onVisibilityChange() {
    if (!stopped && document.visibilityState === "visible" && !isEditingForm()) {
      fn();
    }
  }

  schedule();
  document.addEventListener("visibilitychange", onVisibilityChange);

  return function stop() {
    if (stopped) return;
    stopped = true;
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisibilityChange);
  };
}
