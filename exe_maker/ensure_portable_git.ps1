[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$GitVersion = "2.56.0"
$GitTag = "v2.56.0.windows.1"
$ArchiveName = "MinGit-$GitVersion-64-bit.zip"
$DownloadUrl = "https://github.com/git-for-windows/git/releases/download/$GitTag/$ArchiveName"
$ExpectedSha256 = "064b440ff870ed5198527e8f3a92cdf5bd2fd0fedf5e718af95e3fdaddeff718"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = [IO.Path]::GetFullPath((Join-Path $ScriptDir ".."))
$TargetDir = [IO.Path]::GetFullPath((Join-Path $Root "vendor\PortableGit"))
$GitExe = Join-Path $TargetDir "cmd\git.exe"
$BuildRoot = [IO.Path]::GetFullPath((Join-Path $ScriptDir "build"))
$DownloadDir = Join-Path $BuildRoot "downloads"
$ArchivePath = Join-Path $DownloadDir $ArchiveName
$StagingDir = Join-Path $BuildRoot "_portable_git_staging"

if (Test-Path -LiteralPath $GitExe -PathType Leaf) {
    $versionOutput = & $GitExe --version
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Using bundled MinGit: $versionOutput"
        exit 0
    }
}

New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null

if (Test-Path -LiteralPath $ArchivePath -PathType Leaf) {
    $actualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $ExpectedSha256) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
}

if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
    Write-Host "Downloading MinGit $GitVersion..."
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $ArchivePath -UseBasicParsing
}

$actualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $ExpectedSha256) {
    throw "MinGit checksum mismatch. Expected $ExpectedSha256, got $actualSha256."
}

$normalizedBuildRoot = $BuildRoot.TrimEnd('\') + '\'
$normalizedStagingDir = [IO.Path]::GetFullPath($StagingDir)
if (-not $normalizedStagingDir.StartsWith($normalizedBuildRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe MinGit staging path: $normalizedStagingDir"
}

if (Test-Path -LiteralPath $normalizedStagingDir) {
    Remove-Item -LiteralPath $normalizedStagingDir -Recurse -Force
}

try {
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $normalizedStagingDir -Force
    $stagedGitExe = Join-Path $normalizedStagingDir "cmd\git.exe"
    if (-not (Test-Path -LiteralPath $stagedGitExe -PathType Leaf)) {
        throw "Downloaded MinGit archive does not contain cmd\git.exe."
    }

    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    Get-ChildItem -LiteralPath $TargetDir -Force |
        Where-Object { $_.Name -ne "README.md" } |
        Remove-Item -Recurse -Force
    Copy-Item -Path (Join-Path $normalizedStagingDir "*") -Destination $TargetDir -Recurse -Force
} finally {
    if (Test-Path -LiteralPath $normalizedStagingDir) {
        Remove-Item -LiteralPath $normalizedStagingDir -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $GitExe -PathType Leaf)) {
    throw "MinGit provisioning failed: $GitExe was not created."
}

$versionOutput = & $GitExe --version
if ($LASTEXITCODE -ne 0) {
    throw "Bundled MinGit failed to start."
}
Write-Host "Prepared bundled MinGit: $versionOutput"
