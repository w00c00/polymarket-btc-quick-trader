# Polymarket VPS Version

这个版本和原来的 Tk 桌面版分开维护：VPS 跑 FastAPI 后端，本地浏览器打开前端看数据、跑回测、管理加密凭证。VPS 版支持多用户，每个用户独立登录、独立密文凭证、独立策略任务。

## 安全模型

- 私钥、CLOB key、Server 酱、MiniMax key 在浏览器里用密码加密。
- VPS 磁盘只保存 `backend/data/users.json` 的密码哈希，以及 `backend/data/users/<username>/encrypted_vault.json` 密文。
- 点击“解锁”后，后端只把明文放在内存里；重启进程后需要重新解锁。
- 用户密码只保存 PBKDF2-SHA256 哈希，不保存明文。
- 生产使用建议通过 SSH tunnel、Tailscale 或 HTTPS 访问后端，不要裸奔公网端口。
- 当前 VPS 版真实下单接口默认有安全闸门，只允许 dry-run。确认 dry-run 长时间稳定后，再接入真实交易执行。

## VPS 部署

推荐正式部署路径：

- 程序目录：`/opt/polymarket-vps`
- 数据目录：`/var/lib/polymarket-vps`
- systemd 服务：`polymarket-vps`
- 运行用户：`polymm`

这个方案不依赖任何临时 sudo 用户的 home 目录。你可以用 `root` 登录，也可以用有 sudo 权限的普通用户登录；部署完成后，服务由系统用户 `polymm` 跑。

### 从本机一键部署到 VPS

```bash
cd vps_version
./deploy/deploy_remote.sh root@your-vps-ip
```

如果 SSH 端口不是 22：

```bash
./deploy/deploy_remote.sh ubuntu@your-vps-ip 2222
```

脚本会把当前 `vps_version` 打包上传到 VPS 的 `/tmp`，然后在 VPS 上安装到 `/opt/polymarket-vps`，数据落到 `/var/lib/polymarket-vps`。

### 在 VPS 上本地安装

```bash
cd /tmp/polymarket-vps-deploy
./deploy/install_vps.sh
```

安装脚本会：

- 创建或更新 `/opt/polymarket-vps`
- 创建 `/opt/polymarket-vps/.venv`
- 安装 `backend/requirements.txt`
- 创建系统用户 `polymm`
- 创建数据目录 `/var/lib/polymarket-vps`
- 写入并启动 systemd 服务

默认监听 `127.0.0.1:8787`。如果本地连 VPS，推荐 SSH 隧道：

```bash
ssh -L 8787:127.0.0.1:8787 user@your-vps
```

或者：

```bash
./deploy/ssh_tunnel.sh user@your-vps
```

然后本地浏览器打开：

```text
http://127.0.0.1:8787
```

## VPS 配置建议

小团队只看数据、跑回测、dry-run：

- 1 vCPU
- 1 GB RAM
- 10-20 GB SSD
- Ubuntu 22.04/24.04

多人长期在线、同时跑多个策略任务：

- 2 vCPU
- 2 GB RAM
- 20-40 GB SSD
- 建议加 1 GB swap

如果后面接真实下单并多人同时用，建议至少 2 vCPU / 2 GB RAM，并用 SSH tunnel、Tailscale 或 Nginx HTTPS，不建议直接开放裸 HTTP 端口。

## 运维命令

```bash
sudo systemctl status polymarket-vps
sudo journalctl -u polymarket-vps -f
sudo systemctl restart polymarket-vps
```

备份用户和加密凭证：

```bash
sudo tar -czf polymarket-vps-data-backup.tgz -C /var/lib polymarket-vps
```

## 本地开发运行

```bash
cd vps_version
./deploy/run_backend.sh
```

## API 快速检查

```bash
curl http://127.0.0.1:8787/api/health
curl -X POST http://127.0.0.1:8787/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"change-this-password"}'
curl -X POST http://127.0.0.1:8787/api/strategy/capital \
  -H 'Content-Type: application/json' \
  -d '{"initial_usdc":5,"max_layers":3,"entry_price":0.5,"fee_rate":0.07}'
```

## 目录

- `backend/`: FastAPI 后端、策略逻辑、加密 vault。
- `frontend/`: 静态前端，可由后端直接服务。
- `deploy/`: 本地运行和 VPS systemd 部署脚本。
- `tests/`: 逻辑测试。
