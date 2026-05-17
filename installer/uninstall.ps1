param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\SA-US ERP",
    [switch]$KeepConfig,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

function Remove-IfExists {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Confirm-Uninstall {
    if ($Quiet) {
        return
    }

    Add-Type -AssemblyName System.Windows.Forms
    $message = "Remove SA-US ERP from this user account?`n`nChoose Yes to uninstall.`nChoose No to cancel."
    $result = [System.Windows.Forms.MessageBox]::Show(
        $message,
        "SA-US ERP Uninstaller",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    if ($result -ne [System.Windows.Forms.DialogResult]::Yes) {
        throw "Uninstall cancelled."
    }
}

function Ask-KeepConfig {
    if ($Quiet) {
        return $KeepConfig
    }

    Add-Type -AssemblyName System.Windows.Forms
    $message = "Keep configuration files such as server_config.ini, client_config.ini, tenant_branding.json, and company logo?`n`nChoose Yes to keep them.`nChoose No to remove everything."
    $result = [System.Windows.Forms.MessageBox]::Show(
        $message,
        "SA-US ERP Uninstaller",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    return $result -eq [System.Windows.Forms.DialogResult]::Yes
}

try {
    Confirm-Uninstall
    $preserveConfig = Ask-KeepConfig

    Get-Process | Where-Object { $_.ProcessName -like "SA_US_ERP*" } | Stop-Process -Force -ErrorAction SilentlyContinue

    $startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\SA-US ERP"
    $desktopDir = [Environment]::GetFolderPath("Desktop")

    Remove-IfExists -Path $startMenuDir
    Remove-IfExists -Path (Join-Path $desktopDir "SA-US ERP Client.lnk")
    Remove-IfExists -Path (Join-Path $desktopDir "SA-US ERP Configuration.lnk")
    Remove-IfExists -Path (Join-Path $desktopDir "SA-US ERP Server Console.lnk")

    if ($preserveConfig -and (Test-Path -LiteralPath $InstallDir)) {
        $backupDir = Join-Path $env:LOCALAPPDATA ("SA-US ERP Config Backup " + (Get-Date -Format "yyyyMMdd-HHmmss"))
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

        $configFiles = @(
            "server\server_config.ini",
            "client\client_config.ini",
            "client\tenant_branding.json",
            "client\company_logo.png"
        )
        foreach ($relative in $configFiles) {
            $source = Join-Path $InstallDir $relative
            if (Test-Path -LiteralPath $source) {
                $target = Join-Path $backupDir $relative
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
                Copy-Item -LiteralPath $source -Destination $target -Force
            }
        }
    }

    if (Test-Path -LiteralPath $InstallDir) {
        $cleanupScript = @"
Start-Sleep -Seconds 3
Remove-Item -LiteralPath '$($InstallDir.Replace("'", "''"))' -Recurse -Force -ErrorAction SilentlyContinue
"@
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command", $cleanupScript
        ) -WindowStyle Hidden | Out-Null
    }

    $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SA-US ERP"
    Remove-IfExists -Path $uninstallKey

    if (!$Quiet) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "SA-US ERP was uninstalled successfully.",
            "SA-US ERP Uninstaller",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }
}
catch {
    if (!$Quiet) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            $_.Exception.Message,
            "SA-US ERP Uninstaller",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
    exit 1
}
