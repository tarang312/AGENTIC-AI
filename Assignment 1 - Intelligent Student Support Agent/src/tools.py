import json
import uuid
from datetime import datetime
from typing import Dict, Any
from src.config import STUDENTS_DB_FILE, TICKETS_DB_FILE

def _load_students() -> Dict[str, Any]:
    if not STUDENTS_DB_FILE.exists():
        return {}
    with open(STUDENTS_DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

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

def check_student_record(student_id: str) -> Dict[str, Any]:
    """
    Retrieve academic profile and general enrollment details for a student.
    """
    students = _load_students()
    student_id_norm = student_id.strip().upper()
    
    if student_id_norm not in students:
        return {
            "status": "error",
            "message": f"Student record for ID '{student_id}' was not found in the academic database. Please verify the student ID."
        }
    
    rec = students[student_id_norm]
    return {
        "status": "success",
        "student_id": rec["student_id"],
        "full_name": rec["full_name"],
        "programme": rec["programme"],
        "batch": rec["batch"],
        "current_term": rec["current_term"],
        "cgpa": rec["cgpa"],
        "attendance_percentage": rec["attendance_percentage"],
        "faculty_advisor": rec["faculty_advisor"]
    }

def check_fee_status(student_id: str) -> Dict[str, Any]:
    """
    Retrieve detailed fee status, pending dues, due dates, and payment history for a student.
    """
    students = _load_students()
    student_id_norm = student_id.strip().upper()
    
    if student_id_norm not in students:
        return {
            "status": "error",
            "message": f"Student ID '{student_id}' not found. Cannot retrieve fee information."
        }
        
    rec = students[student_id_norm]
    fee = rec.get("fee_record", {})
    return {
        "status": "success",
        "student_id": rec["student_id"],
        "student_name": rec["full_name"],
        "programme": rec["programme"],
        "current_term": rec["current_term"],
        "term_fee": fee.get("term_fee"),
        "paid_amount": fee.get("paid_amount"),
        "pending_balance": fee.get("pending_balance"),
        "due_date": fee.get("due_date"),
        "payment_status": fee.get("payment_status"),
        "late_fee_accrued": fee.get("late_fee_accrued", 0),
        "recent_installment": fee.get("installment_history", [])[-1] if fee.get("installment_history") else None
    }

def check_scholarship_status(student_id: str) -> Dict[str, Any]:
    """
    Check scholarship award details, maintenance criteria, and renewal eligibility for a student.
    """
    students = _load_students()
    student_id_norm = student_id.strip().upper()
    
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
        "student_current_cgpa": rec["cgpa"],
        "student_attendance": rec["attendance_percentage"],
        "eligibility_remarks": sch.get("eligibility_remarks")
    }

def create_support_ticket(student_id: str, category: str, issue_description: str, priority: str = "Medium") -> Dict[str, Any]:
    """
    Create an official support ticket for administrative, financial, IT, or academic escalation.
    """
    ticket_id = f"TICK-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"
    new_ticket = {
        "ticket_id": ticket_id,
        "student_id": student_id.strip().upper(),
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
    
    return {
        "status": "success",
        "ticket_id": ticket_id,
        "message": f"Support ticket {ticket_id} created successfully.",
        "category": category,
        "priority": priority,
        "estimated_sla": "24 to 48 business hours",
        "next_steps": "Your request has been routed to Student Affairs. You will receive updates via your registered student email."
    }

# Mapping of tool name to implementation
TOOL_DISPATCH = {
    "check_student_record": check_student_record,
    "check_fee_status": check_fee_status,
    "check_scholarship_status": check_scholarship_status,
    "create_support_ticket": create_support_ticket,
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
                        "description": "The unique student ID (e.g. STU101, STU102)."
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
                        "description": "The unique student ID (e.g. STU101, STU102)."
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
                        "description": "The unique student ID (e.g. STU101, STU102)."
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
    }
]
