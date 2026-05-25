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
    row.innerHTML = `<td>${user.username}</td><td>${user.role}</td><td>${user.password_change_required ? "是" : "否"}</td><td>${user.created_at || "--"}</td><td>${user.settings?.daily_report_time || "--"}</td><td>${canDelete ? `<button class="secondary" data-del="${user.username}">删除</button>` : ""}</td>`;
    $("adminUsersBody").appendChild(row);
  }
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
    show("accountBox", data.password_change_required ? "首次登录必须先修改默认密码。" : {ok: true, message: "后台登录成功", username: data.username});
  } catch (e) {
    show("accountBox", e.message);
  }
};

$("changePasswordBtn").onclick = async () => {
  try {
    const data = await api("/api/auth/change_password", {method: "POST", body: JSON.stringify({old_password: $("oldPassword").value, new_password: $("newPassword").value})});
    show("accountBox", data);
  } catch (e) {
    show("accountBox", e.message);
  }
};

$("logoutBtn").onclick = async () => {
  try { await api("/api/auth/logout", {method: "POST"}); } catch {}
  setAuth("", "");
  show("accountBox", "已退出。");
};

$("meBtn").onclick = async () => { try { show("accountBox", await api("/api/me")); } catch (e) { show("accountBox", e.message); } };
$("adminUsersBtn").onclick = async () => { try { await loadAdminUsers(); } catch (e) { show("adminBox", e.message); } };
$("adminJobsBtn").onclick = async () => { try { show("adminBox", await api("/api/admin/jobs")); } catch (e) { show("adminBox", e.message); } };
$("clearCacheBtn").onclick = async () => { try { show("adminBox", await api("/api/admin/cache/clear", {method: "POST"})); } catch (e) { show("adminBox", e.message); } };

updateLoginState();
