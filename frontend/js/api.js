// Backend manzili sahifa ochilgan hostdan olinadi:
// kompyuterda localhost, telefonda kompyuterning IP manzili (masalan 192.168.1.5)
const API_BASE = `http://${window.location.hostname}:8000/api/v1`;

async function apiFetch(path, options = {}) {
  const { headers, ...rest } = options;
  const res = await fetch(API_BASE + path, {
    ...rest,
    headers: { "Content-Type": "application/json", ...(headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || "Xatolik yuz berdi";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}