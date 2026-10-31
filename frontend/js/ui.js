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

// Matn kiritish uchun modal. Natija: Promise<string|null> — "Ha" bosilsa qiymat
// (bo'sh bo'lsa null), "Yo'q"/Esc/tashqariga bosilsa null.
function promptModal(message, options) {
  options = options || {};
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";

    const box = document.createElement("div");
    box.className = "modal-content";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");

    const text = document.createElement("p");
    text.style.margin = "0 0 10px";
    text.style.fontWeight = "600";
    text.textContent = message;

    const input = document.createElement("textarea");
    input.placeholder = options.placeholder || "";
    input.maxLength = options.maxLength || 500;
    input.style.minHeight = "72px";

    const row = document.createElement("div");
    row.className = "modal-actions";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-outline";
    cancelBtn.style.flex = "1";
    cancelBtn.textContent = options.cancelLabel || "Bekor qilish";

    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = "btn " + (options.danger ? "btn-danger" : "btn-accent");
    okBtn.style.flex = "1";
    okBtn.textContent = options.okLabel || "Yuborish";

    function close(result) {
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      resolve(result);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") close(null);
    }

    cancelBtn.addEventListener("click", () => close(null));
    okBtn.addEventListener("click", () => close(input.value.trim() || null));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(null);
    });

    row.append(cancelBtn, okBtn);
    box.append(text, input, row);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    document.addEventListener("keydown", onKeyDown);
    input.focus();
  });
}

// Faqat o'qish uchun ma'lumot modali (native alert() o'rniga — alert bloklaydigan
// va avtomatlashtirishda (va ba'zi brauzer muhitlarida) ishonchsiz ishlaydi).
// lines: satrlar massivi. Natija: Promise<void> — "Yopish" bosilgach hal bo'ladi.
function infoModal(title, lines) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";

    const box = document.createElement("div");
    box.className = "modal-content";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");

    const head = document.createElement("h2");
    head.style.margin = "0 0 10px";
    head.style.fontSize = "1.1rem";
    head.textContent = title;
    box.appendChild(head);

    (lines || []).forEach((line) => {
      const p = document.createElement("p");
      p.style.margin = "4px 0";
      p.style.fontSize = "0.9rem";
      p.textContent = line;
      box.appendChild(p);
    });

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "btn btn-block";
    closeBtn.style.marginTop = "12px";
    closeBtn.textContent = "Yopish";

    function close() {
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      resolve();
    }
    function onKeyDown(e) {
      if (e.key === "Escape") close();
    }

    closeBtn.addEventListener("click", close);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });

    box.appendChild(closeBtn);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    document.addEventListener("keydown", onKeyDown);
    closeBtn.focus();
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

// ================= Bildirishnoma tovushi =================
// Brauzerlar foydalanuvchi sahifa bilan hali o'zaro ta'sirlashmagan bo'lsa
// ovoz chiqarishni bloklaydi — shuning uchun AudioContext birinchi bosish/teginishda
// "qulfdan chiqariladi", keyin istalgan vaqt notificationBeep() chaqirilsa ishlaydi.
let _audioCtx = null;
function _unlockAudio() {
  if (_audioCtx) return;
  try {
    _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  } catch (e) {}
}
document.addEventListener("click", _unlockAudio, { once: true });
document.addEventListener("touchstart", _unlockAudio, { once: true });

// Yangi buyurtma/taklif haqida ikki ohangli qisqa signal (tashqi fayl kerak emas).
function notificationBeep() {
  try {
    if (!_audioCtx) {
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (_audioCtx.state === "suspended") _audioCtx.resume();
    const now = _audioCtx.currentTime;
    [880, 1175].forEach((freq, i) => {
      const osc = _audioCtx.createOscillator();
      const gain = _audioCtx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const start = now + i * 0.16;
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.2, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, start + 0.22);
      osc.connect(gain);
      gain.connect(_audioCtx.destination);
      osc.start(start);
      osc.stop(start + 0.24);
    });
  } catch (e) {
    // Ovoz ixtiyoriy: brauzer taqiqlasa ham oqim davom etadi
  }
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

      if (!mine) {
        const reportBtn = document.createElement("button");
        reportBtn.type = "button";
        reportBtn.title = "Xabar haqida shikoyat qilish";
        reportBtn.setAttribute("aria-label", "Xabar haqida shikoyat qilish");
        reportBtn.textContent = "⚠";
        reportBtn.style.border = "0";
        reportBtn.style.background = "transparent";
        reportBtn.style.cursor = "pointer";
        reportBtn.style.opacity = "0.6";
        reportBtn.style.float = "right";
        reportBtn.style.fontSize = "0.8rem";
        reportBtn.addEventListener("click", async () => {
          const reason = await promptModal(
            "Nima uchun shikoyat qilyapsiz?",
            { placeholder: "Shikoyat sababini yozing (kamida 5 belgi)", okLabel: "Shikoyat qilish" }
          );
          if (!reason) return;
          try {
            await apiFetch("/orders/" + orderId + "/messages/" + m.id + "/report", {
              method: "POST",
              body: JSON.stringify({ reason }),
            });
            toast("Shikoyat yuborildi", "success");
          } catch (err) {
            toast(err.message, "error");
          }
        });
        bubble.appendChild(reportBtn);
      }

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

const DISPUTE_STATUS_LABELS = {
  open: "Ko'rib chiqilmoqda",
  resolved: "Hal qilindi",
  rejected: "Rad etildi",
};

// Buyurtma shikoyatini (GET/POST /orders/{id}/disputes, /dispute) ko'rsatuvchi widget.
// canWrite=false bo'lsa faqat o'qish rejimi (masalan admin uchun ishlatilmaydi, bu yerda shart emas).
// Qaytaradi: { el, reload }.
function createDisputeWidget(orderId) {
  const wrap = document.createElement("div");

  const title = document.createElement("h2");
  title.style.marginTop = "0";
  title.textContent = "Shikoyat";
  wrap.appendChild(title);

  const body = document.createElement("div");
  wrap.appendChild(body);

  function renderOpen(dispute) {
    body.replaceChildren();
    const banner = document.createElement("div");
    banner.className = "status-banner pending";
    banner.textContent = "Shikoyatingiz " + DISPUTE_STATUS_LABELS.open.toLowerCase() + ": " + dispute.reason;
    body.appendChild(banner);
  }

  function renderResolved(dispute) {
    body.replaceChildren();
    const banner = document.createElement("div");
    banner.className = dispute.status === "resolved" ? "status-banner approved" : "status-banner";
    if (dispute.status !== "resolved") {
      banner.style.background = "#fee2e2";
      banner.style.borderColor = "#fca5a5";
      banner.style.color = "#991b1b";
    }
    const title2 = document.createElement("div");
    title2.textContent = "Oxirgi shikoyat: " + DISPUTE_STATUS_LABELS[dispute.status];
    banner.appendChild(title2);
    if (dispute.admin_note) {
      const note = document.createElement("div");
      note.style.fontWeight = "400";
      note.style.marginTop = "4px";
      note.style.fontSize = "0.85rem";
      note.textContent = "Admin izohi: " + dispute.admin_note;
      banner.appendChild(note);
    }
    body.appendChild(banner);
    appendForm();
  }

  function appendForm(labelText) {
    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "btn btn-outline btn-block";
    toggleBtn.style.marginTop = "8px";
    toggleBtn.textContent = labelText || "Shikoyat bildirish";

    const form = document.createElement("form");
    form.style.display = "none";
    form.style.marginTop = "8px";
    form.noValidate = true;

    const textarea = document.createElement("textarea");
    textarea.placeholder = "Muammoni tavsiflang (kamida 5 ta belgi)...";
    textarea.maxLength = 1000;

    const errEl = document.createElement("div");
    errEl.className = "form-error";
    errEl.setAttribute("role", "alert");

    const submitBtn = document.createElement("button");
    submitBtn.type = "submit";
    submitBtn.className = "btn btn-danger btn-block";
    submitBtn.style.marginTop = "8px";
    submitBtn.textContent = "Shikoyatni yuborish";

    toggleBtn.addEventListener("click", () => {
      form.style.display = form.style.display === "none" ? "block" : "none";
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errEl.textContent = "";
      const reason = textarea.value.trim();
      if (reason.length < 5) {
        errEl.textContent = "Kamida 5 ta belgi kiriting";
        return;
      }
      submitBtn.disabled = true;
      try {
        await apiFetch("/orders/" + orderId + "/dispute", {
          method: "POST",
          body: JSON.stringify({ reason }),
        });
        toast("Shikoyat yuborildi", "success");
        load();
      } catch (err) {
        errEl.textContent = err.message;
        submitBtn.disabled = false;
      }
    });

    form.append(textarea, errEl, submitBtn);
    body.append(toggleBtn, form);
  }

  async function load() {
    let disputes;
    try {
      disputes = await apiFetch("/orders/" + orderId + "/disputes");
    } catch (e) {
      return;
    }
    const openDispute = disputes.find((d) => d.status === "open");
    if (openDispute) {
      renderOpen(openDispute);
      return;
    }
    const latest = disputes[0];
    body.replaceChildren();
    if (latest) {
      renderResolved(latest);
    } else {
      appendForm();
    }
  }

  load();
  return { el: wrap, reload: load };
}

// ================= Yandex xarita: joylashuv tanlagich =================

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371.0;
  const toRad = (d) => (d * Math.PI) / 180;
  const dPhi = toRad(lat2 - lat1);
  const dLambda = toRad(lon2 - lon1);
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLambda / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// Koordinata bo'lsa "Xaritada ko'rish" havolasini qaytaradi (Yandex Maps, yangi oynada),
// bo'lmasa null — chaqiruvchi shart bo'yicha qo'shadi/qo'shmaydi.
function mapLink(lat, lon) {
  if (lat == null || lon == null) return null;
  const a = document.createElement("a");
  a.href = "https://yandex.com/maps/?pt=" + lon + "," + lat + "&z=16&l=map";
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = "📍 Xaritada ko'rish";
  a.style.fontSize = "0.85rem";
  return a;
}

const TASHKENT_CENTER = [41.2995, 69.2401];
let _yandexMapsLoadPromise = null;

function _loadYandexMaps(apiKey) {
  if (window.ymaps) return Promise.resolve(window.ymaps);
  if (_yandexMapsLoadPromise) return _yandexMapsLoadPromise;
  _yandexMapsLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://api-maps.yandex.ru/2.1/?apikey=" + encodeURIComponent(apiKey) + "&lang=uz_UZ";
    script.onload = () => window.ymaps.ready(() => resolve(window.ymaps));
    script.onerror = () => reject(new Error("Xarita kutubxonasi yuklanmadi"));
    document.head.appendChild(script);
  });
  return _yandexMapsLoadPromise;
}

// Brauzer geolokatsiyasini so'raydi: Promise<[lat, lon]>, rad etilsa/xato bo'lsa reject qiladi.
function getCurrentLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Brauzeringiz joylashuvni aniqlashni qo'llab-quvvatlamaydi"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve([pos.coords.latitude, pos.coords.longitude]),
      (err) => {
        const msg =
          err.code === err.PERMISSION_DENIED
            ? "Joylashuvga ruxsat berilmadi"
            : "Joylashuvni aniqlab bo'lmadi";
        reject(new Error(msg));
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  });
}

// Login/ro'yxatdan o'tishda bir marta chaqiriladi: ruxsat so'raydi va keshlaydi
// (xatolikni jim o'tkazib yuboradi — foydalanuvchi rad etsa ham oqim davom etadi).
function requestAndCacheLocation() {
  getCurrentLocation()
    .then(([lat, lon]) => {
      try {
        localStorage.setItem(
          "ustabor_last_location",
          JSON.stringify({ lat, lon, ts: Date.now() })
        );
      } catch (e) {}
    })
    .catch(() => {});
}

function _cachedLocation() {
  try {
    const raw = localStorage.getItem("ustabor_last_location");
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (Date.now() - data.ts > 30 * 60 * 1000) return null; // 30 daqiqadan eski — eskirgan
    return [data.lat, data.lon];
  } catch (e) {
    return null;
  }
}

// coords: [lat, lon] | null. onChange(lat, lon, source) xaritada belgi o'zgarganda chaqiriladi
// (source: "search" | "locate" | "click" | "drag" — manzil maydonlarini avtomatik to'ldirish uchun foydali).
// autoLocate: true bo'lsa va initialLat/Lon berilmagan bo'lsa, xarita ochilganda avtomatik
// joriy joylashuvni so'raydi (keshlangan qiymat bo'lsa, so'ramasdan undan foydalanadi).
function createMapPicker({ initialLat, initialLon, onChange, autoLocate } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "map-picker";

  const searchRow = document.createElement("div");
  searchRow.style.display = "flex";
  searchRow.style.gap = "8px";
  searchRow.style.marginBottom = "8px";

  const searchInput = document.createElement("input");
  searchInput.type = "text";
  searchInput.placeholder = "Manzilni qidirish...";
  searchInput.style.flex = "1";
  searchInput.style.margin = "0";

  const searchBtn = document.createElement("button");
  searchBtn.type = "button";
  searchBtn.className = "btn btn-outline";
  searchBtn.style.width = "auto";
  searchBtn.style.padding = "0 14px";
  searchBtn.textContent = "Qidirish";

  const locateBtn = document.createElement("button");
  locateBtn.type = "button";
  locateBtn.className = "btn btn-outline";
  locateBtn.style.width = "auto";
  locateBtn.style.padding = "0 12px";
  locateBtn.title = "Joriy joylashuvim";
  locateBtn.setAttribute("aria-label", "Joriy joylashuvim");
  locateBtn.textContent = "📍";

  searchRow.append(searchInput, searchBtn, locateBtn);

  const resultsList = document.createElement("div");
  resultsList.style.display = "flex";
  resultsList.style.flexDirection = "column";
  resultsList.style.gap = "4px";
  resultsList.style.marginBottom = "8px";

  const mapEl = document.createElement("div");
  mapEl.style.height = "280px";
  mapEl.style.borderRadius = "10px";
  mapEl.style.overflow = "hidden";
  mapEl.style.background = "var(--bg)";

  const stateEl = document.createElement("p");
  stateEl.className = "muted";
  stateEl.style.margin = "6px 0 0";
  stateEl.style.fontSize = "0.85rem";

  wrap.append(searchRow, resultsList, mapEl, stateEl);

  let map = null;
  let placemark = null;
  let coords = initialLat != null && initialLon != null ? [initialLat, initialLon] : null;

  function notify(source) {
    if (coords && onChange) onChange(coords[0], coords[1], source || "unknown");
  }

  function placePin(lat, lon, recenter, source) {
    coords = [lat, lon];
    if (map) {
      if (placemark) {
        placemark.geometry.setCoordinates([lat, lon]);
      } else {
        placemark = new ymaps.Placemark([lat, lon], {}, { draggable: true });
        placemark.events.add("dragend", () => {
          const c = placemark.geometry.getCoordinates();
          coords = c;
          notify("drag");
        });
        map.geoObjects.add(placemark);
      }
      if (recenter) map.setCenter([lat, lon], 15, { duration: 300 });
    }
    notify(source);
  }

  async function doLocate() {
    locateBtn.disabled = true;
    stateEl.textContent = "Joylashuv aniqlanmoqda...";
    try {
      const [lat, lon] = await getCurrentLocation();
      placePin(lat, lon, true, "locate");
      stateEl.textContent = "Joriy joylashuvingiz belgilandi. Kerak bo'lsa belgini suring.";
    } catch (e) {
      stateEl.textContent = e.message;
    } finally {
      locateBtn.disabled = false;
    }
  }
  locateBtn.addEventListener("click", doLocate);

  let searchRequestId = 0;

  async function doSearch() {
    const q = searchInput.value.trim();
    if (q.length < 3) return;
    const myRequestId = ++searchRequestId;

    resultsList.replaceChildren();
    const loadingP = document.createElement("p");
    loadingP.className = "muted";
    loadingP.style.margin = "0";
    loadingP.textContent = "Qidirilmoqda...";
    resultsList.appendChild(loadingP);
    searchBtn.disabled = true;
    try {
      const items = await apiFetch("/geo/search?q=" + encodeURIComponent(q));
      if (myRequestId !== searchRequestId) return; // eskirgan natija — e'tiborsiz qoldiriladi
      resultsList.replaceChildren();
      if (!items.length) {
        const p = document.createElement("p");
        p.className = "muted";
        p.style.margin = "0";
        p.textContent = "Hech narsa topilmadi";
        resultsList.appendChild(p);
        return;
      }
      items.forEach((item) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-outline";
        btn.style.textAlign = "left";
        btn.style.fontSize = "0.85rem";
        btn.textContent = item.address;
        btn.addEventListener("click", () => {
          placePin(item.latitude, item.longitude, true, "search");
          resultsList.replaceChildren();
          searchInput.value = item.address;
        });
        resultsList.appendChild(btn);
      });
    } catch (e) {
      if (myRequestId !== searchRequestId) return;
      resultsList.replaceChildren();
      stateEl.textContent = "Qidirishda xatolik: " + e.message;
    } finally {
      if (myRequestId === searchRequestId) searchBtn.disabled = false;
    }
  }

  searchBtn.addEventListener("click", doSearch);
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      doSearch();
    }
  });

  // Yandexdagi kabi: yozayotganda natijalar o'zi (tugma bosmasdan) chiqadi.
  let searchDebounceTimer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchDebounceTimer);
    const q = searchInput.value.trim();
    if (q.length < 3) {
      resultsList.replaceChildren();
      return;
    }
    searchDebounceTimer = setTimeout(doSearch, 400);
  });

  (async () => {
    stateEl.textContent = "Xarita yuklanmoqda...";
    let cfg;
    try {
      cfg = await apiFetch("/geo/config");
    } catch (e) {
      stateEl.textContent = "Xarita sozlamalarini olishda xatolik";
      mapEl.style.display = "none";
      return;
    }
    if (!cfg.yandex_maps_key) {
      stateEl.textContent = "Xarita xizmati sozlanmagan";
      mapEl.style.display = "none";
      return;
    }
    try {
      await _loadYandexMaps(cfg.yandex_maps_key);
    } catch (e) {
      stateEl.textContent = e.message;
      mapEl.style.display = "none";
      return;
    }
    const center = coords || TASHKENT_CENTER;
    map = new ymaps.Map(mapEl, {
      center,
      zoom: coords ? 15 : 11,
      controls: ["zoomControl"],
    });
    map.events.add("click", (e) => {
      const c = e.get("coords");
      placePin(c[0], c[1], false, "click");
    });

    if (coords) {
      placePin(coords[0], coords[1], false, "init");
      stateEl.textContent = "Manzilni qidiring yoki xaritada belgini bosing/suring";
    } else if (autoLocate) {
      const cached = _cachedLocation();
      if (cached) {
        placePin(cached[0], cached[1], true, "locate");
        stateEl.textContent = "Joriy joylashuvingiz belgilandi. Kerak bo'lsa belgini suring.";
      } else {
        await doLocate();
      }
    } else {
      stateEl.textContent = "Manzilni qidiring yoki xaritada belgini bosing/suring";
    }
  })();

  return {
    el: wrap,
    getCoords: () => coords,
  };
}
