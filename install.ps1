param([Parameter(ValueFromRemainingArguments=$true)][string[]]$InstallerArguments)
$ErrorActionPreference = 'Stop'
$repository = if ($env:ZIOKT_RELEASE_REPOSITORY) {$env:ZIOKT_RELEASE_REPOSITORY} else {'txmu/Ziokt-Releases'}
if ($repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {throw 'Invalid release repository'}
$work = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
[IO.Directory]::CreateDirectory($work) | Out-Null
try {
  $options = @{}
  if ($env:ZIOKT_DOWNLOAD_PROXY) {$options.Proxy = $env:ZIOKT_DOWNLOAD_PROXY}
  $scriptPath = Join-Path $work 'deploy.py'
  Invoke-WebRequest @options -Uri "https://github.com/$repository/releases/download/bootstrap/deploy.py" -OutFile $scriptPath
  $checksum = Invoke-WebRequest @options -Uri "https://github.com/$repository/releases/download/bootstrap/deploy.py.sha256"
  $expected = ($checksum.Content -split '\s+')[0]
  if ((Get-FileHash $scriptPath -Algorithm SHA256).Hash.ToLower() -ne $expected) {throw 'Installer checksum mismatch'}
  & python $scriptPath @InstallerArguments
  if ($LASTEXITCODE -ne 0) {throw "Installer failed: $LASTEXITCODE"}
} finally {Remove-Item -LiteralPath $work -Recurse -Force}
