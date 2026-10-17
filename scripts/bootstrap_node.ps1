param([switch]$Connected)
$ErrorActionPreference = 'Stop'
if (-not $Connected) { throw 'Connected setup requires -Connected. Runtime does not download dependencies.' }
$inspectorRoot = Split-Path -Parent $PSScriptRoot
$inspectorNodeLock = Get-Content -LiteralPath (Join-Path $inspectorRoot 'verification/stage-1/node-toolchain.json') -Raw | ConvertFrom-Json
$inspectorBootstrap = Join-Path $inspectorRoot '.bootstrap'
$inspectorToolchains = Join-Path $inspectorRoot '.toolchains'
New-Item -ItemType Directory -Force -Path $inspectorBootstrap, $inspectorToolchains | Out-Null
$inspectorNodeArchive = Join-Path $inspectorBootstrap ('node-v' + $inspectorNodeLock.version + '-win-x64.zip')
$inspectorNodeClient = New-Object System.Net.WebClient
$inspectorNodeClient.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
$inspectorNodeClient.DownloadFile($inspectorNodeLock.source, $inspectorNodeArchive)
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $inspectorNodeArchive).Hash.ToLowerInvariant() -ne $inspectorNodeLock.sha256) { throw 'Official Node archive checksum differs from the recorded release.' }
Expand-Archive -LiteralPath $inspectorNodeArchive -DestinationPath $inspectorToolchains -Force
Write-Output ('Installed repository-local Node ' + $inspectorNodeLock.version)
