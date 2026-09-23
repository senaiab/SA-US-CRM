"""
Local, on-device data layer for the SA-US ERP Android app.

This replaces the FastAPI server entirely: there is no network call anywhere
in this module. Everything that used to be server-side (auth, permissions,
auto-generated IDs, business rules) lives here instead, backed by a plain
sqlite3 database file in the app's own private storage.

Field lists, dropdown choices, role permissions, and the auto-ID scheme are
ported from server/app.py / client/client_app.py so the same modules and
business rules apply here.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime


MODULES = {
    "leads": ["Lead ID", "Inquiry Date", "Client Name", "Company", "Contact", "Phone/Email", "Source", "Service Type", "Priority", "Assigned Owner", "Lead Status", "Next Action Date", "Last Contact Date", "Quote ID", "Booked?", "Outcome", "Notes"],
    "quotations": ["Quote ID", "Lead ID", "Quote Date", "Client Name", "Service Type", "Consultant", "Quoted Amount", "Cost Estimate", "Currency", "Validity Date", "Quote Status", "Revision No", "Accepted Date", "Booking Ref", "Lost Reason", "Notes"],
    "bookings": ["Booking Ref", "Quote ID", "Lead ID", "Booking Date", "Client Name", "Service Type", "Consultant", "Ticketing Owner", "Supplier/Airline", "Passenger/Pax", "Gross Sale", "Supplier Cost", "Payment Status", "Credit Approved?", "Invoice No", "Invoice Date", "Due Date", "Handover Complete?", "Issue Status", "Issue Date", "Refund Status", "Remarks"],
    "ar": ["Invoice No", "Client Name", "Booking Ref", "Invoice Date", "Due Date", "Invoice Amount", "Amount Received", "Payment Status", "AR Stage", "Owner", "Last Follow-Up", "Next Follow-Up", "Comments"],
    "complaints": ["Complaint ID", "Date Received", "Client Name", "Booking Ref", "Issue Category", "Severity", "Owner", "Status", "Root Cause", "Resolution Date", "Client Informed?", "Corrective Action", "Notes"],
    "exceptions": ["Exception ID", "Date", "Type", "Client/Case", "Related Ref", "Requested By", "Approved By", "Financial Impact", "Reason", "Resolution", "Closed?", "Notes"],
    "clients": ["Client ID", "Client Name", "Company", "Phone", "Email", "Client Type", "Credit Limit", "Payment Terms", "Billing Address", "Notes"],
    "suppliers": ["Supplier ID", "Supplier Name", "Service Type", "Contact", "Phone/Email", "Payment Terms", "Status", "Performance Notes"],
}

DROPDOWNS = {
    "Source": ["Walk-In", "Phone", "Email", "WhatsApp", "Telegram", "Referral", "Repeat Client"],
    "Service Type": ["Air Ticket", "Hotel", "Tour Package", "Visa Support", "Transfer", "Insurance", "Other"],
    "Priority": ["Low", "Normal", "High", "Urgent", "VIP"],
    "Lead Status": ["New", "Qualified", "Quoted", "Follow-Up", "Confirmed", "Closed-Won", "Closed-Lost", "Dormant"],
    "Booked?": ["Yes", "No"],
    "Outcome": ["Won", "Lost-Price", "Lost-Timing", "Lost-No Response", "Cancelled"],
    "Quote Status": ["Draft", "Sent", "Follow-Up", "Accepted", "Expired", "Lost"],
    "Payment Status": ["Pending", "Part Paid", "Paid", "Credit Approved", "Overdue", "Refund Pending", "Refunded"],
    "Credit Approved?": ["Yes", "No"],
    "Handover Complete?": ["Yes", "No"],
    "Issue Status": ["Pending", "Confirmed", "Issued", "Reissued", "Cancelled", "Refunded"],
    "Refund Status": ["None", "Pending", "Submitted", "Approved", "Paid"],
    "AR Stage": ["Current", "Reminder 1", "Reminder 2", "Escalated", "Suspended"],
    "Severity": ["Level 1", "Level 2", "Level 3", "Legal", "Public"],
    "Status": ["Open", "Investigating", "Pending Client", "Resolved", "Closed", "Escalated"],
    "Client Informed?": ["Yes", "No"],
    "Type": ["Discount", "Credit", "Refund/Waiver", "Policy Override", "Client Dispute", "Other"],
    "Closed?": ["Yes", "No"],
    "Client Type": ["Retail", "Corporate Prepaid", "Corporate Credit", "VIP", "Strategic"],
}

ROLE_PERMISSIONS = {
    "Owner": ["*"],
    "Business Manager": ["*"],
    "Sales Agent": ["leads", "quotations", "clients", "bookings"],
    "Ticketing Officer": ["bookings", "quotations", "clients", "complaints"],
    "Finance Officer": ["bookings", "ar", "clients", "exceptions"],
    "Viewer": ["read_only"],
}

ROLES = list(ROLE_PERMISSIONS.keys())

# Fields the app assigns itself on create and refuses to let anyone change afterward.
# No id_field means that module's own identifier stays manual (e.g. Booking Ref holds
# a supplier/airline confirmation code, not an internal ID).
AUTO_ID_FIELDS = {
    "leads": {"id_field": "Lead ID", "date_field": "Inquiry Date", "prefix": "L"},
    "quotations": {"id_field": "Quote ID", "date_field": "Quote Date", "prefix": "Q"},
    "complaints": {"id_field": "Complaint ID", "date_field": "Date Received", "prefix": "C"},
    "bookings": {"date_field": "Booking Date"},
}

# Optional pick-an-existing-record fields: {module: {field_name: source_module}}
CROSS_REF_FIELDS = {
    "quotations": {"Lead ID": "leads"},
    "bookings": {"Quote ID": "quotations"},
}

NOTES_LIKE_FIELDS = {"Notes", "Remarks", "Reason", "Resolution", "Corrective Action", "Performance Notes", "Billing Address"}

_MODULE_DISPLAY_OVERRIDES = {"ar": "AR"}


def display_name(module: str) -> str:
    return _MODULE_DISPLAY_OVERRIDES.get(module, module.replace("_", " ").title())

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS).hex()
    return f"{_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        iterations_str, salt, digest = stored.split("$")
        iterations = int(iterations_str)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations).hex()
    return hmac.compare_digest(candidate, digest)


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


class AuthError(Exception):
    pass


class ValidationError(Exception):
    pass


class Database:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._init_schema()
        self._seed_admin()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'Sales Agent',
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    must_change_password INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crm_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module TEXT NOT NULL,
                    code TEXT,
                    title TEXT,
                    data TEXT NOT NULL,
                    created_by TEXT,
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_records_module ON crm_records(module)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_records_code ON crm_records(code)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    action TEXT NOT NULL,
                    module TEXT,
                    record_id INTEGER,
                    detail TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def _seed_admin(self):
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO users (username, full_name, role, password_hash, is_active, must_change_password, created_at) "
                    "VALUES (?, ?, ?, ?, 1, 1, ?)",
                    ("admin", "System Administrator", "Owner", hash_password("admin123"), utcnow_iso()),
                )
                conn.commit()

    def _audit(self, conn, username, action, module=None, record_id=None, detail=None):
        conn.execute(
            "INSERT INTO audit_log (username, action, module, record_id, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, action, module, record_id, detail, utcnow_iso()),
        )

    # ── Auth ─────────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise AuthError("Incorrect username or password")
            return dict(row)

    def change_password(self, username: str, current_password: str, new_password: str):
        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row or not verify_password(current_password, row["password_hash"]):
                raise AuthError("Current password is incorrect.")
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE username = ?",
                (hash_password(new_password), username),
            )
            self._audit(conn, username, "self_password_change")
            conn.commit()

    # ── Permissions ──────────────────────────────────────────────────────

    @staticmethod
    def can_access(role: str, module: str, write: bool = False) -> bool:
        perms = ROLE_PERMISSIONS.get(role, [])
        if "*" in perms:
            return True
        if "read_only" in perms:
            return not write
        return module in perms

    # ── Auto-ID generation (ported from server/app.py's _generate_sequence_id) ──

    def _generate_sequence_id(self, conn, module: str, prefix: str) -> str:
        today = datetime.utcnow().strftime("%Y%m%d")
        pattern = f"{prefix}-{today}-%"
        rows = conn.execute(
            "SELECT code FROM crm_records WHERE module = ? AND code LIKE ?", (module, pattern)
        ).fetchall()
        max_seq = 0
        for row in rows:
            try:
                max_seq = max(max_seq, int(row["code"].rsplit("-", 1)[-1]))
            except (ValueError, AttributeError):
                pass
        return f"{prefix}-{today}-{max_seq + 1:03d}"

    # ── Records ──────────────────────────────────────────────────────────

    def list_records(self, module: str, q: str = "") -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM crm_records WHERE module = ? ORDER BY updated_at DESC", (module,)
            ).fetchall()
        records = [self._row_to_record(r) for r in rows]
        if q:
            q_low = q.lower()
            records = [
                r for r in records
                if q_low in (r["code"] or "").lower()
                or q_low in (r["title"] or "").lower()
                or q_low in json.dumps(r["data"], default=str).lower()
            ]
        return records

    def get_record(self, record_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM crm_records WHERE id = ?", (record_id,)).fetchone()
        if not row:
            raise ValidationError("Record not found")
        return self._row_to_record(row)

    @staticmethod
    def _row_to_record(row) -> dict:
        d = dict(row)
        d["data"] = json.loads(d["data"]) if d["data"] else {}
        return d

    @staticmethod
    def _derive_code_title(module: str, data: dict) -> tuple:
        fields = MODULES.get(module, [])
        code = data.get(fields[0], "") if fields else ""
        title = data.get("Client Name") or data.get("Company") or data.get("Supplier Name") or code
        return code, title

    def create_record(self, module: str, data: dict, username: str) -> dict:
        if module not in MODULES:
            raise ValidationError("Unknown module")
        data = dict(data)
        with self._connect() as conn:
            auto_cfg = AUTO_ID_FIELDS.get(module)
            if auto_cfg:
                if "id_field" in auto_cfg:
                    data[auto_cfg["id_field"]] = self._generate_sequence_id(conn, module, auto_cfg["prefix"])
                if "date_field" in auto_cfg:
                    data[auto_cfg["date_field"]] = datetime.utcnow().date().isoformat()
            code, title = self._derive_code_title(module, data)
            now = utcnow_iso()
            cur = conn.execute(
                "INSERT INTO crm_records (module, code, title, data, created_by, updated_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (module, code, title, json.dumps(data), username, username, now, now),
            )
            self._audit(conn, username, "create", module, cur.lastrowid)
            conn.commit()
            return self.get_record(cur.lastrowid)

    def update_record(self, record_id: int, data: dict, username: str) -> dict:
        data = dict(data)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM crm_records WHERE id = ?", (record_id,)).fetchone()
            if not row:
                raise ValidationError("Record not found")
            module = row["module"]
            existing_data = json.loads(row["data"]) if row["data"] else {}
            auto_cfg = AUTO_ID_FIELDS.get(module)
            code = row["code"]
            if auto_cfg:
                if "id_field" in auto_cfg:
                    data[auto_cfg["id_field"]] = existing_data.get(auto_cfg["id_field"])
                    # code column stays locked to the original id too
                if "date_field" in auto_cfg:
                    data[auto_cfg["date_field"]] = existing_data.get(auto_cfg["date_field"])
            if not (auto_cfg and "id_field" in auto_cfg):
                code, _ = self._derive_code_title(module, data)
            _, title = self._derive_code_title(module, data)
            conn.execute(
                "UPDATE crm_records SET code = ?, title = ?, data = ?, updated_by = ?, updated_at = ? WHERE id = ?",
                (code, title, json.dumps(data), username, utcnow_iso(), record_id),
            )
            self._audit(conn, username, "update", module, record_id)
            conn.commit()
            return self.get_record(record_id)

    def delete_record(self, record_id: int, username: str, role: str):
        if role not in ("Owner", "Business Manager"):
            raise AuthError("Only Owner or Business Manager can delete records")
        with self._connect() as conn:
            row = conn.execute("SELECT module FROM crm_records WHERE id = ?", (record_id,)).fetchone()
            if not row:
                raise ValidationError("Record not found")
            conn.execute("DELETE FROM crm_records WHERE id = ?", (record_id,))
            self._audit(conn, username, "delete", row["module"], record_id)
            conn.commit()

    # ── Dashboard ────────────────────────────────────────────────────────

    def dashboard(self, role: str) -> dict:
        accessible = [m for m in MODULES if self.can_access(role, m, write=False)]
        with self._connect() as conn:
            counts = {}
            for m in accessible:
                counts[m] = conn.execute("SELECT COUNT(*) FROM crm_records WHERE module = ?", (m,)).fetchone()[0]

            open_leads = 0
            if "leads" in accessible:
                for row in conn.execute("SELECT data FROM crm_records WHERE module = 'leads'").fetchall():
                    d = json.loads(row["data"])
                    if d.get("Lead Status") not in ("Closed-Won", "Closed-Lost", "Dormant"):
                        open_leads += 1

            overdue_ar = 0
            if "ar" in accessible:
                today_str = datetime.utcnow().date().isoformat()
                for row in conn.execute("SELECT data FROM crm_records WHERE module = 'ar'").fetchall():
                    d = json.loads(row["data"])
                    if d.get("Payment Status") == "Paid":
                        continue
                    try:
                        inv = float(d.get("Invoice Amount") or 0)
                        paid = float(d.get("Amount Received") or 0)
                        due = str(d.get("Due Date") or "")[:10]
                        if inv - paid > 0 and due and due < today_str:
                            overdue_ar += 1
                    except (ValueError, TypeError):
                        pass

            open_complaints = 0
            if "complaints" in accessible:
                for row in conn.execute("SELECT data FROM crm_records WHERE module = 'complaints'").fetchall():
                    d = json.loads(row["data"])
                    if d.get("Status") not in ("Resolved", "Closed"):
                        open_complaints += 1

            open_exceptions = 0
            if "exceptions" in accessible:
                for row in conn.execute("SELECT data FROM crm_records WHERE module = 'exceptions'").fetchall():
                    d = json.loads(row["data"])
                    if d.get("Closed?") != "Yes":
                        open_exceptions += 1

        return {
            "counts": counts,
            "open_leads": open_leads,
            "overdue_ar": overdue_ar,
            "open_complaints": open_complaints,
            "open_exceptions": open_exceptions,
        }

    # ── Users / Admin ────────────────────────────────────────────────────

    def list_users(self) -> list:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY username").fetchall()
        return [dict(r) for r in rows]

    def create_or_update_user(self, username: str, full_name: str, role: str, password: str, actor: str):
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if row:
                sets, params = [], []
                if password:
                    if len(password) < 8:
                        raise ValidationError("Password must be at least 8 characters.")
                    sets.append("password_hash = ?")
                    params.append(hash_password(password))
                    sets.append("must_change_password = 1")
                if role:
                    sets.append("role = ?")
                    params.append(role)
                if full_name:
                    sets.append("full_name = ?")
                    params.append(full_name)
                if sets:
                    params.append(username)
                    conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE username = ?", params)
            else:
                if not password or len(password) < 8:
                    raise ValidationError("Password must be at least 8 characters.")
                conn.execute(
                    "INSERT INTO users (username, full_name, role, password_hash, is_active, must_change_password, created_at) "
                    "VALUES (?, ?, ?, ?, 1, 1, ?)",
                    (username, full_name or username, role or "Sales Agent", hash_password(password), utcnow_iso()),
                )
            self._audit(conn, actor, "user_change", detail=username)
            conn.commit()

    def reset_password(self, username: str, new_password: str, actor: str):
        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                raise ValidationError("User not found")
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE username = ?",
                (hash_password(new_password), username),
            )
            self._audit(conn, actor, "password_reset", detail=username)
            conn.commit()

    def set_user_active(self, username: str, active: bool, actor: str):
        if username == actor and not active:
            raise ValidationError("Cannot deactivate your own account")
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                raise ValidationError("User not found")
            conn.execute("UPDATE users SET is_active = ? WHERE username = ?", (1 if active else 0, username))
            self._audit(conn, actor, "activate_user" if active else "deactivate_user", detail=username)
            conn.commit()


_db_instance = None
_db_instance_lock = threading.Lock()


def get_db(app_dir: str) -> Database:
    """Singleton accessor so every screen shares the same connection settings."""
    global _db_instance
    with _db_instance_lock:
        if _db_instance is None:
            os.makedirs(app_dir, exist_ok=True)
            _db_instance = Database(os.path.join(app_dir, "sa_us_erp.db"))
        return _db_instance
