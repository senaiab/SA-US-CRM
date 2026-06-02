<#
.SYNOPSIS
    SA-US ERP Installer Builder
    Assembles the payload folder, creates payload.zip, then compiles the
    single-file setup EXE using the C# bootstrapper (csc.exe).
    Falls back to IExpress if csc.exe is not found.

.PARAMETER RootDir
    Root of the SA-US-CRM project (parent of server/, client/, installer/, etc.)

.PARAMETER ReleaseDir
    Folder where the release output is written (e.g. release\).

.PARAMETER OutputExe
    Full path for the final setup EXE (e.g. release\SA-US-ERP-Setup.exe).
#>

param(
    [Parameter(Mandatory = $true)][string]$RootDir,
    [Parameter(Mandatory = $true)][string]$ReleaseDir,
    [Parameter(Mandatory = $true)][string]$OutputExe
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ─── Helpers ──────────────────────────────────────────────────────────────────

function Write-Step {
    param([string]$Msg)
    Write-Host ""
    Write-Host ">>> $Msg" -ForegroundColor Cyan
}

function Ensure-Dir {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

function Copy-IfExists {
    param([string]$Source, [string]$Destination)
    if (Test-Path -LiteralPath $Source) {
        $destDir = Split-Path -Parent $Destination
        Ensure-Dir $destDir
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        return $true
    }
    return $false
}

function Copy-DirContents {
    param([string]$Source, [string]$Destination)
    if (!(Test-Path -LiteralPath $Source)) { return }
    Ensure-Dir $Destination
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Find-Csc {
    # .NET Framework csc.exe — present on virtually all Windows machines
    $bits = @("Framework64", "Framework")
    $versions = @("v4.0.30319", "v3.5", "v2.0.50727")
    foreach ($bit in $bits) {
        foreach ($ver in $versions) {
            $p = Join-Path $env:SystemRoot "Microsoft.NET\$bit\$ver\csc.exe"
            if (Test-Path -LiteralPath $p) { return $p }
        }
    }
    # Roslyn csc.exe shipped with Visual Studio
    $vs = @("C:\Program Files\Microsoft Visual Studio", "C:\Program Files (x86)\Microsoft Visual Studio")
    foreach ($base in $vs) {
        if (Test-Path $base) {
            $found = Get-ChildItem -Path $base -Filter "csc.exe" -Recurse -ErrorAction SilentlyContinue |
                     Where-Object { $_.DirectoryName -notmatch "arm" } |
                     Select-Object -First 1
            if ($found) { return $found.FullName }
        }
    }
    return $null
}

# ─── Resolve paths ────────────────────────────────────────────────────────────

$RootDir      = (Resolve-Path $RootDir).Path
$serverDist   = Join-Path $RootDir "server\dist"
$clientDist   = Join-Path $RootDir "client\dist"
$installerDir = Join-Path $RootDir "installer"
$sqlDir       = Join-Path $RootDir "sql"
$docsDir      = Join-Path $RootDir "docs"
$distDir      = Join-Path $RootDir "dist"   # top-level dist (contains SA_US_ERP_Config.exe)

Ensure-Dir $ReleaseDir
$payloadDir = Join-Path $ReleaseDir "payload"
$srcDir     = Join-Path $ReleaseDir "installer_source"
$zipPath    = Join-Path $srcDir "payload.zip"

# ─── Step 1: Validate EXE prerequisites ──────────────────────────────────────

Write-Step "Validating build prerequisites"

$serverExe = Join-Path $serverDist "SA_US_ERP_Server.exe"
$clientExe = Join-Path $clientDist "SA_US_ERP_Client.exe"

if (!(Test-Path -LiteralPath $serverExe)) {
    throw "Server EXE not found: $serverExe`nRun windows_scripts\05_build_exe_files.bat first."
}
if (!(Test-Path -LiteralPath $clientExe)) {
    throw "Client EXE not found: $clientExe`nRun windows_scripts\05_build_exe_files.bat first."
}

Write-Host "Server EXE: OK"
Write-Host "Client EXE: OK"

# ─── Step 2: Build payload folder ────────────────────────────────────────────

Write-Step "Assembling payload"

# Clean and recreate
if (Test-Path -LiteralPath $payloadDir) {
    Remove-Item -LiteralPath $payloadDir -Recurse -Force
}
Ensure-Dir $payloadDir

# README
Copy-IfExists (Join-Path $RootDir "README.txt") (Join-Path $payloadDir "README.txt") | Out-Null

# docs/
Copy-DirContents $docsDir (Join-Path $payloadDir "docs")

# sql/
Copy-DirContents $sqlDir (Join-Path $payloadDir "sql")

# server/ — EXE + config (config only copied if no existing install has one)
$payloadServer = Join-Path $payloadDir "server"
Ensure-Dir $payloadServer
Copy-Item -LiteralPath $serverExe -Destination (Join-Path $payloadServer "SA_US_ERP_Server.exe") -Force
Copy-IfExists (Join-Path $serverDist "server_config.ini") (Join-Path $payloadServer "server_config.ini") | Out-Null

# client/ — EXE + config + branding
$payloadClient = Join-Path $payloadDir "client"
Ensure-Dir $payloadClient
Copy-Item -LiteralPath $clientExe -Destination (Join-Path $payloadClient "SA_US_ERP_Client.exe") -Force
Copy-IfExists (Join-Path $clientDist "client_config.ini")    (Join-Path $payloadClient "client_config.ini")    | Out-Null
Copy-IfExists (Join-Path $clientDist "tenant_branding.json") (Join-Path $payloadClient "tenant_branding.json") | Out-Null
Copy-IfExists (Join-Path $clientDist "company_logo.png")     (Join-Path $payloadClient "company_logo.png")     | Out-Null
$brandingSrc = Join-Path $clientDist "branding"
if (Test-Path -LiteralPath $brandingSrc) {
    Copy-DirContents $brandingSrc (Join-Path $payloadClient "branding")
}

# tools/ — config GUI, database backup, prerequisites scripts
$payloadTools = Join-Path $payloadDir "tools"
Ensure-Dir $payloadTools

# SA_US_ERP_Config.exe from top-level dist if it exists
Copy-IfExists (Join-Path $distDir "SA_US_ERP_Config.exe") (Join-Path $payloadTools "SA_US_ERP_Config.exe") | Out-Null

# Database backup script (renamed for end-user clarity)
Copy-IfExists (Join-Path $RootDir "windows_scripts\06_mysql_backup.bat") `
              (Join-Path $payloadTools "Backup Database.bat") | Out-Null

# Database prerequisite installer
Copy-IfExists (Join-Path $installerDir "prerequisites.cmd") (Join-Path $payloadTools "prerequisites.cmd") | Out-Null
Copy-IfExists (Join-Path $installerDir "prerequisites.ps1") (Join-Path $payloadTools "prerequisites.ps1") | Out-Null

# uninstall/ — uninstaller lives here so install.ps1 can copy it to $InstallDir root
$payloadUninstall = Join-Path $payloadDir "uninstall"
Ensure-Dir $payloadUninstall
Copy-IfExists (Join-Path $installerDir "uninstall.cmd") (Join-Path $payloadUninstall "uninstall.cmd") | Out-Null
Copy-IfExists (Join-Path $installerDir "uninstall.ps1") (Join-Path $payloadUninstall "uninstall.ps1") | Out-Null

Write-Host "Payload assembled: $payloadDir"

# ─── Step 3: Create payload.zip ───────────────────────────────────────────────

Write-Step "Creating payload.zip"
Ensure-Dir $srcDir

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

# Compress-Archive includes the top-level folder name, so zip contains payload\ — matches install.ps1 expectation
Compress-Archive -Path $payloadDir -DestinationPath $zipPath -CompressionLevel Optimal
$zipSize = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
Write-Host "payload.zip created: $zipSize MB"

# ─── Step 4: Assemble installer_source folder ─────────────────────────────────

Write-Step "Assembling installer_source"

# payload.zip is already in srcDir from step 3
# Copy installer scripts
Copy-IfExists (Join-Path $installerDir "install.cmd") (Join-Path $srcDir "install.cmd") | Out-Null
Copy-IfExists (Join-Path $installerDir "install.ps1") (Join-Path $srcDir "install.ps1") | Out-Null
Copy-IfExists (Join-Path $installerDir "prerequisites.cmd") (Join-Path $srcDir "prerequisites.cmd") | Out-Null
Copy-IfExists (Join-Path $installerDir "prerequisites.ps1") (Join-Path $srcDir "prerequisites.ps1") | Out-Null

Write-Host "Installer source ready: $srcDir"

# ─── Step 5: Compile setup EXE ────────────────────────────────────────────────

Write-Step "Compiling setup EXE"

$csFile   = Join-Path $installerDir "SetupBootstrapper.cs"
$iconFile  = Join-Path $RootDir "client\branding\app_icon.ico"

Ensure-Dir (Split-Path -Parent $OutputExe)

$csc = Find-Csc
if ($csc) {
    Write-Host "Using CSC: $csc"

    # Build resource args — payload.zip, install.cmd, install.ps1
    $resources = @(
        "/resource:`"$(Join-Path $srcDir 'payload.zip')`",payload.zip",
        "/resource:`"$(Join-Path $srcDir 'install.cmd')`",install.cmd",
        "/resource:`"$(Join-Path $srcDir 'install.ps1')`",install.ps1"
    )

    $cscArgs = @(
        "/target:winexe",
        "/optimize+",
        "/out:`"$OutputExe`"",
        "/nologo"
    )
    if (Test-Path -LiteralPath $iconFile) {
        $cscArgs += "/win32icon:`"$iconFile`""
    }
    $cscArgs += $resources
    $cscArgs += "`"$csFile`""

    $proc = Start-Process -FilePath $csc -ArgumentList $cscArgs -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0) {
        Write-Host "CSC compilation failed (exit $($proc.ExitCode)). Falling back to IExpress." -ForegroundColor Yellow
        $csc = $null
    }
}

if (!$csc) {
    Write-Host "CSC not found or failed — using IExpress (Windows built-in)" -ForegroundColor Yellow

    $iexpress = Join-Path $env:SystemRoot "System32\iexpress.exe"
    if (!(Test-Path -LiteralPath $iexpress)) {
        throw "Neither csc.exe nor iexpress.exe could be found. Cannot build setup EXE."
    }

    # Generate the .sed config dynamically so paths are always correct.
    # Single-quoted here-string avoids variable-expansion / terminator issues;
    # placeholders are swapped out with .Replace() afterwards.
    $sedContent = @'
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=SA-US ERP Setup is complete.
TargetName=__OUTPUT_EXE__
FriendlyName=SA-US ERP Setup
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles

[Strings]
FILE0="install.cmd"
FILE1="install.ps1"
FILE2="prerequisites.cmd"
FILE3="prerequisites.ps1"
FILE4="payload.zip"

[SourceFiles]
SourceFiles0=__SRC_DIR__\

[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
%FILE3%=
%FILE4%=
'@
    $sedContent = $sedContent.Replace('__OUTPUT_EXE__', $OutputExe).Replace('__SRC_DIR__', $srcDir)

    $sedPath = Join-Path $env:TEMP "sa_us_erp_setup.sed"
    $sedContent | Out-File -FilePath $sedPath -Encoding ASCII

    $proc = Start-Process -FilePath $iexpress -ArgumentList "/N `"$sedPath`"" -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0) {
        throw "IExpress failed with exit code $($proc.ExitCode)."
    }
    Remove-Item -LiteralPath $sedPath -Force -ErrorAction SilentlyContinue
}

# ─── Done ─────────────────────────────────────────────────────────────────────

if (!(Test-Path -LiteralPath $OutputExe)) {
    throw "Build appeared to succeed but output EXE was not found: $OutputExe"
}

$exeSize = [math]::Round((Get-Item -LiteralPath $OutputExe).Length / 1MB, 1)

Write-Host ""
Write-Host "========================================"  -ForegroundColor Green
Write-Host "  SA-US ERP Installer Build Complete"     -ForegroundColor Green
Write-Host "========================================"  -ForegroundColor Green
Write-Host ""
Write-Host "  Output : $OutputExe"
Write-Host "  Size   : $exeSize MB"
Write-Host ""
Write-Host "Distribute SA-US-ERP-Setup.exe to any Windows PC." -ForegroundColor Green
Write-Host "No Python or pip install needed on the target machine." -ForegroundColor Green
Write-Host ""
