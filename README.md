# Ziokt ecosystem Releases

Download the ecosystem and all platform software directly from [GitHub Releases](https://github.com/txmu/Ziokt-Releases/releases).

All installers and client packages are hosted on the `txmu/Ziokt-Releases` GitHub repository rather than local staging servers. `catalog.json` in the `catalog` release links to immutable build releases and records source repository, commit, actual CI run, artifact SHA-256 and file list.

## 🚀 各平台软件下载 / Platform Downloads

| Platform | Architecture | Installer / Package Link | Verification |
| :--- | :--- | :--- | :--- |
| **Linux** | `x86_64`, `aarch64` | [Linux Releases](https://github.com/txmu/Ziokt-Releases/releases) | SHA-256 pinned in catalog |
| **macOS** | Apple Silicon (`arm64`), Intel (`x86_64`) | [macOS Releases](https://github.com/txmu/Ziokt-Releases/releases) | SHA-256 pinned in catalog |
| **Windows** | `x64` | [Windows Releases](https://github.com/txmu/Ziokt-Releases/releases) | SHA-256 pinned in catalog |
| **Android** | Universal APK | [Android Releases](https://github.com/txmu/Ziokt-Releases/releases) | SHA-256 pinned in catalog |
| **Extensions** | Chromium, Firefox, Thunderbird | [WebExtensions Releases](https://github.com/txmu/Ziokt-Releases/releases) | Manifest digest |

### 一键安装与部署预检 / Quick Install & Preflight

#### Linux / macOS:
```bash
# 预检环境
curl -fsSL https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.sh | sh -s -- preflight

# 配置新节点（端点显式指定；不会复制本机身份或自动放行共识）：
curl -fsSL https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.sh | sh -s -- bootstrap --seed-peer "$SEED_HOST:$SEED_PORT" --gateway-peer "$SEED_GATEWAY"

# 或生成独立节点配置（不配置远端种子）：
curl -fsSL https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.sh | sh -s -- bootstrap

# 或便携版客户端安装
curl -fsSL https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.sh | sh -s -- install --profile portable --yes
```

#### Windows (PowerShell):
```powershell
irm https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.ps1 | iex -ArgumentList "preflight"
irm https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.ps1 | iex -ArgumentList "install", "--profile", "portable", "--yes"
```

## 🔍 部署预检 / Deployment Preflight

`deploy.py` provides an explicit host and environmental preflight check before any download or service configuration:

```bash
python3 deploy.py preflight [--root /path/to/install]
```

Checks verified:
- Python runtime version (`>= 3.11`)
- Operating system platform (`linux`, `darwin`, `win32`)
- Host CPU architecture (`x86_64`, `amd64`, `aarch64`, `arm64`)
- Target installation root directory writability and non-symlink safety
- Platform service persistence backend (`systemd`, `launchd`, `schtasks`)
- Release repository authority (`txmu/Ziokt-Releases`)

## 📦 来源与保障 / Sources & Assurance

Sources: **Ziokt**, **Corium**, and **Shadow6** (all owned by `txmu`).
Publication does not add browser-store signing, notarization, independent hardware verification or mainnet governance approval. Failed workflows remain explicitly identified; an uploaded binary is never labelled full business acceptance merely because an artifact exists. Development installers retain their original signing state.

The collector examines trusted owner push/manual/scheduled/release events and never publishes artifacts from fork pull requests. It performs no compilation. Older immutable build releases are kept permanently.

`bootstrap` 保留新节点的共识安全锁，并默认关闭 MCP 写入。配置文件生成不代表原生初始化、可信链同步或共识已经就绪。启用服务前须先安装经全部 CI 检查通过的原生交付包并完成原生节点初始化与链身份核验；`--enable-services` 在未安装交付包时会明确失败。服务名前缀可由 `--service-prefix` 指定，既有配置和密钥不会被覆盖。不会内置本机验证者、生产历史授权签名或 H64 检查点。

Release 自动收集器只发布成功的 owner CI，并检查相同源码 revision 的全部工作流通过；已知失败产物不进入下载目录或安装计划。

### 独立原生节点与 CI 部署验收

Ubuntu 24.04 VPS 的完整依赖、单条 curl 安装并初始化/启动、接入已有网络、端口、
安全锁与验收步骤见 [VPS 建节点教程](VPS_BOOTSTRAP.zh-CN.md)。`bootstrap --install
--runtime --yes --enable-services` 会安装精确匹配的 green 原生与编译器包后执行初始化。

安装全部通过 CI 的 `--profile gateway` bundle 后，`bootstrap --enable-services` 从该 bundle 的 `corix-ziokt.sh` 初始化真实 Corium 状态、该节点自己的密钥、Gateway、节点 ZDNS、MCP 和 OpenCI。原生配置位于实际 `corium/etc/corix/networks/<network>/corix.conf`，不再写入原生运行时不会读取的位置。所有路径由 --root 派生；--service-prefix、P2P/Gateway/MCP/OpenCI/DNS/DoH 端口可显式配置，不复用生产机器的身份或服务权限。没有配置种子时不连接隐式种子。

接入已有网络须显式提供其公开创世文件和 SHA256；启用种子连接还须提供种子公开 TLS 证书和 SHA256。它们都不是验证者私钥，不能用复制远端身份的方式部署新节点：

```sh
python3 deploy.py --root "$NODE_ROOT" bootstrap \
  --network "$NETWORK" --public-ip "$THIS_NODE_IP" \
  --seed-peer "$SEED_HOST:$SEED_PORT" --gateway-peer "$SEED_GATEWAY_ORIGIN" \
  --genesis "$PUBLIC_GENESIS" --genesis-sha256 "$GENESIS_SHA256" \
  --seed-certificate "$PUBLIC_SEED_CERT" --seed-certificate-sha256 "$SEED_CERT_SHA256" \
  --service-prefix "$SERVICE_PREFIX" --enable-services
```

原生运行依赖须通过节点预检并由节点维护者安装；脚本不悄悄修改系统包、关闭 TLS 校验或代替节点批准链历史。初始化仅创建并验证实际创世状态，`BOOTSTRAP_HISTORY_NOT_VERIFIED` 保留共识暂停和写操作关闭，直到真实链同步、恢复声明与对应区块证明通过独立验收。种子只负责发现，不获得特权。

`Independent release deployment with own Gateway and ZDNS` 是手动 CI 验收流程：给出已经全部通过并发布的精确源码 revision 与 catalog SHA256，在空白 CI 主机上实际执行 deploy.py 的下载校验、安装、两个独立根目录初始化和 systemd 启动，以公开创世和明确证书 pin 建立真实原生 PING/PONG，检查两个身份不同且各自 Gateway/ZDNS/MCP/OpenCI 可用。证据不包含私钥或 token；同一 CI 主机不冒充两个物理故障域，也不宣称已经接受生产链的完整历史。

### VPS、家庭节点与平台边界

`bootstrap --connectivity outbound` 适用于没有公网 IP 的家庭节点：不调用公网 IP 探测服务、不把 NAT 出口误当本机可入站地址、不预填公共 STUN 服务、不自动启用 UPnP。自己的 Gateway/ZDNS/MCP/OpenCI 在本机提供相同能力，种子连接仍通过显式端点和证书 pin 发起。需要从外网访问家庭节点时，应由节点维护者选择端口映射、已配置的匿名载体或反向中继；脚本不会制造一个不存在的公网入口。公网 VPS 可显式设置 --public-ip，或使用 --connectivity public 请求出口探测；是否真的可入站仍须外部节点实测，配置成功不等于探测成功。

协调器、应用和 OpenCI 服务采用 Python 便携包，安装管理器支持 Linux/systemd、macOS/launchd 和 Windows/任务计划；Windows 与 Android 奋斗端有各自 CI。完整 Corium 原生脚本依赖 GNU/Linux 与其运行依赖，因此 Windows 完整原生节点应在 WSL2/Linux VM 中运行，macOS 使用 Linux VM；管理器会明确拒绝把未验证的原生运行方式冒充该操作系统的完整节点。轻量编译当前严格支持 x86_64/aarch64，设备必须匹配所连节点，其他架构不能伪装领取。更多架构只有在实际构建和运行验收后才进入可用矩阵。

gateway/openci 安装 profile 同时选择与原生协调器精确 revision 匹配、且全部通过 CI 的轻量 WASM 编译器 bundle，避免混装工具链。bootstrap 为每个节点配置自己的奋斗服务与本机 OpenCI 路径挂载；Windows/Android 和网页从所选节点读取 network_id 并绑定任务，不再把某个固定网络 ID 当作节点特权。公开下载地址可在奋斗配置的 downloads.android/windows 中显式指定；默认仅链接源码发布目录，不借用另一台生产机器的运行时接口。

### Verified independent deployment

The latest native catalogue entry is published only after CI and Lean checks pass for the exact locked Ziokt, Corium and Shadow6 revisions. Deployment verifies the complete native contract and every file digest before activation, including ziokt.pyz, openci.pyz, corix_v108.sh and the GIMPS runtime. Incomplete or unverified native entries cannot become the default native release. CI can finish after a source release; pending source revisions are not advertised as verified binary releases.

The native runtime also carries deploy_dna_sidechain.py. Independent DNA nodes can use --recovery-file with the public signed recovery declaration; they do not need the originating authority private key. DNA uses a separate data root and an explicitly trusted legacy checkpoint.

Native nodes use the P2P base port for DHT, base+1 for the embedded native API, base+1000 for the TLS API and base+2000 for file transfer. Bootstrap validates these against every application listener. Separate node roots and distinct base/application ports support several nodes on one host. The service wrapper monitors the detached native daemon and lets systemd restart it on failure.

### Optional Mail and Telegram on independent nodes

Bootstrap grants the local `ziokt-operator` the Mail scopes, keeps writes disabled, and creates no shared Internet mailbox credentials. Each node creates its own native Mail identity on first use. Configure only that node's `config/mcp.json` → `mail.clients.<authenticated-client>.internet` when actual accounts are available; account state is isolated per client and account. Follow the [Mail configuration guide](https://github.com/txmu/Ziokt/blob/main/docs/MAIL-BRIDGE-V1.0.md) for aliases, OAuth2, scanning, read-receipt policy and optional Internet gateway prerequisites.

A standalone background Mail worker needs no source checkout: `python /path/to/installed/ziokt.pyz mail --config /private/this-node-mail.json internet-sync`. Add `--once` for one bounded cycle. Run it as a supervised service with this node's own private config. MCP also starts configured Mail workers automatically. Never copy another node's identity, state database, tokens or Telegram bot credentials. Telegram needs the operator's explicitly configured bot/token and permitted chat mapping; unconfigured external services are reported as unconfigured.

The remote independent-deployment acceptance now checks three separately generated Mail identities alongside the existing Gateway, ZDNS, Content Fabric, native peer and compiler checks. Actual multi-host acceptance remains a separate deployment test; one-host CI does not certify separate failure domains.

The built-in browser OAuth client is provisioned with callback URLs derived from this node's Gateway port, read scopes and the explicitly enabled Mail write scope. No node-owner admin scope is granted to the browser. Existing OAuth sessions must request the new Mail scopes through the normal authorization flow; role configuration does not silently expand previously issued tokens.
