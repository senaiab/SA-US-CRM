import configparser
import json
import re
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Text, func, or_, text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import OperationalError

BASE_DIR = Path(__file__).resolve().parent
config = configparser.ConfigParser()
config.read(BASE_DIR / "server_config.ini")

DATABASE_URL = config.get("database", "url", fallback="sqlite:///./sa_us_erp.db")
_secret = config.get("server", "secret_key", fallback="")
if not _secret or _secret == "CHANGE_THIS_TO_A_RANDOM_SECRET":
    import secrets as _secrets
    SECRET_KEY = _secrets.token_hex(32)
    print("WARNING: secret_key not configured in server_config.ini. A random key was generated — all sessions expire on restart. Set a fixed secret_key.")
else:
    SECRET_KEY = _secret

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 10
_RATE_WINDOW = 300
_RATE_MAX = 5
_login_failures: dict = defaultdict(list)
_admin_write_attempts: dict = defaultdict(list)
_database_error: Optional[str] = None

# DSR response window (Ethiopian Proclamation 1321/2024 Art. 25: 30 days)
DSR_RESPONSE_DAYS = int(config.get("compliance", "dsr_response_days", fallback="30"))

# PCI-DSS: detect card numbers and CVV keywords in free-text fields
_CARD_RE = re.compile(r'(?<!\d)(\d[ \-]?){13,19}(?!\d)')
_CVV_RE  = re.compile(r'\b(cvv2?|cvc2?|security\s*code|card\s*verification\s*(?:number|value)?)\b', re.I)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    full_name = Column(String(150), nullable=False, default="")
    email = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="Sales/Booking User")
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
    must_change_password = Column(Integer, nullable=False, default=0)
    last_login = Column(DateTime, nullable=True)
    failed_login_count = Column(Integer, nullable=False, default=0)
    privacy_training_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class CRMRecord(Base):
    __tablename__ = "crm_records"
    id = Column(Integer, primary_key=True, index=True)
    module = Column(String(80), index=True, nullable=False)
    code = Column(String(80), index=True, nullable=True)
    title = Column(String(255), index=True, nullable=True)
    data = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(80), nullable=True)
    updated_by = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    version = Column(Integer, nullable=False, default=1)
    deleted_at = Column(DateTime, nullable=True, default=None)
    is_anonymized = Column(Integer, nullable=False, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=True)
    action = Column(String(80), nullable=False)
    module = Column(String(80), nullable=True)
    record_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id = Column(Integer, primary_key=True)
    subject_name = Column(String(255), nullable=False)
    subject_ref = Column(String(80), nullable=True)
    purpose = Column(String(255), nullable=False)
    lawful_basis = Column(String(80), nullable=False)
    given = Column(Integer, nullable=False, default=1)
    given_at = Column(DateTime, nullable=True)
    withdrawn_at = Column(DateTime, nullable=True)
    method = Column(String(80), nullable=True)
    scope = Column(Text, nullable=True)
    created_by = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class DataSubjectRequest(Base):
    __tablename__ = "dsr_requests"
    id = Column(Integer, primary_key=True)
    request_type = Column(String(80), nullable=False)
    subject_name = Column(String(255), nullable=False)
    subject_email = Column(String(255), nullable=True)
    subject_phone = Column(String(80), nullable=True)
    status = Column(String(80), nullable=False, default="Received")
    received_at = Column(DateTime, default=utcnow)
    due_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    handled_by = Column(String(80), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class BreachRecord(Base):
    __tablename__ = "breach_records"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(40), nullable=False, default="Medium")
    discovered_at = Column(DateTime, nullable=True)
    reported_at = Column(DateTime, nullable=True)
    reported_to = Column(String(255), nullable=True)
    affected_count = Column(Integer, default=0)
    data_categories = Column(Text, nullable=True)
    risk_level = Column(String(40), nullable=True, default="Medium")
    status = Column(String(80), nullable=False, default="Open")
    containment_actions = Column(Text, nullable=True)
    dpa_notified = Column(Integer, default=0)
    dpa_notified_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class RetentionSchedule(Base):
    __tablename__ = "retention_schedules"
    id = Column(Integer, primary_key=True)
    module = Column(String(80), nullable=False)
    category = Column(String(255), nullable=False)
    retention_years = Column(Integer, nullable=False, default=7)
    legal_hold = Column(Integer, default=0)
    disposal_method = Column(String(80), nullable=True, default="delete")
    review_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ThirdPartyProcessor(Base):
    __tablename__ = "third_party_processors"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    service = Column(String(255), nullable=True)
    country = Column(String(80), nullable=True)
    transfer_mechanism = Column(String(80), nullable=True)
    dpa_signed = Column(Integer, default=0)
    dpa_date = Column(DateTime, nullable=True)
    review_date = Column(DateTime, nullable=True)
    contact = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ExportLog(Base):
    __tablename__ = "export_logs"
    id = Column(Integer, primary_key=True)
    module = Column(String(80), nullable=True)
    record_count = Column(Integer, default=0)
    exported_by = Column(String(80), nullable=False)
    purpose = Column(String(255), nullable=True)
    approved_by = Column(String(80), nullable=True)
    destination = Column(String(255), nullable=True)
    cross_border = Column(Integer, default=0)
    destination_country = Column(String(80), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class PrivacyTraining(Base):
    __tablename__ = "privacy_training"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False, index=True)
    training_name = Column(String(255), nullable=False)
    completed_at = Column(DateTime, nullable=False)
    expiry_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=utcnow)


# ── Modules ───────────────────────────────────────────────────────────────────

MODULES = {
    "leads": [
        "Lead ID", "Inquiry Date", "Client Name", "Company", "Contact", "Phone/Email",
        "Source", "Service Type", "Priority", "Assigned Owner", "Lead Status",
        "Next Action Date", "Last Contact Date", "Quote ID", "Booked?", "Outcome",
        "Lawful Basis", "Privacy Notice Sent?", "Privacy Notice Date", "Notes",
    ],
    "quotations": [
        "Quote ID", "Lead ID", "Quote Date", "Client Name", "Service Type", "Consultant",
        "Quoted Amount", "Cost Estimate", "Currency", "Validity Date", "Quote Status",
        "Revision No", "Accepted Date", "Booking Ref", "Lost Reason", "Notes",
    ],
    "bookings": [
        "Booking Ref", "Quote ID", "Lead ID", "Booking Date", "Client Name",
        "Service Type", "Consultant", "Ticketing Owner", "Supplier/Airline", "Passenger/Pax",
        "Passenger Nationality", "Passport Number", "Date of Birth",
        "Contact Purpose", "Contact Consent", "Contact Refused?", "IATA Data Usage",
        "Gross Sale", "Supplier Cost", "Payment Status", "Credit Approved?",
        "Invoice No", "Invoice Date", "Due Date",
        "Handover Complete?", "Issue Status", "Issue Date", "Refund Status", "Remarks",
    ],
    "ar": [
        "Invoice No", "Client Name", "Booking Ref", "Invoice Date", "Due Date",
        "Invoice Amount", "Amount Received", "Payment Status", "AR Stage",
        "Owner", "Last Follow-Up", "Next Follow-Up", "Comments",
    ],
    "complaints": [
        "Complaint ID", "Date Received", "Client Name", "Booking Ref", "Issue Category",
        "Severity", "Owner", "Status", "Root Cause", "Resolution Date",
        "Client Informed?", "Corrective Action", "Notes",
    ],
    "exceptions": [
        "Exception ID", "Date", "Type", "Client/Case", "Related Ref",
        "Requested By", "Approved By", "Financial Impact", "Reason",
        "Resolution", "Closed?", "Notes",
    ],
    "clients": [
        "Client ID", "Client Name", "Company", "Phone", "Email", "Client Type",
        "Credit Limit", "Payment Terms", "Billing Address",
        "Lawful Basis", "Privacy Notice Sent?", "Privacy Notice Date",
        "Data Retention Category", "Notes",
    ],
    "suppliers": [
        "Supplier ID", "Supplier Name", "Service Type", "Contact", "Phone/Email",
        "Payment Terms", "Status", "Performance Notes",
    ],
}

# Fields the server assigns itself on create and refuses to let any client change afterward.
# No id_field means that module's own identifier stays manual (e.g. Booking Ref holds a
# supplier/airline confirmation code, not an internal ID).
AUTO_ID_FIELDS = {
    "leads": {"id_field": "Lead ID", "date_field": "Inquiry Date", "prefix": "L"},
    "quotations": {"id_field": "Quote ID", "date_field": "Quote Date", "prefix": "Q"},
    "complaints": {"id_field": "Complaint ID", "date_field": "Date Received", "prefix": "C"},
    "bookings": {"date_field": "Booking Date"},
}

_id_seq_lock = threading.Lock()


def _generate_sequence_id(db: Session, module: str, prefix: str) -> str:
    """Builds PREFIX-YYYYMMDD-NNN, sequential per day per module. Uniqueness is only
    guaranteed within a single server process, which matches how this app is deployed
    (one uvicorn process, no --workers)."""
    today = utcnow().strftime("%Y%m%d")
    pattern = f"{prefix}-{today}-%"
    with _id_seq_lock:
        codes = db.query(CRMRecord.code).filter(CRMRecord.module == module, CRMRecord.code.like(pattern)).all()
        max_seq = 0
        for (code,) in codes:
            try:
                max_seq = max(max_seq, int(code.rsplit("-", 1)[-1]))
            except (ValueError, AttributeError):
                pass
        return f"{prefix}-{today}-{max_seq + 1:03d}"

# ── RBAC ──────────────────────────────────────────────────────────────────────

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    # Legacy names preserved for backward compatibility
    "Owner": ["*"],
    "Business Manager": ["*"],
    "Sales Agent": ["leads", "quotations", "clients", "bookings"],
    "Ticketing Officer": ["bookings", "quotations", "clients", "complaints"],
    "Finance Officer": ["bookings", "ar", "clients", "exceptions"],
    # New role names
    "Super Admin": ["*"],
    "Manager": ["*"],
    "DPO/Privacy Officer": ["*"],
    "Sales/Booking User": ["leads", "quotations", "clients", "bookings"],
    "Customer Service User": ["bookings", "quotations", "clients", "complaints"],
    "Finance User": ["bookings", "ar", "clients", "exceptions"],
    "Viewer": ["read_only"],
    "Auditor": ["read_only"],
}

ADMIN_ROLES = frozenset({"Owner", "Business Manager", "Super Admin", "Manager"})
COMPLIANCE_ROLES = frozenset({"Owner", "Business Manager", "Super Admin", "Manager", "DPO/Privacy Officer"})
DPO_ROLES = frozenset({"Owner", "Super Admin", "DPO/Privacy Officer"})
AUDIT_READ_ROLES = ADMIN_ROLES | frozenset({"Auditor", "DPO/Privacy Officer"})

ALL_ROLES = sorted(ROLE_PERMISSIONS.keys())


# ── Data masking ──────────────────────────────────────────────────────────────

def mask_passport(v: str) -> str:
    if not v:
        return ""
    v = str(v)
    if len(v) <= 4:
        return "***"
    return v[:2] + "*" * (len(v) - 4) + v[-2:]


def mask_phone(v: str) -> str:
    if not v:
        return ""
    v = str(v)
    if len(v) <= 5:
        return "***"
    return v[:3] + "*" * (len(v) - 5) + v[-2:]


def mask_email(v: str) -> str:
    if not v or "@" not in str(v):
        return "***"
    local, domain = str(v).split("@", 1)
    return (local[0] if local else "") + "***@" + domain


_MASK_MAP: Dict[str, Dict[str, Any]] = {
    "bookings": {"Passport Number": mask_passport, "Date of Birth": lambda _: "****-**-**"},
    "clients":  {"Phone": mask_phone, "Email": mask_email},
    "leads":    {"Phone/Email": mask_phone},
}


def mask_record(module: str, data: dict) -> dict:
    """Return copy of data with PII fields masked for non-privileged views."""
    field_fns = _MASK_MAP.get(module, {})
    if not field_fns:
        return data
    out = dict(data)
    for field, fn in field_fns.items():
        if out.get(field):
            out[field] = fn(str(out[field]))
    return out


# ── PCI-DSS card detection ────────────────────────────────────────────────────

def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def detect_card_data(data: dict) -> Optional[str]:
    """
    Return the first field name that appears to contain a card number or CVV keyword,
    or None if clean. Requires Luhn check + minimum digit length to reduce false positives.
    """
    for field, v in data.items():
        if not v:
            continue
        text = str(v)
        if _CVV_RE.search(text):
            return field
        for m in _CARD_RE.findall(text):
            digits = re.sub(r'[ \-]', '', m if isinstance(m, str) else "".join(m))
            if len(digits) >= 13 and _luhn_ok(digits):
                return field
    return None


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain_password, password_hash):
    return pwd_context.verify(plain_password, password_hash)


def validate_password(plain_password: str):
    if len(plain_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")


def get_password_hash(password):
    validate_password(password)
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username, User.is_active == 1).first()
    if user is None:
        raise credentials_exception
    return user


def can_access(user: User, module: str, write=False):
    perms = ROLE_PERMISSIONS.get(user.role, [])
    if "*" in perms:
        return True
    if "read_only" in perms:
        return not write
    return module in perms


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def audit(
    db: Session,
    username: str,
    action: str,
    module: Optional[str] = None,
    record_id: Optional[int] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    reason: Optional[str] = None,
):
    db.add(AuditLog(
        username=username, action=action, module=module, record_id=record_id,
        detail=detail, ip_address=ip_address,
        old_value=old_value, new_value=new_value, reason=reason,
    ))


def _check_rate_limit(username: str):
    now = time.time()
    recent = [t for t in _login_failures[username] if now - t < _RATE_WINDOW]
    _login_failures[username] = recent
    if len(recent) >= _RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Wait 5 minutes and try again.")


def _record_failure(username: str):
    _login_failures[username].append(time.time())


def _check_admin_rate_limit(username: str):
    now = time.time()
    recent = [t for t in _admin_write_attempts[username] if now - t < _RATE_WINDOW]
    _admin_write_attempts[username] = recent
    if len(recent) >= 20:
        raise HTTPException(status_code=429, detail="Too many admin operations. Wait 5 minutes.")
    _admin_write_attempts[username].append(now)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    full_name: str
    must_change_password: bool = False


class RecordIn(BaseModel):
    module: str
    code: Optional[str] = None
    title: Optional[str] = None
    data: Dict[str, Any]
    version: Optional[int] = None


class RecordOut(BaseModel):
    id: int
    module: str
    code: Optional[str]
    title: Optional[str]
    data: Dict[str, Any]
    created_by: Optional[str]
    updated_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    version: int = 1
    is_anonymized: int = 0


class PasswordChange(BaseModel):
    username: str
    new_password: str
    role: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None


class SelfPasswordChange(BaseModel):
    current_password: str
    new_password: str


class ConsentIn(BaseModel):
    subject_name: str
    subject_ref: Optional[str] = None
    purpose: str
    lawful_basis: str
    given: int = 1
    given_at: Optional[str] = None
    withdrawn_at: Optional[str] = None
    method: Optional[str] = None
    scope: Optional[str] = None


class DSRIn(BaseModel):
    request_type: str
    subject_name: str
    subject_email: Optional[str] = None
    subject_phone: Optional[str] = None
    status: Optional[str] = "Received"
    handled_by: Optional[str] = None
    notes: Optional[str] = None


class DSRUpdate(BaseModel):
    status: Optional[str] = None
    handled_by: Optional[str] = None
    notes: Optional[str] = None
    completed_at: Optional[str] = None


class BreachIn(BaseModel):
    title: str
    description: Optional[str] = None
    severity: Optional[str] = "Medium"
    discovered_at: Optional[str] = None
    reported_at: Optional[str] = None
    reported_to: Optional[str] = None
    affected_count: Optional[int] = 0
    data_categories: Optional[str] = None
    risk_level: Optional[str] = "Medium"
    status: Optional[str] = "Open"
    containment_actions: Optional[str] = None
    dpa_notified: Optional[int] = 0
    dpa_notified_at: Optional[str] = None
    notes: Optional[str] = None


class RetentionIn(BaseModel):
    module: str
    category: str
    retention_years: int
    legal_hold: Optional[int] = 0
    disposal_method: Optional[str] = "delete"
    review_date: Optional[str] = None
    notes: Optional[str] = None


class ProcessorIn(BaseModel):
    name: str
    service: Optional[str] = None
    country: Optional[str] = None
    transfer_mechanism: Optional[str] = None
    dpa_signed: Optional[int] = 0
    dpa_date: Optional[str] = None
    review_date: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None


class TrainingIn(BaseModel):
    username: str
    training_name: str
    completed_at: str
    expiry_date: Optional[str] = None
    notes: Optional[str] = None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19])
    except Exception:
        return None


# ── Database initialization ───────────────────────────────────────────────────

def initialize_database():
    global _database_error
    try:
        Base.metadata.create_all(bind=engine)
        with engine.connect() as conn:
            # New columns on existing tables — ignore errors if column already exists
            for table, col, definition in [
                ("users", "must_change_password", "INT NOT NULL DEFAULT 0"),
                ("users", "email", "VARCHAR(255) NULL"),
                ("users", "last_login", "DATETIME NULL"),
                ("users", "failed_login_count", "INT NOT NULL DEFAULT 0"),
                ("users", "privacy_training_date", "DATETIME NULL"),
                ("crm_records", "version", "INT NOT NULL DEFAULT 1"),
                ("crm_records", "deleted_at", "DATETIME NULL DEFAULT NULL"),
                ("crm_records", "is_anonymized", "INT NOT NULL DEFAULT 0"),
                ("audit_log", "ip_address", "VARCHAR(45) NULL"),
                ("audit_log", "old_value", "TEXT NULL"),
                ("audit_log", "new_value", "TEXT NULL"),
                ("audit_log", "reason", "VARCHAR(255) NULL"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                    conn.commit()
                except Exception:
                    conn.rollback()

        db = SessionLocal()
        try:
            if not db.query(User).filter(User.username == "admin").first():
                db.add(User(
                    username="admin",
                    full_name="System Administrator",
                    role="Super Admin",
                    password_hash=get_password_hash("admin123"),
                    must_change_password=1,
                ))
                db.commit()
        finally:
            db.close()
        _database_error = None
        return True
    except OperationalError as e:
        _database_error = str(e)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not initialize_database():
        print("Database connection failed. Server is running in setup mode.")
        print("Check database and server_config.ini, then retry /health or restart the server.")
        print(_database_error)
    yield


app = FastAPI(title="SA-US ERP Local Network Server", version="2.9.0", lifespan=lifespan)
_cors_origins = [o.strip() for o in config.get("server", "cors_origins", fallback="http://127.0.0.1,http://localhost").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_static_dir = BASE_DIR / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/ui", response_class=HTMLResponse)
@app.get("/ui/{path:path}", response_class=HTMLResponse)
def serve_ui():
    ui_file = _static_dir / "index.html"
    if not ui_file.exists():
        raise HTTPException(404, "Web UI not found")
    return HTMLResponse(content=ui_file.read_text(encoding="utf-8"))


@app.get("/health")
def health():
    if not initialize_database():
        raise HTTPException(
            status_code=503,
            detail={
                "status": "setup_required",
                "message": "Database connection failed. Check database and server_config.ini.",
                "database_error": _database_error,
            },
        )
    return {"status": "ok", "server_time": utcnow().isoformat(), "modules": list(MODULES.keys())}


@app.post("/token", response_model=Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    _check_rate_limit(form_data.username)
    user = db.query(User).filter(User.username == form_data.username, User.is_active == 1).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        _record_failure(form_data.username)
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            db.commit()
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    _login_failures.pop(form_data.username, None)
    user.last_login = utcnow()
    user.failed_login_count = 0
    db.commit()
    audit(db, user.username, "login", ip_address=_client_ip(request))
    db.commit()
    token = create_access_token(data={"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "role": user.role, "full_name": user.full_name, "must_change_password": bool(user.must_change_password)}


@app.get("/modules")
def modules(user: User = Depends(get_current_user)):
    return {"modules": MODULES, "role": user.role, "permissions": ROLE_PERMISSIONS.get(user.role, []), "all_roles": ALL_ROLES}


@app.get("/records/{module}", response_model=List[RecordOut])
def list_records(module: str, q: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if module not in MODULES:
        raise HTTPException(404, "Unknown module")
    if not can_access(user, module, write=False):
        raise HTTPException(403, "Not allowed")
    query = db.query(CRMRecord).filter(CRMRecord.module == module, CRMRecord.deleted_at == None)
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(CRMRecord.code.ilike(pattern), CRMRecord.title.ilike(pattern)))
    records = query.order_by(CRMRecord.updated_at.desc()).limit(1000).all()
    if q:
        q_low = q.lower()
        records = [r for r in records if q_low in (r.code or "").lower() or q_low in (r.title or "").lower() or q_low in json.dumps(r.data, default=str).lower()]
    return records


@app.post("/records", response_model=RecordOut)
def create_record(request: Request, record: RecordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if record.module not in MODULES:
        raise HTTPException(404, "Unknown module")
    if not can_access(user, record.module, write=True):
        raise HTTPException(403, "Not allowed")
    auto_cfg = AUTO_ID_FIELDS.get(record.module)
    if auto_cfg:
        if "id_field" in auto_cfg:
            record.data[auto_cfg["id_field"]] = _generate_sequence_id(db, record.module, auto_cfg["prefix"])
            record.code = record.data[auto_cfg["id_field"]]
        if "date_field" in auto_cfg:
            record.data[auto_cfg["date_field"]] = utcnow().date().isoformat()
    # PCI-DSS: block card numbers / CVV in any field
    bad_field = detect_card_data(record.data)
    if bad_field:
        audit(db, user.username, "pci_blocked", record.module, detail=f"card data detected in field: {bad_field}", ip_address=_client_ip(request))
        db.commit()
        raise HTTPException(400, f"PCI-DSS policy violation: field '{bad_field}' appears to contain a card number or CVV. Do not store card data.")
    db_record = CRMRecord(module=record.module, code=record.code, title=record.title, data=record.data, created_by=user.username, updated_by=user.username)
    db.add(db_record)
    db.flush()
    audit(db, user.username, "create", record.module, db_record.id, ip_address=_client_ip(request))
    db.commit()
    db.refresh(db_record)
    return db_record


@app.put("/records/{record_id}", response_model=RecordOut)
def update_record(record_id: int, request: Request, record: RecordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_record = db.query(CRMRecord).filter(CRMRecord.id == record_id, CRMRecord.deleted_at == None).first()
    if not db_record:
        raise HTTPException(404, "Record not found")
    if not can_access(user, db_record.module, write=True):
        raise HTTPException(403, "Not allowed")
    if record.version is not None and record.version != db_record.version:
        raise HTTPException(409, "Record was modified by another user. Reload and try again.")
    auto_cfg = AUTO_ID_FIELDS.get(db_record.module)
    if auto_cfg:
        if "id_field" in auto_cfg:
            record.data[auto_cfg["id_field"]] = db_record.data.get(auto_cfg["id_field"])
            record.code = db_record.code
        if "date_field" in auto_cfg:
            record.data[auto_cfg["date_field"]] = db_record.data.get(auto_cfg["date_field"])
    bad_field = detect_card_data(record.data)
    if bad_field:
        audit(db, user.username, "pci_blocked", db_record.module, record_id, detail=f"card data detected in field: {bad_field}", ip_address=_client_ip(request))
        db.commit()
        raise HTTPException(400, f"PCI-DSS policy violation: field '{bad_field}' appears to contain a card number or CVV. Do not store card data.")
    old_val = json.dumps(db_record.data, default=str)
    db_record.code = record.code
    db_record.title = record.title
    # Merge incoming data over existing — preserves server-masking of sensitive fields
    # when non-privileged users omit them from the payload.
    merged = dict(db_record.data or {})
    merged.update(record.data)
    db_record.data = merged
    db_record.updated_by = user.username
    db_record.updated_at = utcnow()
    db_record.version = (db_record.version or 1) + 1
    audit(db, user.username, "update", db_record.module, db_record.id, ip_address=_client_ip(request), old_value=old_val[:2000])
    db.commit()
    db.refresh(db_record)
    return db_record


@app.delete("/records/{record_id}")
def delete_record(record_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_record = db.query(CRMRecord).filter(CRMRecord.id == record_id, CRMRecord.deleted_at == None).first()
    if not db_record:
        raise HTTPException(404, "Record not found")
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only administrators can delete records")
    db_record.deleted_at = utcnow()
    audit(db, user.username, "delete", db_record.module, record_id, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


@app.post("/records/{record_id}/anonymize")
def anonymize_record(record_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Irreversibly remove PII from a record. DPO/Privacy Officer or Super Admin only."""
    if user.role not in DPO_ROLES:
        raise HTTPException(403, "Only DPO/Privacy Officer or Super Admin can anonymize records")
    db_record = db.query(CRMRecord).filter(CRMRecord.id == record_id).first()
    if not db_record:
        raise HTTPException(404, "Record not found")
    if db_record.is_anonymized:
        raise HTTPException(400, "Record is already anonymized")
    ANON_FIELDS = {
        "bookings": ["Passenger/Pax", "Passport Number", "Date of Birth", "Passenger Nationality", "Client Name"],
        "clients":  ["Client Name", "Phone", "Email", "Billing Address"],
        "leads":    ["Client Name", "Contact", "Phone/Email"],
    }
    old_val = json.dumps(db_record.data, default=str)
    new_data = dict(db_record.data or {})
    for field in ANON_FIELDS.get(db_record.module, []):
        if field in new_data:
            new_data[field] = "[ANONYMIZED]"
    db_record.data = new_data
    db_record.is_anonymized = 1
    db_record.updated_at = utcnow()
    audit(db, user.username, "anonymize", db_record.module, record_id, ip_address=_client_ip(request), old_value=old_val[:2000], reason="data_subject_request")
    db.commit()
    db.refresh(db_record)
    return {"ok": True, "id": record_id}


@app.get("/trash/{module}", response_model=List[RecordOut])
def list_trash(module: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if module not in MODULES:
        raise HTTPException(404, "Unknown module")
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Not allowed")
    return db.query(CRMRecord).filter(CRMRecord.module == module, CRMRecord.deleted_at != None).order_by(CRMRecord.deleted_at.desc()).all()


@app.post("/records/{record_id}/restore", response_model=RecordOut)
def restore_record(record_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_record = db.query(CRMRecord).filter(CRMRecord.id == record_id, CRMRecord.deleted_at != None).first()
    if not db_record:
        raise HTTPException(404, "Deleted record not found")
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Not allowed")
    db_record.deleted_at = None
    audit(db, user.username, "restore", db_record.module, record_id)
    db.commit()
    db.refresh(db_record)
    return db_record


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _dashboard_sql_metrics(db: Session) -> dict:
    open_leads = db.execute(text(
        "SELECT COUNT(*) FROM crm_records WHERE module='leads' AND deleted_at IS NULL "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$.\"Lead Status\"')), '') "
        "NOT IN ('Closed-Won', 'Closed-Lost', 'Dormant')"
    )).scalar() or 0

    open_complaints = db.execute(text(
        "SELECT COUNT(*) FROM crm_records WHERE module='complaints' AND deleted_at IS NULL "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$.Status')), '') "
        "NOT IN ('Resolved', 'Closed')"
    )).scalar() or 0

    open_exceptions = db.execute(text(
        "SELECT COUNT(*) FROM crm_records WHERE module='exceptions' AND deleted_at IS NULL "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$.\"Closed?\"')), '') != 'Yes'"
    )).scalar() or 0

    today_str = datetime.today().date().isoformat()
    ar_rows = db.execute(text(
        "SELECT "
        "  JSON_UNQUOTE(JSON_EXTRACT(data, '$.\"Invoice Amount\"')), "
        "  JSON_UNQUOTE(JSON_EXTRACT(data, '$.\"Amount Received\"')) "
        "FROM crm_records WHERE module='ar' AND deleted_at IS NULL "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$.\"Payment Status\"')), '') != 'Paid' "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$.\"Due Date\"')), '') < :today"
    ), {"today": today_str}).fetchall()
    overdue_ar = sum(1 for inv, paid in ar_rows if _safe_float(inv) - _safe_float(paid) > 0)

    return {"open_leads": open_leads, "overdue_ar": overdue_ar, "open_complaints": open_complaints, "open_exceptions": open_exceptions}


def _safe_float(v) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _dashboard_python_metrics(db: Session) -> dict:
    open_leads = sum(1 for r in db.query(CRMRecord).filter(CRMRecord.module == "leads", CRMRecord.deleted_at == None).all()
                     if (r.data or {}).get("Lead Status") not in ["Closed-Won", "Closed-Lost", "Dormant"])

    today = datetime.today().date()
    overdue_ar = 0
    for rec in db.query(CRMRecord).filter(CRMRecord.module == "ar", CRMRecord.deleted_at == None).all():
        d = rec.data or {}
        try:
            if _safe_float(d.get("Invoice Amount")) - _safe_float(d.get("Amount Received")) > 0:
                due = d.get("Due Date")
                if due and datetime.fromisoformat(str(due)).date() < today:
                    overdue_ar += 1
        except Exception:
            pass

    open_complaints = sum(1 for r in db.query(CRMRecord).filter(CRMRecord.module == "complaints", CRMRecord.deleted_at == None).all()
                          if (r.data or {}).get("Status") not in ["Resolved", "Closed"])
    open_exceptions = sum(1 for r in db.query(CRMRecord).filter(CRMRecord.module == "exceptions", CRMRecord.deleted_at == None).all()
                          if (r.data or {}).get("Closed?") != "Yes")

    return {"open_leads": open_leads, "overdue_ar": overdue_ar, "open_complaints": open_complaints, "open_exceptions": open_exceptions}


@app.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accessible = [m for m in MODULES if can_access(user, m, write=False)]
    count_rows = db.query(CRMRecord.module, func.count(CRMRecord.id)).filter(
        CRMRecord.module.in_(accessible), CRMRecord.deleted_at == None
    ).group_by(CRMRecord.module).all()
    counts = {m: 0 for m in accessible}
    for module, cnt in count_rows:
        if module in counts:
            counts[module] = cnt
    try:
        metrics = _dashboard_sql_metrics(db)
    except Exception:
        metrics = _dashboard_python_metrics(db)
    return {"counts": counts, **metrics}


@app.get("/reminders")
def reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.today().date()
    week_ahead = (today + timedelta(days=7)).isoformat()
    today_str = today.isoformat()
    result: Dict[str, List] = {"overdue_leads": [], "upcoming_leads": [], "overdue_ar": []}

    if can_access(user, "leads", write=False):
        for rec in db.query(CRMRecord).filter(CRMRecord.module == "leads", CRMRecord.deleted_at == None).all():
            d = rec.data or {}
            if d.get("Lead Status") in ["Closed-Won", "Closed-Lost", "Dormant"]:
                continue
            nad = str(d.get("Next Action Date") or "")[:10]
            if nad:
                if nad < today_str:
                    result["overdue_leads"].append({"id": rec.id, "code": rec.code, "title": rec.title, "next_action_date": nad})
                elif nad <= week_ahead:
                    result["upcoming_leads"].append({"id": rec.id, "code": rec.code, "title": rec.title, "next_action_date": nad})

    if can_access(user, "ar", write=False):
        for rec in db.query(CRMRecord).filter(CRMRecord.module == "ar", CRMRecord.deleted_at == None).all():
            d = rec.data or {}
            if d.get("Payment Status") == "Paid":
                continue
            try:
                if _safe_float(d.get("Invoice Amount")) - _safe_float(d.get("Amount Received")) > 0:
                    due = str(d.get("Due Date") or "")[:10]
                    if due and due < today_str:
                        result["overdue_ar"].append({"id": rec.id, "code": rec.code, "title": rec.title, "due_date": due})
            except Exception:
                pass

    return result


@app.get("/search")
def global_search(q: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not q or len(q) < 2:
        raise HTTPException(400, "Query must be at least 2 characters")
    accessible = [m for m in MODULES if can_access(user, m, write=False)]
    pattern = f"%{q}%"
    records = db.query(CRMRecord).filter(
        CRMRecord.module.in_(accessible), CRMRecord.deleted_at == None,
        or_(CRMRecord.code.ilike(pattern), CRMRecord.title.ilike(pattern)),
    ).order_by(CRMRecord.updated_at.desc()).limit(50).all()
    q_low = q.lower()
    return [r for r in records if q_low in (r.code or "").lower() or q_low in (r.title or "").lower() or q_low in json.dumps(r.data, default=str).lower()]


# ── Compliance endpoints ───────────────────────────────────────────────────────

def _require_compliance(user: User):
    if user.role not in COMPLIANCE_ROLES:
        raise HTTPException(403, "Compliance module access requires Manager, DPO/Privacy Officer, or Super Admin role")


def _require_dpo(user: User):
    if user.role not in DPO_ROLES:
        raise HTTPException(403, "This action requires DPO/Privacy Officer or Super Admin role")


# — Consent records —

@app.get("/compliance/consent")
def list_consent(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    rows = db.query(ConsentRecord).order_by(ConsentRecord.created_at.desc()).limit(500).all()
    return [{"id": r.id, "subject_name": r.subject_name, "subject_ref": r.subject_ref, "purpose": r.purpose,
             "lawful_basis": r.lawful_basis, "given": r.given,
             "given_at": r.given_at.isoformat() if r.given_at else None,
             "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
             "method": r.method, "scope": r.scope, "created_by": r.created_by,
             "created_at": r.created_at.isoformat()} for r in rows]


@app.post("/compliance/consent", status_code=201)
def create_consent(payload: ConsentIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    row = ConsentRecord(
        subject_name=payload.subject_name, subject_ref=payload.subject_ref,
        purpose=payload.purpose, lawful_basis=payload.lawful_basis,
        given=payload.given, given_at=_parse_dt(payload.given_at),
        withdrawn_at=_parse_dt(payload.withdrawn_at),
        method=payload.method, scope=payload.scope, created_by=user.username,
    )
    db.add(row)
    db.flush()
    audit(db, user.username, "consent_create", record_id=row.id, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True, "id": row.id}


@app.put("/compliance/consent/{cid}")
def update_consent(cid: int, payload: ConsentIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    row = db.query(ConsentRecord).filter(ConsentRecord.id == cid).first()
    if not row:
        raise HTTPException(404, "Not found")
    row.subject_name = payload.subject_name
    row.subject_ref = payload.subject_ref
    row.purpose = payload.purpose
    row.lawful_basis = payload.lawful_basis
    row.given = payload.given
    row.given_at = _parse_dt(payload.given_at)
    row.withdrawn_at = _parse_dt(payload.withdrawn_at)
    row.method = payload.method
    row.scope = payload.scope
    row.updated_at = utcnow()
    audit(db, user.username, "consent_update", record_id=cid, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


# — Data Subject Requests —

@app.get("/compliance/dsr")
def list_dsr(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    rows = db.query(DataSubjectRequest).order_by(DataSubjectRequest.received_at.desc()).limit(500).all()
    return [{"id": r.id, "request_type": r.request_type, "subject_name": r.subject_name,
             "subject_email": r.subject_email, "subject_phone": r.subject_phone,
             "status": r.status, "received_at": r.received_at.isoformat() if r.received_at else None,
             "due_at": r.due_at.isoformat() if r.due_at else None,
             "completed_at": r.completed_at.isoformat() if r.completed_at else None,
             "handled_by": r.handled_by, "notes": r.notes, "created_by": r.created_by,
             "created_at": r.created_at.isoformat()} for r in rows]


@app.post("/compliance/dsr", status_code=201)
def create_dsr(payload: DSRIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    received = utcnow()
    due = received + timedelta(days=DSR_RESPONSE_DAYS)
    row = DataSubjectRequest(
        request_type=payload.request_type, subject_name=payload.subject_name,
        subject_email=payload.subject_email, subject_phone=payload.subject_phone,
        status=payload.status or "Received", received_at=received, due_at=due,
        handled_by=payload.handled_by or user.username,
        notes=payload.notes, created_by=user.username,
    )
    db.add(row)
    db.flush()
    audit(db, user.username, "dsr_create", record_id=row.id, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True, "id": row.id, "due_at": due.isoformat()}


@app.put("/compliance/dsr/{dsr_id}")
def update_dsr(dsr_id: int, payload: DSRUpdate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    row = db.query(DataSubjectRequest).filter(DataSubjectRequest.id == dsr_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    if payload.status:
        row.status = payload.status
    if payload.handled_by:
        row.handled_by = payload.handled_by
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.completed_at:
        row.completed_at = _parse_dt(payload.completed_at) or utcnow()
    elif payload.status in ("Completed", "Rejected", "Withdrawn") and not row.completed_at:
        row.completed_at = utcnow()
    row.updated_at = utcnow()
    audit(db, user.username, "dsr_update", record_id=dsr_id, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


# — Breach Register —

@app.get("/compliance/breach")
def list_breaches(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    rows = db.query(BreachRecord).order_by(BreachRecord.created_at.desc()).limit(200).all()
    return [{"id": r.id, "title": r.title, "description": r.description, "severity": r.severity,
             "discovered_at": r.discovered_at.isoformat() if r.discovered_at else None,
             "reported_at": r.reported_at.isoformat() if r.reported_at else None,
             "reported_to": r.reported_to, "affected_count": r.affected_count,
             "data_categories": r.data_categories, "risk_level": r.risk_level,
             "status": r.status, "containment_actions": r.containment_actions,
             "dpa_notified": r.dpa_notified,
             "dpa_notified_at": r.dpa_notified_at.isoformat() if r.dpa_notified_at else None,
             "notes": r.notes, "created_by": r.created_by,
             "created_at": r.created_at.isoformat()} for r in rows]


@app.post("/compliance/breach", status_code=201)
def create_breach(payload: BreachIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    row = BreachRecord(
        title=payload.title, description=payload.description, severity=payload.severity,
        discovered_at=_parse_dt(payload.discovered_at), reported_at=_parse_dt(payload.reported_at),
        reported_to=payload.reported_to, affected_count=payload.affected_count or 0,
        data_categories=payload.data_categories, risk_level=payload.risk_level,
        status=payload.status or "Open", containment_actions=payload.containment_actions,
        dpa_notified=payload.dpa_notified or 0, dpa_notified_at=_parse_dt(payload.dpa_notified_at),
        notes=payload.notes, created_by=user.username,
    )
    db.add(row)
    db.flush()
    audit(db, user.username, "breach_create", record_id=row.id, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True, "id": row.id}


@app.put("/compliance/breach/{bid}")
def update_breach(bid: int, payload: BreachIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    row = db.query(BreachRecord).filter(BreachRecord.id == bid).first()
    if not row:
        raise HTTPException(404, "Not found")
    for attr, val in [
        ("title", payload.title), ("description", payload.description), ("severity", payload.severity),
        ("discovered_at", _parse_dt(payload.discovered_at)), ("reported_at", _parse_dt(payload.reported_at)),
        ("reported_to", payload.reported_to), ("affected_count", payload.affected_count),
        ("data_categories", payload.data_categories), ("risk_level", payload.risk_level),
        ("status", payload.status), ("containment_actions", payload.containment_actions),
        ("dpa_notified", payload.dpa_notified), ("dpa_notified_at", _parse_dt(payload.dpa_notified_at)),
        ("notes", payload.notes),
    ]:
        if val is not None:
            setattr(row, attr, val)
    row.updated_at = utcnow()
    audit(db, user.username, "breach_update", record_id=bid, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


# — Retention Schedules —

@app.get("/compliance/retention")
def list_retention(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    rows = db.query(RetentionSchedule).order_by(RetentionSchedule.module).all()
    return [{"id": r.id, "module": r.module, "category": r.category, "retention_years": r.retention_years,
             "legal_hold": r.legal_hold, "disposal_method": r.disposal_method,
             "review_date": r.review_date.isoformat() if r.review_date else None,
             "notes": r.notes, "created_by": r.created_by, "created_at": r.created_at.isoformat()} for r in rows]


@app.post("/compliance/retention", status_code=201)
def create_retention(payload: RetentionIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_dpo(user)
    row = RetentionSchedule(
        module=payload.module, category=payload.category,
        retention_years=payload.retention_years, legal_hold=payload.legal_hold or 0,
        disposal_method=payload.disposal_method, review_date=_parse_dt(payload.review_date),
        notes=payload.notes, created_by=user.username,
    )
    db.add(row)
    db.flush()
    audit(db, user.username, "retention_create", record_id=row.id, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True, "id": row.id}


@app.put("/compliance/retention/{rid}")
def update_retention(rid: int, payload: RetentionIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_dpo(user)
    row = db.query(RetentionSchedule).filter(RetentionSchedule.id == rid).first()
    if not row:
        raise HTTPException(404, "Not found")
    row.module = payload.module
    row.category = payload.category
    row.retention_years = payload.retention_years
    row.legal_hold = payload.legal_hold or 0
    row.disposal_method = payload.disposal_method
    row.review_date = _parse_dt(payload.review_date)
    row.notes = payload.notes
    row.updated_at = utcnow()
    audit(db, user.username, "retention_update", record_id=rid, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


# — Third-Party Processors —

@app.get("/compliance/processors")
def list_processors(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    rows = db.query(ThirdPartyProcessor).order_by(ThirdPartyProcessor.name).all()
    return [{"id": r.id, "name": r.name, "service": r.service, "country": r.country,
             "transfer_mechanism": r.transfer_mechanism, "dpa_signed": r.dpa_signed,
             "dpa_date": r.dpa_date.isoformat() if r.dpa_date else None,
             "review_date": r.review_date.isoformat() if r.review_date else None,
             "contact": r.contact, "notes": r.notes, "created_by": r.created_by,
             "created_at": r.created_at.isoformat()} for r in rows]


@app.post("/compliance/processors", status_code=201)
def create_processor(payload: ProcessorIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    row = ThirdPartyProcessor(
        name=payload.name, service=payload.service, country=payload.country,
        transfer_mechanism=payload.transfer_mechanism, dpa_signed=payload.dpa_signed or 0,
        dpa_date=_parse_dt(payload.dpa_date), review_date=_parse_dt(payload.review_date),
        contact=payload.contact, notes=payload.notes, created_by=user.username,
    )
    db.add(row)
    db.flush()
    audit(db, user.username, "processor_create", record_id=row.id, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True, "id": row.id}


@app.put("/compliance/processors/{pid}")
def update_processor(pid: int, payload: ProcessorIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    row = db.query(ThirdPartyProcessor).filter(ThirdPartyProcessor.id == pid).first()
    if not row:
        raise HTTPException(404, "Not found")
    row.name = payload.name
    row.service = payload.service
    row.country = payload.country
    row.transfer_mechanism = payload.transfer_mechanism
    row.dpa_signed = payload.dpa_signed or 0
    row.dpa_date = _parse_dt(payload.dpa_date)
    row.review_date = _parse_dt(payload.review_date)
    row.contact = payload.contact
    row.notes = payload.notes
    row.updated_at = utcnow()
    audit(db, user.username, "processor_update", record_id=pid, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


# — Export Log —

@app.get("/compliance/export-log")
def list_export_log(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    rows = db.query(ExportLog).order_by(ExportLog.created_at.desc()).limit(200).all()
    return [{"id": r.id, "module": r.module, "record_count": r.record_count,
             "exported_by": r.exported_by, "purpose": r.purpose, "approved_by": r.approved_by,
             "destination": r.destination, "cross_border": r.cross_border,
             "destination_country": r.destination_country, "notes": r.notes,
             "created_at": r.created_at.isoformat()} for r in rows]


# — Privacy Training —

@app.get("/compliance/training")
def list_training(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    rows = db.query(PrivacyTraining).order_by(PrivacyTraining.completed_at.desc()).limit(500).all()
    return [{"id": r.id, "username": r.username, "training_name": r.training_name,
             "completed_at": r.completed_at.isoformat() if r.completed_at else None,
             "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None,
             "notes": r.notes, "created_by": r.created_by, "created_at": r.created_at.isoformat()} for r in rows]


@app.post("/compliance/training", status_code=201)
def create_training(payload: TrainingIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    completed = _parse_dt(payload.completed_at)
    if not completed:
        raise HTTPException(400, "completed_at is required")
    row = PrivacyTraining(
        username=payload.username, training_name=payload.training_name,
        completed_at=completed, expiry_date=_parse_dt(payload.expiry_date),
        notes=payload.notes, created_by=user.username,
    )
    db.add(row)
    # Update user's privacy_training_date
    u = db.query(User).filter(User.username == payload.username).first()
    if u:
        u.privacy_training_date = completed
    db.flush()
    audit(db, user.username, "training_create", record_id=row.id, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True, "id": row.id}


# — Privacy / DPO Dashboard —

@app.get("/compliance/dashboard")
def compliance_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_compliance(user)
    now = utcnow()
    dsr_open = db.query(func.count(DataSubjectRequest.id)).filter(
        DataSubjectRequest.status.notin_(["Completed", "Rejected", "Withdrawn"])
    ).scalar() or 0
    dsr_overdue = db.query(func.count(DataSubjectRequest.id)).filter(
        DataSubjectRequest.status.notin_(["Completed", "Rejected", "Withdrawn"]),
        DataSubjectRequest.due_at < now,
    ).scalar() or 0
    breach_open = db.query(func.count(BreachRecord.id)).filter(
        BreachRecord.status.notin_(["Resolved", "Reported"])
    ).scalar() or 0
    breach_unnotified = db.query(func.count(BreachRecord.id)).filter(
        BreachRecord.severity.in_(["High", "Critical"]),
        BreachRecord.dpa_notified == 0,
    ).scalar() or 0
    consent_withdrawn = db.query(func.count(ConsentRecord.id)).filter(
        ConsentRecord.given == 0
    ).scalar() or 0
    processor_no_dpa = db.query(func.count(ThirdPartyProcessor.id)).filter(
        ThirdPartyProcessor.dpa_signed == 0
    ).scalar() or 0
    # Users with expired/missing privacy training (training older than 1 year)
    training_threshold = datetime(now.year - 1, now.month, now.day)
    users_needing_training = db.query(func.count(User.id)).filter(
        User.is_active == 1,
        or_(User.privacy_training_date == None, User.privacy_training_date < training_threshold)
    ).scalar() or 0

    return {
        "dsr_open": dsr_open, "dsr_overdue": dsr_overdue,
        "breach_open": breach_open, "breach_unnotified_dpa": breach_unnotified,
        "consent_withdrawn": consent_withdrawn,
        "processors_without_dpa": processor_no_dpa,
        "users_needing_training": users_needing_training,
    }


# ── Backup / Export ────────────────────────────────────────────────────────────

@app.get("/backup/json")
def export_json(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Not allowed")
    accessible = [m for m in MODULES if can_access(user, m, write=False)]
    records = db.query(CRMRecord).filter(CRMRecord.module.in_(accessible)).all()
    # Log the export
    log = ExportLog(
        module="all", record_count=len(records),
        exported_by=user.username, purpose="json_backup",
        destination="local_download", cross_border=0,
    )
    db.add(log)
    audit(db, user.username, "export_json", detail=f"{len(records)} records", ip_address=_client_ip(request))
    db.commit()
    return [{"id": r.id, "module": r.module, "code": r.code, "title": r.title, "data": r.data,
             "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat()} for r in records]


# ── Admin ──────────────────────────────────────────────────────────────────────

@app.put("/users/me/password")
def change_own_password(payload: SelfPasswordChange, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    user.password_hash = get_password_hash(payload.new_password)
    user.must_change_password = 0
    audit(db, user.username, "self_password_change", ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


@app.post("/admin/user")
def create_or_update_user(payload: PasswordChange, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Not allowed")
    _check_admin_rate_limit(user.username)
    u = db.query(User).filter(User.username == payload.username).first()
    if not u:
        u = User(
            username=payload.username,
            full_name=payload.full_name or payload.username,
            role=payload.role or "Sales/Booking User",
            email=payload.email,
            password_hash=get_password_hash(payload.new_password),
        )
        db.add(u)
    else:
        u.password_hash = get_password_hash(payload.new_password)
        if payload.role:
            u.role = payload.role
        if payload.full_name:
            u.full_name = payload.full_name
        if payload.email is not None:
            u.email = payload.email
    audit(db, user.username, "user_change", detail=payload.username, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


@app.get("/admin/users")
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in AUDIT_READ_ROLES:
        raise HTTPException(403, "Not allowed")
    users = db.query(User).order_by(User.username).all()
    return [{"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
             "email": u.email, "is_active": bool(u.is_active),
             "last_login": u.last_login.isoformat() if u.last_login else None,
             "privacy_training_date": u.privacy_training_date.isoformat() if u.privacy_training_date else None,
             "created_at": u.created_at.isoformat() if u.created_at else None} for u in users]


@app.post("/admin/users/{username}/deactivate")
def deactivate_user(username: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Not allowed")
    if username == user.username:
        raise HTTPException(400, "Cannot deactivate your own account")
    u = db.query(User).filter(User.username == username).first()
    if not u:
        raise HTTPException(404, "User not found")
    u.is_active = 0
    audit(db, user.username, "deactivate_user", detail=username, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


@app.post("/admin/users/{username}/activate")
def activate_user(username: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Not allowed")
    u = db.query(User).filter(User.username == username).first()
    if not u:
        raise HTTPException(404, "User not found")
    u.is_active = 1
    audit(db, user.username, "activate_user", detail=username, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


@app.get("/admin/audit")
def get_audit_log(
    module: Optional[str] = None,
    username: Optional[str] = None,
    limit: int = 200,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in AUDIT_READ_ROLES:
        raise HTTPException(403, "Not allowed")
    query = db.query(AuditLog)
    if module:
        query = query.filter(AuditLog.module == module)
    if username:
        query = query.filter(AuditLog.username == username)
    rows = query.order_by(AuditLog.created_at.desc()).limit(min(limit, 1000)).all()
    return [{"id": r.id, "username": r.username, "action": r.action, "module": r.module,
             "record_id": r.record_id, "detail": r.detail, "ip_address": r.ip_address,
             "reason": r.reason, "created_at": r.created_at.isoformat()} for r in rows]


@app.get("/records/{module}/count")
def count_records(module: str, q: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if module not in MODULES:
        raise HTTPException(404, "Unknown module")
    if not can_access(user, module, write=False):
        raise HTTPException(403, "Not allowed")
    query = db.query(func.count(CRMRecord.id)).filter(CRMRecord.module == module, CRMRecord.deleted_at == None)
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(CRMRecord.code.ilike(pattern), CRMRecord.title.ilike(pattern)))
    return {"count": query.scalar() or 0}


if __name__ == "__main__":
    import uvicorn
    host = config.get("server", "host", fallback="0.0.0.0")
    port = config.getint("server", "port", fallback=8080)
    uvicorn.run(app, host=host, port=port, reload=False)
