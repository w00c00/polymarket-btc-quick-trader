# Polymarket VPS Version

这个版本和原来的 Tk 桌面版分开维护：VPS 跑 FastAPI 后端，本地浏览器打开前端看数据、跑回测、管理加密凭证。

## 安全模型

- 私钥、CLOB key、Server 酱、MiniMax key 在浏览器里用密码加密。
- VPS 磁盘只保存 `backend/data/encrypted_vault.json` 密文。
- 点击“解锁”后，后端只把明文放在内存里；重启进程后需要重新解锁。
- 生产使用建议通过 SSH tunnel、Tailscale 或 HTTPS 访问后端，不要裸奔公网端口。
- 当前 VPS 版真实下单接口默认有安全闸门，只允许 dry-run。确认 dry-run 长时间稳定后，再接入真实交易执行。

## VPS 部署

```bash
cd ~/polymarket-btc-quick-trader/vps_version
./deploy/install_vps.sh
```

安装脚本会：

- 创建 `.venv`
- 安装 `backend/requirements.txt`
- 生成 systemd service 模板到 `deploy/polymarket-vps.service.generated`

按你的路径检查 service 后：

```bash
sudo cp deploy/polymarket-vps.service.generated /etc/systemd/system/polymarket-vps.service
sudo systemctl daemon-reload
sudo systemctl enable --now polymarket-vps
sudo systemctl status polymarket-vps
```

默认监听 `127.0.0.1:8787`。如果本地连 VPS，推荐 SSH 隧道：

```bash
ssh -L 8787:127.0.0.1:8787 user@your-vps
```

然后本地浏览器打开：

```text
http://127.0.0.1:8787
```

## 本地开发运行

```bash
cd vps_version
./deploy/run_backend.sh
```

## API 快速检查

```bash
curl http://127.0.0.1:8787/api/health
curl -X POST http://127.0.0.1:8787/api/strategy/capital \
  -H 'Content-Type: application/json' \
  -d '{"initial_usdc":5,"max_layers":3,"entry_price":0.5,"fee_rate":0.07}'
```

## 目录

- `backend/`: FastAPI 后端、策略逻辑、加密 vault。
- `frontend/`: 静态前端，可由后端直接服务。
- `deploy/`: 本地运行和 VPS systemd 部署脚本。
- `tests/`: 逻辑测试。
