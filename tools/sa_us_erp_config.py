import configparser
import re
import secrets
import socket
import sys
from pathlib import Path
from tkinter import *
from tkinter import ttk, messagebox

import pymysql
from passlib.context import CryptContext


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

SERVER_DIR = BASE_DIR / "server"
CLIENT_DIR = BASE_DIR / "client"
SERVER_CONFIG = SERVER_DIR / "server_config.ini"
CLIENT_CONFIG = CLIENT_DIR / "client_config.ini"

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def validate_password(password):
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")


def parse_database_url(url):
    defaults = {
        "host": "127.0.0.1",
        "port": "3306",
        "database": "sa_us_erp",
        "username": "sa_us_user",
        "password": "SAUSERP2026!",
    }
    prefix = "mysql+pymysql://"
    suffix = "?charset=utf8mb4"
    if not url.startswith(prefix):
        return defaults
    body = url[len(prefix):]
    if body.endswith(suffix):
        body = body[:-len(suffix)]
    try:
        auth, host_part = body.rsplit("@", 1)
        username, password = auth.split(":", 1)
        host_port, database = host_part.split("/", 1)
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
        else:
            host, port = host_port, "3306"
        return {
            "host": host,
            "port": port,
            "database": database,
            "username": username,
            "password": password,
        }
    except Exception:
        return defaults


def build_database_url(host, port, database, username, password):
    return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}?charset=utf8mb4"


def read_server_config():
    config = configparser.ConfigParser()
    config.read(SERVER_CONFIG)
    db_url = config.get(
        "database",
        "url",
        fallback="mysql+pymysql://sa_us_user:SAUSERP2026!@127.0.0.1:3306/sa_us_erp?charset=utf8mb4",
    )
    db = parse_database_url(db_url)
    return {
        "host": config.get("server", "host", fallback="0.0.0.0"),
        "port": config.get("server", "port", fallback="8080"),
        "secret_key": config.get("server", "secret_key", fallback=""),
        **db,
    }


def read_client_config():
    config = configparser.ConfigParser()
    config.read(CLIENT_CONFIG)
    return config.get("server", "url", fallback="http://127.0.0.1:8080")


def write_server_config(values):
    SERVER_DIR.mkdir(parents=True, exist_ok=True)
    config = configparser.ConfigParser()
    config["database"] = {
        "url": build_database_url(
            values["host_db"],
            values["port_db"],
            values["database"],
            values["username_db"],
            values["password_db"],
        )
    }
    config["server"] = {
        "host": values["host_server"],
        "port": values["port_server"],
        "secret_key": values["secret_key"],
    }
    with SERVER_CONFIG.open("w", encoding="utf-8") as f:
        config.write(f)


def write_client_config(server_url):
    CLIENT_DIR.mkdir(parents=True, exist_ok=True)
    config = configparser.ConfigParser()
    config["server"] = {"url": server_url.rstrip("/")}
    with CLIENT_CONFIG.open("w", encoding="utf-8") as f:
        config.write(f)


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def connect_db():
    cfg = read_server_config()
    return pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["username"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        autocommit=False,
    )


def connect_root(root_host, root_port, root_user, root_password):
    return pymysql.connect(
        host=root_host,
        port=int(root_port),
        user=root_user,
        password=root_password,
        charset="utf8mb4",
        autocommit=False,
    )


def validate_identifier(value, label):
    if not re.fullmatch(r"[A-Za-z0-9_]+", value or ""):
        raise ValueError(f"{label} can only contain letters, numbers, and underscores.")


def initialize_database(root_host, root_port, root_user, root_password):
    cfg = read_server_config()
    validate_identifier(cfg["database"], "Database name")
    validate_identifier(cfg["username"], "Database username")

    conn = connect_root(root_host, root_port, root_user, root_password)
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{cfg['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            for host in ("localhost", "127.0.0.1", "%"):
                cur.execute(
                    f"CREATE USER IF NOT EXISTS `{cfg['username']}`@%s IDENTIFIED BY %s",
                    (host, cfg["password"]),
                )
                cur.execute(
                    f"ALTER USER `{cfg['username']}`@%s IDENTIFIED BY %s",
                    (host, cfg["password"]),
                )
                cur.execute(
                    f"GRANT ALL PRIVILEGES ON `{cfg['database']}`.* TO `{cfg['username']}`@%s",
                    (host,),
                )
            cur.execute("FLUSH PRIVILEGES")
        conn.commit()
    finally:
        conn.close()

    app_conn = connect_db()
    try:
        ensure_users_table(app_conn)
    finally:
        app_conn.close()


def ensure_users_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(80) NOT NULL UNIQUE,
                full_name VARCHAR(150) NOT NULL DEFAULT '',
                role VARCHAR(50) NOT NULL DEFAULT 'Sales Agent',
                password_hash VARCHAR(255) NOT NULL,
                is_active INT NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """
        )
    conn.commit()


def upsert_user(username, full_name, role, password):
    validate_password(password)
    password_hash = pwd_context.hash(password)
    conn = connect_db()
    try:
        ensure_users_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username=%s", (username,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE users
                    SET full_name=%s, role=%s, password_hash=%s, is_active=1
                    WHERE username=%s
                    """,
                    (full_name or username, role, password_hash, username),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO users (username, full_name, role, password_hash, is_active)
                    VALUES (%s, %s, %s, %s, 1)
                    """,
                    (username, full_name or username, role, password_hash),
                )
        conn.commit()
    finally:
        conn.close()


class ConfigApp(Tk):
    def __init__(self):
        super().__init__()
        self.title("SA-US ERP Configuration")
        self.geometry("680x720")
        self.resizable(False, False)

        notebook = ttk.Notebook(self)
        notebook.pack(fill=BOTH, expand=True, padx=12, pady=12)

        self.server_vars = {}
        self.client_url = StringVar(value=read_client_config())
        self.user_vars = {}
        self.root_vars = {}

        server_tab = Frame(notebook)
        client_tab = Frame(notebook)
        user_tab = Frame(notebook)
        help_tab = Frame(notebook)

        notebook.add(server_tab, text="Server")
        notebook.add(client_tab, text="Client Network")
        notebook.add(user_tab, text="Users")
        notebook.add(help_tab, text="Help")

        self.build_server_tab(server_tab)
        self.build_client_tab(client_tab)
        self.build_user_tab(user_tab)
        self.build_help_tab(help_tab)

    def add_entry(self, parent, label, var, row, show=None):
        Label(parent, text=label).grid(row=row, column=0, sticky=W, padx=10, pady=7)
        entry = Entry(parent, textvariable=var, width=45, show=show)
        entry.grid(row=row, column=1, sticky=W, padx=10, pady=7)
        return entry

    def build_server_tab(self, parent):
        cfg = read_server_config()
        fields = [
            ("host_server", "Server bind host", cfg["host"]),
            ("port_server", "Server port", cfg["port"]),
            ("host_db", "Database host", cfg["host"]),
            ("port_db", "Database port", cfg["port"]),
            ("database", "Database name", cfg["database"]),
            ("username_db", "Database user", cfg["username"]),
            ("password_db", "Database password", cfg["password"]),
            ("secret_key", "Server secret key", cfg["secret_key"]),
        ]
        for idx, (key, label, value) in enumerate(fields):
            var = StringVar(value=value)
            self.server_vars[key] = var
            self.add_entry(parent, label, var, idx, show="*" if key == "password_db" else None)

        Button(parent, text="Generate Secret Key", command=self.generate_secret).grid(row=8, column=1, sticky=W, padx=10, pady=(10, 4))
        Button(parent, text="Save Server Config", command=self.save_server).grid(row=9, column=1, sticky=W, padx=10, pady=4)
        Button(parent, text="Test Database Connection", command=self.test_database).grid(row=10, column=1, sticky=W, padx=10, pady=4)

        ttk.Separator(parent, orient=HORIZONTAL).grid(row=11, column=0, columnspan=2, sticky=EW, padx=10, pady=14)
        Label(parent, text="Initialize database using MariaDB/MySQL root login", font=("Segoe UI", 9, "bold")).grid(row=12, column=0, columnspan=2, sticky=W, padx=10, pady=(0, 6))
        root_defaults = {
            "root_host": cfg["host"],
            "root_port": cfg["port"],
            "root_user": "root",
            "root_password": "",
        }
        root_labels = [
            ("root_host", "Root host"),
            ("root_port", "Root port"),
            ("root_user", "Root user"),
            ("root_password", "Root password"),
        ]
        for offset, (key, label) in enumerate(root_labels):
            var = StringVar(value=root_defaults[key])
            self.root_vars[key] = var
            self.add_entry(parent, label, var, 13 + offset, show="*" if key == "root_password" else None)
        Button(parent, text="Initialize SA-US ERP Database", command=self.initialize_database).grid(row=17, column=1, sticky=W, padx=10, pady=8)

    def build_client_tab(self, parent):
        Label(parent, text=f"This machine IP: {local_ip()}").pack(anchor=W, padx=14, pady=(16, 8))
        Label(parent, text="Client server URL").pack(anchor=W, padx=14)
        Entry(parent, textvariable=self.client_url, width=55).pack(anchor=W, padx=14, pady=8)
        Button(parent, text="Use This PC as Server", command=self.use_local_ip).pack(anchor=W, padx=14, pady=4)
        Button(parent, text="Save Client Network Config", command=self.save_client).pack(anchor=W, padx=14, pady=4)

    def build_user_tab(self, parent):
        defaults = {
            "username": "admin",
            "full_name": "System Administrator",
            "role": "Owner",
            "password": "",
        }
        labels = [
            ("username", "Username"),
            ("full_name", "Full name"),
            ("role", "Role"),
            ("password", "New password"),
        ]
        for idx, (key, label) in enumerate(labels):
            var = StringVar(value=defaults[key])
            self.user_vars[key] = var
            if key == "role":
                Label(parent, text=label).grid(row=idx, column=0, sticky=W, padx=10, pady=7)
                cb = ttk.Combobox(
                    parent,
                    textvariable=var,
                    values=["Owner", "Business Manager", "Sales Agent", "Ticketing Officer", "Finance Officer", "Viewer"],
                    width=42,
                )
                cb.grid(row=idx, column=1, sticky=W, padx=10, pady=7)
            else:
                self.add_entry(parent, label, var, idx, show="*" if key == "password" else None)
        Button(parent, text="Create / Reset User Password", command=self.save_user).grid(row=5, column=1, sticky=W, padx=10, pady=14)

    def build_help_tab(self, parent):
        text = Text(parent, wrap=WORD, height=24, width=76)
        text.pack(fill=BOTH, expand=True, padx=12, pady=12)
        text.insert(
            "1.0",
            """Recommended setup:

1. On the main office/server PC, install MariaDB or MySQL first.
2. Run sql\\create_database.sql in MySQL, or create the database/user manually.
3. Open this configuration tool.
4. On Server, confirm database host/user/password and generate a secret key.
5. On Users, set the admin password before staff use the system.
6. Start SA-US ERP Server.
7. On staff PCs, install Client only and set Client Network to:
   http://<SERVER_PC_IP>:8080

If the server opens and closes immediately, the usual cause is database connection failure.
Open the Start Menu shortcut named "SA-US ERP Server Console"; it keeps the window open so you can read the exact error.
""",
        )
        text.config(state=DISABLED)

    def generate_secret(self):
        self.server_vars["secret_key"].set(secrets.token_hex(32))

    def save_server(self):
        try:
            values = {key: var.get().strip() for key, var in self.server_vars.items()}
            if not values["secret_key"] or values["secret_key"] == "CHANGE_THIS_TO_A_RANDOM_SECRET":
                values["secret_key"] = secrets.token_hex(32)
            write_server_config(values)
            messagebox.showinfo("Saved", "Server configuration saved. Restart the server.")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def test_database(self):
        try:
            conn = connect_db()
            conn.close()
            messagebox.showinfo("Database OK", "Database connection succeeded.")
        except Exception as exc:
            messagebox.showerror("Database failed", str(exc))

    def initialize_database(self):
        try:
            initialize_database(
                self.root_vars["root_host"].get().strip(),
                self.root_vars["root_port"].get().strip(),
                self.root_vars["root_user"].get().strip(),
                self.root_vars["root_password"].get(),
            )
            messagebox.showinfo("Database initialized", "SA-US ERP database and database user are ready.")
        except Exception as exc:
            messagebox.showerror("Database setup failed", str(exc))

    def use_local_ip(self):
        port = self.server_vars.get("port_server", StringVar(value="8080")).get() or "8080"
        self.client_url.set(f"http://{local_ip()}:{port}")

    def save_client(self):
        try:
            write_client_config(self.client_url.get().strip())
            messagebox.showinfo("Saved", "Client network configuration saved. Restart the client.")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def save_user(self):
        try:
            upsert_user(
                self.user_vars["username"].get().strip(),
                self.user_vars["full_name"].get().strip(),
                self.user_vars["role"].get().strip(),
                self.user_vars["password"].get(),
            )
            messagebox.showinfo("Saved", "User password saved.")
        except Exception as exc:
            messagebox.showerror("User update failed", str(exc))


if __name__ == "__main__":
    ConfigApp().mainloop()
