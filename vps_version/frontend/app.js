const $ = (id) => document.getElementById(id);
let markets = [];
let selectedMarket = null;

for (const btn of document.querySelectorAll(".tab")) {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    btn.classList.add("active");
    $(btn.dataset.tab).classList.add("active");
  });
}

if ($("apiBase") && !$("apiBase").value) {
  $("apiBase").value = window.location.origin;
}

function apiBase() {
  return $("apiBase").value.replace(/\/$/, "");
}

function authToken() {
  return localStorage.getItem("poly_vps_token") || "";
}

function setAuth(token, username) {
  if (token) {
    localStorage.setItem("poly_vps_token", token);
    localStorage.setItem("poly_vps_username", username);
  } else {
    localStorage.removeItem("poly_vps_token");
    localStorage.removeItem("poly_vps_username");
  }
  updateLoginState();
}

function updateLoginState() {
  const username = localStorage.getItem("poly_vps_username");
  $("loginState").textContent = username ? `已登录: ${username}` : "未登录";
  if ($("accountStatus")) {
    $("accountStatus").textContent = username ? `当前已登录账号：${username}` : "未登录";
    $("accountStatus").className = username ? "status-line ok" : "status-line warn";
  }
}

async function api(path, options = {}) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (authToken()) headers.Authorization = `Bearer ${authToken()}`;
  const response = await fetch(`${apiBase()}${path}`, {
    ...options,
    headers,
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {raw: text};
  }
  if (!response.ok) {
    throw new Error(data.detail || response.statusText);
  }
  return data;
}

updateLoginState();

function show(id, value) {
  $(id).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatPrice(value) {
  return Number(value || 0).toFixed(2);
}

function setSelectedMarket(index) {
  selectedMarket = markets[index] || null;
  document.querySelectorAll("#marketsBody tr").forEach((row) => row.classList.remove("selected"));
  const row = document.querySelector(`#marketsBody tr[data-index="${index}"]`);
  if (row) row.classList.add("selected");
  if (!selectedMarket) {
    $("selectedMarketBox").textContent = "未选择市场";
    $("selectedMarketBox").className = "status-line warn";
    return;
  }
  $("selectedMarketBox").textContent = `已选择：${selectedMarket.period} | ${selectedMarket.time_label_bj || selectedMarket.end_dt_bj || selectedMarket.end_dt || "--"} | ${selectedMarket.question} | Up ${formatPrice(selectedMarket.up_bid)}/${formatPrice(selectedMarket.up_ask)} Down ${formatPrice(selectedMarket.down_bid)}/${formatPrice(selectedMarket.down_ask)}`;
  $("selectedMarketBox").className = "status-line ok";
}

function params(prefix = "") {
  return {
    mode: $(`${prefix}mode`)?.value || $("mode").value,
    initial_usdc: Number($(`${prefix}initial`)?.value || $("initial").value),
    max_layers: Number($(`${prefix}layers`)?.value || $("layers").value),
    entry_price: Number($(`${prefix}entry`)?.value || $("entry").value),
    fee_rate: 0.07,
  };
}

$("healthBtn").onclick = async () => {
  try { show("healthBox", await api("/api/health")); } catch (e) { show("healthBox", e.message); }
};

$("loginBtn").onclick = async () => {
  try {
    const data = await api("/api/auth/login", {method: "POST", body: JSON.stringify({username: $("username").value, password: $("password").value})});
    setAuth(data.token, data.username);
    show("accountBox", {ok: true, message: "登录成功", username: data.username});
  } catch (e) { show("accountBox", e.message); }
};

$("registerBtn").onclick = async () => {
  try {
    const data = await api("/api/auth/register", {method: "POST", body: JSON.stringify({username: $("username").value, password: $("password").value})});
    setAuth(data.token, data.username);
    show("accountBox", {ok: true, message: "注册并登录成功", username: data.username});
  } catch (e) { show("accountBox", e.message); }
};

$("logoutBtn").onclick = async () => {
  try { await api("/api/auth/logout", {method: "POST"}); } catch {}
  setAuth("", "");
  show("accountBox", "已退出。");
};

$("meBtn").onclick = async () => {
  try { show("accountBox", await api("/api/me")); } catch (e) { show("accountBox", e.message); }
};

$("scanBtn").onclick = async () => {
  $("marketsBody").innerHTML = "<tr><td colspan='7'>扫描中...</td></tr>";
  try {
    const data = await api("/api/markets/quick");
    markets = data.items || [];
    selectedMarket = null;
    $("marketsBody").innerHTML = "";
    $("selectedMarketBox").textContent = markets.length ? "请选择一个短周期市场后再预测。" : "未扫描到短周期市场。";
    $("selectedMarketBox").className = markets.length ? "status-line warn" : "status-line";
    for (const [index, m] of markets.entries()) {
      const row = document.createElement("tr");
      row.dataset.index = String(index);
      row.innerHTML = `<td><button class="secondary" data-select="${index}">选择</button></td><td>${m.period}</td><td>${m.time_label_bj || m.end_dt_bj || m.end_dt || "--"}</td><td>${formatPrice(m.up_bid)}/${formatPrice(m.up_ask)}</td><td>${formatPrice(m.down_bid)}/${formatPrice(m.down_ask)}</td><td>${Math.round(m.volume24h)}</td><td>${m.question}</td>`;
      row.addEventListener("click", (event) => {
        if (event.target?.tagName === "BUTTON" || event.target?.tagName === "TD") {
          setSelectedMarket(index);
        }
      });
      $("marketsBody").appendChild(row);
    }
    if (markets.length) setSelectedMarket(0);
  } catch (e) {
    $("marketsBody").innerHTML = `<tr><td colspan='7'>${e.message}</td></tr>`;
  }
};

$("predictBtn").onclick = async () => {
  if (!selectedMarket) {
    show("healthBox", "请先扫描并选择一个短周期市场。");
    return;
  }
  try {
    show("healthBox", "预测中...");
    const data = await api("/api/strategy/predict", {method: "POST", body: JSON.stringify({market: selectedMarket, days: 3})});
    show("healthBox", {
      market: `${selectedMarket.period} ${selectedMarket.question}`,
      market_time_bj: selectedMarket.time_label_bj || selectedMarket.end_dt_bj || selectedMarket.end_dt,
      action: data.action,
      up_probability: formatPct(data.up_probability),
      down_probability: formatPct(data.down_probability),
      confidence: formatPct(data.confidence),
      last_price: Number(data.last_price.toFixed(2)),
      last_kline: data.last_kline_bj || data.last_kline,
      signals: data.signals,
      note: data.note,
    });
  } catch (e) { show("healthBox", e.message); }
};

$("capitalBtn").onclick = async () => {
  try {
    const data = await api("/api/strategy/capital", {method: "POST", body: JSON.stringify(params(""))});
    show("capitalBox", {
      stakes: data.stakes.map((x) => Number(x.toFixed(2))),
      stake_sum: Number(data.stake_sum.toFixed(2)),
      worst_loss: Number(data.worst_loss.toFixed(2)),
      recommended_single_strategy_usdc: data.recommended_single_strategy_usdc,
      recommended_both_strategies_usdc: data.recommended_both_strategies_usdc,
    });
  } catch (e) { show("capitalBox", e.message); }
};

$("backtestBtn").onclick = async () => {
  try {
    const body = {...params(""), days: Number($("days").value)};
    const data = await api("/api/strategy/backtest", {method: "POST", body: JSON.stringify(body)});
    show("backtestBox", {
      label: data.label,
      range: `${data.from} -> ${data.to}`,
      cycles: data.cycles,
      wins: data.wins,
      losses: data.losses,
      win_rate: `${(data.win_rate * 100).toFixed(2)}%`,
      total_pnl: Number(data.total_pnl.toFixed(2)),
      max_drawdown: Number(data.max_drawdown.toFixed(2)),
      recent: data.recent,
    });
  } catch (e) { show("backtestBox", e.message); }
};

function bytesToB64(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)));
}

function b64ToBytes(value) {
  return Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
}

async function deriveKey(password, salt, iterations) {
  const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    {name: "PBKDF2", salt, iterations, hash: "SHA-256"},
    material,
    {name: "AES-GCM", length: 256},
    false,
    ["encrypt", "decrypt"],
  );
}

function credentialPayload() {
  return {
    priv_key: $("privKey").value,
    funder: $("funder").value,
    signature_type: Number($("signatureType").value || "3"),
    api_key: $("apiKey").value,
    secret: $("apiSecret").value,
    passphrase: $("apiPassphrase").value,
    sendkey: $("serverChan").value,
    minimax_key: $("minimax").value,
  };
}

async function encryptedVaultBlob() {
  const password = $("vaultPassword").value;
  if (password.length < 8) throw new Error("本地加密密码至少 8 位。");
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const iterations = 250000;
  const key = await deriveKey(password, salt, iterations);
  const plaintext = new TextEncoder().encode(JSON.stringify(credentialPayload()));
  const ciphertext = await crypto.subtle.encrypt({name: "AES-GCM", iv: nonce, additionalData: new TextEncoder().encode("poly-vps-vault-v1")}, key, plaintext);
  return {
    version: 1,
    kdf: "PBKDF2-SHA256",
    iterations,
    salt: bytesToB64(salt),
    nonce: bytesToB64(nonce),
    ciphertext: bytesToB64(ciphertext),
  };
}

$("saveVaultBtn").onclick = async () => {
  try {
    const blob = await encryptedVaultBlob();
    show("vaultBox", await api("/api/vault/save", {method: "POST", body: JSON.stringify(blob)}));
  } catch (e) { show("vaultBox", e.message); }
};

$("unlockVaultBtn").onclick = async () => {
  try {
    show("vaultBox", await api("/api/vault/unlock", {method: "POST", body: JSON.stringify({passphrase: $("vaultPassword").value})}));
  } catch (e) { show("vaultBox", e.message); }
};

$("lockVaultBtn").onclick = async () => {
  try { show("vaultBox", await api("/api/vault/lock", {method: "POST"})); } catch (e) { show("vaultBox", e.message); }
};

$("vaultStatusBtn").onclick = async () => {
  try { show("vaultBox", await api("/api/vault/status")); } catch (e) { show("vaultBox", e.message); }
};

$("startDryRunBtn").onclick = async () => {
  try {
    const body = {
      mode: $("liveMode").value,
      initial_usdc: Number($("liveInitial").value),
      max_layers: Number($("liveLayers").value),
      entry_price: Number($("liveEntry").value),
      max_hours: Number($("liveHours").value),
      fee_rate: 0.07,
      dry_run: true,
    };
    show("liveBox", await api("/api/strategy/live/start", {method: "POST", body: JSON.stringify(body)}));
  } catch (e) { show("liveBox", e.message); }
};

$("stopLiveBtn").onclick = async () => {
  try { show("liveBox", await api("/api/strategy/live/stop", {method: "POST"})); } catch (e) { show("liveBox", e.message); }
};

$("liveStatusBtn").onclick = async () => {
  try { show("liveBox", await api("/api/strategy/live/status")); } catch (e) { show("liveBox", e.message); }
};
