# v1.0 外部 VPS 建节点

完整原生节点使用 GNU/Linux；推荐 Ubuntu 24.04、至少 2 核/2 GiB、10 GiB 可用磁盘。
全过程安装 CI 产物，不在 VPS 编译原生组件。

先安装运行依赖（root 执行，普通用户加 sudo）：

```sh
apt-get update
apt-get install -y python3 python3-venv ca-certificates curl bash sqlite3 bc xxd jq rsync iproute2 procps lsof unzip git tar openssl gpg socat ripgrep
```

一条命令建立独立验收节点，完成校验下载、私有 Python 运行环境、独立密钥、创世、
Gateway/ZDNS/MCP/OpenCI/奋斗与 systemd 服务：

```sh
curl --proto '=https' --tlsv1.2 -fsSL https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.sh | sudo sh -s -- --root /opt/ziokt-node bootstrap --install --runtime --yes --enable-services --connectivity public --network ziokt-acceptance --service-prefix ziokt-acceptance
```

可在 `bootstrap` 后加 `--catalog-sha256 <v1.0 发布证据中的 catalog SHA256>` 固定目录。
默认 P2P 7234、Gateway 8185、MCP 8186、OpenCI 8768、奋斗 8081、DNS 5353、DoH 8188。
应用和管理端默认回环监听；外部访问应配置自己的 HTTPS 反向代理与访问权限。
不要把管理端 token 暴露到公网。按实际 P2P TCP/UDP 监听配置云安全组与防火墙，
再从另一台节点实测入站；公网出口探测不等于已具备入站能力。

这条命令创建的是独立 `ziokt-acceptance` 网络。接入已有网络必须使用其公开创世与
种子公开 TLS 证书，并从独立可信渠道核对 SHA256；每个节点保持自己的私钥。
在全新的根目录使用下面的参数，替换公开材料路径和端点：

```sh
curl --proto '=https' --tlsv1.2 -fsSL https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.sh | sudo sh -s -- \
  --root /opt/ziokt-main-node bootstrap --install --runtime --yes --enable-services \
  --network "$NETWORK" --public-ip "$THIS_NODE_IP" --service-prefix ziokt-main-node \
  --seed-peer "$SEED_HOST:$SEED_PORT" --gateway-peer "$SEED_GATEWAY" \
  --genesis "$PUBLIC_GENESIS_FILE" --genesis-sha256 "$GENESIS_SHA256" \
  --seed-certificate "$PUBLIC_SEED_CERT_FILE" --seed-certificate-sha256 "$SEED_CERT_SHA256"
```

没有公网 IP 时用 `--connectivity outbound`，省略 `--public-ip`。不会自动开启 UPnP、
填写公共 STUN、中继或绕过匿名载体。匿名组网必须显式配置经审查的载体；载体失败
不能降级直连。

查看实际服务和节点状态：

```sh
systemctl --no-pager status ziokt-acceptance-corium-p2p ziokt-acceptance-gateway ziokt-acceptance-mcp ziokt-acceptance-openci ziokt-acceptance-effort
journalctl -u ziokt-acceptance-corium-p2p -n 80 --no-pager
curl -fsS http://127.0.0.1:8185/api/gateway/status
curl -fsS http://127.0.0.1:8081/api/people/config
curl -fsS http://127.0.0.1:8081/openci/v1/light/config
```

`/opt/ziokt-node/config` 保存 owner-only 配置与 token；`corium/bin` 包含原生入口、
历史验证与安全锁工具。保存自己的密钥备份，不复制种子身份。已存在配置不会覆盖。
更换网络/重试初始化应选全新根目录及不冲突的 `--service-prefix` 和端口。

启动后 `BOOTSTRAP_HISTORY_NOT_VERIFIED` 保持共识暂停，MCP 写入默认关闭。
必须独立核对链 ID、创世、连续区块、签名、共识策略及检查点，完成真实同步/历史
重放后再由节点所有者按该网络治理批准启用。删除锁文件、只改 active=false 或
复制其他节点的旧恢复声明不构成历史验收。

多节点验收应记录每个身份和相同创世，进行真实双向通信、种子停机后的存活节点
互通、重启保持身份、竞争分叉拒绝/接纳、检查点边界及冷恢复。CI 的三个独立根目录
测试不代替多台 VPS 的独立物理故障域与运营商条件。
