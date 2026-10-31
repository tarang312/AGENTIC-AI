from typing import Tuple, Optional
from src.auth import UserSession
from src.audit import audit_logger

class AuthorizationPolicy:
    """
    Enforces role-based and student-boundary access controls in backend Python code.
    Guarantees that the LLM cannot bypass authorization rules.
    """

    @staticmethod
    def check_student_access(
        session: Optional[UserSession],
        action: str,
        target_student_id: str,
        resource_type: str = "student_record"
    ) -> Tuple[bool, str]:
        """
        Validates if the session is allowed to access the target student's resources.
        Returns: (is_authorized, message)
        """
        if not session:
            # Fallback if unauthenticated session tries to access private records
            audit_logger.log(
                user_id="ANONYMOUS",
                user_role="unauthenticated",
                action=action,
                target_resource=f"{resource_type}:{target_student_id}",
                permission_decision="DENIED",
                execution_result="BLOCKED",
                details={"reason": "No active authenticated session."}
            )
            return False, "Access Denied: Unauthenticated session. Please log in first."

        target_norm = target_student_id.strip().upper()
        current_norm = session.user_id.strip().upper()

        # Administrators have full legitimate read access to student records
        if session.is_admin:
            audit_logger.log(
                user_id=session.user_id,
                user_role=session.role,
                action=action,
                target_resource=f"{resource_type}:{target_student_id}",
                permission_decision="ALLOWED",
                execution_result="SUCCESS",
                details={"admin_access": True}
            )
            return True, "AUTHORIZED_ADMIN"

        # Students can strictly ONLY access their own records
        if session.is_student:
            if current_norm == target_norm:
                audit_logger.log(
                    user_id=session.user_id,
                    user_role=session.role,
                    action=action,
                    target_resource=f"{resource_type}:{target_student_id}",
                    permission_decision="ALLOWED",
                    execution_result="SUCCESS",
                    details={"self_access": True}
                )
                return True, "AUTHORIZED_SELF"
            else:
                # Unauthorized cross-student access attempt!
                error_msg = (
                    f"ACCESS DENIED: You are authenticated as student '{session.user_id}'. "
                    f"You are strictly prohibited from accessing private financial or academic records "
                    f"belonging to '{target_student_id}' (Data Privacy & FERPA Compliance Policy). "
                    f"This security incident has been recorded in the administrative audit log."
                )
                audit_logger.log(
                    user_id=session.user_id,
                    user_role=session.role,
                    action=action,
                    target_resource=f"{resource_type}:{target_student_id}",
                    permission_decision="DENIED",
                    execution_result="BLOCKED",
                    details={
                        "attempted_target": target_student_id,
                        "violating_user": session.user_id,
                        "reason": "Cross-student privacy violation blocked by backend authorization engine."
                    }
                )
                return False, error_msg

        return False, "Access Denied: Unknown user role."

    @staticmethod
    def check_admin_action(session: Optional[UserSession], action: str, target_resource: str) -> Tuple[bool, str]:
        """Ensures action can strictly be performed by an Administrator."""
        if not session or not session.is_admin:
            u_id = session.user_id if session else "ANONYMOUS"
            u_role = session.role if session else "unauthenticated"
            error_msg = f"ACCESS DENIED: Action '{action}' requires administrative privileges. User '{u_id}' has role '{u_role}'."
            audit_logger.log(
                user_id=u_id,
                user_role=u_role,
                action=action,
                target_resource=target_resource,
                permission_decision="DENIED",
                execution_result="BLOCKED",
                details={"reason": "Administrative role required."}
            )
            return False, error_msg

        return True, "AUTHORIZED_ADMIN"

