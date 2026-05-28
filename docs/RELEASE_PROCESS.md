# SA-US ERP Release Process

## Official Windows build path

Use the PyInstaller build script as the official release path unless the team explicitly switches to Nuitka after testing.

```bat
windows_scripts\05_build_exe_files.bat
```

Expected outputs:

```text
server\dist\SA_US_ERP_Server.exe
server\dist\server_config.ini
client\dist\SA_US_ERP_Client.exe
client\dist\client_config.ini
client\dist\tenant_branding.json
client\dist\branding\*
```

## Versioning

Update `VERSION.txt` before each release.

Recommended format:

```text
MAJOR.MINOR.PATCH
```

Examples:

- `2.3.0` — production hardening release
- `2.4.0` — reporting and dashboard release
- `3.0.0` — database model migration release

## Release checklist

Before building a release:

- Confirm `server/server_config.ini` does not contain real production credentials.
- Confirm `server/server_secret.key` is not committed.
- Run the server locally and check `/health`.
- Log in as admin and change the password.
- Create a non-admin user and test role restrictions.
- Create, edit, delete, search, and export records.
- Test database backup.
- Build EXE files.
- Test the server EXE and client EXE from a clean folder.

## Packaging checklist

A release package should include:

- Server EXE
- Client EXE
- Configuration examples
- Branding folder
- Installer scripts
- SQL setup script
- User guide
- Release notes

Do not include:

- Local `.venv` folders
- Build folders
- Dist folders from previous releases
- Runtime logs
- Real production secrets
- SQL backup files unless explicitly packaged for a client handover
