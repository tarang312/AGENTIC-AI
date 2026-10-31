import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from src.config import STUDENTS_DB_FILE, TICKETS_DB_FILE
from src.auth import UserSession
from src.authorization import AuthorizationPolicy
from src.approvals import approval_manager
from src.audit import audit_logger

def _load_students() -> Dict[str, Any]:
    if not STUDENTS_DB_FILE.exists():
        return {}
    with open(STUDENTS_DB_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def _load_tickets() -> list:
    if not TICKETS_DB_FILE.exists():
        return []
    with open(TICKETS_DB_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def _save_tickets(tickets: list):
    with open(TICKETS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2)

def check_student_record(student_id: str, session: Optional[UserSession] = None) -> Dict[str, Any]:
    """
    Retrieve academic profile and general enrollment details for a student.
    Enforces backend authorization to prevent unauthorized access across student boundaries.
    """
    student_id_norm = student_id.strip().upper()

    if student_id_norm in ["ADMIN", "ADMIN001"]:
        return {
            "status": "notice",
            "user_role": "administrator",
            "message": "User 'ADMIN001' is an Academic Administrator (Staff Officer), not an enrolled student. Administrative staff do not have student enrollments, terms, or grades."
        }

    # Backend Authorization Check
    if session:
        allowed, msg = AuthorizationPolicy.check_student_access(
            session=session,
            action="check_student_record",
            target_student_id=student_id_norm,
            resource_type="academic_profile"
        )
        if not allowed:
            return {"status": "denied", "error": "ACCESS_DENIED", "message": msg}

    students = _load_students()
    if student_id_norm not in students:
        return {
            "status": "error",
            "message": f"Student record for ID '{student_id}' was not found in the academic database. Please verify the student ID."
        }

    rec = students[student_id_norm]
    return {
        "status": "success",
        "student_id": rec.get("student_id", student_id_norm),
        "full_name": rec.get("full_name"),
        "email": rec.get("email"),
        "programme": rec.get("programme"),
        "batch": rec.get("batch"),
        "current_term": rec.get("current_term"),
        "cgpa": rec.get("cgpa"),
        "attendance_percentage": rec.get("attendance_percentage"),
        "faculty_advisor": rec.get("faculty_advisor")
    }

def check_fee_status(student_id: str, session: Optional[UserSession] = None) -> Dict[str, Any]:
    """
    Retrieve detailed fee status, pending dues, due dates, and payment history for a student.
    Enforces strict backend privacy authorization.
    """
    student_id_norm = student_id.strip().upper()

    if student_id_norm in ["ADMIN", "ADMIN001"]:
        return {
            "status": "notice",
            "user_role": "administrator",
            "message": "User 'ADMIN001' is an Academic Administrator (Office of Student Affairs), not an enrolled student. Administrative staff have no student tuition fee obligations. To check student fee records, specify a student ID such as STU101."
        }

    # Backend Authorization Check
    if session:
        allowed, msg = AuthorizationPolicy.check_student_access(
            session=session,
            action="check_fee_status",
            target_student_id=student_id_norm,
            resource_type="financial_record"
        )
        if not allowed:
            return {"status": "denied", "error": "ACCESS_DENIED", "message": msg}

    students = _load_students()
    if student_id_norm not in students:
        return {
            "status": "error",
            "message": f"Student ID '{student_id}' not found. Cannot retrieve fee information."
        }

    rec = students[student_id_norm]
    fee = rec.get("fee_record", {})
    return {
        "status": "success",
        "student_id": rec.get("student_id", student_id_norm),
        "student_name": rec.get("full_name"),
        "programme": rec.get("programme"),
        "current_term": rec.get("current_term"),
        "term_fee": fee.get("term_fee"),
        "paid_amount": fee.get("paid_amount"),
        "pending_balance": fee.get("pending_balance"),
        "due_date": fee.get("due_date"),
        "payment_status": fee.get("payment_status"),
        "late_fee_accrued": fee.get("late_fee_accrued", 0),
        "recent_installment": fee.get("installment_history", [])[-1] if fee.get("installment_history") else None
    }

def check_scholarship_status(student_id: str, session: Optional[UserSession] = None) -> Dict[str, Any]:
    """
    Check scholarship award details, maintenance criteria, and renewal eligibility for a student.
    """
    student_id_norm = student_id.strip().upper()

    if student_id_norm in ["ADMIN", "ADMIN001"]:
        return {
            "status": "notice",
            "user_role": "administrator",
            "message": "User 'ADMIN001' is an Academic Administrator, not an enrolled student. Scholarship schemes apply only to enrolled students. To check student scholarship details, specify a student ID such as STU101."
        }

    # Backend Authorization Check
    if session:
        allowed, msg = AuthorizationPolicy.check_student_access(
            session=session,
            action="check_scholarship_status",
            target_student_id=student_id_norm,
            resource_type="scholarship_record"
        )
        if not allowed:
            return {"status": "denied", "error": "ACCESS_DENIED", "message": msg}

    students = _load_students()
    if student_id_norm not in students:
        return {
            "status": "error",
            "message": f"Student ID '{student_id}' not found. Cannot retrieve scholarship records."
        }

    rec = students[student_id_norm]
    sch = rec.get("scholarship", {})
    return {
        "status": "success",
        "student_id": rec["student_id"],
        "student_name": rec["full_name"],
        "has_scholarship": sch.get("has_scholarship", False),
        "scheme_name": sch.get("scheme_name"),
        "waiver_percentage": sch.get("waiver_percentage", 0),
        "scholarship_status": sch.get("status"),
        "min_cgpa_required": sch.get("min_cgpa_required"),
        "student_current_cgpa": rec.get("cgpa"),
        "student_attendance": rec.get("attendance_percentage"),
        "eligibility_remarks": sch.get("eligibility_remarks")
    }

def create_support_ticket(
    student_id: str,
    category: str,
    issue_description: str,
    priority: str = "Medium",
    session: Optional[UserSession] = None
) -> Dict[str, Any]:
    """
    Create an official support ticket for administrative, financial, IT, or academic escalation.
    """
    effective_id = session.user_id if session and session.is_student else student_id.strip().upper()
    ticket_id = f"TICK-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"
    new_ticket = {
        "ticket_id": ticket_id,
        "student_id": effective_id,
        "category": category,
        "priority": priority,
        "issue_description": issue_description,
        "created_at": datetime.now().isoformat(),
        "status": "OPEN",
        "assigned_department": "Student Affairs & Helpdesk",
        "estimated_sla": "24 to 48 business hours"
    }

    tickets = _load_tickets()
    tickets.append(new_ticket)
    _save_tickets(tickets)

    audit_logger.log(
        user_id=effective_id,
        user_role=session.role if session else "student",
        action="CREATE_SUPPORT_TICKET",
        target_resource=f"ticket:{ticket_id}",
        permission_decision="ALLOWED",
        execution_result="SUCCESS",
        details={"category": category, "priority": priority}
    )

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "message": f"Support ticket {ticket_id} created successfully.",
        "category": category,
        "priority": priority,
        "estimated_sla": "24 to 48 business hours",
        "next_steps": "Your request has been routed to Student Affairs. You will receive updates via your registered student email."
    }

def request_email_update(new_email: str, session: Optional[UserSession] = None, student_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Submits a pending approval request to update the student's registered email address.
    Does NOT modify the student database until an administrator approves it.
    """
    if not session:
        if student_id:
            from src.auth import get_user_profile
            prof = get_user_profile(student_id)
            if prof:
                session = UserSession(
                    user_id=student_id,
                    name=prof.get("full_name", student_id),
                    role=prof.get("role", "student"),
                    email=prof.get("email", "")
                )
        if not session:
            return {"status": "denied", "message": "Authentication required to request profile updates."}

    return approval_manager.submit_email_update_request(session, new_email)

def view_my_approval_requests(session: Optional[UserSession] = None, student_id: Optional[str] = None) -> Dict[str, Any]:
    """
    View the active student's submitted profile change requests and their approval statuses.
    """
    sid = session.user_id if session else student_id
    if not sid:
        return {"status": "error", "message": "Active student session required."}

    reqs = approval_manager.list_requests(requester_id=sid)
    return {
        "status": "success",
        "student_id": sid,
        "total_requests": len(reqs),
        "requests": reqs
    }

# Tool Dispatch Table
TOOL_DISPATCH = {
    "check_student_record": check_student_record,
    "check_fee_status": check_fee_status,
    "check_scholarship_status": check_scholarship_status,
    "create_support_ticket": create_support_ticket,
    "request_email_update": request_email_update,
    "view_my_approval_requests": view_my_approval_requests,
}

# Groq Tool Schemas
GROQ_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "check_student_record",
            "description": "Fetch academic records, enrolled programme, term, CGPA, and advisor details for a specific student ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": "The student ID (e.g. STU101, STU102)."
                    }
                },
                "required": ["student_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_fee_status",
            "description": "Retrieve tuition fee details, pending balance, payment due dates, and recent payment history for a student.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": "The student ID (e.g. STU101, STU102)."
                    }
                },
                "required": ["student_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_scholarship_status",
            "description": "Retrieve scholarship award information, criteria, waiver percentage, and renewal eligibility status for a student.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": "The student ID (e.g. STU101, STU102)."
                    }
                },
                "required": ["student_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": "Open an official support ticket for questions or issues that cannot be resolved automatically or require administrative intervention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": "The student ID submitting the ticket."
                    },
                    "category": {
                        "type": "string",
                        "enum": ["Fee & Finance", "Academic / Course", "Scholarship", "IT & Portal Failure", "General Support"],
                        "description": "The category of the issue."
                    },
                    "issue_description": {
                        "type": "string",
                        "description": "A clear description of the problem or request."
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["Low", "Medium", "High", "Urgent"],
                        "description": "Priority level of the support request."
                    }
                },
                "required": ["student_id", "category", "issue_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_email_update",
            "description": "Submit a formal request to update the student's registered email address. This creates a pending approval request that must be reviewed and approved by an administrator before changes take effect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_email": {
                        "type": "string",
                        "description": "The new email address to update to (e.g., student.new@gmail.com)."
                    }
                },
                "required": ["new_email"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_my_approval_requests",
            "description": "Check the status of submitted profile modification requests (e.g. pending, approved, or rejected email changes).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]
