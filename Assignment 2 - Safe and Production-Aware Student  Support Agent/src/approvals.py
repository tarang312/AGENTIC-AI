import json
import re
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from src.config import APPROVALS_DB_FILE
from src.auth import UserSession, get_user_profile, update_user_field
from src.audit import audit_logger

EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"

class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"APP-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}")
    requester_id: str
    action_type: str = "EMAIL_UPDATE"
    target_field: str = "email"
    old_value: str
    requested_value: str
    status: str = "PENDING"  # "PENDING", "APPROVED", "REJECTED", "EXECUTED"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    reviewed_by: Optional[str] = None
    review_decision: Optional[str] = None
    rejection_reason: Optional[str] = None

class ApprovalManager:
    def __init__(self, file_path=APPROVALS_DB_FILE):
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

    def _save_all(self, requests: List[Dict[str, Any]]):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(requests, f, indent=2)

    def submit_email_update_request(self, session: UserSession, new_email: str) -> Dict[str, Any]:
        """
        Student initiates a request to change their registered email address.
        Creates a PENDING approval request. Does NOT modify the database yet.
        """
        student_id = session.user_id
        new_email = new_email.strip()

        # 1. Validate email syntax
        if not re.match(EMAIL_REGEX, new_email):
            audit_logger.log(
                user_id=student_id,
                user_role=session.role,
                action="REQUEST_EMAIL_UPDATE",
                target_resource=f"student:{student_id}:email",
                permission_decision="DENIED",
                approval_status="N/A",
                execution_result="FAILED",
                details={"reason": f"Invalid email format: '{new_email}'"}
            )
            return {
                "status": "error",
                "message": f"Invalid email format '{new_email}'. Please provide a valid email address (e.g., student@domain.com)."
            }

        # 2. Get current record
        profile = get_user_profile(student_id)
        if not profile:
            return {"status": "error", "message": f"Student profile '{student_id}' not found."}

        current_email = profile.get("email", "Not Registered")

        if current_email.lower() == new_email.lower():
            return {
                "status": "notice",
                "message": f"Your registered email is already set to '{current_email}'. No update required."
            }

        # 3. Check for existing pending request to avoid duplicates
        all_reqs = self._load_all()
        for r in all_reqs:
            if r["requester_id"] == student_id and r["status"] == "PENDING" and r["action_type"] == "EMAIL_UPDATE":
                return {
                    "status": "pending_exists",
                    "request_id": r["id"],
                    "message": f"You already have a pending email update request ({r['id']}) awaiting administrator review."
                }

        # 4. Create Approval Request
        req = ApprovalRequest(
            requester_id=student_id,
            action_type="EMAIL_UPDATE",
            target_field="email",
            old_value=current_email,
            requested_value=new_email,
            status="PENDING"
        )

        all_reqs.append(req.model_dump())
        self._save_all(all_reqs)

        # 5. Audit Log Entry
        audit_logger.log(
            user_id=student_id,
            user_role=session.role,
            action="REQUEST_EMAIL_UPDATE",
            target_resource=f"student:{student_id}:email",
            permission_decision="ALLOWED",
            approval_status="PENDING",
            execution_result="SUCCESS",
            details={
                "request_id": req.id,
                "old_email": current_email,
                "requested_email": new_email,
                "workflow": "Awaiting Administrator Review & Approval"
            }
        )

        return {
            "status": "success",
            "request_id": req.id,
            "approval_status": "PENDING",
            "old_email": current_email,
            "requested_email": new_email,
            "message": (
                f"Your request to update email from '{current_email}' to '{new_email}' has been submitted "
                f"under Request ID [{req.id}]. As per academic safety policies, profile modifications "
                f"require administrator approval and will take effect once reviewed."
            )
        }

    def list_requests(
        self,
        status: Optional[str] = None,
        requester_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List requests filtered by status or requester."""
        reqs = self._load_all()
        filtered = []
        for r in reversed(reqs):
            if status and r.get("status", "").upper() != status.upper():
                continue
            if requester_id and r.get("requester_id", "").upper() != requester_id.upper():
                continue
            filtered.append(r)
        return filtered

    def approve_and_execute(self, admin_session: UserSession, request_id: str) -> Dict[str, Any]:
        """
        Administrator reviews and approves request.
        Executes database modification strictly after approval.
        Guarantees no duplicate execution.
        """
        if not admin_session.is_admin:
            return {"status": "denied", "message": "Only administrators can approve change requests."}

        reqs = self._load_all()
        target_req = None
        for r in reqs:
            if r["id"] == request_id:
                target_req = r
                break

        if not target_req:
            return {"status": "error", "message": f"Approval request '{request_id}' not found."}

        if target_req["status"] != "PENDING":
            return {
                "status": "error",
                "message": f"Request '{request_id}' cannot be approved because current status is '{target_req['status']}'."
            }

        # Execute the update on student record
        student_id = target_req["requester_id"]
        field_name = target_req["target_field"]
        new_val = target_req["requested_value"]

        updated = update_user_field(student_id, field_name, new_val)
        if not updated:
            return {"status": "error", "message": f"Failed to update database for student '{student_id}'."}

        # Update request state to EXECUTED
        target_req["status"] = "EXECUTED"
        target_req["reviewed_by"] = admin_session.user_id
        target_req["review_decision"] = "APPROVED"
        target_req["updated_at"] = datetime.now().isoformat()
        self._save_all(reqs)

        # Audit log execution
        audit_logger.log(
            user_id=admin_session.user_id,
            user_role=admin_session.role,
            action="APPROVE_AND_EXECUTE",
            target_resource=f"student:{student_id}:{field_name}",
            permission_decision="ALLOWED",
            approval_status="EXECUTED",
            execution_result="SUCCESS",
            details={
                "request_id": request_id,
                "requester_id": student_id,
                "old_value": target_req["old_value"],
                "new_value": new_val,
                "approved_by": admin_session.user_id
            }
        )

        return {
            "status": "success",
            "request_id": request_id,
            "new_status": "EXECUTED",
            "message": f"Request '{request_id}' approved and executed. Student '{student_id}' {field_name} updated to '{new_val}'."
        }

    def reject_request(self, admin_session: UserSession, request_id: str, reason: str = "Rejected by Academic Administration") -> Dict[str, Any]:
        """
        Administrator rejects request. Database remains completely unchanged.
        """
        if not admin_session.is_admin:
            return {"status": "denied", "message": "Only administrators can reject change requests."}

        reqs = self._load_all()
        target_req = None
        for r in reqs:
            if r["id"] == request_id:
                target_req = r
                break

        if not target_req:
            return {"status": "error", "message": f"Approval request '{request_id}' not found."}

        if target_req["status"] != "PENDING":
            return {
                "status": "error",
                "message": f"Request '{request_id}' cannot be rejected because current status is '{target_req['status']}'."
            }

        # Update state to REJECTED. Do NOT touch student database!
        target_req["status"] = "REJECTED"
        target_req["reviewed_by"] = admin_session.user_id
        target_req["review_decision"] = "REJECTED"
        target_req["rejection_reason"] = reason
        target_req["updated_at"] = datetime.now().isoformat()
        self._save_all(reqs)

        # Audit log rejection
        audit_logger.log(
            user_id=admin_session.user_id,
            user_role=admin_session.role,
            action="REJECT_REQUEST",
            target_resource=f"student:{target_req['requester_id']}:{target_req['target_field']}",
            permission_decision="ALLOWED",
            approval_status="REJECTED",
            execution_result="SUCCESS",
            details={
                "request_id": request_id,
                "requester_id": target_req["requester_id"],
                "rejection_reason": reason,
                "rejected_by": admin_session.user_id,
                "database_modified": False
            }
        )

        return {
            "status": "success",
            "request_id": request_id,
            "new_status": "REJECTED",
            "message": f"Request '{request_id}' has been rejected. Student record was NOT modified. Reason: {reason}"
        }

approval_manager = ApprovalManager()

