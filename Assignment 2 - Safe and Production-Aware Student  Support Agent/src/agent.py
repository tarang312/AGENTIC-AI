import json
import inspect
import time
from typing import Dict, Any, List, Optional
from src.groq_client import GroqClientWrapper, LLMResponse
from src.tools import TOOL_DISPATCH, GROQ_TOOLS_SCHEMA
from src.policy_retriever import PolicyRetriever
from src.memory import MemoryManager, redact_sensitive_credentials
from src.auth import UserSession, get_user_profile
from src.audit import audit_logger

SYSTEM_PROMPT_STUDENT = """You are a Safe and Production-Aware Intelligent Student Support Agent for the PGDM (Big Data Analytics / Artificial Intelligence & Data Science) Programme.
You are interacting with an AUTHENTICATED STUDENT.

### Core Guidelines for Student Users:
1. **Access Scope**:
   - The student may only inspect their own academic, fee, and scholarship records.
   - If they request another student's private record, the backend authorization engine will DENY it. Report this clearly and politely.
2. **Tools**:
   - `check_student_record`: For their academic profile, CGPA, advisor, or enrolled programme.
   - `check_fee_status`: For pending fees, due dates, installment history, or balance.
   - `check_scholarship_status`: For scholarship awards, waiver percentage, or renewal conditions.
   - `create_support_ticket`: For raising issues, complaints, or technical failures.
   - `request_email_update`: When the student requests to update their registered email address. This queues a pending approval request for administrator verification.
   - `view_my_approval_requests`: To check the status of pending or reviewed change requests.
3. **Sensitive Information**:
   - NEVER ask for, store, or accept passwords, OTPs, API keys, or payment card details.
   - If credentials appear, advise: "For your security, please do not share passwords, OTPs or authentication credentials in this chat."
4. **Policy Knowledge (RAG)**:
   - Rely strictly on retrieved policy chunks provided in context. Do NOT invent policies.
"""

SYSTEM_PROMPT_ADMIN = """You are an Intelligent Academic Operations & Governance Assistant for the PGDM Programme.
You are interacting with an AUTHENTICATED ADMINISTRATOR (Office of Academic & Student Affairs).

### Core Guidelines for Administrator Users:
1. **Role & Authority**:
   - You are an administrative staff officer, NOT an enrolled student.
   - You do NOT have student fee balances, student tuition, student CGPA, or student scholarships.
   - If the administrator asks about their own fee status or scholarship, explain clearly that administrative staff do not have student tuition fee obligations or course enrollments.
2. **Administrative Access**:
   - Administrators have legitimate authority to inspect any student's records (e.g. STU101, STU102, STU103) for academic advising, fee reconciliation, or audit reviews.
   - Use `check_student_record(student_id)`, `check_fee_status(student_id)`, `check_scholarship_status(student_id)` when the administrator inquires about a specific student.
   - Support queries regarding institutional handbook policies, approval workflows, and audit procedures.
3. **Sensitive Actions & Governance**:
   - Profile changes (such as email modifications) submitted by students require administrator review and approval via the management dashboard.
"""

class StudentSupportAgent:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        retriever: Optional[PolicyRetriever] = None,
        memory: Optional[MemoryManager] = None
    ):
        self.llm = GroqClientWrapper(api_key=api_key, model=model) if model else GroqClientWrapper(api_key=api_key)
        self.retriever = retriever or PolicyRetriever()
        self.memory = memory or MemoryManager()

    def process_query(
        self,
        query: str,
        student_id: Optional[str] = None,
        session_history: Optional[List[Dict[str, str]]] = None,
        auto_inspect_memory: bool = True,
        session: Optional[UserSession] = None
    ) -> Dict[str, Any]:
        """
        Executes the Safe & Production-Aware Agentic reasoning and execution loop:
        1. Authentication & Role-specific persona selection (Student vs Administrator).
        2. Sensitive Credential Scrubbing (Prevents API & log leakage).
        3. Memory Inspection & Temporary/Fleeting Filter.
        4. Context Selection (Top-K BM25 RAG Chunks + Persistent Student Memory).
        5. LLM Decision & Tool Calling Loop with Backend Authorization Enforcement.
        6. Observation synthesis & Final Response generation.
        7. Tracing metadata generation (latency, token usage, tools used, evidence).
        """
        start_time = time.perf_counter()
        tools_used = []
        retrieved_evidence = []
        total_prompt_tokens = 0
        total_completion_tokens = 0

        # Step 1: Session Resolution
        if not session and student_id:
            profile = get_user_profile(student_id)
            if profile:
                session = UserSession(
                    user_id=profile.get("student_id", profile.get("user_id", student_id)),
                    name=profile.get("full_name", student_id),
                    role=profile.get("role", "student"),
                    email=profile.get("email", "")
                )
            else:
                session = UserSession(
                    user_id=student_id,
                    name=student_id,
                    role="student",
                    email=""
                )

        is_admin = session.is_admin if session else False
        effective_user_id = session.user_id if session else student_id

        # Step 2: Sensitive Credential Scrubbing
        sanitized_query, has_sensitive_credentials, detected_types = redact_sensitive_credentials(query)

        memory_notice = ""
        if has_sensitive_credentials:
            memory_notice = "For your security, please do not share passwords, OTPs or authentication credentials in this chat."

        # Step 3: Inspect for temporary / fleeting conditions
        if auto_inspect_memory and effective_user_id and not is_admin:
            is_allowed, reason = self.memory.inspect_statement(query)
            if not is_allowed and not memory_notice:
                memory_notice = f"[Memory Security Filter Alert: {reason}]"

        # Step 4: Context Selection (RAG)
        policy_context = ""
        matched_chunks = self.retriever.retrieve(sanitized_query, top_k=2)
        if matched_chunks:
            policy_context = "\n\n### Relevant Policy Handbook Chunks:\n"
            for chunk in matched_chunks:
                retrieved_evidence.append(f"{chunk['chunk_id']} ({chunk['title']})")
                policy_context += f"--- {chunk['title']} (ID: {chunk['chunk_id']}) ---\n{chunk['content']}\n\n"
        else:
            policy_context = "\n\n### Relevant Policy Handbook Chunks:\n[No matching policy sections found in the handbook for this query.]\n"

        # Step 5: User Identity Context & Memory Injection
        identity_context = ""
        if is_admin:
            identity_context = (
                f"\n\n### Authenticated Administrator: {session.name} [{session.user_id}]\n"
                f"Role: Academic Administrator (Office of Academic & Student Affairs)\n"
                f"Notice: You are an administrative officer. You do NOT have personal student tuition fees, scholarships, or CGPA. "
                f"You have legitimate authority to query and review any enrolled student's records by student ID.\n"
            )
        elif effective_user_id:
            identity_context = f"\n\n### Authenticated Enrolled Student: {session.name if session else effective_user_id} [{effective_user_id}]\n"
            mem_str = self.memory.format_memory_for_context(effective_user_id)
            identity_context += mem_str
            facts = self.memory.get_memory(effective_user_id)
            for k in facts.keys():
                retrieved_evidence.append(f"Memory: {k}")

        # Assemble Prompt Messages
        base_prompt = SYSTEM_PROMPT_ADMIN if is_admin else SYSTEM_PROMPT_STUDENT
        system_content = base_prompt + policy_context + identity_context
        if memory_notice:
            system_content += f"\n\nSECURITY NOTICE: {memory_notice}"

        messages = [{"role": "system", "content": system_content}]

        # Append recent session history if provided
        if session_history:
            messages.extend(session_history[-4:])  # Keep last 2 turns

        # Current user query
        messages.append({"role": "user", "content": sanitized_query})

        # Step 6: Call LLM with tool definitions
        response: LLMResponse = self.llm.complete(
            messages=messages,
            tools=GROQ_TOOLS_SCHEMA,
            tool_choice="auto"
        )
        total_prompt_tokens += response.prompt_tokens
        total_completion_tokens += response.completion_tokens

        # Step 7: Agent Loop - Handle Tool Calls
        if response.tool_calls:
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"]
                        }
                    }
                    for tc in response.tool_calls
                ]
            })

            # Execute each called tool with backend authorization injection
            for tc in response.tool_calls:
                func_name = tc["name"]
                tools_used.append(func_name)

                try:
                    args = json.loads(tc["arguments"])
                except Exception:
                    args = {}

                # Fallback student_id ONLY for students querying without explicit argument
                if not is_admin:
                    if "student_id" in args and not args["student_id"] and effective_user_id:
                        args["student_id"] = effective_user_id
                    elif "student_id" not in args and effective_user_id and func_name in [
                        "check_student_record", "check_fee_status", "check_scholarship_status", "create_support_ticket"
                    ]:
                        args["student_id"] = effective_user_id

                if func_name in TOOL_DISPATCH:
                    tool_func = TOOL_DISPATCH[func_name]
                    sig = inspect.signature(tool_func)
                    if "session" in sig.parameters:
                        args["session"] = session

                    try:
                        observation = tool_func(**args)
                    except Exception as err:
                        observation = {"status": "error", "message": f"Tool execution failed: {str(err)}"}
                else:
                    observation = {"status": "error", "message": f"Unknown tool: {func_name}"}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": func_name,
                    "content": json.dumps(observation)
                })

            final_response = self.llm.complete(messages=messages, tools=None)
            total_prompt_tokens += final_response.prompt_tokens
            total_completion_tokens += final_response.completion_tokens
            answer = final_response.content
        else:
            answer = response.content

        end_time = time.perf_counter()
        total_latency = end_time - start_time

        return {
            "answer": answer,
            "tools_used": tools_used,
            "retrieved_evidence": retrieved_evidence,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "latency_seconds": round(total_latency, 3),
            "memory_notice": memory_notice,
            "model_used": response.model
        }
