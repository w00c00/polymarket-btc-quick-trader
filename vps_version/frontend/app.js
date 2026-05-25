const $ = (id) => document.getElementById(id);
let markets = [];
let selectedMarket = null;
let latestPositions = [];
let modelProviders = {};

for (const btn of document.querySelectorAll(".tab")) {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    btn.classList.add("active");
    $(btn.dataset.tab).classList.add("active");
  });
}

if ($("apiBase") && !$("apiBase").value) $("apiBase").value = window.location.origin;

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

function afterLogin(data) {
  setAuth(data.token, data.username);
  if (data.role === "admin") {
    window.location.href = "/admin";
    return;
  }
  if (data.password_change_required) {
    showForcePasswordView("该账号必须先修改初始密码。");
    return;
  }
  showAppView(data.username);
}

function updateLoginState() {
  const username = localStorage.getItem("poly_vps_username");
  $("loginState").textContent = username ? `已登录: ${username}` : "未登录";
  $("accountStatus").textContent = username ? `当前已登录账号：${username}` : "未登录";
  $("accountStatus").className = username ? "status-line ok" : "status-line warn";
  if ($("sessionBanner")) $("sessionBanner").textContent = username ? `已登录：${username}` : "未登录";
}

function setActiveTab(tabId) {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x.dataset.tab === tabId));
  document.querySelectorAll(".panel").forEach((x) => x.classList.toggle("active", x.id === tabId));
}

function showLoginView(message = "") {
  $("loginView").classList.remove("hidden");
  $("forcePasswordView").classList.add("hidden");
  $("appView").classList.add("hidden");
  if (message) show("loginBox", message);
}

function showForcePasswordView(message = "") {
  $("loginView").classList.add("hidden");
  $("forcePasswordView").classList.remove("hidden");
  $("appView").classList.add("hidden");
  if (message) show("forcePasswordBox", message);
}

function showAppView(username = localStorage.getItem("poly_vps_username")) {
  $("loginView").classList.add("hidden");
  $("forcePasswordView").classList.add("hidden");
  $("appView").classList.remove("hidden");
  updateLoginState();
  setActiveTab("manual");
  if (username) $("sessionBanner").textContent = `已登录：${username}`;
}

async function bootstrapSession() {
  if (!authToken()) {
    showLoginView();
    return;
  }
  try {
    const data = await api("/api/me");
    if (data.role === "admin") {
      window.location.href = "/admin";
      return;
    }
    if (data.password_change_required) {
      showForcePasswordView("该账号必须先修改初始密码。");
      return;
    }
    showAppView(data.username);
  } catch {
    setAuth("", "");
    showLoginView("登录已失效，请重新登录。");
  }
}

async function api(path, options = {}) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (authToken()) headers.Authorization = `Bearer ${authToken()}`;
  const response = await fetch(`${apiBase()}${path}`, {...options, headers});
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = {raw: text}; }
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}

function show(id, value) {
  $(id).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function formatPrice(value) {
  return Number(value || 0).toFixed(2);
}

function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
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
  $("selectedMarketBox").textContent = `已选择：${selectedMarket.period} | ${selectedMarket.time_label_bj || "--"} | Up ${formatPrice(selectedMarket.up_bid)}/${formatPrice(selectedMarket.up_ask)} Down ${formatPrice(selectedMarket.down_bid)}/${formatPrice(selectedMarket.down_ask)} | ${selectedMarket.question}`;
  $("selectedMarketBox").className = "status-line ok";
}

function renderMarkets(items) {
  markets = items || [];
  selectedMarket = null;
  $("marketsBody").innerHTML = "";
  $("selectedMarketBox").textContent = markets.length ? "请选择一个短周期市场。" : "未扫描到短周期市场。";
  $("selectedMarketBox").className = markets.length ? "status-line warn" : "status-line";
  for (const [index, m] of markets.entries()) {
    const row = document.createElement("tr");
    row.dataset.index = String(index);
    row.innerHTML = `<td><button class="secondary" data-select="${index}">选择</button></td><td>${m.period}</td><td>${m.time_label_bj || m.end_dt_bj || "--"}</td><td>${formatPrice(m.up_bid)}/${formatPrice(m.up_ask)}</td><td>${formatPrice(m.down_bid)}/${formatPrice(m.down_ask)}</td><td>${Math.round(m.volume24h)}</td><td>${m.question}</td>`;
    row.addEventListener("click", () => setSelectedMarket(index));
    $("marketsBody").appendChild(row);
  }
  if (markets.length) setSelectedMarket(0);
}

function renderSnapshot(data) {
  const summary = data.summary || {};
  $("snapshotSummary").innerHTML = `
    <div><strong>${summary.count || 0}</strong><span>持仓</span></div>
    <div><strong>${Number(summary.total_value || 0).toFixed(2)}</strong><span>现值 USDC</span></div>
    <div><strong>${Number(summary.total_pnl || 0).toFixed(2)}</strong><span>浮盈亏</span></div>
    <div><strong>${data.refreshed_at || "--"}</strong><span>刷新时间</span></div>
  `;
  latestPositions = summary.positions || [];
  $("positionsBody").innerHTML = "";
  for (const [index, p] of latestPositions.entries()) {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${p.outcome || ""}</td><td>${Number(p.size || 0).toFixed(2)}</td><td>${Number(p.avgPrice || 0).toFixed(4)}</td><td>${Number(p.curPrice || 0).toFixed(4)}</td><td>${Number(p.currentValue || 0).toFixed(2)}</td><td class="${Number(p.cashPnl || 0) >= 0 ? "pnl-pos" : "pnl-neg"}">${Number(p.cashPnl || 0).toFixed(2)} (${Number(p.percentPnl || 0).toFixed(2)}%)</td><td><button class="secondary" data-sell="${index}">按现价卖出</button></td><td>${String(p.title || "").slice(0, 90)}</td>`;
    $("positionsBody").appendChild(row);
  }
  if (!latestPositions.length) $("positionsBody").innerHTML = "<tr><td colspan='8'>当前没有可显示持仓。</td></tr>";
  document.querySelectorAll("[data-sell]").forEach((btn) => {
    btn.addEventListener("click", () => sellPosition(Number(btn.dataset.sell)));
  });
}

async function refreshSnapshot() {
  show("manualBox", "刷新余额/持仓中...");
  const data = await api("/api/trading/snapshot");
  renderSnapshot(data);
  show("manualBox", data);
}

async function submitManual(direction) {
  if (!selectedMarket) throw new Error("请先扫描并选择市场。");
  const amount = Number($("manualAmount").value);
  const maxPrice = Number($("manualMaxPrice").value);
  const text = `确认真实买入 ${direction}？\n金额: ${amount} USDC\n最高价: ${maxPrice}\n市场: ${selectedMarket.question}`;
  if (!window.confirm(text)) return;
  show("manualBox", "提交真实订单中...");
  const data = await api("/api/trading/manual_order", {
    method: "POST",
    body: JSON.stringify({market: selectedMarket, direction, side: "BUY", usdc_amount: amount, max_price: maxPrice}),
  });
  renderSnapshot({summary: data.summary, refreshed_at: "刚刚"});
  show("manualBox", data);
}

async function sellPosition(index) {
  const p = latestPositions[index];
  if (!p) return;
  const price = Number(p.curPrice || 0);
  const size = Number(p.size || 0);
  if (!window.confirm(`确认真实限价卖出？\n方向: ${p.outcome}\n数量: ${size.toFixed(2)}\n价格: ${price.toFixed(4)}\n市场: ${p.title}`)) return;
  show("manualBox", "提交卖出订单中...");
  const data = await api("/api/trading/sell_position", {
    method: "POST",
    body: JSON.stringify({token_id: String(p.asset), size, price, tick_size: String(p.orderPriceMinTickSize || "0.01"), title: p.title || "", outcome: p.outcome || "", slug: p.slug || p.eventSlug || ""}),
  });
  renderSnapshot({summary: data.summary, refreshed_at: "刚刚"});
  show("manualBox", data);
}

async function startDryRun(mode) {
  const body = {
    mode,
    initial_usdc: Number($("liveInitial").value),
    max_layers: Number($("liveLayers").value),
    entry_price: Number($("liveEntry").value),
    max_hours: Number($("liveHours").value),
    fee_rate: 0.07,
    dry_run: true,
  };
  return api("/api/strategy/live/start", {method: "POST", body: JSON.stringify(body)});
}

function renderLiveStatus(data) {
  const jobs = data.jobs || {};
  $("liveCards").innerHTML = "";
  for (const job of Object.values(jobs)) {
    const card = document.createElement("div");
    card.className = `status-card ${job.status}`;
    const events = (job.events || []).slice(-4).map((line) => `<li>${line}</li>`).join("");
    card.innerHTML = `<h3>${job.mode || "策略"}</h3><p><b>${job.status}</b> | ${job.started_at || "--"}</p><p>首单 ${job.config?.initial_usdc || "--"}U，最多 ${job.config?.max_layers || "--"} 单，最高价 ${job.config?.entry_price || "--"}</p><ul>${events}</ul>`;
    $("liveCards").appendChild(card);
  }
  if (!Object.keys(jobs).length) $("liveCards").innerHTML = "<div class='status-line'>当前没有运行中的策略任务。</div>";
}

function bytesToB64(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)));
}

async function deriveKey(password, salt, iterations) {
  const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({name: "PBKDF2", salt, iterations, hash: "SHA-256"}, material, {name: "AES-GCM", length: 256}, false, ["encrypt", "decrypt"]);
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
    openai_key: $("openaiKey").value,
    anthropic_key: $("anthropicKey").value,
    google_key: $("googleKey").value,
    deepseek_key: $("deepseekKey").value,
    qwen_key: $("qwenKey").value,
    kimi_key: $("kimiKey").value,
    zhipu_key: $("zhipuKey").value,
    openrouter_key: $("openrouterKey").value,
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
  return {version: 1, kdf: "PBKDF2-SHA256", iterations, salt: bytesToB64(salt), nonce: bytesToB64(nonce), ciphertext: bytesToB64(ciphertext)};
}

bootstrapSession();

$("healthBtn").onclick = async () => { try { show("manualBox", await api("/api/health")); } catch (e) { show("manualBox", e.message); } };
$("scanBtn").onclick = async () => { $("marketsBody").innerHTML = "<tr><td colspan='7'>扫描中...</td></tr>"; try { renderMarkets((await api("/api/markets/quick")).items); } catch (e) { $("marketsBody").innerHTML = `<tr><td colspan='7'>${e.message}</td></tr>`; } };
$("predictBtn").onclick = async () => { try { if (!selectedMarket) throw new Error("请先选择市场。"); show("manualBox", "预测中..."); const data = await api("/api/strategy/predict", {method: "POST", body: JSON.stringify({market: selectedMarket, days: 3})}); show("manualBox", {market: selectedMarket.question, market_time_bj: selectedMarket.time_label_bj, action: data.action, up_probability: formatPct(data.up_probability), down_probability: formatPct(data.down_probability), confidence: formatPct(data.confidence), last_price: Number(data.last_price.toFixed(2)), last_kline: data.last_kline_bj || data.last_kline, signals: data.signals, note: data.note}); } catch (e) { show("manualBox", e.message); } };
$("snapshotBtn").onclick = async () => { try { await refreshSnapshot(); } catch (e) { show("manualBox", e.message); } };
$("buyUpBtn").onclick = async () => { try { await submitManual("UP"); } catch (e) { show("manualBox", e.message); } };
$("buyDownBtn").onclick = async () => { try { await submitManual("DOWN"); } catch (e) { show("manualBox", e.message); } };

$("loginBtn").onclick = async () => { try { const data = await api("/api/auth/login", {method: "POST", body: JSON.stringify({username: $("username").value, password: $("password").value})}); afterLogin(data); } catch (e) { show("loginBox", e.message); } };
$("registerBtn").onclick = async () => { try { const data = await api("/api/auth/register", {method: "POST", body: JSON.stringify({username: $("username").value, password: $("password").value})}); show("loginBox", data.pending_approval ? "注册申请已提交，请等待管理员审批后再登录。" : data); } catch (e) { show("loginBox", e.message); } };
$("logoutBtn").onclick = async () => { try { await api("/api/auth/logout", {method: "POST"}); } catch {} setAuth("", ""); showLoginView("已退出。"); };
$("meBtn").onclick = async () => { try { show("accountBox", await api("/api/me")); } catch (e) { show("accountBox", e.message); } };
$("changePasswordBtn").onclick = async () => { try { show("accountBox", await api("/api/auth/change_password", {method: "POST", body: JSON.stringify({old_password: $("oldPassword").value, new_password: $("newPassword").value})})); } catch (e) { show("accountBox", e.message); } };
$("forceChangePasswordBtn").onclick = async () => { try { const data = await api("/api/auth/change_password", {method: "POST", body: JSON.stringify({old_password: $("forceOldPassword").value, new_password: $("forceNewPassword").value})}); showAppView(data.username); } catch (e) { show("forcePasswordBox", e.message); } };
$("forceLogoutBtn").onclick = async () => { try { await api("/api/auth/logout", {method: "POST"}); } catch {} setAuth("", ""); showLoginView("已退出。"); };

$("capitalBtn").onclick = async () => { try { const data = await api("/api/strategy/capital", {method: "POST", body: JSON.stringify(params(""))}); show("capitalBox", {stakes: data.stakes.map((x) => Number(x.toFixed(2))), stake_sum: Number(data.stake_sum.toFixed(2)), worst_loss: Number(data.worst_loss.toFixed(2)), recommended_single_strategy_usdc: data.recommended_single_strategy_usdc, recommended_both_strategies_usdc: data.recommended_both_strategies_usdc}); } catch (e) { show("capitalBox", e.message); } };
$("backtestBtn").onclick = async () => { try { const body = {...params(""), days: Number($("days").value)}; const data = await api("/api/strategy/backtest", {method: "POST", body: JSON.stringify(body)}); show("backtestBox", {label: data.label, range: `${data.from} -> ${data.to}`, cycles: data.cycles, wins: data.wins, losses: data.losses, win_rate: `${(data.win_rate * 100).toFixed(2)}%`, total_pnl: Number(data.total_pnl.toFixed(2)), max_drawdown: Number(data.max_drawdown.toFixed(2)), recent: data.recent}); } catch (e) { show("backtestBox", e.message); } };

$("saveVaultBtn").onclick = async () => { try { show("vaultBox", await api("/api/vault/save", {method: "POST", body: JSON.stringify(await encryptedVaultBlob())})); } catch (e) { show("vaultBox", e.message); } };
$("unlockVaultBtn").onclick = async () => { try { show("vaultBox", await api("/api/vault/unlock", {method: "POST", body: JSON.stringify({passphrase: $("vaultPassword").value})})); } catch (e) { show("vaultBox", e.message); } };
$("lockVaultBtn").onclick = async () => { try { show("vaultBox", await api("/api/vault/lock", {method: "POST"})); } catch (e) { show("vaultBox", e.message); } };
$("vaultStatusBtn").onclick = async () => { try { show("vaultBox", await api("/api/vault/status")); } catch (e) { show("vaultBox", e.message); } };

$("startDryRunBtn").onclick = async () => { try { show("liveBox", await startDryRun($("liveMode").value)); renderLiveStatus(await api("/api/strategy/live/status")); } catch (e) { show("liveBox", e.message); } };
$("startBothDryRunBtn").onclick = async () => { try { const a = await startDryRun("三连阴转UP"); const b = await startDryRun("三连阳转DOWN"); show("liveBox", {red_up: a, green_down: b}); renderLiveStatus(await api("/api/strategy/live/status")); } catch (e) { show("liveBox", e.message); } };
$("stopLiveBtn").onclick = async () => { try { show("liveBox", await api("/api/strategy/live/stop", {method: "POST"})); renderLiveStatus(await api("/api/strategy/live/status")); } catch (e) { show("liveBox", e.message); } };
$("liveStatusBtn").onclick = async () => { try { const data = await api("/api/strategy/live/status"); renderLiveStatus(data); show("liveBox", data); } catch (e) { show("liveBox", e.message); } };

$("loadNotifyBtn").onclick = async () => { try { const data = await api("/api/settings/notifications"); $("telegramToken").value = data.telegram_bot_token || ""; $("telegramChat").value = data.telegram_chat_id || ""; $("dailyReportTime").value = data.daily_report_time || "21:30"; show("notifyBox", data); } catch (e) { show("notifyBox", e.message); } };
$("saveNotifyBtn").onclick = async () => { try { show("notifyBox", await api("/api/settings/notifications", {method: "POST", body: JSON.stringify({telegram_bot_token: $("telegramToken").value, telegram_chat_id: $("telegramChat").value, daily_report_time: $("dailyReportTime").value || "21:30"})})); } catch (e) { show("notifyBox", e.message); } };
$("sendReportBtn").onclick = async () => { try { show("notifyBox", await api("/api/reports/send_now", {method: "POST"})); } catch (e) { show("notifyBox", e.message); } };

function updateModelProviderUi(data = {}) {
  if (data.providers) modelProviders = data.providers;
  const provider = $("preferredProvider").value;
  const isCustom = provider === "custom";
  $("customBaseUrlWrap").classList.toggle("hidden", !isCustom);
  $("customModelWrap").classList.toggle("hidden", !isCustom);
  const info = modelProviders[provider];
  $("providerBaseHint").textContent = isCustom
    ? "自定义接口需要填写 Base URL 和模型名。"
    : `当前使用内置 Base URL：${info?.base_url || "内置"}；无需单独填写。`;
  if (info && data.preferred_provider !== provider) $("preferredModel").value = info.default_model;
}

$("preferredProvider").onchange = () => updateModelProviderUi();
$("loadModelBtn").onclick = async () => { try { const data = await api("/api/settings/model"); $("preferredProvider").value = data.preferred_provider || "minimax_cn"; $("preferredModel").value = data.preferred_model || "MiniMax-M2.7"; $("customBaseUrl").value = data.custom_base_url || ""; $("customModel").value = data.custom_model || ""; updateModelProviderUi(data); show("modelBox", data); } catch (e) { show("modelBox", e.message); } };
$("saveModelBtn").onclick = async () => { try { show("modelBox", await api("/api/settings/model", {method: "POST", body: JSON.stringify({preferred_provider: $("preferredProvider").value, preferred_model: $("preferredModel").value, custom_base_url: $("customBaseUrl").value, custom_model: $("customModel").value})})); } catch (e) { show("modelBox", e.message); } };

setInterval(() => {
  if (authToken() && document.getElementById("manual").classList.contains("active")) {
    refreshSnapshot().catch(() => {});
  }
}, 120000);
