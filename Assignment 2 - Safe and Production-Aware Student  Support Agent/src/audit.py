import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from src.config import AUDIT_LOGS_FILE, LOGS_DIR

class AuditRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"AUD-{uuid.uuid4().hex[:8].upper()}")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    user_id: str
    user_role: str
    action: str
    target_resource: str
    permission_decision: str  # "ALLOWED", "DENIED", "N/A"
    approval_status: str = "N/A"  # "PENDING", "APPROVED", "REJECTED", "EXECUTED", "N/A"
    execution_result: str = "SUCCESS"  # "SUCCESS", "BLOCKED", "FAILED"
    details: Dict[str, Any] = Field(default_factory=dict)

class AuditLogger:
    def __init__(self, file_path=AUDIT_LOGS_FILE):
        self.file_path = file_path
        self._ensure_file()

    def _ensure_file(self):
        if not self.file_path.exists():
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def _load_all(self) -> List[Dict[str, Any]]:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_all(self, logs: List[Dict[str, Any]]):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)

    def log(
        self,
        user_id: str,
        user_role: str,
        action: str,
        target_resource: str,
        permission_decision: str = "ALLOWED",
        approval_status: str = "N/A",
        execution_result: str = "SUCCESS",
        details: Optional[Dict[str, Any]] = None
    ) -> AuditRecord:
        """
        Record a secure audit log entry.
        Guarantees that sensitive secrets (passwords, tokens, OTPs) are sanitized out.
        """
        sanitized_details = self._sanitize_dict(details or {})
        record = AuditRecord(
            user_id=user_id,
            user_role=user_role,
            action=action,
            target_resource=target_resource,
            permission_decision=permission_decision,
            approval_status=approval_status,
            execution_result=execution_result,
            details=sanitized_details
        )

        logs = self._load_all()
        logs.append(record.model_dump())
        self._save_all(logs)

        # Also append to secondary jsonl file in logs/
        jsonl_path = LOGS_DIR / "audit_log.jsonl"
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

        return record

    def get_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        permission_decision: Optional[str] = None,
        approval_status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Filter audit logs for admin review."""
        logs = self._load_all()
        filtered = []
        for entry in reversed(logs):
            if user_id and entry.get("user_id", "").upper() != user_id.upper():
                continue
            if action and action.lower() not in entry.get("action", "").lower():
                continue
            if permission_decision and entry.get("permission_decision", "").upper() != permission_decision.upper():
                continue
            if approval_status and entry.get("approval_status", "").upper() != approval_status.upper():
                continue
            filtered.append(entry)
            if len(filtered) >= limit:
                break
        return filtered

    @staticmethod
    def _sanitize_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        """Strip or mask passwords, OTPs, tokens from audit details."""
        clean = {}
        for k, v in d.items():
            k_lower = k.lower()
            if any(secret_term in k_lower for secret_term in ["password", "otp", "token", "secret", "cvv", "key"]):
                clean[k] = "[REDACTED_SECRET]"
            elif isinstance(v, dict):
                clean[k] = AuditLogger._sanitize_dict(v)
            elif isinstance(v, str) and any(term in v.lower() for term in ["pass#", "secret", "gsk_"]):
                clean[k] = "[REDACTED_SECRET_STRING]"
            else:
                clean[k] = v
        return clean

# Singleton instance
audit_logger = AuditLogger()

