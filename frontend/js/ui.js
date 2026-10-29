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
    if (!el) return false;
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return true;
    // Yulduz tanlagich tugmalari ham forma elementi deb hisoblanadi: aks holda
    // fon yangilanishi foydalanuvchi hali yubormagan tanlovni o'chirib qo'yadi.
    if (el.tagName === "BUTTON" && el.closest(".star-rating")) return true;
    return false;
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

// Buyurtma chatini (GET/POST /orders/{id}/messages) ko'rsatuvchi widget.
// Qaytaradi: { el, reload } — el DOM'ga qo'shiladi, reload() fon yangilanishida chaqiriladi.
function createChatWidget(orderId, currentUserId) {
  const wrap = document.createElement("div");
  wrap.className = "chat-widget";

  const title = document.createElement("div");
  title.style.fontWeight = "600";
  title.style.margin = "10px 0 6px";
  title.textContent = "Xabarlar";

  const list = document.createElement("div");
  list.style.display = "flex";
  list.style.flexDirection = "column";
  list.style.gap = "6px";
  list.style.maxHeight = "240px";
  list.style.overflowY = "auto";
  list.style.marginBottom = "8px";
  list.style.padding = "8px";
  list.style.background = "var(--bg)";
  list.style.borderRadius = "10px";

  const form = document.createElement("form");
  form.style.display = "flex";
  form.style.gap = "8px";
  form.noValidate = true;

  const input = document.createElement("input");
  input.type = "text";
  input.maxLength = 2000;
  input.placeholder = "Xabar yozing...";
  input.style.flex = "1";
  input.style.margin = "0";

  const sendBtn = document.createElement("button");
  sendBtn.type = "submit";
  sendBtn.className = "btn";
  sendBtn.style.width = "auto";
  sendBtn.style.padding = "0 16px";
  sendBtn.textContent = "Yuborish";

  const errEl = document.createElement("div");
  errEl.className = "form-error";
  errEl.style.margin = "4px 0 0";
  errEl.setAttribute("role", "alert");

  form.append(input, sendBtn);
  wrap.append(title, list, form, errEl);

  async function load() {
    let items;
    try {
      items = await apiFetch("/orders/" + orderId + "/messages");
    } catch (e) {
      return; // fon rejimida xatolikni jim o'tkazib yuboramiz
    }
    list.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.style.margin = "0";
      empty.textContent = "Hali xabar yo'q";
      list.appendChild(empty);
      return;
    }
    items.forEach((m) => {
      const mine = m.sender_id === currentUserId;
      const bubble = document.createElement("div");
      bubble.style.alignSelf = mine ? "flex-end" : "flex-start";
      bubble.style.maxWidth = "80%";
      bubble.style.padding = "6px 10px";
      bubble.style.borderRadius = "12px";
      bubble.style.background = mine ? "var(--primary)" : "#fff";
      bubble.style.color = mine ? "#fff" : "var(--text)";
      bubble.style.border = mine ? "0" : "1px solid var(--border)";
      bubble.style.fontSize = "0.9rem";
      bubble.style.overflowWrap = "anywhere";

      const nameEl = document.createElement("div");
      nameEl.style.fontSize = "0.7rem";
      nameEl.style.opacity = "0.75";
      nameEl.style.fontWeight = "600";
      nameEl.textContent = mine ? "Siz" : m.sender_name;

      const bodyEl = document.createElement("div");
      bodyEl.textContent = m.body;

      bubble.append(nameEl, bodyEl);
      list.appendChild(bubble);
    });
    list.scrollTop = list.scrollHeight;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errEl.textContent = "";
    const body = input.value.trim();
    if (!body) return;
    input.disabled = true;
    sendBtn.disabled = true;
    try {
      await apiFetch("/orders/" + orderId + "/messages", {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      input.value = "";
      await load();
    } catch (err) {
      errEl.textContent = err.message;
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  });

  load();
  return { el: wrap, reload: load };
}
