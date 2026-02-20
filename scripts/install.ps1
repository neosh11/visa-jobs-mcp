param(
  [string]$Version = $env:VISA_JOBS_MCP_VERSION,
  [string]$InstallRoot = $env:VISA_JOBS_MCP_INSTALL_ROOT,
  [string]$Repo = $(if ($env:VISA_JOBS_MCP_REPO) { $env:VISA_JOBS_MCP_REPO } else { "neosh11/visa-jobs-mcp" })
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-not [Environment]::Is64BitProcess) {
  throw "visa-jobs-mcp requires 64-bit Windows."
}

function Get-LatestVersion {
  param([string]$RepoName)
  $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$RepoName/releases/latest" -ErrorAction Stop
  if (-not $release.tag_name) {
    throw "Unable to resolve latest release tag for $RepoName"
  }
  return $release.tag_name.TrimStart("v")
}

function Resolve-Version {
  param([string]$RequestedVersion)
  if (-not $RequestedVersion -or $RequestedVersion -eq "latest" -or $RequestedVersion -eq "stable") {
    return Get-LatestVersion -RepoName $Repo
  }
  return $RequestedVersion.TrimStart("v")
}

function Resolve-Platform {
  $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
  switch ($arch.ToString()) {
    "X64" { return "windows-x86_64" }
    "Arm64" { return "windows-arm64" }
    default { throw "Unsupported Windows architecture: $arch" }
  }
}

function Parse-ChecksumFile {
  param([string]$ChecksumPath)
  $content = Get-Content -Path $ChecksumPath -Raw
  if ($content -match "([a-fA-F0-9]{64})") {
    return $matches[1].ToLowerInvariant()
  }
  throw "Invalid checksum file format: $ChecksumPath"
}

function Ensure-AssetWithChecksum {
  param(
    [string]$AssetName,
    [string]$BaseUrl,
    [string]$TmpDirPath
  )
  $archivePath = Join-Path $TmpDirPath $AssetName
  $checksumPath = "$archivePath.sha256"
  $assetUrl = "$BaseUrl/$AssetName"
  $checksumUrl = "$assetUrl.sha256"

  Invoke-WebRequest -Uri $assetUrl -OutFile $archivePath -UseBasicParsing -ErrorAction Stop
  Invoke-WebRequest -Uri $checksumUrl -OutFile $checksumPath -UseBasicParsing -ErrorAction Stop

  $expectedChecksum = Parse-ChecksumFile -ChecksumPath $checksumPath
  $actualChecksum = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actualChecksum -ne $expectedChecksum) {
    throw "Checksum verification failed for $AssetName"
  }

  return $archivePath
}

$Version = Resolve-Version -RequestedVersion $Version
if (-not ($Version -match '^\d+\.\d+\.\d+([-.][A-Za-z0-9._-]+)?$')) {
  throw "Invalid version: $Version"
}

if (-not $InstallRoot) {
  $InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\\visa-jobs-mcp"
}

$platform = Resolve-Platform
$baseUrl = "https://github.com/$Repo/releases/download/v$Version"
$zipAsset = "visa-jobs-mcp-v$Version-$platform.zip"
$tarAsset = "visa-jobs-mcp-v$Version-$platform.tar.gz"

$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("visa-jobs-mcp-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

try {
  $archivePath = $null
  $assetName = $zipAsset
  try {
    $archivePath = Ensure-AssetWithChecksum -AssetName $zipAsset -BaseUrl $baseUrl -TmpDirPath $tmpDir
  }
  catch {
    $assetName = $tarAsset
    $archivePath = Ensure-AssetWithChecksum -AssetName $tarAsset -BaseUrl $baseUrl -TmpDirPath $tmpDir
  }

  if ($assetName.EndsWith(".zip")) {
    Expand-Archive -Path $archivePath -DestinationPath $tmpDir -Force
  }
  else {
    tar -xzf $archivePath -C $tmpDir
  }

  $packageRoot = $tmpDir
  if ((-not (Test-Path (Join-Path $packageRoot "visa-jobs-mcp.exe"))) -and (Test-Path (Join-Path $packageRoot "visa-jobs-mcp\\visa-jobs-mcp.exe"))) {
    $packageRoot = Join-Path $packageRoot "visa-jobs-mcp"
  }

  $binarySource = Join-Path $packageRoot "visa-jobs-mcp.exe"
  $datasetSource = Join-Path $packageRoot "data\\companies.csv"
  if (-not (Test-Path $binarySource)) {
    throw "Archive missing visa-jobs-mcp.exe"
  }
  if (-not (Test-Path $datasetSource)) {
    throw "Archive missing data/companies.csv"
  }

  $binDir = Join-Path $InstallRoot "bin"
  $shareDir = Join-Path $InstallRoot "share\\visa-jobs-mcp\\data"
  New-Item -ItemType Directory -Force -Path $binDir | Out-Null
  New-Item -ItemType Directory -Force -Path $shareDir | Out-Null

  Copy-Item -Path $binarySource -Destination (Join-Path $binDir "visa-jobs-mcp.exe") -Force
  Copy-Item -Path $datasetSource -Destination (Join-Path $shareDir "companies.csv") -Force

  $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $pathEntries = @()
  if ($currentPath) {
    $pathEntries = $currentPath.Split(";", [System.StringSplitOptions]::RemoveEmptyEntries)
  }
  if (-not ($pathEntries | Where-Object { $_.TrimEnd("\") -ieq $binDir.TrimEnd("\") })) {
    $newPath = @($pathEntries + $binDir) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
  }

  Write-Host ""
  Write-Host "Installed visa-jobs-mcp $Version"
  Write-Host "Binary: $(Join-Path $binDir 'visa-jobs-mcp.exe')"
  Write-Host "Dataset: $(Join-Path $shareDir 'companies.csv')"
  Write-Host ""
  Write-Host "Open a new PowerShell window, then register in Codex:"
  Write-Host "  codex mcp add visa-jobs-mcp --env VISA_JOB_SITES=linkedin -- $(Join-Path $binDir 'visa-jobs-mcp.exe')"
}
finally {
  if (Test-Path $tmpDir) {
    Remove-Item -Path $tmpDir -Recurse -Force
  }
}
