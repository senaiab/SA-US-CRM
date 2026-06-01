#!/bin/bash
# SA Ultimate Solutions — Distribution Package Builder (Android/Termux)
#
# Nuitka cannot cross-compile to Windows from Android:
#   - --mingw64 is a no-op on Linux
#   - 'ldd' is absent on Android (required for C extension DLL detection)
#   - pydantic-core/bcrypt require Rust (unavailable on Android for ARM64)
#
# This script creates two distribution zips:
#   dist/SA_US_ERP_Server_<date>.zip  — server package (run on server PC)
#   dist/SA_US_ERP_Client_<date>.zip  — client package (deploy to staff PCs)
#
# To build the actual .exe files, use a Windows PC:
#   windows_scripts\05_build_exe_files.bat   (requires Nuitka + MinGW on Windows)
#
# Or push to GitHub and use the Actions workflow (.github/workflows/build_exe.yml)
# which builds the exe automatically on a Windows runner.

set -e

PROJECT="/storage/emulated/0/SA-US-CRM"
DIST="$PROJECT/dist"
BUILD_DATE=$(date +%Y%m%d)
SERVER_ZIP="$DIST/SA_US_ERP_Server_${BUILD_DATE}.zip"
CLIENT_ZIP="$DIST/SA_US_ERP_Client_${BUILD_DATE}.zip"

mkdir -p "$DIST"
cd "$PROJECT"

echo ""
echo "================================================"
echo "  SA Ultimate Solutions — Distribution Build"
echo "  Date: $BUILD_DATE"
echo "================================================"

# ── Server Package ──────────────────────────────────
echo ""
echo "[1/2] Packaging server ..."
rm -f "$SERVER_ZIP"
zip -qr "$SERVER_ZIP" \
    server/ \
    sql/ \
    windows_scripts/01_install_server_dependencies.bat \
    windows_scripts/02_run_server.bat \
    windows_scripts/05_build_exe_files.bat \
    windows_scripts/06_mysql_backup.bat \
    README.txt
echo "    Done: $SERVER_ZIP"

# ── Client Package ──────────────────────────────────
echo ""
echo "[2/2] Packaging client ..."
rm -f "$CLIENT_ZIP"
zip -qr "$CLIENT_ZIP" \
    client/ \
    windows_scripts/03_install_client_dependencies.bat \
    windows_scripts/04_run_client.bat \
    windows_scripts/05_build_exe_files.bat \
    README.txt
echo "    Done: $CLIENT_ZIP"

# ── Summary ────────────────────────────────────────
echo ""
echo "================================================"
echo "  Packages ready — $BUILD_DATE"
echo ""
echo "  Server package:"
ls -lh "$SERVER_ZIP"
echo ""
echo "  Client package:"
ls -lh "$CLIENT_ZIP"
echo ""
echo "  Deployment:"
echo "    Server PC : unzip SA_US_ERP_Server_*.zip"
echo "                run windows_scripts\\01_install_server_dependencies.bat"
echo "                run windows_scripts\\02_run_server.bat"
echo ""
echo "    Staff PCs : unzip SA_US_ERP_Client_*.zip"
echo "                edit client\\client_config.ini (set server IP)"
echo "                run windows_scripts\\03_install_client_dependencies.bat"
echo "                run windows_scripts\\04_run_client.bat"
echo ""
echo "  To build .exe files:"
echo "    On a Windows PC: run windows_scripts\\05_build_exe_files.bat"
echo "    Via GitHub Actions: push to GitHub (see .github/workflows/build_exe.yml)"
echo "================================================"
echo ""
