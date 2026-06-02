#!/bin/bash
# SA-US ERP Installer for macOS
# Installs MariaDB, copies binaries, creates launcher scripts and database.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/Applications/SA-US ERP"
LOG="$HOME/Library/Logs/sa_us_erp_install.log"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

step() { echo -e "\n${CYAN}>>> $1${NC}" | tee -a "$LOG"; }
ok()   { echo -e "${GREEN}✓ $1${NC}" | tee -a "$LOG"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}" | tee -a "$LOG"; }
fail() { echo -e "${RED}✗ $1${NC}" | tee -a "$LOG"; exit 1; }

echo "" | tee "$LOG"
echo "================================================" | tee -a "$LOG"
echo "  SA-US ERP Installer for macOS" | tee -a "$LOG"
echo "  SA Ultimate Solutions — v2.3.0" | tee -a "$LOG"
echo "  $(date)" | tee -a "$LOG"
echo "================================================" | tee -a "$LOG"

# ── Choose install mode ────────────────────────────────────────────────────
echo ""
echo "What do you want to install on this Mac?"
echo "  1) Server only  (main office Mac — runs the database + API)"
echo "  2) Client only  (staff Mac — connects to a server on the network)"
echo "  3) Both         (single-Mac setup)"
echo ""
read -rp "Enter 1, 2, or 3 [3]: " MODE_INPUT
MODE_INPUT="${MODE_INPUT:-3}"
case "$MODE_INPUT" in
  1) INSTALL_MODE="server" ;;
  2) INSTALL_MODE="client" ;;
  *) INSTALL_MODE="both" ;;
esac
echo "Install mode: $INSTALL_MODE" | tee -a "$LOG"

# ── Install Homebrew if missing ────────────────────────────────────────────
if [[ "$INSTALL_MODE" == "server" || "$INSTALL_MODE" == "both" ]]; then
  step "Checking Homebrew"
  if ! command -v brew &>/dev/null; then
    warn "Homebrew not found. Installing Homebrew (requires internet)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || \
      fail "Homebrew installation failed. Install it manually from https://brew.sh then re-run this script."
    # Add brew to PATH for Apple Silicon
    if [[ -f /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
  fi
  ok "Homebrew available: $(brew --version | head -1)"

  # ── Install MariaDB ──────────────────────────────────────────────────────
  step "Checking MariaDB"
  if brew list mariadb &>/dev/null 2>&1; then
    ok "MariaDB already installed"
  else
    echo "Installing MariaDB via Homebrew (this may take a few minutes)..."
    brew install mariadb | tee -a "$LOG" || fail "MariaDB installation failed."
    ok "MariaDB installed"
  fi

  # ── Start MariaDB service ────────────────────────────────────────────────
  step "Starting MariaDB service"
  brew services start mariadb | tee -a "$LOG" || warn "Could not start MariaDB service automatically."
  sleep 3
  if mysql -u root -e "SELECT 1" &>/dev/null 2>&1; then
    ok "MariaDB is running"
  else
    warn "MariaDB may not be running yet. Try: brew services start mariadb"
  fi
fi

# ── Copy application files ─────────────────────────────────────────────────
step "Installing SA-US ERP to: $APP_DIR"
mkdir -p "$APP_DIR"

if [[ "$INSTALL_MODE" == "server" || "$INSTALL_MODE" == "both" ]]; then
  mkdir -p "$APP_DIR/server"
  cp -f "$SCRIPT_DIR/server/SA_US_ERP_Server" "$APP_DIR/server/SA_US_ERP_Server"
  chmod +x "$APP_DIR/server/SA_US_ERP_Server"
  # Copy config template only if no config exists yet
  if [[ ! -f "$APP_DIR/server/server_config.ini" && -f "$SCRIPT_DIR/server/server_config.example.ini" ]]; then
    cp "$SCRIPT_DIR/server/server_config.example.ini" "$APP_DIR/server/server_config.ini"
    warn "Created server_config.ini from template. Edit it to set your database password and secret key."
  fi
  mkdir -p "$APP_DIR/sql"
  cp -rf "$SCRIPT_DIR/sql/." "$APP_DIR/sql/"
  ok "Server files installed"
fi

if [[ "$INSTALL_MODE" == "client" || "$INSTALL_MODE" == "both" ]]; then
  mkdir -p "$APP_DIR/client"
  cp -f "$SCRIPT_DIR/client/SA_US_ERP_Client" "$APP_DIR/client/SA_US_ERP_Client"
  chmod +x "$APP_DIR/client/SA_US_ERP_Client"
  # Preserve existing client config
  if [[ ! -f "$APP_DIR/client/client_config.ini" && -f "$SCRIPT_DIR/client/client_config.ini" ]]; then
    cp "$SCRIPT_DIR/client/client_config.ini" "$APP_DIR/client/client_config.ini"
  fi
  if [[ -d "$SCRIPT_DIR/client/branding" ]]; then
    cp -rf "$SCRIPT_DIR/client/branding/." "$APP_DIR/client/branding/"
  fi
  ok "Client files installed"
fi

# ── Create launcher scripts ────────────────────────────────────────────────
step "Creating launchers"

if [[ "$INSTALL_MODE" == "server" || "$INSTALL_MODE" == "both" ]]; then
  # Server launcher (.command opens in Terminal)
  cat > "$APP_DIR/Start SA-US ERP Server.command" <<'LAUNCHER'
#!/bin/bash
cd "$(dirname "$0")/server"
echo "Starting SA-US ERP Server..."
./SA_US_ERP_Server
echo ""
echo "Server stopped. Press Enter to close."
read
LAUNCHER
  chmod +x "$APP_DIR/Start SA-US ERP Server.command"
  ok "Created: Start SA-US ERP Server.command"
fi

if [[ "$INSTALL_MODE" == "client" || "$INSTALL_MODE" == "both" ]]; then
  cat > "$APP_DIR/Start SA-US ERP Client.command" <<'LAUNCHER'
#!/bin/bash
cd "$(dirname "$0")/client"
./SA_US_ERP_Client
LAUNCHER
  chmod +x "$APP_DIR/Start SA-US ERP Client.command"
  ok "Created: Start SA-US ERP Client.command"
fi

# ── Create database ────────────────────────────────────────────────────────
if [[ "$INSTALL_MODE" == "server" || "$INSTALL_MODE" == "both" ]]; then
  step "Creating SA-US ERP database"
  SQL_FILE="$APP_DIR/sql/create_database.sql"
  if [[ -f "$SQL_FILE" ]]; then
    echo ""
    echo "This will create the sa_us_erp database and user."
    read -rp "Enter MariaDB root password (leave blank if none): " -s ROOT_PW
    echo ""
    if [[ -n "$ROOT_PW" ]]; then
      MYSQL_CMD="mysql -u root -p${ROOT_PW}"
    else
      MYSQL_CMD="mysql -u root"
    fi
    if $MYSQL_CMD < "$SQL_FILE" 2>>"$LOG"; then
      ok "Database created successfully"
    else
      warn "Database creation failed or already exists. See: $LOG"
      warn "You can create it manually: mysql -u root < '$SQL_FILE'"
    fi
  else
    warn "SQL file not found — skipping database creation."
  fi
fi

# ── Launchd agent for auto-start (server) ─────────────────────────────────
if [[ "$INSTALL_MODE" == "server" || "$INSTALL_MODE" == "both" ]]; then
  step "Setting up server auto-start"
  PLIST_DIR="$HOME/Library/LaunchAgents"
  PLIST_FILE="$PLIST_DIR/com.saultimatesolutions.sa_us_erp_server.plist"
  mkdir -p "$PLIST_DIR"
  cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.saultimatesolutions.sa_us_erp_server</string>
    <key>ProgramArguments</key>
    <array>
        <string>$APP_DIR/server/SA_US_ERP_Server</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$APP_DIR/server</string>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/sa_us_erp_server.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/sa_us_erp_server.log</string>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
PLIST
  launchctl load "$PLIST_FILE" 2>/dev/null || true
  ok "Launchd agent installed (RunAtLoad=false — use launcher to start manually)"
fi

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo -e "${GREEN}  SA-US ERP installed successfully!${NC}"
echo "================================================"
echo ""
echo "  Location: $APP_DIR"
echo ""
if [[ "$INSTALL_MODE" == "server" || "$INSTALL_MODE" == "both" ]]; then
  echo "  Server:"
  echo "    1. Edit: $APP_DIR/server/server_config.ini"
  echo "       — set database password and a strong secret_key"
  echo "    2. Double-click: 'Start SA-US ERP Server.command'"
  echo ""
fi
if [[ "$INSTALL_MODE" == "client" || "$INSTALL_MODE" == "both" ]]; then
  echo "  Client:"
  echo "    1. Edit: $APP_DIR/client/client_config.ini"
  echo "       — set url = http://<server-ip>:8080"
  echo "    2. Double-click: 'Start SA-US ERP Client.command'"
  echo ""
fi
echo "  Install log: $LOG"
echo ""
echo "Press Enter to close."
read
