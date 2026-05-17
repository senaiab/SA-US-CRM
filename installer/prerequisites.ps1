$ErrorActionPreference = "Stop"

function Get-DatabaseService {
    Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match "mysql|maria" -or $_.DisplayName -match "mysql|maria"
        } |
        Select-Object -First 1
}

function Test-WingetMariaDbInstalled {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (!$winget) {
        return $false
    }

    & winget list --id MariaDB.Server -e --accept-source-agreements | Out-String | ForEach-Object {
        return $_ -match "MariaDB\.Server"
    }
}

function Get-MariaDbBinaries {
    $paths = @(
        "$env:ProgramFiles\MariaDB*\bin\mysqld.exe",
        "${env:ProgramFiles(x86)}\MariaDB*\bin\mysqld.exe"
    )
    foreach ($path in $paths) {
        Get-ChildItem -Path $path -ErrorAction SilentlyContinue | Select-Object -First 1
    }
}

function Start-DatabaseService {
    $service = Get-DatabaseService
    if (!$service) {
        return $false
    }

    if ($service.State -ne "Running") {
        Start-Service -Name $service.Name -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
    }

    $service = Get-DatabaseService
    return $service -and $service.State -eq "Running"
}

Write-Host "SA-US ERP Database Prerequisite"
Write-Host "================================"
Write-Host ""

$existing = Get-DatabaseService
if ($existing) {
    Write-Host "Detected database service: $($existing.DisplayName) [$($existing.State)]"
    if (Start-DatabaseService) {
        Write-Host "Database service is running."
        exit 0
    }
    Write-Host "Database service exists but could not be started automatically."
    Write-Host "Open services.msc and start: $($existing.DisplayName)"
    exit 1
}

if (Test-WingetMariaDbInstalled) {
    Write-Host "MariaDB is already installed according to winget."
    $mysqld = Get-MariaDbBinaries
    if (!$mysqld) {
        Write-Host ""
        Write-Host "MariaDB is listed in winget but mysqld.exe was not found."
        Write-Host "Try reinstalling MariaDB from https://mariadb.org/download/"
        exit 1
    }

    Write-Host "MariaDB binaries found: $($mysqld.FullName)"
    Write-Host ""
    Write-Host "No Windows service detected — registering MariaDB service now..."

    # ── Elevation check ──────────────────────────────────────────────────────
    $isAdmin = ([Security.Principal.WindowsPrincipal]
                [Security.Principal.WindowsIdentity]::GetCurrent()
               ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    if (!$isAdmin) {
        Write-Host "Administrator rights required to register a Windows service."
        Write-Host "Relaunching as Administrator..."
        $scriptPath = $MyInvocation.MyCommand.Path
        Start-Process powershell.exe `
            -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" `
            -Verb RunAs
        exit 0
    }

    # ── Initialize data directory if missing ─────────────────────────────────
    $mysqldExe  = $mysqld.FullName
    $binDir     = Split-Path -Parent $mysqldExe
    $mariaRoot  = Split-Path -Parent $binDir
    $dataDir    = Join-Path $mariaRoot "data"

    if (!(Test-Path -LiteralPath (Join-Path $dataDir "mysql"))) {
        Write-Host "Data directory not initialized — running mysqld --initialize-insecure..."
        $initProc = Start-Process -FilePath $mysqldExe `
            -ArgumentList "--initialize-insecure", "--datadir=`"$dataDir`"" `
            -Wait -PassThru -NoNewWindow
        if ($initProc.ExitCode -ne 0) {
            Write-Host "WARNING: Data directory initialization returned exit code $($initProc.ExitCode)."
            Write-Host "         The service registration will still be attempted."
        } else {
            Write-Host "Data directory initialized."
        }
    }

    # ── Register the service ─────────────────────────────────────────────────
    Write-Host "Running: mysqld --install MariaDB"
    $installProc = Start-Process -FilePath $mysqldExe `
        -ArgumentList "--install", "MariaDB" `
        -Wait -PassThru -NoNewWindow

    if ($installProc.ExitCode -ne 0) {
        Write-Host ""
        Write-Host "Service registration failed (exit $($installProc.ExitCode))."
        Write-Host "Try running this script again as Administrator, or reinstall MariaDB."
        exit 1
    }

    Write-Host "Service 'MariaDB' registered successfully."
    Start-Sleep -Seconds 2

    # ── Start the newly registered service ───────────────────────────────────
    if (Start-DatabaseService) {
        Write-Host ""
        Write-Host "MariaDB service is running."
        Write-Host "Next: open SA-US ERP Configuration and initialize the database."
        exit 0
    }

    Write-Host ""
    Write-Host "Service registered but could not be started automatically."
    Write-Host "Open services.msc and start 'MariaDB' manually, then re-run this script."
    exit 1
}

$winget = Get-Command winget.exe -ErrorAction SilentlyContinue
if (!$winget) {
    Write-Host "winget is not available on this PC."
    Write-Host "Install MariaDB Server manually from https://mariadb.org/download/"
    exit 1
}

Write-Host "MariaDB/MySQL was not found."
Write-Host "Installing MariaDB Server with winget..."
Write-Host "This may show a Windows administrator prompt and requires internet access."
Write-Host ""

& winget install --id MariaDB.Server -e --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0 -and !(Test-WingetMariaDbInstalled)) {
    Write-Host ""
    Write-Host "MariaDB installation failed or was cancelled."
    exit $LASTEXITCODE
}

if (Start-DatabaseService) {
    Write-Host ""
    Write-Host "MariaDB installed and service is running."
    Write-Host "Next: open SA-US ERP Configuration and initialize the database."
    exit 0
}

Write-Host ""
Write-Host "MariaDB installed, but the service was not detected as running."
Write-Host "Restart this PC or open services.msc and start the MariaDB service."
exit 1
