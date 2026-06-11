const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

async function handle(res) {
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  get: (url) => fetch(url).then(handle),
  post: (url, body) => fetch(url, json("POST", body)).then(handle),
  put: (url, body) => fetch(url, json("PUT", body)).then(handle),
  patch: (url, body) => fetch(url, json("PATCH", body)).then(handle),
  del: (url) => fetch(url, { method: "DELETE" }).then(handle),
  upload: (url, formData) =>
    fetch(url, { method: "POST", body: formData }).then(handle),
};

export function fmtTime(s) {
  if (s == null) return "–:––";
  s = Math.max(0, s);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
    : `${m}:${String(sec).padStart(2, "0")}`;
}

export const streamUrl = (mediaId) => `/stream/${mediaId}`;
