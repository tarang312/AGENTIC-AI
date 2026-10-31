import sys
import json
from pathlib import Path
from colorama import init, Fore, Style

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
from evaluate import run_evaluation_suite

init(autoreset=True)

def load_students():
    if not STUDENTS_DB_FILE.exists():
        return {}
    with open(STUDENTS_DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    print(f"\n{Fore.CYAN}{Style.BRIGHT}========================================================================")
    print("      AGENTIC AI ENGINEERING: INTELLIGENT STUDENT SUPPORT AGENT")
    print("            PGDM (Big Data Analytics / AI & Data Science)")
    print(f"========================================================================{Style.RESET_ALL}")

    # Ensure API Key is configured (prompts user if not in .env)
    ensure_api_key(interactive=True)

    retriever = PolicyRetriever()
    memory = MemoryManager()
    agent = StudentSupportAgent(retriever=retriever, memory=memory)
    students = load_students()

    current_student_id = "STU101"
    student_info = students.get(current_student_id, {})
    student_name = student_info.get("full_name", "Aarav Sharma")
    programme = student_info.get("programme", "PGDM (AI & Data Science)")

    print(f"\n{Fore.GREEN}Active Student:{Style.RESET_ALL} {student_name} [{current_student_id}]")
    print(f"{Fore.GREEN}Programme:{Style.RESET_ALL}      {programme}")
    print(f"{Fore.YELLOW}Commands:{Style.RESET_ALL}       '/eval' to display evaluation table | '/student <ID>' to switch student | 'exit' to quit\n")
    print(f"{Fore.WHITE}Agent: Hello! I am your AI Student Support Agent. How can I assist you today?{Style.RESET_ALL}\n")

    history = []

    while True:
        try:
            prompt_str = f"{Fore.BLUE}{Style.BRIGHT}[{current_student_id}] You > {Style.RESET_ALL}"
            user_input = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting session. Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
            print("Session ended. Goodbye!")
            break

        if user_input.lower() == "/eval":
            run_evaluation_suite()
            continue

        if user_input.startswith("/student"):
            parts = user_input.split()
            if len(parts) > 1:
                new_id = parts[1].upper()
                if new_id in students:
                    current_student_id = new_id
                    s_info = students[current_student_id]
                    print(f"{Fore.GREEN}[OK] Switched student to {s_info['full_name']} ({current_student_id}){Style.RESET_ALL}\n")
                    history = []
                else:
                    print(f"{Fore.RED}[!] Student ID '{new_id}' not found. Available IDs: {', '.join(students.keys())}{Style.RESET_ALL}\n")
            else:
                print(f"Active student is {current_student_id}. Switch using: /student <ID>\n")
            continue

        # Process student query through the agentic loop
        agent_out = agent.process_query(
            query=user_input,
            student_id=current_student_id,
            session_history=history
        )

        # Show trace details
        if agent_out["tools_used"]:
            print(f"{Fore.MAGENTA}[Tool Used]: {', '.join(agent_out['tools_used'])}{Style.RESET_ALL}")
        if agent_out["retrieved_evidence"]:
            print(f"{Fore.CYAN}[Evidence]: {', '.join(agent_out['retrieved_evidence'])}{Style.RESET_ALL}")
        if agent_out["memory_notice"]:
            print(f"{Fore.YELLOW}[Security Guard]: {agent_out['memory_notice']}{Style.RESET_ALL}")

        print(f"\n{Fore.WHITE}{Style.BRIGHT}Agent:{Style.RESET_ALL} {agent_out['answer']}")
        print(f"{Fore.LIGHTBLACK_EX}[Latency: {agent_out['latency_seconds']}s | Tokens: {agent_out['prompt_tokens']} prompt + {agent_out['completion_tokens']} completion = {agent_out['total_tokens']} total]{Style.RESET_ALL}\n")

        # Update history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": agent_out["answer"]})

if __name__ == "__main__":
    main()
