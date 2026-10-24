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
curl -fsSL https://raw.githubusercontent.com/txmu/Ziokt-Releases/main/install.sh | sh -s -- preflight
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
- Python runtime version (`>= 3.10`)
- Operating system platform (`linux`, `darwin`, `win32`)
- Host CPU architecture (`x86_64`, `amd64`, `aarch64`, `arm64`)
- Target installation root directory writability and non-symlink safety
- Platform service persistence backend (`systemd`, `launchd`, `schtasks`)
- Release repository authority (`txmu/Ziokt-Releases`)

## 📦 来源与保障 / Sources & Assurance

Sources: **Ziokt**, **Corium**, and **Shadow6** (all owned by `txmu`).
Publication does not add browser-store signing, notarization, independent hardware verification or mainnet governance approval. Failed workflows remain explicitly identified; an uploaded binary is never labelled full business acceptance merely because an artifact exists. Development installers retain their original signing state.

The collector examines trusted owner push/manual/scheduled/release events and never publishes artifacts from fork pull requests. It performs no compilation. Older immutable build releases are kept permanently.
