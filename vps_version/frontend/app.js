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

function showGuide(title, html) {
  $("guideTitle").textContent = title;
  $("guideContent").innerHTML = html;
  $("guideDialog").showModal();
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

function durationHours(prefix) {
  const preset = $(`${prefix}DurationPreset`).value;
  if (preset === "custom") return Number($(`${prefix}Hours`).value || 24);
  return Number(preset || 24);
}

function toggleDurationInput(prefix) {
  $(`${prefix}HoursWrap`).classList.toggle("hidden", $(`${prefix}DurationPreset`).value !== "custom");
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
  return startStrategy(mode, true, "live");
}

async function startReal(mode) {
  return startStrategy(mode, false, "real");
}

async function startStrategy(mode, dryRun, prefix) {
  const body = {
    mode,
    initial_usdc: Number($(`${prefix}Initial`).value),
    max_layers: Number($(`${prefix}Layers`).value),
    entry_price: Number($(`${prefix}Entry`).value),
    max_hours: durationHours(prefix),
    fee_rate: 0.07,
    dry_run: dryRun,
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
$("predictBtn").onclick = async () => { try { if (!selectedMarket) throw new Error("请先选择市场。"); show("predictionBox", "预测中..."); const data = await api("/api/strategy/predict", {method: "POST", body: JSON.stringify({market: selectedMarket, days: 3})}); show("predictionBox", {type: "选中周期方向预测", market: selectedMarket.question, market_time_bj: selectedMarket.time_label_bj, action: data.action, up_probability: formatPct(data.up_probability), down_probability: formatPct(data.down_probability), confidence: formatPct(data.confidence), last_price: Number(data.last_price.toFixed(2)), last_kline: data.last_kline_bj || data.last_kline, signals: {ret_45m: data.signals?.ret_45m, ret_120m: data.signals?.ret_120m, ret_240m: data.signals?.ret_240m, rsi14: data.signals?.rsi14}, note: "手动页预测只看当前选中周期的方向概率，不触发三连策略。"}); } catch (e) { show("predictionBox", e.message); } };
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

$("liveDurationPreset").onchange = () => toggleDurationInput("live");
$("realDurationPreset").onchange = () => toggleDurationInput("real");
$("reportPeriod").onchange = () => $("reportHoursWrap").classList.toggle("hidden", $("reportPeriod").value !== "custom");

$("startDryRunBtn").onclick = async () => { try { show("liveBox", await startDryRun($("liveMode").value)); renderLiveStatus(await api("/api/strategy/live/status")); } catch (e) { show("liveBox", e.message); } };
$("startBothDryRunBtn").onclick = async () => { try { const a = await startDryRun("三连阴转UP"); const b = await startDryRun("三连阳转DOWN"); show("liveBox", {red_up: a, green_down: b}); renderLiveStatus(await api("/api/strategy/live/status")); } catch (e) { show("liveBox", e.message); } };
$("stopLiveBtn").onclick = async () => { try { show("liveBox", await api("/api/strategy/live/stop", {method: "POST"})); renderLiveStatus(await api("/api/strategy/live/status")); } catch (e) { show("liveBox", e.message); } };
$("liveStatusBtn").onclick = async () => { try { const data = await api("/api/strategy/live/status"); renderLiveStatus(data); show("liveBox", data); } catch (e) { show("liveBox", e.message); } };

$("enableLiveBtn").onclick = () => {
  const ok = window.confirm("确认显示实盘策略页？实盘任务会使用真实凭证，连续亏损会触发加注本金占用。");
  if (!ok) return;
  $("liveTabBtn").classList.remove("hidden");
  setActiveTab("liveStrategy");
};
$("startRealBtn").onclick = async () => { try { if (!window.confirm("二次确认：启动选中策略实盘？")) return; show("realBox", await startReal($("realMode").value)); renderLiveStatus(await api("/api/strategy/live/status")); } catch (e) { show("realBox", e.message); } };
$("startBothRealBtn").onclick = async () => { try { if (!window.confirm("二次确认：同时启动正反实盘？这会占用双倍本金，且可能互相对冲。")) return; const a = await startReal("三连阴转UP"); const b = await startReal("三连阳转DOWN"); show("realBox", {red_up: a, green_down: b}); renderLiveStatus(await api("/api/strategy/live/status")); } catch (e) { show("realBox", e.message); } };
$("realStatusBtn").onclick = async () => { try { const data = await api("/api/strategy/live/status"); renderLiveStatus(data); show("realBox", data); } catch (e) { show("realBox", e.message); } };

$("loadNotifyBtn").onclick = async () => { try { const data = await api("/api/settings/notifications"); $("notifyServerChan").value = data.server_chan_sendkey || ""; $("telegramToken").value = data.telegram_bot_token || ""; $("telegramChat").value = data.telegram_chat_id || ""; $("dailyReportTime").value = data.daily_report_time || "21:30"; show("notifyBox", data); } catch (e) { show("notifyBox", e.message); } };
$("saveNotifyBtn").onclick = async () => { try { show("notifyBox", await api("/api/settings/notifications", {method: "POST", body: JSON.stringify({server_chan_sendkey: $("notifyServerChan").value, telegram_bot_token: $("telegramToken").value, telegram_chat_id: $("telegramChat").value, daily_report_time: $("dailyReportTime").value || "21:30"})})); } catch (e) { show("notifyBox", e.message); } };
$("sendReportBtn").onclick = async () => { try { show("notifyBox", await api("/api/reports/send_now", {method: "POST", body: JSON.stringify({period: $("reportPeriod").value, hours: $("reportPeriod").value === "custom" ? Number($("reportHours").value || 24) : null})})); } catch (e) { show("notifyBox", e.message); } };

$("guideCloseBtn").onclick = () => $("guideDialog").close();
$("credentialGuideBtn").onclick = () => showGuide("凭证填写指南", `
  <h3>Polymarket 钱包凭证</h3>
  <p>常见有三类：浏览器钱包地址、代理/Funder 地址、CLOB API 三件套。VPS 程序最稳定的方式是填写 Polygon 私钥 + Funder 地址 + 签名类型，然后由程序自动派生 CLOB API Key、Secret、Passphrase。</p>
  <ul>
    <li><b>Polygon 私钥</b>：用于签名，不要使用主钱包，建议单独建交易钱包，只放策略本金。</li>
    <li><b>Funder 地址</b>：Polymarket 代理钱包/资金地址。签名类型为 1 或 2 或 3 时通常必须填写。</li>
    <li><b>签名类型</b>：普通 EOA 通常是 0；Polymarket 代理钱包常见是 1/2/3。你之前用 Polymarket 网页充值到平台账户，通常应按代理钱包方式填 Funder。</li>
    <li><b>CLOB 三件套</b>：可以留空。留空时后端会通过私钥自动派生，长期跑更省心；如果你已有固定三件套，也可以三项一起填写。</li>
    <li><b>稳定性建议</b>：优先使用“私钥自主派生三件套”的方式。它减少手填错误，也避免 API key 过期或抄错导致 401。</li>
  </ul>
  <h3>通知和模型</h3>
  <p>方糖 SendKey 建议填到“通知报告”页。模型 Key 仍放在本页加密 vault 中；模型 Base URL 已内置，只有自定义接口需要填 Base URL。</p>
  <h3>安全建议</h3>
  <p>VPS 只保存浏览器加密后的密文。解锁密码不要和账号密码相同；实盘钱包只放可承受损失的小额 USDC。</p>
`);
$("strategyHelpBtn").onclick = () => showGuide("三连反转策略说明", `
  <p>策略只在策略任务和回测页使用，和手动交易页的方向预测无关。</p>
  <ul>
    <li><b>三连阴转UP</b>：连续 3 根 15m 阴线后，从下一轮开始只买 UP。</li>
    <li><b>三连阳转DOWN</b>：连续 3 根 15m 阳线后，从下一轮开始只买 DOWN。</li>
    <li><b>加注</b>：首单失败后下一轮按计算好的金额加注，最多跑设定单数。</li>
    <li><b>模拟任务</b>：长期轮询 K 线，只记录信号和任务状态，不真实下单。</li>
    <li><b>实盘任务</b>：默认隐藏，必须二次确认后进入；当前后端仍保留安全闸门，未接入真实自动执行前不会盲目下单。</li>
  </ul>
`);
$("liveHelpBtn").onclick = $("strategyHelpBtn").onclick;

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
