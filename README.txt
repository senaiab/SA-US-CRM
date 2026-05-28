SA-US ERP LOCAL NETWORK EDITION
===============================

Developed and distributed by SA Ultimate Solutions.

This package provides a local-network ERP/CRM starter system that runs on office PCs without cPanel and without internet.

Current version
---------------
See VERSION.txt.

Branding rules
--------------
- Software product name: SA-US ERP
- Developer / distributor: SA Ultimate Solutions
- The client company name and logo are set after installation through:
  client\tenant_branding.json
  client\company_logo.png

Architecture
------------
1. One main office PC runs:
   - MariaDB/MySQL database
   - SA_US_ERP_Server

2. Staff PCs run:
   - SA_US_ERP_Client
   - The client connects to the server PC over the local network.

Default login
-------------
Username: admin
Password: admin123

Change this immediately after first login from the Admin tab or Change Password button.

Important folders
-----------------
server\app.py                       API server
server\server_config.ini            Local database and server settings
server\server_config.example.ini    Safe example configuration
client\client_app.py                Desktop client
client\client_config.ini            Server IP address for client PCs
client\tenant_branding.json         Client-company branding settings
client\branding\                   App logo and developer logo assets
sql\create_database.sql             Database and user creation script
windows_scripts\*.bat               Install, run, build, and backup scripts
docs\BRANDING_SETUP.md              How to apply the client company name and logo
docs\PRODUCTION_HARDENING.md        Production-readiness roadmap
docs\RELEASE_PROCESS.md             Release and packaging checklist

Initial setup on the Server PC
------------------------------
1. Install Python 3.11 or newer. Tick "Add Python to PATH".
2. Install MariaDB or MySQL on the Server PC.
3. Copy or edit:
   server\server_config.example.ini
   into:
   server\server_config.ini
4. Set a strong database password in:
   sql\create_database.sql
   and in:
   server\server_config.ini
5. Run the SQL in:
   sql\create_database.sql
6. Start the server:
   windows_scripts\02_run_server.bat
7. Test:
   http://127.0.0.1:8080/health

Local network setup
-------------------
1. Find the Server PC IPv4 address using `ipconfig`.
2. Allow port 8080 through Windows Firewall.
3. On each staff PC, edit:
   client\client_config.ini
   Example:
   url = http://192.168.1.20:8080

Client setup on staff PCs
-------------------------
1. Install Python 3.11 or newer.
2. Copy the client folder to the staff PC.
3. Edit client_config.ini to point to the Server PC IP address.
4. Set the client company name/logo in tenant_branding.json and company_logo.png.
5. Run:
   windows_scripts\03_install_client_dependencies.bat
6. Start the client:
   windows_scripts\04_run_client.bat

Building EXE files
------------------
Official build command:
   build_windows.bat

This calls:
   windows_scripts\05_build_exe_files.bat

This builder script will:
- create `server\.venv` and `client\.venv` if missing
- install dependencies automatically
- build both EXE files with PyInstaller
- copy required config and branding files into each `dist` folder

Outputs:
- server\dist\SA_US_ERP_Server.exe
- server\dist\server_config.ini
- client\dist\SA_US_ERP_Client.exe
- client\dist\client_config.ini
- client\dist\tenant_branding.json
- client\dist\branding\*

Backup
------
Run:
   windows_scripts\06_mysql_backup.bat

Backups are saved to:
   C:\SA_US_ERP\Backups

Modules included
----------------
- Dashboard
- Leads
- Quotations
- Bookings
- Accounts Receivable
- Complaints
- Exceptions
- Clients
- Suppliers
- Admin user management

Security note
-------------
Change the default password, change the database password, use a persistent secret_key or generated server_secret.key, and restrict access to the office LAN only.
