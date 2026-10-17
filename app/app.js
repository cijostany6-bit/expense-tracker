/* ══════════════════════════════════════════════════════════════
   Expense Tracker — app logic (vanilla JS, no dependencies)
   Auth  : Amazon Cognito user pool (direct JSON API calls)
   Data  : API Gateway (JWT-authorised) -> Lambda -> DynamoDB
   Files : S3 presigned URLs (PUT to upload, GET to preview)
   ══════════════════════════════════════════════════════════════ */

/* ── config (filled in when the stack was created) ── */
const REGION     = "eu-central-1";
const CLIENT_ID  = "4grucsnelng73rhl3c1kbasi7j";
const API_BASE   = "https://4haajttqgh.execute-api.eu-central-1.amazonaws.com";
const COGNITO    = `https://cognito-idp.${REGION}.amazonaws.com/`;

const CATEGORIES = ["food","travel","rent","utilities","health","shopping","entertainment","other"];
const CURRENCIES = ["EUR","USD","INR","GBP"];

/* category -> colour (hex for text/gradient, rgb for translucent fills) */
const CAT = {
  food:          { hex:"#fb923c", rgb:"251,146,60"  },
  travel:        { hex:"#38bdf8", rgb:"56,189,248"  },
  rent:          { hex:"#a78bfa", rgb:"167,139,250" },
  utilities:     { hex:"#facc15", rgb:"250,204,21"  },
  health:        { hex:"#34d399", rgb:"52,211,153"  },
  shopping:      { hex:"#f472b6", rgb:"244,114,182" },
  entertainment: { hex:"#22d3ee", rgb:"34,211,238"  },
  other:         { hex:"#94a3b8", rgb:"148,163,184" },
};

/* ── tiny helpers ── */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
const money = (n, cur) => `${Number(n || 0).toFixed(2)}${cur ? " " + cur : ""}`;
const catOf = (c) => CAT[c] || CAT.other;

/* ── state ── */
const state = {
  idToken: null,
  email: "",
  expenses: [],
  summary: { byCategory: {}, grandTotal: 0, count: 0 },
  q: "",
  category: "all",
  sort: "date_desc",
};

/* ══════════════ toasts & modals ══════════════ */
function toast(text, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.textContent = text;
  $("toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transform = "translateX(20px)"; }, 3200);
  setTimeout(() => t.remove(), 3600);
}

function closeModal() {
  const r = $("modalRoot");
  r.classList.add("hidden");
  r.innerHTML = "";
  r.onclick = null;
}

function openModal(html, onMount) {
  const r = $("modalRoot");
  r.innerHTML = `<div class="modal">${html}</div>`;
  r.classList.remove("hidden");
  r.onclick = (e) => { if (e.target === r) closeModal(); };
  if (onMount) onMount(r.querySelector(".modal"));
}

/* ══════════════ Cognito auth ══════════════ */
async function cognito(target, body) {
  const res = await fetch(COGNITO, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}`,
    },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || data.__type || `Cognito error (${res.status})`);
  return data;
}

const signUp = (email, password) => cognito("SignUp", {
  ClientId: CLIENT_ID, Username: email, Password: password,
  UserAttributes: [{ Name: "email", Value: email }],
});

async function signIn(email, password) {
  const data = await cognito("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH", ClientId: CLIENT_ID,
    AuthParameters: { USERNAME: email, PASSWORD: password },
  });
  return data.AuthenticationResult.IdToken;
}

/* ══════════════ API helper ══════════════ */
async function api(method, path, body) {
  const res = await fetch(API_BASE + path, {
    method,
    headers: { "Authorization": state.idToken, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `API error ${res.status}`);
  return data;
}

/* ══════════════ screens ══════════════ */
function showAuth() {
  state.idToken = null;
  state.expenses = [];
  $("authScreen").classList.remove("hidden");
  $("appScreen").classList.add("hidden");
  $("btnLogout").classList.add("hidden");
  $("whoami").classList.add("hidden");
  $("password").value = "";
}

function showApp() {
  $("authScreen").classList.add("hidden");
  $("appScreen").classList.remove("hidden");
  $("btnLogout").classList.remove("hidden");
  $("whoami").classList.remove("hidden");
  $("whoami").textContent = state.email;
  load();
}

/* ══════════════ data ══════════════ */
async function load() {
  try {
    const [list, summary] = await Promise.all([api("GET", "/expenses"), api("GET", "/summary")]);
    state.expenses = list.items || [];
    state.summary = summary || state.summary;
    renderAll();
  } catch (e) {
    toast(e.message, "bad");
  }
}

function filtered() {
  const q = state.q.trim().toLowerCase();
  const out = state.expenses.filter((e) => {
    if (state.category !== "all" && (e.category || "other") !== state.category) return false;
    if (q && !`${e.note || ""} ${e.category || ""} ${e.vendor || ""}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const s = state.sort;
  out.sort((a, b) => {
    if (s === "amount_desc") return Number(b.amount) - Number(a.amount);
    if (s === "amount_asc")  return Number(a.amount) - Number(b.amount);
    if (s === "date_asc")    return String(a.date || "").localeCompare(String(b.date || ""));
    return String(b.date || "").localeCompare(String(a.date || ""));
  });
  return out;
}

/* ══════════════ render ══════════════ */
function renderAll() { renderKpis(); renderChart(); renderList(); }

function countUp(el, target, decimals) {
  const dur = 650, t0 = performance.now();
  const frame = (t) => {
    const p = Math.min(1, (t - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = (target * eased).toFixed(decimals);
    if (p < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function renderKpis() {
  const items = filtered();
  const total = items.reduce((s, e) => s + Number(e.amount || 0), 0);
  const avg = items.length ? total / items.length : 0;
  const byCat = items.reduce((m, e) => {
    const k = e.category || "other";
    m[k] = (m[k] || 0) + Number(e.amount || 0);
    return m;
  }, {});
  const top = Object.entries(byCat).sort((a, b) => b[1] - a[1])[0];

  const stats = [
    { label: "Total spend",  num: total,        dec: 2, sub: `${items.length} expense${items.length === 1 ? "" : "s"}`, color: "var(--primary)" },
    { label: "Expenses",     num: items.length, dec: 0, sub: "matching filters",  color: "var(--primary-2)" },
    { label: "Average",      num: avg,          dec: 2, sub: "per expense",       color: "var(--warn)" },
    { label: "Top category", text: top ? top[0] : "—", sub: top ? money(top[1]) : "no data",
      color: top ? catOf(top[0]).hex : "var(--muted)" },
  ];

  $("kpis").innerHTML = stats.map((s) => `
    <div class="kpi" style="--k:${s.color}">
      <div class="k-label">${s.label}</div>
      <div class="k-value" ${s.num !== undefined ? `data-num="${s.num}" data-dec="${s.dec}"` : ""}>
        ${s.num !== undefined ? "0" : esc(s.text)}
      </div>
      <div class="k-sub">${esc(s.sub)}</div>
    </div>`).join("");

  $("kpis").querySelectorAll("[data-num]").forEach((el) =>
    countUp(el, parseFloat(el.dataset.num), parseInt(el.dataset.dec, 10)));
}

function renderChart() {
  const items = filtered();
  const byCat = {};
  items.forEach((e) => {
    const k = e.category || "other";
    byCat[k] = (byCat[k] || 0) + Number(e.amount || 0);
  });
  const entries = Object.entries(byCat).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));

  $("chartTotal").textContent = `all-time (server /summary): ${money(state.summary.grandTotal)}`;

  const box = $("chart");
  if (!entries.length) {
    box.innerHTML = `<div class="empty"><span class="big">📊</span>No data to chart yet.</div>`;
    return;
  }
  box.innerHTML = entries.map(([cat, val]) => {
    const c = catOf(cat);
    const pct = Math.round((val / max) * 100);
    return `
      <div class="bar-row">
        <div class="bar-label"><span class="dot" style="background:${c.hex}"></span>${esc(cat)}</div>
        <div class="bar-track">
          <div class="bar-fill" data-pct="${pct}"
               style="background:linear-gradient(90deg,rgba(${c.rgb},.55),${c.hex})"></div>
        </div>
        <div class="bar-val"><b>${money(val)}</b></div>
      </div>`;
  }).join("");

  requestAnimationFrame(() => {
    box.querySelectorAll(".bar-fill").forEach((b) => { b.style.width = b.dataset.pct + "%"; });
  });
}

function renderList() {
  const items = filtered();
  const all = state.expenses.length;
  $("listCount").textContent = items.length === all ? `(${all})` : `(${items.length} of ${all})`;

  const box = $("list");
  if (!items.length) {
    box.innerHTML = `<div class="empty"><span class="big">${all ? "🔍" : "🧾"}</span>
      ${all ? "No expenses match your filters." : "No expenses yet — add your first one!"}</div>`;
    return;
  }

  box.innerHTML = items.map((e) => {
    const c = catOf(e.category);
    const status = e.status || "processed";
    const pending = status === "pending";

    const receipt = e.receiptKey
      ? `<span class="receipt-chip" data-receipt="${esc(e.expenseId)}">📎 view receipt</span>`
      : `<span class="receipt-chip" data-upload="${esc(e.expenseId)}"
              style="background:rgba(56,189,248,.14);color:#38bdf8;border-color:rgba(56,189,248,.35)">＋ add receipt</span>`;

    const statusChip = pending
      ? `<span class="receipt-chip" style="background:rgba(250,204,21,.14);color:#facc15;border-color:rgba(250,204,21,.35)">⏳ reading receipt…</span>`
      : status === "needs_review"
        ? `<span class="receipt-chip" style="background:rgba(248,113,113,.14);color:#f87171;border-color:rgba(248,113,113,.35)">⚠️ needs review</span>`
        : "";

    const title = e.vendor
      ? `${esc(e.vendor)}${e.note ? ` <span class="muted">— ${esc(e.note)}</span>` : ""}`
      : (e.note ? esc(e.note) : `<span class="muted">no note</span>`);

    return `
      <div class="item${pending ? " is-pending" : ""}">
        <span class="cat-badge"
              style="background:rgba(${c.rgb},.18);border:1px solid rgba(${c.rgb},.45);color:${c.hex}">
          ${esc(e.category || "other")}
        </span>
        <div class="main">
          <div class="note">${title}</div>
          <div class="meta">
            <span>📅 ${esc(e.date || "")}</span>
            <span>💱 ${esc(e.currency || "")}</span>
            ${statusChip}
            ${receipt}
          </div>
        </div>
        <div class="amt">${pending ? "…" : money(e.amount, e.currency)}</div>
        <div class="actions">
          <button class="icon-btn" data-edit="${esc(e.expenseId)}" title="Edit">✏️</button>
          <button class="icon-btn del" data-del="${esc(e.expenseId)}" title="Delete">🗑️</button>
        </div>
      </div>`;
  }).join("");
}

/* ══════════════ actions ══════════════ */
async function addExpense(ev) {
  ev.preventDefault();
  const amount = parseFloat($("f-amount").value);
  if (!amount || amount <= 0) { toast("Enter a valid amount", "bad"); return; }

  const btn = ev.target.querySelector("button[type=submit]");
  btn.disabled = true;
  try {
    await api("POST", "/expenses", {
      amount,
      currency: $("f-currency").value,
      category: $("f-category").value,
      date: $("f-date").value || undefined,
      note: $("f-note").value,
    });
    $("f-amount").value = ""; $("f-note").value = "";
    toast("Expense added ✔", "ok");
    await load();
  } catch (e) {
    toast(e.message, "bad");
  } finally {
    btn.disabled = false;
  }
}

function openEdit(id) {
  const e = state.expenses.find((x) => x.expenseId === id);
  if (!e) return;
  openModal(`
    <h3>✏️ Edit expense</h3>
    <div class="form-grid">
      <label class="field"><span>Amount</span>
        <input id="e-amount" type="number" step="0.01" value="${esc(e.amount)}"></label>
      <label class="field"><span>Currency</span>
        <select id="e-currency">${CURRENCIES.map((c) => `<option ${c === e.currency ? "selected" : ""}>${c}</option>`).join("")}</select></label>
      <label class="field"><span>Category</span>
        <select id="e-category">${CATEGORIES.map((c) => `<option value="${c}" ${c === (e.category || "other") ? "selected" : ""}>${c}</option>`).join("")}</select></label>
      <label class="field"><span>Date</span>
        <input id="e-date" type="date" value="${esc(e.date || "")}"></label>
      <label class="field span2"><span>Note</span>
        <input id="e-note" value="${esc(e.note || "")}"></label>
    </div>
    <div class="row">
      <button class="btn ghost" id="eCancel" type="button">Cancel</button>
      <button class="btn" id="eSave" type="button">Save changes</button>
    </div>`, (m) => {
    m.querySelector("#eCancel").onclick = closeModal;
    m.querySelector("#eSave").onclick = async () => {
      const btn = m.querySelector("#eSave");
      btn.disabled = true;
      try {
        await api("PUT", `/expenses/${id}`, {
          amount: parseFloat(m.querySelector("#e-amount").value),
          currency: m.querySelector("#e-currency").value,
          category: m.querySelector("#e-category").value,
          date: m.querySelector("#e-date").value,
          note: m.querySelector("#e-note").value,
        });
        closeModal();
        toast("Expense updated ✔", "ok");
        await load();
      } catch (err) { toast(err.message, "bad"); btn.disabled = false; }
    };
  });
}

function confirmDelete(id) {
  const e = state.expenses.find((x) => x.expenseId === id);
  openModal(`
    <h3>🗑️ Delete expense?</h3>
    <p class="muted">${e ? esc(e.note || "no note") : ""} — ${e ? money(e.amount, e.currency) : ""}<br>
    This removes the item from DynamoDB. It cannot be undone.</p>
    <div class="row">
      <button class="btn ghost" id="dCancel" type="button">Cancel</button>
      <button class="btn danger" id="dGo" type="button">Delete</button>
    </div>`, (m) => {
    m.querySelector("#dCancel").onclick = closeModal;
    m.querySelector("#dGo").onclick = async () => {
      try {
        await api("DELETE", `/expenses/${id}`);
        closeModal();
        toast("Expense deleted", "ok");
        await load();
      } catch (err) { toast(err.message, "bad"); }
    };
  });
}

async function uploadReceipt(id) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*,application/pdf";
  input.onchange = async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast("File must be under 5 MB", "bad"); return; }
    try {
      toast("Requesting presigned upload URL…");
      const { uploadUrl } = await api("POST", `/expenses/${id}/receipt-url`);
      const res = await fetch(uploadUrl, {
        method: "PUT", body: file,
        headers: { "Content-Type": file.type || "application/octet-stream" },
      });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);
      toast("Receipt uploaded 📎", "ok");
      await load();
    } catch (e) { toast(e.message, "bad"); }
  };
  input.click();
}

/* ── scan a receipt: create a pending expense, upload, watch the AI fill it in ── */
function scanReceipt() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.onchange = async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) { toast("Please choose an image (JPG/PNG)", "bad"); return; }
    if (file.size > 5 * 1024 * 1024) { toast("File must be under 5 MB", "bad"); return; }
    try {
      toast("Creating expense + upload URL…");
      const { expenseId, uploadUrl } = await api("POST", "/expenses/scan");

      const res = await fetch(uploadUrl, {
        method: "PUT", body: file,
        headers: { "Content-Type": file.type || "application/octet-stream" },
      });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);

      toast("Reading your receipt… 🔎");
      await load();               // the pending row appears immediately
      pollScan(expenseId);
    } catch (e) { toast(e.message, "bad"); }
  };
  input.click();
}

async function pollScan(expenseId) {
  for (let i = 0; i < 15; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    await load();
    const e = state.expenses.find((x) => x.expenseId === expenseId);
    if (e && e.status && e.status !== "pending") {
      if (e.status === "processed") {
        toast(`Got it: ${e.vendor || "expense"} · ${money(e.amount, e.currency)} ✔`, "ok");
      } else {
        toast("Couldn't read that receipt — please fill the details in ✏️", "bad");
      }
      return;
    }
  }
  toast("Still reading — refresh in a moment", "");
}

async function previewReceipt(id) {
  try {
    const { downloadUrl } = await api("GET", `/expenses/${id}/receipt-url`);
    openModal(`
      <h3>📎 Receipt</h3>
      <div id="rcptBox" class="muted">Loading…</div>
      <div class="row">
        <button class="btn ghost" id="rClose" type="button">Close</button>
        <a class="btn" href="${downloadUrl}" target="_blank" rel="noopener">Open in new tab</a>
      </div>`, (m) => { m.querySelector("#rClose").onclick = closeModal; });

    const box = $("rcptBox");
    const img = new Image();
    img.onload = () => { box.innerHTML = ""; box.classList.remove("muted"); box.appendChild(img); };
    img.onerror = () => { box.innerHTML = `<p class="muted">Not a previewable image — use “Open in new tab”.</p>`; };
    img.src = downloadUrl;
  } catch (e) {
    toast(e.message, "bad");
  }
}

function exportCsv() {
  const rows = [["date", "category", "amount", "currency", "note", "expenseId"]];
  filtered().forEach((e) => rows.push([
    e.date || "", e.category || "", e.amount, e.currency || "",
    String(e.note || "").replace(/"/g, '""'), e.expenseId,
  ]));
  const csv = rows.map((r) => r.map((v) => `"${v}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `expenses-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  toast("CSV exported ⬇", "ok");
}

/* ══════════════ wiring ══════════════ */
function initSelects() {
  $("f-currency").innerHTML  = CURRENCIES.map((c) => `<option>${c}</option>`).join("");
  $("f-category").innerHTML  = CATEGORIES.map((c) => `<option value="${c}">${c}</option>`).join("");
  $("filterCategory").innerHTML =
    `<option value="all">All categories</option>` +
    CATEGORIES.map((c) => `<option value="${c}">${c}</option>`).join("");
  $("f-date").value = new Date().toISOString().slice(0, 10);
}

function wire() {
  initSelects();

  $("btnSignIn").onclick = async () => {
    const email = $("email").value.trim(), password = $("password").value;
    if (!email || !password) return toast("Enter email and password", "bad");
    try {
      toast("Signing in…");
      state.idToken = await signIn(email, password);
      state.email = email;
      showApp();
      toast("Signed in ✔", "ok");
    } catch (e) { toast(e.message, "bad"); }
  };

  $("btnSignUp").onclick = async () => {
    const email = $("email").value.trim(), password = $("password").value;
    if (!email || !password) return toast("Enter email and password", "bad");
    try {
      toast("Creating account…");
      await signUp(email, password);
      state.idToken = await signIn(email, password);
      state.email = email;
      showApp();
      toast("Account created — you're in ✔", "ok");
    } catch (e) { toast(e.message, "bad"); }
  };

  $("btnLogout").onclick = () => { showAuth(); toast("Signed out"); };

  $("addForm").onsubmit = addExpense;
  $("btnScan").onclick = scanReceipt;

  $("fq").oninput        = (e) => { state.q = e.target.value; renderAll(); };
  $("filterCategory").onchange = (e) => { state.category = e.target.value; renderAll(); };
  $("sortBy").onchange   = (e) => { state.sort = e.target.value; renderAll(); };
  $("btnExport").onclick = exportCsv;

  $("list").onclick = (ev) => {
    const t = ev.target.closest("[data-edit],[data-del],[data-receipt],[data-upload]");
    if (!t) return;
    if (t.dataset.edit)    return openEdit(t.dataset.edit);
    if (t.dataset.del)     return confirmDelete(t.dataset.del);
    if (t.dataset.receipt) return previewReceipt(t.dataset.receipt);
    if (t.dataset.upload)  return uploadReceipt(t.dataset.upload);
  };

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
    if (e.key === "/" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      e.preventDefault();
      $("fq").focus();
    }
  });

  $("email").addEventListener("keydown", (e) => { if (e.key === "Enter") $("password").focus(); });
  $("password").addEventListener("keydown", (e) => { if (e.key === "Enter") $("btnSignIn").click(); });
}

wire();
showAuth();
