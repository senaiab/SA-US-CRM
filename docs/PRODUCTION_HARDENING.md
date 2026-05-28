# SA-US ERP Production Hardening Plan

This document defines the upgrade direction for turning SA-US ERP from a starter LAN CRM into a safer production-ready office system.

## Completed in this branch

- Added a central `VERSION.txt` file.
- Replaced committed server configuration with safer placeholders.
- Added `server/server_config.example.ini`.
- Added `.gitignore` rules for generated runtime secrets and environment files.

## Recommended production defaults

1. Change the default admin password on first login.
2. Set a strong database password during installation.
3. Set or generate a persistent server secret key.
4. Keep the server bound to the office LAN only.
5. Do not expose port 8080 to the public internet.
6. Restrict CORS origins if a browser/web client is introduced.
7. Back up the database daily.
8. Keep a copy of server config, client branding, and SQL backups in the backup set.

## Target upgrade roadmap

### Phase 1 — Foundation

- Standardize the Windows build path.
- Add a clean release process.
- Add configuration examples.
- Remove or quarantine placeholder Android files until a real mobile client is built.

### Phase 2 — Security

- Force admin password change after first login.
- Add user disable/reactivate support.
- Add audit log viewer in the Admin tab.
- Add environment variable overrides for sensitive settings.
- Add stronger validation for new passwords.

### Phase 3 — Installer and operations

- Add a setup wizard for Server / Client mode.
- Auto-detect LAN IP address.
- Test database connection from the installer/config tool.
- Add backup and restore buttons.
- Add firewall guidance or automated firewall rule creation for Windows.

### Phase 4 — Maintainability

- Split `server/app.py` into config, database, models, auth, permissions, and route modules.
- Split `client/client_app.py` into API, branding, dialogs, screens, widgets, and module tabs.
- Add tests for login, permissions, record CRUD, dashboard metrics, and backup export.

### Phase 5 — Business features

- Add Excel import with validation and duplicate detection.
- Add AR aging report.
- Add quote conversion report.
- Add booking revenue dashboard.
- Add client activity summary.
- Add PDF/Excel dashboard exports.

### Phase 6 — Data model upgrade

- Keep the flexible JSON record model for custom fields.
- Add normalized tables for clients, invoices, payments, bookings, users, and audit where reporting requires structure.
- Add migration tooling before changing existing database schema.

## Build direction

The official build direction should be PyInstaller unless Nuitka is deliberately selected and tested. Mixing build systems creates support problems. Keep one official build command and one release workflow.
