param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\SA-US ERP",
    [ValidateSet("", "server", "client", "both")]
    [string]$InstallMode = "",
    [switch]$SkipShortcuts,
    [switch]$SkipMaintenanceDialog,
    [switch]$UpdateMode
)

$ErrorActionPreference = "Stop"

function New-Shortcut {
    param(
        [Parameter(Mandatory = $true)][string]$ShortcutPath,
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [string]$WorkingDirectory,
        [string]$IconLocation
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    if ($WorkingDirectory) {
        $shortcut.WorkingDirectory = $WorkingDirectory
    }
    if ($IconLocation) {
        $shortcut.IconLocation = "$IconLocation,0"
    }
    $shortcut.Save()
}

function Copy-TreePreservingConfig {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    Get-ChildItem -LiteralPath $Source -Recurse -Force | ForEach-Object {
        $relativePath = $_.FullName.Substring($Source.Length).TrimStart("\")
        $target = Join-Path $Destination $relativePath

        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $target | Out-Null
            return
        }

        $configNames = @(
            "server_config.ini",
            "client_config.ini",
            "tenant_branding.json",
            "company_logo.png",
            "sa_us_erp.db"
        )

        if ((Test-Path -LiteralPath $target) -and ($configNames -contains $_.Name)) {
            return
        }

        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

function Select-InstallMode {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "SA-US ERP Setup"
    $form.Size = New-Object System.Drawing.Size(430, 260)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false

    $label = New-Object System.Windows.Forms.Label
    $label.Text = "Choose what to install on this machine:"
    $label.AutoSize = $true
    $label.Location = New-Object System.Drawing.Point(22, 22)
    $form.Controls.Add($label)

    $server = New-Object System.Windows.Forms.RadioButton
    $server.Text = "Server only - main office PC"
    $server.AutoSize = $true
    $server.Location = New-Object System.Drawing.Point(36, 58)
    $form.Controls.Add($server)

    $client = New-Object System.Windows.Forms.RadioButton
    $client.Text = "Client only - staff PC"
    $client.AutoSize = $true
    $client.Location = New-Object System.Drawing.Point(36, 90)
    $form.Controls.Add($client)

    $both = New-Object System.Windows.Forms.RadioButton
    $both.Text = "Both server and client"
    $both.AutoSize = $true
    $both.Checked = $true
    $both.Location = New-Object System.Drawing.Point(36, 122)
    $form.Controls.Add($both)

    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = "Install"
    $ok.Location = New-Object System.Drawing.Point(230, 172)
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $ok
    $form.Controls.Add($ok)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = "Cancel"
    $cancel.Location = New-Object System.Drawing.Point(315, 172)
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $cancel
    $form.Controls.Add($cancel)

    if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw "Installation cancelled."
    }
    if ($server.Checked) { return "server" }
    if ($client.Checked) { return "client" }
    return "both"
}

function Get-ExistingInstallDir {
    $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SA-US ERP"
    if (Test-Path -LiteralPath $uninstallKey) {
        $props = Get-ItemProperty -LiteralPath $uninstallKey -ErrorAction SilentlyContinue
        if ($props -and $props.InstallLocation -and (Test-Path -LiteralPath $props.InstallLocation)) {
            return $props.InstallLocation
        }
    }

    $defaultDir = "$env:LOCALAPPDATA\Programs\SA-US ERP"
    if (Test-Path -LiteralPath $defaultDir) {
        return $defaultDir
    }

    return $null
}

function Select-MaintenanceAction {
    param([Parameter(Mandatory = $true)][string]$ExistingDir)

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "SA-US ERP Setup"
    $form.Size = New-Object System.Drawing.Size(470, 245)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false

    $label = New-Object System.Windows.Forms.Label
    $label.Text = "SA-US ERP is already installed.`n`nInstalled location:`n$ExistingDir`n`nChoose what you want to do."
    $label.AutoSize = $true
    $label.Location = New-Object System.Drawing.Point(22, 18)
    $form.Controls.Add($label)

    $repair = New-Object System.Windows.Forms.Button
    $repair.Text = "Repair / Reinstall"
    $repair.Size = New-Object System.Drawing.Size(125, 34)
    $repair.Location = New-Object System.Drawing.Point(70, 155)
    $repair.Add_Click({
        $form.Tag = "repair"
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
    })
    $form.Controls.Add($repair)

    $remove = New-Object System.Windows.Forms.Button
    $remove.Text = "Remove"
    $remove.Size = New-Object System.Drawing.Size(95, 34)
    $remove.Location = New-Object System.Drawing.Point(210, 155)
    $remove.Add_Click({
        $form.Tag = "remove"
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
    })
    $form.Controls.Add($remove)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = "Cancel"
    $cancel.Size = New-Object System.Drawing.Size(95, 34)
    $cancel.Location = New-Object System.Drawing.Point(320, 155)
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $cancel
    $form.Controls.Add($cancel)

    if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw "Setup cancelled."
    }
    return [string]$form.Tag
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadZip = Join-Path $scriptDir "payload.zip"
$extractDir = Join-Path $env:TEMP ("SA-US-ERP-Installer-" + [guid]::NewGuid().ToString("N"))
$logDir = Join-Path $env:LOCALAPPDATA "SA-US ERP"
$logPath = Join-Path $logDir "install.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

try {
    "Starting SA-US ERP install: $(Get-Date -Format s)" | Out-File -FilePath $logPath -Encoding utf8
    "InstallDir=$InstallDir" | Out-File -FilePath $logPath -Append -Encoding utf8

    if (!(Test-Path -LiteralPath $payloadZip)) {
        throw "Installer payload not found: $payloadZip"
    }

    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
    Expand-Archive -LiteralPath $payloadZip -DestinationPath $extractDir -Force

    $payloadRoot = Join-Path $extractDir "payload"
    if (!(Test-Path -LiteralPath $payloadRoot)) {
        throw "Invalid installer payload."
    }

    $existingInstallDir = Get-ExistingInstallDir
    if ($existingInstallDir -and !$SkipShortcuts -and !$SkipMaintenanceDialog) {
        $maintenanceAction = Select-MaintenanceAction -ExistingDir $existingInstallDir
        if ($maintenanceAction -eq "remove") {
            $uninstallCmd = Join-Path $existingInstallDir "uninstall.cmd"
            if (!(Test-Path -LiteralPath $uninstallCmd)) {
                throw "Uninstaller was not found in the installed folder: $uninstallCmd"
            }
            Start-Process -FilePath $uninstallCmd -WorkingDirectory $existingInstallDir -Wait
            Write-Host "SA-US ERP remove action completed."
            exit 0
        }
        if ($maintenanceAction -eq "repair") {
            $InstallDir = $existingInstallDir
        }
    }

    if (!$InstallMode) {
        $InstallMode = Select-InstallMode
    }
    "InstallMode=$InstallMode" | Out-File -FilePath $logPath -Append -Encoding utf8

    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

    if ($UpdateMode) {
        Write-Host "Update mode: preserving database and configuration files."
        $dbPath = Join-Path $InstallDir "server\sa_us_erp.db"
        if (Test-Path -LiteralPath $dbPath) {
            $backupPath = $dbPath + ".bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
            Copy-Item -LiteralPath $dbPath -Destination $backupPath -Force
            Write-Host "Database backed up to: $backupPath"
        }
    }

    $readmeSrc = Join-Path $payloadRoot "README.txt"
    if (Test-Path -LiteralPath $readmeSrc) {
        Copy-Item -LiteralPath $readmeSrc -Destination (Join-Path $InstallDir "README.txt") -Force
    }
    $docsSrc = Join-Path $payloadRoot "docs"
    if (Test-Path -LiteralPath $docsSrc) {
        Copy-TreePreservingConfig -Source $docsSrc -Destination (Join-Path $InstallDir "docs")
    }
    $toolsSrc = Join-Path $payloadRoot "tools"
    if (Test-Path -LiteralPath $toolsSrc) {
        Copy-TreePreservingConfig -Source $toolsSrc -Destination $InstallDir
    }
    Copy-TreePreservingConfig -Source (Join-Path $payloadRoot "uninstall") -Destination $InstallDir
    if ($InstallMode -eq "server" -or $InstallMode -eq "both") {
        Copy-TreePreservingConfig -Source (Join-Path $payloadRoot "server") -Destination (Join-Path $InstallDir "server")
        Copy-TreePreservingConfig -Source (Join-Path $payloadRoot "sql") -Destination (Join-Path $InstallDir "sql")
    }
    if ($InstallMode -eq "client" -or $InstallMode -eq "both") {
        Copy-TreePreservingConfig -Source (Join-Path $payloadRoot "client") -Destination (Join-Path $InstallDir "client")
    }

    $serverExe = Join-Path $InstallDir "server\SA_US_ERP_Server.exe"
    $clientExe = Join-Path $InstallDir "client\SA_US_ERP_Client.exe"
    $clientIcon = Join-Path $InstallDir "client\branding\app_icon.ico"
    $serverConsoleCmd = Join-Path $InstallDir "SA-US ERP Server Console.cmd"

    # Remove stale shortcuts from older installs (config EXE that no longer exists)
    $desktopDir = [Environment]::GetFolderPath("Desktop")
    $startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\SA-US ERP"
    @(
        (Join-Path $desktopDir "SA-US ERP Configuration.lnk"),
        (Join-Path $startMenuDir "SA-US ERP Configuration.lnk")
    ) | ForEach-Object { if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force } }
    if ($InstallMode -eq "server" -or $InstallMode -eq "both") {
    @"
@echo off
cd /d "%~dp0server"
echo Starting SA-US ERP Server...
echo.
SA_US_ERP_Server.exe
echo.
echo Server stopped or failed. Read the message above.
pause
"@ | Set-Content -Path $serverConsoleCmd -Encoding ASCII
    }

    if (!$SkipShortcuts) {
        New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null

        if ($InstallMode -eq "server" -or $InstallMode -eq "both") {
            New-Shortcut `
                -ShortcutPath (Join-Path $startMenuDir "SA-US ERP Server Console.lnk") `
                -TargetPath $serverConsoleCmd `
                -WorkingDirectory $InstallDir

            New-Shortcut `
                -ShortcutPath (Join-Path $desktopDir "SA-US ERP Server Console.lnk") `
                -TargetPath $serverConsoleCmd `
                -WorkingDirectory $InstallDir
        }

        if ($InstallMode -eq "client" -or $InstallMode -eq "both") {
            New-Shortcut `
                -ShortcutPath (Join-Path $startMenuDir "SA-US ERP Client.lnk") `
                -TargetPath $clientExe `
                -WorkingDirectory (Join-Path $InstallDir "client") `
                -IconLocation $clientIcon

            New-Shortcut `
                -ShortcutPath (Join-Path $desktopDir "SA-US ERP Client.lnk") `
                -TargetPath $clientExe `
                -WorkingDirectory (Join-Path $InstallDir "client") `
                -IconLocation $clientIcon
        }

        New-Shortcut `
            -ShortcutPath (Join-Path $startMenuDir "Uninstall SA-US ERP.lnk") `
            -TargetPath (Join-Path $InstallDir "uninstall.cmd") `
            -WorkingDirectory $InstallDir `
            -IconLocation $clientIcon
    }

    $openServerCmd = Join-Path $InstallDir "Open Installed Folder.cmd"
    @"
@echo off
start "" "%InstallDir%"
"@.Replace("%InstallDir%", $InstallDir) | Set-Content -Path $openServerCmd -Encoding ASCII

    $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SA-US ERP"
    New-Item -Path $uninstallKey -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "DisplayName" -Value "SA-US ERP" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "DisplayVersion" -Value "2.8.4" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "Publisher" -Value "SA Ultimate Solutions" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "InstallLocation" -Value $InstallDir -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "UninstallString" -Value "`"$InstallDir\uninstall.cmd`"" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "QuietUninstallString" -Value "`"$InstallDir\uninstall.cmd`" -Quiet" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "NoModify" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "NoRepair" -Value 1 -PropertyType DWord -Force | Out-Null

    if ($InstallMode -eq "server" -or $InstallMode -eq "both") {
        # SQLite database is created automatically on first server startup — no setup needed.
        $serverConfigPath = Join-Path $InstallDir "server\server_config.ini"
        if (!(Test-Path -LiteralPath $serverConfigPath)) {
            $exampleConfig = Join-Path $InstallDir "server\server_config.example.ini"
            if (Test-Path -LiteralPath $exampleConfig) {
                Copy-Item -LiteralPath $exampleConfig -Destination $serverConfigPath
            } else {
@"
[database]
url = sqlite:///./sa_us_erp.db

[server]
host = 0.0.0.0
port = 8080
secret_key = CHANGE_THIS_TO_A_RANDOM_SECRET
cors_origins = http://127.0.0.1,http://localhost
"@ | Set-Content -Path $serverConfigPath -Encoding UTF8
            }
        }
        Write-Host "SQLite database will be created automatically when the server first starts."
    }

    "Installed successfully: $(Get-Date -Format s)" | Out-File -FilePath $logPath -Append -Encoding utf8

    Write-Host ""
    if ($UpdateMode) {
        Write-Host "SA-US ERP updated to v2.8.4 successfully."
    } else {
        Write-Host "SA-US ERP v2.8.4 installed successfully."
    }
    Write-Host "Installed mode: $InstallMode"
    Write-Host "Install folder: $InstallDir"
    Write-Host ""
    if (!$SkipShortcuts) {
        Write-Host "Shortcuts created:"
        Write-Host "  Start Menu > SA-US ERP"
        Write-Host "  Desktop shortcuts for installed components"
    }
    Write-Host ""
    if ($InstallMode -eq "server" -or $InstallMode -eq "both") {
        Write-Host "Server: open 'SA-US ERP Server Console' shortcut to start the server."
        Write-Host "        Edit server\server_config.ini to set a strong secret_key before going live."
    }
    if ($InstallMode -eq "client" -or $InstallMode -eq "both") {
        Write-Host "Client: edit client\client_config.ini and set the server PC IP address."
        Write-Host "        Then launch 'SA-US ERP Client' from the desktop shortcut."
    }
}
catch {
    "Install failed: $($_.Exception.Message)" | Out-File -FilePath $logPath -Append -Encoding utf8
    Write-Host "Install failed: $($_.Exception.Message)"
    Write-Host "Log: $logPath"
    exit 1
}
finally {
    if (Test-Path -LiteralPath $extractDir) {
        Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
