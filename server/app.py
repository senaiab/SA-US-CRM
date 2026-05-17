import configparser
import json
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Text, func, or_, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import OperationalError

BASE_DIR = Path(__file__).resolve().parent
config = configparser.ConfigParser()
config.read(BASE_DIR / "server_config.ini")

DATABASE_URL = config.get("database", "url", fallback="mysql+pymysql://sa_us_user:SAUSERP2026!@127.0.0.1:3306/sa_us_erp?charset=utf8mb4")
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
_database_error: Optional[str] = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    full_name = Column(String(150), nullable=False, default="")
    role = Column(String(50), nullable=False, default="Sales Agent")
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
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


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=True)
    action = Column(String(80), nullable=False)
    module = Column(String(80), nullable=True)
    record_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    full_name: str


class RecordIn(BaseModel):
    module: str
    code: Optional[str] = None
    title: Optional[str] = None
    data: Dict[str, Any]


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


class PasswordChange(BaseModel):
    """Admin-initiated password change for any user."""
    username: str
    new_password: str
    role: Optional[str] = None
    full_name: Optional[str] = None


class SelfPasswordChange(BaseModel):
    """User changing their own password — requires current password verification."""
    current_password: str
    new_password: str


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

ROLE_PERMISSIONS = {
    "Owner": ["*"],
    "Business Manager": ["*"],
    "Sales Agent": ["leads", "quotations", "clients", "bookings"],
    "Ticketing Officer": ["bookings", "quotations", "clients", "complaints"],
    "Finance Officer": ["bookings", "ar", "clients", "exceptions"],
    "Viewer": ["read_only"],
}


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


def audit(db: Session, username: str, action: str, module: Optional[str] = None, record_id: Optional[int] = None, detail: Optional[str] = None):
    db.add(AuditLog(username=username, action=action, module=module, record_id=record_id, detail=detail))


def _check_rate_limit(username: str):
    now = time.time()
    recent = [t for t in _login_failures[username] if now - t < _RATE_WINDOW]
    _login_failures[username] = recent
    if len(recent) >= _RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Wait 5 minutes and try again.")


def _record_failure(username: str):
    _login_failures[username].append(time.time())


def initialize_database():
    global _database_error
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            if not db.query(User).filter(User.username == "admin").first():
                db.add(User(username="admin", full_name="System Administrator", role="Owner", password_hash=get_password_hash("admin123")))
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
        print("Check MariaDB/MySQL and server_config.ini, then retry /health or restart the server.")
        print(_database_error)
    yield


app = FastAPI(title="SA-US ERP Local Network Server", version="2.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    if not initialize_database():
        raise HTTPException(
            status_code=503,
            detail={
                "status": "setup_required",
                "message": "Database connection failed. Check MariaDB/MySQL and server_config.ini.",
                "database_error": _database_error,
            },
        )
    return {"status": "ok", "server_time": utcnow().isoformat(), "modules": list(MODULES.keys())}


@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    _check_rate_limit(form_data.username)
    user = db.query(User).filter(User.username == form_data.username, User.is_active == 1).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        _record_failure(form_data.username)
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    _login_failures.pop(form_data.username, None)
    token = create_access_token(data={"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "role": user.role, "full_name": user.full_name}


@app.get("/modules")
def modules(user: User = Depends(get_current_user)):
    return {"modules": MODULES, "role": user.role, "permissions": ROLE_PERMISSIONS.get(user.role, [])}


@app.get("/records/{module}", response_model=List[RecordOut])
def list_records(module: str, q: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if module not in MODULES:
        raise HTTPException(404, "Unknown module")
    if not can_access(user, module, write=False):
        raise HTTPException(403, "Not allowed")
    query = db.query(CRMRecord).filter(CRMRecord.module == module)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                CRMRecord.code.ilike(pattern),
                CRMRecord.title.ilike(pattern),
            )
        )
    records = query.order_by(CRMRecord.updated_at.desc()).limit(1000).all()
    if q:
        q_low = q.lower()
        records = [r for r in records if q_low in (r.code or "").lower() or q_low in (r.title or "").lower() or q_low in json.dumps(r.data, default=str).lower()]
    return records


@app.post("/records", response_model=RecordOut)
def create_record(record: RecordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if record.module not in MODULES:
        raise HTTPException(404, "Unknown module")
    if not can_access(user, record.module, write=True):
        raise HTTPException(403, "Not allowed")
    db_record = CRMRecord(module=record.module, code=record.code, title=record.title, data=record.data, created_by=user.username, updated_by=user.username)
    db.add(db_record)
    db.flush()
    audit(db, user.username, "create", record.module, db_record.id)
    db.commit()
    db.refresh(db_record)
    return db_record


@app.put("/records/{record_id}", response_model=RecordOut)
def update_record(record_id: int, record: RecordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_record = db.query(CRMRecord).filter(CRMRecord.id == record_id).first()
    if not db_record:
        raise HTTPException(404, "Record not found")
    if not can_access(user, db_record.module, write=True):
        raise HTTPException(403, "Not allowed")
    db_record.code = record.code
    db_record.title = record.title
    db_record.data = record.data
    db_record.updated_by = user.username
    db_record.updated_at = utcnow()
    audit(db, user.username, "update", db_record.module, db_record.id)
    db.commit()
    db.refresh(db_record)
    return db_record


@app.delete("/records/{record_id}")
def delete_record(record_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_record = db.query(CRMRecord).filter(CRMRecord.id == record_id).first()
    if not db_record:
        raise HTTPException(404, "Record not found")
    if user.role not in ["Owner", "Business Manager"]:
        raise HTTPException(403, "Only Owner or Business Manager can delete records")
    module = db_record.module
    db.delete(db_record)
    audit(db, user.username, "delete", module, record_id)
    db.commit()
    return {"ok": True}


def _dashboard_sql_metrics(db: Session) -> dict:
    """
    Fast dashboard metrics using SQL JSON_EXTRACT (MySQL 5.7+ / MariaDB 10.2+).
    Raises on any error so the caller can fall back to Python scanning.
    """
    open_leads = db.execute(text(
        "SELECT COUNT(*) FROM crm_records WHERE module='leads' "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$. \"Lead Status\"')), '') "
        "NOT IN ('Closed-Won', 'Closed-Lost', 'Dormant')"
    )).scalar() or 0

    open_complaints = db.execute(text(
        "SELECT COUNT(*) FROM crm_records WHERE module='complaints' "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$.Status')), '') "
        "NOT IN ('Resolved', 'Closed')"
    )).scalar() or 0

    open_exceptions = db.execute(text(
        "SELECT COUNT(*) FROM crm_records WHERE module='exceptions' "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$. \"Closed?\"')), '') != 'Yes'"
    )).scalar() or 0

    # AR overdue: SQL pre-filters unpaid + past-due rows; Python checks the amounts
    today_str = datetime.today().date().isoformat()
    ar_rows = db.execute(text(
        "SELECT "
        "  JSON_UNQUOTE(JSON_EXTRACT(data, '$. \"Invoice Amount\"')), "
        "  JSON_UNQUOTE(JSON_EXTRACT(data, '$. \"Amount Received\"')) "
        "FROM crm_records WHERE module='ar' "
        "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$. \"Payment Status\"')), '') != 'Paid' "
        f"AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(data, '$. \"Due Date\"')), '') < '{today_str}'"
    )).fetchall()
    overdue_ar = 0
    for inv_str, paid_str in ar_rows:
        try:
            if float(inv_str or 0) - float(paid_str or 0) > 0:
                overdue_ar += 1
        except Exception:
            pass

    return {
        "open_leads": open_leads,
        "overdue_ar": overdue_ar,
        "open_complaints": open_complaints,
        "open_exceptions": open_exceptions,
    }


def _dashboard_python_metrics(db: Session) -> dict:
    """Fallback Python-side metric scan. Slower but compatible with all DB versions."""
    open_leads = 0
    for rec in db.query(CRMRecord).filter(CRMRecord.module == "leads").all():
        if (rec.data or {}).get("Lead Status") not in ["Closed-Won", "Closed-Lost", "Dormant"]:
            open_leads += 1

    overdue_ar = 0
    for rec in db.query(CRMRecord).filter(CRMRecord.module == "ar").all():
        d = rec.data or {}
        try:
            inv = float(d.get("Invoice Amount") or 0)
            paid = float(d.get("Amount Received") or 0)
            due = d.get("Due Date")
            if inv - paid > 0 and due and datetime.fromisoformat(str(due)).date() < datetime.today().date():
                overdue_ar += 1
        except Exception:
            pass

    open_complaints = 0
    for rec in db.query(CRMRecord).filter(CRMRecord.module == "complaints").all():
        if (rec.data or {}).get("Status") not in ["Resolved", "Closed"]:
            open_complaints += 1

    open_exceptions = 0
    for rec in db.query(CRMRecord).filter(CRMRecord.module == "exceptions").all():
        if (rec.data or {}).get("Closed?") != "Yes":
            open_exceptions += 1

    return {
        "open_leads": open_leads,
        "overdue_ar": overdue_ar,
        "open_complaints": open_complaints,
        "open_exceptions": open_exceptions,
    }


@app.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # SQL aggregate counts — no full table scan
    count_rows = db.query(CRMRecord.module, func.count(CRMRecord.id)).group_by(CRMRecord.module).all()
    counts = {m: 0 for m in MODULES}
    for module, cnt in count_rows:
        if module in counts:
            counts[module] = cnt

    # Try fast SQL JSON metrics first; fall back to Python scan if DB lacks JSON functions
    try:
        metrics = _dashboard_sql_metrics(db)
    except Exception:
        metrics = _dashboard_python_metrics(db)

    return {"counts": counts, **metrics}


@app.put("/users/me/password")
def change_own_password(
    payload: SelfPasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Any authenticated user can change their own password by supplying their current one."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    user.password_hash = get_password_hash(payload.new_password)
    audit(db, user.username, "self_password_change")
    db.commit()
    return {"ok": True}


@app.post("/admin/user")
def create_or_update_user(payload: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ["Owner", "Business Manager"]:
        raise HTTPException(403, "Not allowed")
    u = db.query(User).filter(User.username == payload.username).first()
    if not u:
        u = User(username=payload.username, full_name=payload.full_name or payload.username, role=payload.role or "Sales Agent", password_hash=get_password_hash(payload.new_password))
        db.add(u)
    else:
        u.password_hash = get_password_hash(payload.new_password)
        if payload.role:
            u.role = payload.role
        if payload.full_name:
            u.full_name = payload.full_name
    audit(db, user.username, "user_change", detail=payload.username)
    db.commit()
    return {"ok": True}


@app.get("/backup/json")
def export_json(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ["Owner", "Business Manager"]:
        raise HTTPException(403, "Not allowed")
    records = db.query(CRMRecord).all()
    return [{"id": r.id, "module": r.module, "code": r.code, "title": r.title, "data": r.data, "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat()} for r in records]


if __name__ == "__main__":
    import uvicorn
    host = config.get("server", "host", fallback="0.0.0.0")
    port = config.getint("server", "port", fallback=8080)
    uvicorn.run(app, host=host, port=port, reload=False)
