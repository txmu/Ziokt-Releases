#!/bin/sh
# Explicit source trust: TLS to the selected repository and SHA-256 verification.
set -eu
repo=${ZIOKT_RELEASE_REPOSITORY:-txmu/Ziokt-Releases}
case "$repo" in *[!A-Za-z0-9_./-]*|/*|*..*) echo 'Invalid release repository' >&2; exit 2;; esac
work=$(mktemp -d);trap 'rm -rf "$work"' EXIT HUP INT TERM
proxy=${ZIOKT_DOWNLOAD_PROXY:-}
if [ -n "$proxy" ]; then
  curl --fail --location --proto '=https' --proto-redir '=https' --proxy "$proxy" "https://github.com/$repo/releases/download/bootstrap/deploy.py" -o "$work/deploy.py"
  curl --fail --location --proto '=https' --proto-redir '=https' --proxy "$proxy" "https://github.com/$repo/releases/download/bootstrap/deploy.py.sha256" -o "$work/deploy.py.sha256"
else
  curl --fail --location --proto '=https' --proto-redir '=https' "https://github.com/$repo/releases/download/bootstrap/deploy.py" -o "$work/deploy.py"
  curl --fail --location --proto '=https' --proto-redir '=https' "https://github.com/$repo/releases/download/bootstrap/deploy.py.sha256" -o "$work/deploy.py.sha256"
fi
python3 - "$work" <<'PY'
import hashlib,pathlib,sys
root=pathlib.Path(sys.argv[1]);expected=(root/'deploy.py.sha256').read_text().split()[0]
if hashlib.sha256((root/'deploy.py').read_bytes()).hexdigest()!=expected:raise SystemExit('Installer checksum mismatch')
PY
python3 "$work/deploy.py" "$@"
