# Changelog

## 2.3.0 — Production hardening foundation

### Added

- Central `VERSION.txt` file.
- Official `build_windows.bat` wrapper.
- GitHub Actions workflow for Windows EXE builds.
- `server/server_config.example.ini` with placeholder values.
- Production hardening roadmap in `docs/PRODUCTION_HARDENING.md`.
- Release process checklist in `docs/RELEASE_PROCESS.md`.

### Changed

- Updated README to match the official build and setup process.
- Replaced committed server configuration with safer placeholder values.
- Replaced database bootstrap password with a required placeholder.
- Added `.gitignore` rules for generated runtime secrets and local environment files.

### Notes

This release does not yet complete the full code refactor, installer wizard, normalized database migration, mobile client, or advanced reporting. Those are planned follow-on work items.
