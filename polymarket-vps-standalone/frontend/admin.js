const $ = (id) => document.getElementById(id);

if ($("apiBase") && !$("apiBase").value) $("apiBase").value = window.location.origin;

function apiBase() {
  return $("apiBase").value.replace(/\/$/, "");
}

function authToken() {
  return localStorage.getItem("poly_admin_token") || "";
}

function setAuth(token, username) {
  if (token) {
    localStorage.setItem("poly_admin_token", token);
    localStorage.setItem("poly_admin_username", username);
  } else {
    localStorage.removeItem("poly_admin_token");
    localStorage.removeItem("poly_admin_username");
  }
  updateLoginState();
}

function updateLoginState() {
  const username = localStorage.getItem("poly_admin_username");
  $("loginState").textContent = username ? `管理员: ${username}` : "未登录";
  if ($("adminBanner")) $("adminBanner").textContent = username ? `管理员已登录：${username}` : "管理员已登录";
}

function showLoginView(message = "") {
  $("adminLoginView").classList.remove("hidden");
  $("adminForcePasswordView").classList.add("hidden");
  $("adminAppView").classList.add("hidden");
  if (message) show("loginBox", message);
}

function showForcePasswordView(message = "") {
  $("adminLoginView").classList.add("hidden");
  $("adminForcePasswordView").classList.remove("hidden");
  $("adminAppView").classList.add("hidden");
  if (message) show("accountBox", message);
}

function showAdminApp(username = localStorage.getItem("poly_admin_username")) {
  $("adminLoginView").classList.add("hidden");
  $("adminForcePasswordView").classList.add("hidden");
  $("adminAppView").classList.remove("hidden");
  updateLoginState();
  if (username) $("adminBanner").textContent = `管理员已登录：${username}`;
  loadAdminUsers().catch((e) => show("adminBox", e.message));
}

async function bootstrapSession() {
  if (!authToken()) {
    showLoginView();
    return;
  }
  try {
    const data = await api("/api/me");
    if (data.role !== "admin") {
      setAuth("", "");
      showLoginView("当前登录的不是管理员账号。");
      return;
    }
    if (data.password_change_required) {
      showForcePasswordView("首次登录必须先修改默认密码。");
      return;
    }
    showAdminApp(data.username);
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

async function loadAdminUsers() {
  const data = await api("/api/admin/users");
  $("adminUsersBody").innerHTML = "";
  for (const user of data.users || []) {
    const row = document.createElement("tr");
    const canDelete = user.role !== "admin";
    const pendingActions = user.status === "pending"
      ? `<button data-approve="${user.username}">批准</button><button class="danger" data-reject="${user.username}">拒绝</button>`
      : "";
    row.innerHTML = `<td>${user.username}</td><td>${user.role}</td><td>${user.status || "approved"}</td><td>${user.password_change_required ? "是" : "否"}</td><td>${user.created_at || "--"}</td><td>${user.settings?.daily_report_time || "--"}</td><td>${pendingActions}${canDelete ? `<button class="secondary" data-del="${user.username}">删除</button>` : ""}</td>`;
    $("adminUsersBody").appendChild(row);
  }
  document.querySelectorAll("[data-approve]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      show("adminBox", await api(`/api/admin/users/${encodeURIComponent(btn.dataset.approve)}/approve`, {method: "POST"}));
      await loadAdminUsers();
    });
  });
  document.querySelectorAll("[data-reject]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!window.confirm(`确认拒绝并删除用户 ${btn.dataset.reject}？`)) return;
      show("adminBox", await api(`/api/admin/users/${encodeURIComponent(btn.dataset.reject)}/reject`, {method: "POST"}));
      await loadAdminUsers();
    });
  });
  document.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!window.confirm(`确认删除用户 ${btn.dataset.del}？`)) return;
      show("adminBox", await api(`/api/admin/users/${encodeURIComponent(btn.dataset.del)}`, {method: "DELETE"}));
      await loadAdminUsers();
    });
  });
}

$("loginBtn").onclick = async () => {
  try {
    const data = await api("/api/auth/login", {method: "POST", body: JSON.stringify({username: $("username").value, password: $("password").value})});
    if (data.role !== "admin") throw new Error("该账号不是管理员。");
    setAuth(data.token, data.username);
    if (data.password_change_required) {
      showForcePasswordView("首次登录必须先修改默认密码。");
    } else {
      showAdminApp(data.username);
    }
  } catch (e) {
    show("loginBox", e.message);
  }
};

$("changePasswordBtn").onclick = async () => {
  try {
    const data = await api("/api/auth/change_password", {method: "POST", body: JSON.stringify({old_password: $("oldPassword").value, new_password: $("newPassword").value})});
    showAdminApp(data.username);
  } catch (e) {
    show("accountBox", e.message);
  }
};

$("forceLogoutBtn").onclick = async () => {
  try { await api("/api/auth/logout", {method: "POST"}); } catch {}
  setAuth("", "");
  showLoginView("已退出。");
};

$("logoutBtn").onclick = async () => {
  try { await api("/api/auth/logout", {method: "POST"}); } catch {}
  setAuth("", "");
  showLoginView("已退出。");
};

$("meBtn").onclick = async () => { try { show("accountBox", await api("/api/me")); } catch (e) { show("accountBox", e.message); } };
$("adminUsersBtn").onclick = async () => { try { await loadAdminUsers(); } catch (e) { show("adminBox", e.message); } };
$("adminJobsBtn").onclick = async () => { try { show("adminBox", await api("/api/admin/jobs")); } catch (e) { show("adminBox", e.message); } };
$("clearCacheBtn").onclick = async () => { try { show("adminBox", await api("/api/admin/cache/clear", {method: "POST"})); } catch (e) { show("adminBox", e.message); } };

bootstrapSession();
