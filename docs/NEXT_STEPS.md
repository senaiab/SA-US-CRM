# SA-US ERP Next Steps

## Priority 1 — Build and deployment

- Confirm GitHub Actions artifacts on a tagged release.
- Add a release ZIP/package job.
- Add smoke testing after build.
- Keep PyInstaller as the official build path unless Nuitka is deliberately tested and selected.

## Priority 2 — Admin and access controls

- Add first-login credential reset flow in the client.
- Add user enable/disable controls.
- Add an Admin audit log viewer.
- Add stronger credential guidance in the UI.

## Priority 3 — Setup wizard

- Extend the configuration tool into a first-run wizard.
- Add Server / Client installation mode.
- Add database setup and connection testing.
- Add LAN IP detection and client URL update.
- Add optional Windows Firewall setup guidance.

## Priority 4 — Backup and restore

- Add backup button in Admin.
- Add restore workflow with confirmations.
- Add backup verification.
- Package config, branding, and database dump together.

## Priority 5 — Code refactor

- Split `server/app.py` into config, database, models, auth, permissions, and route modules.
- Split `client/client_app.py` into API client, branding loader, dialogs, screens, widgets, and module tabs.

## Priority 6 — Business features

- Excel import with field mapping.
- Duplicate detection for clients and leads.
- Required field validation.
- Date picker and currency validation.
- AR aging report.
- Quote conversion report.
- Sales and booking revenue dashboard.
- Dashboard export to Excel/PDF.

## Priority 7 — Data model upgrade

- Keep flexible JSON record support.
- Add normalized tables only where reporting and data integrity require it.
- Add migration tooling before changing deployed databases.

## Priority 8 — Mobile direction

- Remove the placeholder Android/Kivy test app from production releases, or replace it with a real mobile companion connected to the FastAPI server.
