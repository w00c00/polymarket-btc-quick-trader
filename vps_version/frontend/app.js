const $ = (id) => document.getElementById(id);

for (const btn of document.querySelectorAll(".tab")) {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    btn.classList.add("active");
    $(btn.dataset.tab).classList.add("active");
  });
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
    show("accountBox", data);
  } catch (e) { show("accountBox", e.message); }
};

$("registerBtn").onclick = async () => {
  try {
    const data = await api("/api/auth/register", {method: "POST", body: JSON.stringify({username: $("username").value, password: $("password").value})});
    setAuth(data.token, data.username);
    show("accountBox", data);
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
  $("marketsBody").innerHTML = "<tr><td colspan='6'>扫描中...</td></tr>";
  try {
    const data = await api("/api/markets/quick");
    $("marketsBody").innerHTML = "";
    for (const m of data.items) {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${m.period}</td><td>${m.end_dt || "--"}</td><td>${m.up_bid.toFixed(2)}/${m.up_ask.toFixed(2)}</td><td>${m.down_bid.toFixed(2)}/${m.down_ask.toFixed(2)}</td><td>${Math.round(m.volume24h)}</td><td>${m.question}</td>`;
      $("marketsBody").appendChild(row);
    }
  } catch (e) {
    $("marketsBody").innerHTML = `<tr><td colspan='6'>${e.message}</td></tr>`;
  }
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
