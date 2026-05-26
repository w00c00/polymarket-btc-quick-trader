# Polymarket VPS 项目上下文

这份文档用于把 VPS 版从旧桌面脚本里拆出来时保留关键记忆。新开项目或新开对话时，先读这里，再读代码。

## 当前目标

这是一个多人使用的 Polymarket BTC 短周期控制台：

- VPS 跑 FastAPI 后端，Nginx/HTTPS 对外提供页面。
- 前端是静态 HTML/CSS/JS，由后端直接服务。
- 用户用账号密码登录，各自保存凭证、通知、模型配置和策略任务。
- 管理员只做后台管理，不参与交易。
- 手动交易、短周期方向预测、三连反转策略、回测、通知报告分开显示，避免逻辑混淆。

## 当前线上部署记忆

- 当前线上域名：`https://yc.xiaobaizf.one`
- 管理后台：`https://yc.xiaobaizf.one/admin`
- VPS 服务目录：`/opt/polymarket-vps`
- VPS 数据目录：`/var/lib/polymarket-vps`
- systemd 服务：`polymarket-vps`
- 后端监听：`127.0.0.1:8787`
- Nginx 反代 HTTPS 到 `127.0.0.1:8787`
- 运行用户：`polymm`
- 本地 SSH alias 曾配置为 `polymarket-vps`

不要在文档或提交里记录 VPS root 密码、用户私钥、API key。

## 账号和权限

- 默认管理员：`poly`
- 默认管理员密码：`123456`
- 管理员首次登录必须改密码。
- 管理员页面独立在 `/admin`，管理员账号不能交易、不能保存交易凭证。
- 用户注册后状态是 `pending`，必须管理员批准后才能登录。
- 管理员后台可以批准、拒绝、删除用户，查看所有用户任务状态，清理缓存。

## 多用户安全隔离

- 用户密码只保存 PBKDF2-SHA256 哈希。
- 每个用户有独立 session token。
- 每个用户有独立 settings，包括通知配置、模型配置、日报时间。
- 每个用户有独立 encrypted vault 文件。
- vault 解锁后的明文凭证按用户名保存在后端进程内存中。
- 策略任务 id 包含用户名，用户只能管理自己的任务。
- 管理员后台能看任务状态，但管理员账号不执行交易。

## 凭证和 vault 逻辑

前端凭证页做浏览器端加密：

- 用户填写 Polygon 私钥、Funder 地址、签名类型、可选 CLOB API 三件套、模型 API key。
- 用户输入“本地加密密码”。
- 浏览器用 PBKDF2-SHA256 派生 AES-GCM key。
- 浏览器把凭证 JSON 加密后上传 VPS。
- VPS 磁盘只保存密文，不保存明文私钥。

按钮含义：

- 加密保存到 VPS：覆盖保存该用户密文，并锁定内存中的旧明文。
- 解锁到 VPS 内存：用本地加密密码解密密文，明文只存在后端进程内存。
- 锁定：删除当前用户后端内存里的明文凭证，磁盘密文仍保留。
- 后端服务重启后内存凭证会消失，需要重新解锁。

Polymarket 凭证建议：

- 最稳定方式：填写 Polygon 私钥 + Funder 地址 + 签名类型，让后端自动派生 CLOB API 三件套。
- CLOB API Key、Secret、Passphrase 可以全留空；如果手动填写，必须三项都填。
- Funder 是 Polymarket 代理钱包/资金地址，常常不等于浏览器钱包地址。
- Funder 获取方式：优先从 Polymarket 网页钱包/资金页面复制；也可从 Polygonscan 追踪代理钱包；最终以刷新持仓/余额能否匹配网页为准。
- 普通 EOA 签名类型通常是 0；代理钱包常见是 1/2/3。当前 UI 默认 3。

## 手动交易逻辑

手动交易页只做短周期市场选择和当前选中周期的 UP/DOWN 方向预测。

- 扫描短周期市场：`GET /api/markets/quick`
- 预测选中市场：`POST /api/strategy/predict`
- 刷新余额/持仓：`GET /api/trading/snapshot`
- 手动买入：`POST /api/trading/manual_order`
- 持仓限价卖出：`POST /api/trading/sell_position`

重要边界：

- 手动页预测不使用三连反转加权。
- 手动页预测不要显示三连策略建议。
- 手动页和策略页不要共用输出区域。
- 手动真实买卖需要用户二次确认。

## 策略和回测逻辑

策略页和回测页才使用“三连反转”：

- 三连阴转 UP：连续 3 根 15m 阴线后，从下一轮开始买 UP。
- 三连阳转 DOWN：连续 3 根 15m 阳线后，从下一轮开始买 DOWN。
- 首单失败后下一轮按马丁金额加注，最多跑设定单数。
- 本金计算使用 `reversal_stakes`。
- 回测使用 Binance BTCUSDT 15m K 线。

页面分区：

- `策略任务（模拟）`：长期 dry-run，记录心跳和信号，不真实下单。
- `策略任务（实盘）`：默认隐藏，点击开启实盘页并二次确认后才显示。

当前安全状态：

- 后端真实自动策略仍保留安全闸门，`dry_run=false` 会被阻止。
- 手动交易真实买入/卖出功能可以使用。
- 接真实自动策略前，先让 dry-run 长期跑稳。

## 通知和报告

通知报告页配置：

- 方糖 / Server 酱 SendKey
- Telegram Bot Token
- Telegram Chat ID
- 每日报告时间

发送规则：

- 方糖和 Telegram 任意一个可用即可发送。
- 两个都填写时会同时发送。
- 兼容旧 vault 里的 `sendkey`，但推荐新配置放到通知报告页。

报告内容：

- 统计周期：日、周、月、自定义小时。
- 成交笔数和成交名义额。
- 成交/订单详情，来自 CLOB trades API，失败时降级显示接口错误。
- 未成交挂单数。
- 当前持仓数、总现值、当前持仓浮盈亏。
- 发送报告时的实时余额快照。
- 当前运行任务数量。

注意：当前盈亏以持仓接口的浮盈亏为主，没有强行用大模型估算已实现盈亏。

## 模型配置

- 每个用户的模型设置独立保存。
- 模型 API key 保存在用户自己的 encrypted vault 中。
- 内置服务有内置 Base URL，只有自定义 OpenAI 兼容接口需要填 Base URL。
- MiniMax 国内版为默认首选。
- 当前手动本地预测主要是轻量技术指标逻辑；大模型接入可以继续增强，但不要让它替代真实交易数据。

内置模型服务：

- MiniMax 国内版
- DeepSeek
- 阿里 Qwen
- Kimi
- 智谱 GLM
- OpenAI
- Anthropic Claude
- Google Gemini
- OpenRouter

## 重要文件

- `backend/app.py`：FastAPI 路由、用户依赖、交易接口、报告、任务循环。
- `backend/auth.py`：用户、session、管理员、审批状态。
- `backend/vault.py`：加密 vault 存储和内存解锁状态。
- `backend/core.py`：市场扫描、K 线、概率、三连反转、本金和回测。
- `frontend/index.html`：用户主控制台。
- `frontend/app.js`：用户前端交互。
- `frontend/admin.html` / `frontend/admin.js`：管理员后台。
- `frontend/styles.css`：UI 样式。
- `deploy/install_vps.sh`：安装到 `/opt/polymarket-vps` 和 systemd。
- `deploy/deploy_remote.sh`：远程部署。
- `tests/`：认证、vault、核心策略测试。

## 开发验证命令

```bash
python3 -m pytest tests -q
python3 -m py_compile backend/app.py backend/auth.py backend/core.py backend/vault.py
node --check frontend/app.js
node --check frontend/admin.js
```

部署后验证：

```bash
systemctl is-active polymarket-vps
curl -fsS http://127.0.0.1:8787/api/health
curl -fsS https://yc.xiaobaizf.one/api/health
```

## 已踩过的坑

- 不要把管理员做成“第一个注册用户”，管理员固定为 `poly`。
- 登录页不要混入改密和凭证配置；登录后再显示账号页。
- 手动预测不要混三连策略逻辑。
- 策略模拟和实盘必须明显区分。
- 实盘页默认隐藏，并且要二次确认。
- 方糖不应该藏在凭证页，通知报告页才是主配置入口。
- VPS 部署不要依赖临时用户 home，程序固定放 `/opt/polymarket-vps`，数据固定放 `/var/lib/polymarket-vps`。
- 不要影响 VPS 上其他服务，Nginx 只加本站点反代，后端只绑定本机 8787。
