import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from src.config import STUDENTS_DB_FILE
from src.audit import audit_logger

SALT = b"aeai_salt_2026"

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with project salt."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SALT, 100000).hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against stored PBKDF2 hash."""
    return hash_password(plain_password) == hashed_password

class UserSession(BaseModel):
    user_id: str
    name: str
    role: str  # "student" or "administrator"
    email: str
    logged_in_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_admin(self) -> bool:
        return self.role.lower() == "administrator"

    @property
    def is_student(self) -> bool:
        return self.role.lower() == "student"

def load_user_db() -> Dict[str, Any]:
    if not STUDENTS_DB_FILE.exists():
        return {}
    with open(STUDENTS_DB_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_user_db(data: Dict[str, Any]):
    with open(STUDENTS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def authenticate(identifier: str, password: str) -> Optional[UserSession]:
    """
    Authenticate user by student_id/username or email.
    Logs all attempts (success/failure) to security audit trail.
    """
    db = load_user_db()
    ident_norm = identifier.strip().upper()

    user_record = None
    matched_id = None

    # Check direct ID match (e.g. STU101, ADMIN001, ADMIN)
    if ident_norm in db:
        user_record = db[ident_norm]
        matched_id = ident_norm
    elif ident_norm == "ADMIN":
        if "ADMIN001" in db:
            user_record = db["ADMIN001"]
            matched_id = "ADMIN001"
    else:
        # Check by email
        for uid, rec in db.items():
            if rec.get("email", "").lower() == identifier.strip().lower():
                user_record = rec
                matched_id = uid
                break

    if not user_record:
        audit_logger.log(
            user_id=identifier.strip(),
            user_role="unknown",
            action="LOGIN_ATTEMPT",
            target_resource="auth_system",
            permission_decision="DENIED",
            execution_result="FAILED",
            details={"reason": "User identifier not found"}
        )
        return None

    stored_hash = user_record.get("password_hash", "")
    if not verify_password(password, stored_hash):
        audit_logger.log(
            user_id=matched_id,
            user_role=user_record.get("role", "unknown"),
            action="LOGIN_ATTEMPT",
            target_resource="auth_system",
            permission_decision="DENIED",
            execution_result="FAILED",
            details={"reason": "Invalid password credentials"}
        )
        return None

    # Successful authentication
    session = UserSession(
        user_id=matched_id,
        name=user_record.get("full_name", matched_id),
        role=user_record.get("role", "student"),
        email=user_record.get("email", "")
    )

    audit_logger.log(
        user_id=session.user_id,
        user_role=session.role,
        action="LOGIN_ATTEMPT",
        target_resource="auth_system",
        permission_decision="ALLOWED",
        execution_result="SUCCESS",
        details={"name": session.name, "email": session.email}
    )

    return session

def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    db = load_user_db()
    return db.get(user_id.strip().upper())

def update_user_field(user_id: str, field_name: str, new_value: Any) -> bool:
    db = load_user_db()
    user_id_norm = user_id.strip().upper()
    if user_id_norm not in db:
        return False
    db[user_id_norm][field_name] = new_value
    save_user_db(db)
    return True

def list_students() -> List[Dict[str, Any]]:
    db = load_user_db()
    return [
        {
            "student_id": k,
            "full_name": v.get("full_name"),
            "email": v.get("email"),
            "programme": v.get("programme"),
            "batch": v.get("batch"),
            "cgpa": v.get("cgpa"),
            "attendance": v.get("attendance_percentage"),
            "attendance_percentage": v.get("attendance_percentage"),
            "pending_balance": v.get("fee_record", {}).get("pending_balance"),
            "fee_record": v.get("fee_record", {}),
            "scholarship": v.get("scholarship", {})
        }
        for k, v in db.items()
        if v.get("role") == "student"
    ]

