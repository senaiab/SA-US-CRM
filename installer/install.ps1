param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\SA-US ERP",
    [ValidateSet("", "server", "client", "both")]
    [string]$InstallMode = "",
    [switch]$SkipShortcuts
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
        $shortcut.IconLocation = $IconLocation
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
            "company_logo.png"
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

function Test-DatabaseServiceInstalled {
    $service = Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match "mysql|maria" -or $_.DisplayName -match "mysql|maria"
        } |
        Select-Object -First 1
    return $null -ne $service
}

function Find-MySql {
    # Check PATH first
    $fromPath = Get-Command mysql.exe -ErrorAction SilentlyContinue
    if ($fromPath) { return $fromPath.Source }

    # Common MariaDB / MySQL installation locations
    $patterns = @(
        "$env:ProgramFiles\MariaDB*\bin\mysql.exe",
        "${env:ProgramFiles(x86)}\MariaDB*\bin\mysql.exe",
        "$env:ProgramFiles\MySQL\MySQL Server *\bin\mysql.exe",
        "${env:ProgramFiles(x86)}\MySQL\MySQL Server *\bin\mysql.exe"
    )
    foreach ($pattern in $patterns) {
        $found = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue |
                 Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

function Offer-DatabasePrerequisite {
    param([Parameter(Mandatory = $true)][string]$InstallDir)

    if (Test-DatabaseServiceInstalled) {
        return
    }

    Add-Type -AssemblyName System.Windows.Forms
    $message = "MariaDB/MySQL was not detected on this PC.`n`nInstall MariaDB Server now as the database prerequisite?`n`nThis requires internet access and may ask for administrator permission."
    $result = [System.Windows.Forms.MessageBox]::Show(
        $message,
        "SA-US ERP Database Prerequisite",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )

    if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {
        $prereq = Join-Path $InstallDir "prerequisites.cmd"
        if (Test-Path -LiteralPath $prereq) {
            Start-Process -FilePath $prereq -WorkingDirectory $InstallDir -Wait
        }
    }
}

function Initialize-Database {
    <#
    .SYNOPSIS
        Creates the SA-US ERP database and user automatically during installation.
        Shows a GUI dialog asking for the MySQL/MariaDB root password, then runs
        sql\create_database.sql. Safe to run on an existing install (uses IF NOT EXISTS).
    #>
    param([Parameter(Mandatory = $true)][string]$InstallDir)

    $sqlFile = Join-Path $InstallDir "sql\create_database.sql"
    if (!(Test-Path -LiteralPath $sqlFile)) {
        Write-Host "SQL script not found at $sqlFile — skipping database setup." -ForegroundColor Yellow
        return
    }

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    # ── Find mysql.exe (may have just been installed by Offer-DatabasePrerequisite) ──
    $mysql = Find-MySql

    # ── Build the dialog ──────────────────────────────────────────────────────
    $form = New-Object System.Windows.Forms.Form
    $form.Text     = "SA-US ERP — Database Setup"
    $form.Size     = New-Object System.Drawing.Size(500, 310)
    $form.StartPosition   = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false

    # Info text
    $info = New-Object System.Windows.Forms.Label
    if ($mysql) {
        $info.Text = "SA-US ERP will now create its database and user on this machine.`n`nEnter your MySQL / MariaDB ROOT password below, then click`n""Create Database"".  Leave blank if root has no password.`n`n(Safe to run again — uses CREATE IF NOT EXISTS.)"
    } else {
        $info.Text = "mysql.exe was not found in PATH or common install locations.`n`nYou can still skip this step and create the database manually`nby running the SQL script at:`n`n   $sqlFile"
    }
    $info.AutoSize = $false
    $info.Size     = New-Object System.Drawing.Size(450, 100)
    $info.Location = New-Object System.Drawing.Point(20, 16)
    $form.Controls.Add($info)

    # Password label + field (only shown when mysql is available)
    $pwLabel = New-Object System.Windows.Forms.Label
    $pwLabel.Text     = "MySQL root password:"
    $pwLabel.AutoSize = $true
    $pwLabel.Location = New-Object System.Drawing.Point(20, 126)
    $pwLabel.Enabled  = ($null -ne $mysql)
    $form.Controls.Add($pwLabel)

    $pwBox = New-Object System.Windows.Forms.TextBox
    $pwBox.UseSystemPasswordChar = $true
    $pwBox.Size     = New-Object System.Drawing.Size(300, 22)
    $pwBox.Location = New-Object System.Drawing.Point(20, 148)
    $pwBox.Enabled  = ($null -ne $mysql)
    $form.Controls.Add($pwBox)

    # Status label
    $statusLbl = New-Object System.Windows.Forms.Label
    $statusLbl.Text      = ""
    $statusLbl.AutoSize  = $false
    $statusLbl.Size      = New-Object System.Drawing.Size(450, 22)
    $statusLbl.Location  = New-Object System.Drawing.Point(20, 180)
    $statusLbl.ForeColor = [System.Drawing.Color]::DarkRed
    $form.Controls.Add($statusLbl)

    # "Create Database" button
    $createBtn = New-Object System.Windows.Forms.Button
    $createBtn.Text     = "Create Database"
    $createBtn.Size     = New-Object System.Drawing.Size(150, 36)
    $createBtn.Location = New-Object System.Drawing.Point(20, 218)
    $createBtn.Enabled  = ($null -ne $mysql)
    $createBtn.BackColor = [System.Drawing.Color]::FromArgb(31, 78, 120)
    $createBtn.ForeColor = [System.Drawing.Color]::White
    $createBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $form.Controls.Add($createBtn)
    $form.AcceptButton = $createBtn

    # "Skip" button
    $skipBtn = New-Object System.Windows.Forms.Button
    $skipBtn.Text           = "Skip (do manually later)"
    $skipBtn.Size           = New-Object System.Drawing.Size(180, 36)
    $skipBtn.Location       = New-Object System.Drawing.Point(185, 218)
    $skipBtn.DialogResult   = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton      = $skipBtn
    $form.Controls.Add($skipBtn)

    # ── Create Database click handler ─────────────────────────────────────────
    $createBtn.Add_Click({
        $createBtn.Enabled  = $false
        $statusLbl.ForeColor = [System.Drawing.Color]::DarkBlue
        $statusLbl.Text     = "Creating database..."
        $form.Refresh()

        $rootPw = $pwBox.Text

        # Build cmd.exe command — pipe SQL file via stdin redirection
        # Use cmd /c so we get proper < redirection support
        $escapedSql   = $sqlFile.Replace('"', '""')
        $escapedMysql = $mysql.Replace('"', '""')
        if ($rootPw) {
            # -p with no space before password — standard mysql syntax
            $mysqlArgs = "-u root -p$rootPw"
        } else {
            $mysqlArgs = "-u root"
        }
        $cmdLine = "/c `"`"$escapedMysql`" $mysqlArgs < `"$escapedSql`"`""

        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName               = "cmd.exe"
        $psi.Arguments              = $cmdLine
        $psi.UseShellExecute        = $false
        $psi.RedirectStandardError  = $true
        $psi.RedirectStandardOutput = $true
        $psi.CreateNoWindow         = $true

        try {
            $proc   = [System.Diagnostics.Process]::Start($psi)
            $stderr = $proc.StandardError.ReadToEnd()
            $stdout = $proc.StandardOutput.ReadToEnd()
            $proc.WaitForExit()

            if ($proc.ExitCode -eq 0) {
                $statusLbl.ForeColor = [System.Drawing.Color]::DarkGreen
                $statusLbl.Text = "Database created successfully! Open SA-US ERP Configuration to set the password."
                $form.Refresh()
                Start-Sleep -Milliseconds 1400
                $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
                $form.Close()
            } else {
                $errMsg = ($stderr.Trim() -replace "`r`n|`r|`n", " ")
                if ($errMsg.Length -gt 90) { $errMsg = $errMsg.Substring(0, 90) + "..." }
                $statusLbl.ForeColor = [System.Drawing.Color]::DarkRed
                $statusLbl.Text = "Failed: $errMsg"
                $createBtn.Enabled = $true
            }
        } catch {
            $statusLbl.ForeColor = [System.Drawing.Color]::DarkRed
            $statusLbl.Text      = "Error: $($_.Exception.Message)"
            $createBtn.Enabled   = $true
        }
    })

    # ── Show dialog ───────────────────────────────────────────────────────────
    $result = $form.ShowDialog()

    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        Write-Host "Database initialized successfully."
        "Database initialized: $(Get-Date -Format s)" | Out-File -FilePath $logPath -Append -Encoding utf8
    } else {
        Write-Host "Database setup skipped. Run sql\create_database.sql manually when ready." -ForegroundColor Yellow
        "Database setup skipped by user: $(Get-Date -Format s)" | Out-File -FilePath $logPath -Append -Encoding utf8
    }
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
    if ($existingInstallDir -and !$SkipShortcuts) {
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
    Copy-Item -LiteralPath (Join-Path $payloadRoot "README.txt") -Destination (Join-Path $InstallDir "README.txt") -Force
    Copy-TreePreservingConfig -Source (Join-Path $payloadRoot "docs") -Destination (Join-Path $InstallDir "docs")
    Copy-TreePreservingConfig -Source (Join-Path $payloadRoot "tools") -Destination $InstallDir
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
    $configExe = Join-Path $InstallDir "SA_US_ERP_Config.exe"
    $clientIcon = Join-Path $InstallDir "client\branding\app_icon.ico"
    $serverConsoleCmd = Join-Path $InstallDir "SA-US ERP Server Console.cmd"
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
        $startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\SA-US ERP"
        $desktopDir = [Environment]::GetFolderPath("Desktop")
        New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null

        New-Shortcut `
            -ShortcutPath (Join-Path $startMenuDir "SA-US ERP Configuration.lnk") `
            -TargetPath $configExe `
            -WorkingDirectory $InstallDir `
            -IconLocation $clientIcon

        if ($InstallMode -eq "server" -or $InstallMode -eq "both") {
            New-Shortcut `
                -ShortcutPath (Join-Path $startMenuDir "Install or Repair MariaDB Prerequisite.lnk") `
                -TargetPath (Join-Path $InstallDir "prerequisites.cmd") `
                -WorkingDirectory $InstallDir `
                -IconLocation $clientIcon
        }

        New-Shortcut `
            -ShortcutPath (Join-Path $desktopDir "SA-US ERP Configuration.lnk") `
            -TargetPath $configExe `
            -WorkingDirectory $InstallDir `
            -IconLocation $clientIcon

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
    New-ItemProperty -Path $uninstallKey -Name "DisplayVersion" -Value "2.3.0" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "Publisher" -Value "SA Ultimate Solutions" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "InstallLocation" -Value $InstallDir -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "UninstallString" -Value "`"$InstallDir\uninstall.cmd`"" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "QuietUninstallString" -Value "`"$InstallDir\uninstall.cmd`" -Quiet" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "NoModify" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "NoRepair" -Value 1 -PropertyType DWord -Force | Out-Null

    if ($InstallMode -eq "server" -or $InstallMode -eq "both") {
        # 1. Install MariaDB if not already present
        if (!$SkipShortcuts) {
            Offer-DatabasePrerequisite -InstallDir $InstallDir
        }
        # 2. Create the database and app user automatically
        Initialize-Database -InstallDir $InstallDir
    }

    "Installed successfully: $(Get-Date -Format s)" | Out-File -FilePath $logPath -Append -Encoding utf8

    Write-Host ""
    Write-Host "SA-US ERP installed successfully."
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
