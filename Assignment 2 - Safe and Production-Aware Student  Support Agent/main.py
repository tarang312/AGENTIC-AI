import sys
import json
from pathlib import Path
from colorama import init, Fore, Style
from tabulate import tabulate

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.config import ensure_api_key, STUDENTS_DB_FILE
from src.agent import StudentSupportAgent
from src.policy_retriever import PolicyRetriever
from src.memory import MemoryManager
from src.auth import authenticate, UserSession, list_students, get_user_profile
from src.approvals import approval_manager
from src.audit import audit_logger
from evaluate import run_evaluation_suite

init(autoreset=True)

def print_banner():
    print(f"\n{Fore.CYAN}{Style.BRIGHT}========================================================================")
    print("      AGENTIC AI ENGINEERING: SAFE & PRODUCTION-AWARE AGENT")
    print("               Intelligent Student Support System (v2.0)")
    print("            PGDM (Big Data Analytics / AI & Data Science)")
    print(f"========================================================================{Style.RESET_ALL}")

def interactive_login() -> UserSession:
    """Provides quick demo login shortcuts or full credential entry."""
    while True:
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}--- SECURE AUTHENTICATION PORTAL ---{Style.RESET_ALL}")
        print("Select a login option or enter credentials:")
        print("  [1] Quick Login: Aarav Sharma [STU101] (Student - AI & Data Science)")
        print("  [2] Quick Login: Ananya Iyer [STU102] (Student - Big Data Analytics)")
        print("  [3] Quick Login: Rohan Verma [STU103] (Student - FinTech Analytics)")
        print("  [4] Quick Login: Priyanka Nair [STU104] (Student - AI & Data Science - Gold Scholar)")
        print("  [5] Quick Login: Academic Administrator [ADMIN001] (Administrator)")
        print("  [6] Custom Username & Password (or other Student IDs: STU105-STU108)")
        print("  [7] Run Assignment Evaluation Suite (/eval)")
        print("  [8] Exit")

        try:
            choice = input(f"\n{Fore.CYAN}Selection (1-8) [default: 1]: {Style.RESET_ALL}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            sys.exit(0)

        if choice in ("", "1"):
            session = authenticate("STU101", "student123")
            if session:
                return session
        elif choice == "2":
            session = authenticate("STU102", "student123")
            if session:
                return session
        elif choice == "3":
            session = authenticate("STU103", "student123")
            if session:
                return session
        elif choice == "4":
            session = authenticate("STU104", "student123")
            if session:
                return session
        elif choice == "5":
            session = authenticate("ADMIN001", "admin123")
            if session:
                return session
        elif choice == "7":
            run_evaluation_suite()
            continue
        elif choice in ("8", "exit", "quit"):
            print("Goodbye!")
            sys.exit(0)
        elif choice == "6":
            ident = input("Username or Student ID: ").strip()
            import getpass
            try:
                pwd = getpass.getpass("Password: ")
            except Exception:
                pwd = input("Password: ")
            session = authenticate(ident, pwd)
            if session:
                return session
            print(f"{Fore.RED}[!] Authentication failed. Invalid username or password.{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[!] Invalid option. Please choose 1-7.{Style.RESET_ALL}")

def show_admin_dashboard(session: UserSession):
    """Displays the administrative KPI dashboard."""
    students = list_students()
    all_requests = approval_manager.list_requests()
    pending = [r for r in all_requests if r["status"] == "PENDING"]
    approved = [r for r in all_requests if r["status"] in ("APPROVED", "EXECUTED")]
    rejected = [r for r in all_requests if r["status"] == "REJECTED"]
    
    logs = audit_logger.get_logs(limit=200)
    unauthorized = [l for l in logs if l.get("permission_decision") == "DENIED"]

    print(f"\n{Fore.CYAN}{Style.BRIGHT}========================================================================")
    print("                 ADMINISTRATOR EXECUTIVE DASHBOARD")
    print(f"========================================================================{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Total Registered Students:      {Fore.GREEN}{len(students)}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Pending Approval Requests:      {Fore.YELLOW}{len(pending)}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Approved / Executed Requests:   {Fore.GREEN}{len(approved)}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Rejected Requests:              {Fore.RED}{len(rejected)}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Unauthorized Attempts Blocked:  {Fore.RED}{Style.BRIGHT}{len(unauthorized)}{Style.RESET_ALL}")
    print(f"========================================================================\n")

def show_pending_approvals():
    reqs = approval_manager.list_requests(status="PENDING")
    if not reqs:
        print(f"{Fore.GREEN}[✓] No pending approval requests found.{Style.RESET_ALL}\n")
        return

    table_data = []
    for r in reqs:
        table_data.append([
            r["id"],
            r["requester_id"],
            r["action_type"],
            r["old_value"],
            r["requested_value"],
            r["created_at"][:19]
        ])

    headers = ["Request ID", "Student ID", "Action", "Current Value", "Requested Value", "Submitted At"]
    print(f"\n{Fore.YELLOW}{Style.BRIGHT}PENDING HUMAN APPROVAL QUEUE:{Style.RESET_ALL}")
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print(f"{Fore.CYAN}Commands: /approve <REQUEST_ID>  |  /reject <REQUEST_ID> [reason]{Style.RESET_ALL}\n")

def show_audit_logs(filter_user: str = ""):
    logs = audit_logger.get_logs(user_id=filter_user if filter_user else None, limit=15)
    if not logs:
        print(f"{Fore.YELLOW}[!] No audit records matching filter.{Style.RESET_ALL}\n")
        return

    table_data = []
    for l in logs:
        dec = l.get("permission_decision", "N/A")
        color_dec = f"{Fore.GREEN}ALLOWED" if dec == "ALLOWED" else f"{Fore.RED}DENIED"
        table_data.append([
            l.get("id"),
            l.get("timestamp")[:19],
            l.get("user_id"),
            l.get("action"),
            color_dec,
            l.get("approval_status"),
            l.get("execution_result")
        ])

    headers = ["Audit ID", "Timestamp", "User", "Action", "Decision", "Approval", "Result"]
    print(f"\n{Fore.CYAN}{Style.BRIGHT}SECURITY AUDIT LOGS (Latest {len(logs)} Events):{Style.RESET_ALL}")
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print("")

def main():
    print_banner()

    # Ensure API Key is configured
    ensure_api_key(interactive=True)

    retriever = PolicyRetriever()
    memory = MemoryManager()
    agent = StudentSupportAgent(retriever=retriever, memory=memory)

    while True:
        session = interactive_login()
        history = []

        print(f"\n{Fore.GREEN}[✓] Authenticated Successfully!{Style.RESET_ALL}")
        print(f"{Fore.WHITE}User:{Style.RESET_ALL}       {session.name} [{session.user_id}]")
        print(f"{Fore.WHITE}Role:{Style.RESET_ALL}       {Fore.CYAN}{session.role.upper()}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Email:{Style.RESET_ALL}      {session.email}")

        if session.is_admin:
            print(f"\n{Fore.YELLOW}Administrator Commands:{Style.RESET_ALL}")
            print("  /dashboard              - Display system overview and metrics")
            print("  /approvals              - View pending approval requests")
            print("  /approve <REQUEST_ID>   - Approve request and execute database change")
            print("  /reject <REQUEST_ID>    - Reject request without modifying database")
            print("  /audit [USER_ID]        - View security audit log")
            print("  /students               - View registered student records")
            print("  /eval                   - Run automated evaluation suite")
            print("  /logout                 - Logout current session")
            print("  exit                    - Terminate program\n")
        else:
            print(f"\n{Fore.YELLOW}Student Commands:{Style.RESET_ALL}")
            print("  Ask any question directly (fees, scholarships, policies, update email, etc.)")
            print("  /my-requests            - View status of your submitted change requests")
            print("  /eval                   - Run automated evaluation suite")
            print("  /logout                 - Switch account / Logout")
            print("  exit                    - Terminate program\n")
            print(f"{Fore.WHITE}Agent: Hello {session.name}! How may I help you with your academic or administrative needs today?{Style.RESET_ALL}\n")

        # Session Loop
        while True:
            try:
                role_tag = "ADMIN" if session.is_admin else session.user_id
                prompt_str = f"{Fore.BLUE}{Style.BRIGHT}[{role_tag}] > {Style.RESET_ALL}"
                user_input = input(prompt_str).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nLogging out current session...")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                print("Session terminated. Goodbye!")
                sys.exit(0)

            if user_input.lower() in ("/logout", "logout"):
                print(f"{Fore.YELLOW}Logged out of user '{session.user_id}'.{Style.RESET_ALL}")
                break

            if user_input.lower() == "/eval":
                run_evaluation_suite()
                continue

            # Student specific commands
            if user_input.lower() == "/my-requests":
                reqs = approval_manager.list_requests(requester_id=session.user_id)
                if not reqs:
                    print(f"{Fore.YELLOW}No submitted profile change requests found for your account.{Style.RESET_ALL}\n")
                else:
                    tdata = [[r["id"], r["action_type"], r["old_value"], r["requested_value"], r["status"], r["created_at"][:19]] for r in reqs]
                    print(f"\n{Fore.CYAN}YOUR PROFILE CHANGE REQUESTS:{Style.RESET_ALL}")
                    print(tabulate(tdata, headers=["ID", "Action", "Original", "Requested", "Status", "Date"], tablefmt="grid"))
                    print("")
                continue

            # Admin specific commands
            if session.is_admin:
                if user_input.lower() == "/dashboard":
                    show_admin_dashboard(session)
                    continue

                if user_input.lower() == "/approvals":
                    show_pending_approvals()
                    continue

                if user_input.lower().startswith("/approve"):
                    parts = user_input.split()
                    if len(parts) > 1:
                        req_id = parts[1].strip()
                        res = approval_manager.approve_and_execute(session, req_id)
                        color = Fore.GREEN if res["status"] == "success" else Fore.RED
                        print(f"{color}{res['message']}{Style.RESET_ALL}\n")
                    else:
                        print(f"{Fore.RED}Usage: /approve <REQUEST_ID>{Style.RESET_ALL}\n")
                    continue

                if user_input.lower().startswith("/reject"):
                    parts = user_input.split(maxsplit=2)
                    if len(parts) > 1:
                        req_id = parts[1].strip()
                        reason = parts[2] if len(parts) > 2 else "Rejected by Administrator"
                        res = approval_manager.reject_request(session, req_id, reason)
                        color = Fore.GREEN if res["status"] == "success" else Fore.RED
                        print(f"{color}{res['message']}{Style.RESET_ALL}\n")
                    else:
                        print(f"{Fore.RED}Usage: /reject <REQUEST_ID> [reason]{Style.RESET_ALL}\n")
                    continue

                if user_input.lower().startswith("/audit"):
                    parts = user_input.split()
                    filt = parts[1].strip() if len(parts) > 1 else ""
                    show_audit_logs(filt)
                    continue

                if user_input.lower() == "/students":
                    stus = list_students()
                    tdata = [[s["student_id"], s["full_name"], s["email"], s["programme"], s["cgpa"], f"₹{s['pending_balance']:,}" if s['pending_balance'] is not None else "N/A"] for s in stus]
                    print(f"\n{Fore.CYAN}REGISTERED STUDENTS REGISTRY:{Style.RESET_ALL}")
                    print(tabulate(tdata, headers=["ID", "Name", "Email", "Programme", "CGPA", "Pending Fee"], tablefmt="grid"))
                    print("")
                    continue

            # Process query via Agentic AI Loop
            agent_out = agent.process_query(
                query=user_input,
                session=session,
                session_history=history
            )

            # Trace output
            if agent_out["tools_used"]:
                print(f"{Fore.MAGENTA}[Tool Used]: {', '.join(agent_out['tools_used'])}{Style.RESET_ALL}")
            if agent_out["retrieved_evidence"]:
                print(f"{Fore.CYAN}[Evidence]: {', '.join(agent_out['retrieved_evidence'])}{Style.RESET_ALL}")
            if agent_out["memory_notice"]:
                print(f"{Fore.YELLOW}[Security Notice]: {agent_out['memory_notice']}{Style.RESET_ALL}")

            print(f"\n{Fore.WHITE}{Style.BRIGHT}Agent:{Style.RESET_ALL} {agent_out['answer']}")
            print(f"{Fore.LIGHTBLACK_EX}[Latency: {agent_out['latency_seconds']}s | Tokens: {agent_out['prompt_tokens']} prompt + {agent_out['completion_tokens']} completion = {agent_out['total_tokens']} total]{Style.RESET_ALL}\n")

            # Update session history
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": agent_out["answer"]})

if __name__ == "__main__":
    main()
