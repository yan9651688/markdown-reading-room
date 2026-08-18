[CmdletBinding()]
param(
    [string]$OutputDirectory = "",
    [switch]$SkipNpmInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$package = Get-Content -LiteralPath (Join-Path $repoRoot "package.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$version = [string]$package.version

if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repoRoot "dist\windows"
} elseif (-not [IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $repoRoot $OutputDirectory
}
$outputPath = (New-Item -ItemType Directory -Force -Path $OutputDirectory).FullName

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction Stop
}
$cargoCommand = Get-Command cargo.exe -ErrorAction SilentlyContinue
if (-not $cargoCommand) {
    $cargoCommand = Get-Command cargo -ErrorAction Stop
}
$cargoExecutable = $cargoCommand.Source

$cargoHomePath = if ($env:CARGO_HOME) {
    $env:CARGO_HOME
} else {
    Split-Path -Parent (Split-Path -Parent $cargoExecutable)
}
$rustupHomePath = if ($env:RUSTUP_HOME) {
    $env:RUSTUP_HOME
} else {
    Join-Path (Split-Path -Parent $cargoHomePath) ".rustup"
}

$programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
$vswherePath = Join-Path $programFilesX86 "Microsoft Visual Studio\Installer\vswhere.exe"
$vsInstallPath = $null
if (Test-Path -LiteralPath $vswherePath) {
    $vsInstallPath = & $vswherePath -latest -products "*" -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1
}
if (-not $vsInstallPath) {
    $fallbackVsPath = Join-Path $programFilesX86 "Microsoft Visual Studio\2022\BuildTools"
    if (Test-Path -LiteralPath $fallbackVsPath) {
        $vsInstallPath = $fallbackVsPath
    }
}
if (-not $vsInstallPath) {
    throw "Visual Studio 2022 C++ Build Tools not found. Install the Desktop development with C++ workload."
}

$devShellPath = Join-Path $vsInstallPath "Common7\Tools\Launch-VsDevShell.ps1"
if (-not (Test-Path -LiteralPath $devShellPath)) {
    throw "Visual Studio developer shell not found: $devShellPath"
}
& $devShellPath -Arch amd64 -HostArch amd64

function Add-ProcessPath {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Entries
    )

    $existing = [Environment]::GetEnvironmentVariable($Name, "Process")
    $validEntries = $Entries | Where-Object { Test-Path -LiteralPath $_ }
    $combined = @($validEntries)
    if ($existing) {
        $combined += $existing
    }
    [Environment]::SetEnvironmentVariable($Name, ($combined -join ";"), "Process")
}

# Some Build Tools installations contain a valid Windows SDK but do not expose
# it through Launch-VsDevShell. Discover the newest usable SDK explicitly.
$sdkRoot = Join-Path $programFilesX86 "Windows Kits\10"
$sdkVersionDirectory = Get-ChildItem -LiteralPath (Join-Path $sdkRoot "Lib") -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "um\x64\kernel32.lib") } |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if (-not $sdkVersionDirectory) {
    throw "A usable Windows 10/11 SDK was not found (x64 kernel32.lib is missing)."
}

$sdkVersion = $sdkVersionDirectory.Name
Add-ProcessPath -Name "LIB" -Entries @(
    (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x64"),
    (Join-Path $sdkRoot "Lib\$sdkVersion\um\x64")
)
Add-ProcessPath -Name "INCLUDE" -Entries @(
    (Join-Path $sdkRoot "Include\$sdkVersion\ucrt"),
    (Join-Path $sdkRoot "Include\$sdkVersion\shared"),
    (Join-Path $sdkRoot "Include\$sdkVersion\um"),
    (Join-Path $sdkRoot "Include\$sdkVersion\winrt"),
    (Join-Path $sdkRoot "Include\$sdkVersion\cppwinrt")
)
Add-ProcessPath -Name "PATH" -Entries @(
    (Split-Path -Parent $cargoExecutable),
    (Join-Path $sdkRoot "bin\$sdkVersion\x64")
)
$env:WindowsSdkDir = "$sdkRoot\"
$env:WindowsSDKVersion = "$sdkVersion\"

# MSVC's linker can misread a Unicode user-profile temp path. A stable ASCII
# temp directory keeps builds working for Windows accounts with Chinese names.
$publicRoot = Split-Path -Parent ([Environment]::GetFolderPath("CommonDocuments"))
if (-not $publicRoot) {
    $publicRoot = Join-Path $env:SystemDrive "Users\Public"
}
$buildTempPath = Join-Path $publicRoot "MoyueBuildTemp"
New-Item -ItemType Directory -Force -Path $buildTempPath | Out-Null
$localAppDataPath = Join-Path $buildTempPath "LocalAppData"
$roamingAppDataPath = Join-Path $buildTempPath "RoamingAppData"
New-Item -ItemType Directory -Force -Path $localAppDataPath | Out-Null
New-Item -ItemType Directory -Force -Path $roamingAppDataPath | Out-Null
$env:TEMP = $buildTempPath
$env:TMP = $buildTempPath
$env:LOCALAPPDATA = $localAppDataPath
$env:APPDATA = $roamingAppDataPath
$env:npm_config_cache = Join-Path $buildTempPath "npm-cache"
$env:CARGO_HOME = $cargoHomePath
$env:RUSTUP_HOME = $rustupHomePath

Push-Location $repoRoot
try {
    if (-not $SkipNpmInstall) {
        & $npmCommand.Source ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed."
        }
    }

    & $cargoExecutable fmt --manifest-path "src-tauri\Cargo.toml" -- --check
    if ($LASTEXITCODE -ne 0) {
        throw "Rust formatting check failed."
    }

    & $npmCommand.Source run desktop:build
    if ($LASTEXITCODE -ne 0) {
        throw "Tauri Windows build failed."
    }
} finally {
    Pop-Location
}

$targetRoot = Join-Path $repoRoot "src-tauri\target\release"
$installer = Get-ChildItem -LiteralPath (Join-Path $targetRoot "bundle\nsis") -Filter "*.exe" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$desktopExecutable = Join-Path $targetRoot "Moyue.exe"
if (-not $installer) {
    throw "The build completed but no NSIS installer was found."
}
if (-not (Test-Path -LiteralPath $desktopExecutable)) {
    throw "The build completed but the desktop executable was not found: $desktopExecutable"
}

$setupPath = Join-Path $outputPath "Moyue-Setup.exe"
$portablePath = Join-Path $outputPath "Moyue.exe"
$portableZipPath = Join-Path $outputPath "Moyue-Portable.zip"
Copy-Item -LiteralPath $installer.FullName -Destination $setupPath -Force
Copy-Item -LiteralPath $desktopExecutable -Destination $portablePath -Force
Compress-Archive -LiteralPath $portablePath -DestinationPath $portableZipPath -CompressionLevel Optimal -Force

$artifactPaths = @($setupPath, $portableZipPath, $portablePath)
$artifacts = foreach ($artifactPath in $artifactPaths) {
    $file = Get-Item -LiteralPath $artifactPath
    [ordered]@{
        name = $file.Name
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifestPath = Join-Path $outputPath "release-manifest.json"
[ordered]@{
    product = "Moyue Markdown Reading Room"
    version = $version
    platform = "windows-x86_64"
    unsigned = $true
    artifacts = $artifacts
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host ""
Write-Host "Windows release artifacts generated:"
Write-Host "  Installer: $setupPath"
Write-Host "  Portable:  $portableZipPath"
Write-Host "  Manifest:  $manifestPath"
