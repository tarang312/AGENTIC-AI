import json
import time
from typing import Dict, Any, List, Optional
from src.groq_client import GroqClientWrapper, LLMResponse
from src.tools import TOOL_DISPATCH, GROQ_TOOLS_SCHEMA
from src.policy_retriever import PolicyRetriever
from src.memory import MemoryManager

SYSTEM_PROMPT = """You are an Intelligent Student Support Agent for the PGDM (Big Data Analytics / Artificial Intelligence & Data Science) Programme.
Your role is to assist students with queries regarding tuition fees, academic records, scholarships, institutional policies, and support requests.

### Core Guidelines:
1. **Tool Usage**: Use tools when specific student data is requested:
   - `check_student_record`: For student profile, CGPA, advisor, or enrolled programme.
   - `check_fee_status`: For pending fees, due dates, installment history, or balance.
   - `check_scholarship_status`: For scholarship awards, waiver percentage, or renewal conditions.
   - `create_support_ticket`: For raising issues, complaints, technical failures, or when a question cannot be answered from available policy.
2. **Policy Knowledge**: Use the retrieved policy chunks provided in context. Do NOT invent policies. If a question is not covered by the retrieved policy or available data, explicitly acknowledge that the policy handbook does not contain this information and offer to open a support ticket.
3. **Persistent Memory**: Utilize remembered student facts if provided in context (e.g., student's academic interests, career goals).
4. **Security & Privacy**: NEVER request or store passwords, OTPs, or payment card details. If a student mentions them, advise them that credentials should never be shared.
5. **Tone**: Be professional, clear, empathetic, and actionable. Cite relevant policy section numbers or deadlines when applicable.
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
        auto_inspect_memory: bool = True
    ) -> Dict[str, Any]:
        """
        Executes the agentic reasoning and execution loop:
        1. Context Selection (Retrieve relevant policy chunks + Persistent memory).
        2. Prompt Assembly (Strictly bounded context).
        3. LLM Decision & Tool Calling Loop.
        4. Observation synthesis & Final Response.
        5. Tracing metadata generation (latency, token usage, tools used, evidence).
        """
        start_time = time.perf_counter()
        tools_used = []
        retrieved_evidence = []
        total_prompt_tokens = 0
        total_completion_tokens = 0

        # Step 1: Memory Inspection & Filtering
        memory_notice = ""
        if auto_inspect_memory and student_id:
            # Check if user query contains sensitive or temporary statements
            is_allowed, reason = self.memory.inspect_statement(query)
            if not is_allowed:
                memory_notice = f"[Memory Security Filter Alert: {reason}]"

        # Step 2: Context Selection (RAG)
        policy_context = ""
        matched_chunks = self.retriever.retrieve(query, top_k=2)
        if matched_chunks:
            policy_context = "\n\n### Relevant Policy Handbook Chunks:\n"
            for chunk in matched_chunks:
                retrieved_evidence.append(f"{chunk['chunk_id']} ({chunk['title']})")
                policy_context += f"--- {chunk['title']} (ID: {chunk['chunk_id']}) ---\n{chunk['content']}\n\n"
        else:
            policy_context = "\n\n### Relevant Policy Handbook Chunks:\n[No matching policy sections found in the handbook for this query.]\n"

        # Step 3: Persistent Memory Injection
        student_memory_context = ""
        if student_id:
            student_memory_context = f"\n\n### Student ID: {student_id}\n"
            mem_str = self.memory.format_memory_for_context(student_id)
            student_memory_context += mem_str
            facts = self.memory.get_memory(student_id)
            for k in facts.keys():
                retrieved_evidence.append(f"Memory: {k}")

        # Assemble Messages
        system_content = SYSTEM_PROMPT + policy_context + student_memory_context
        if memory_notice:
            system_content += f"\n\nNOTICE: {memory_notice}"

        messages = [{"role": "system", "content": system_content}]

        # Append recent session history if provided
        if session_history:
            messages.extend(session_history[-4:])  # Keep last 2 turns

        # Current user query
        messages.append({"role": "user", "content": query})

        # Step 4: Call LLM with tool definitions
        response: LLMResponse = self.llm.complete(
            messages=messages,
            tools=GROQ_TOOLS_SCHEMA,
            tool_choice="auto"
        )
        total_prompt_tokens += response.prompt_tokens
        total_completion_tokens += response.completion_tokens

        # Step 5: Agent Loop - Handle Tool Calls
        if response.tool_calls:
            # Append model's tool calling response
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

            # Execute each called tool
            for tc in response.tool_calls:
                func_name = tc["name"]
                tools_used.append(func_name)
                
                try:
                    args = json.loads(tc["arguments"])
                except Exception:
                    args = {}

                # If student_id was missing in arguments, fallback to active session student_id
                if "student_id" in args and not args["student_id"] and student_id:
                    args["student_id"] = student_id
                elif "student_id" not in args and student_id:
                    args["student_id"] = student_id

                if func_name in TOOL_DISPATCH:
                    tool_func = TOOL_DISPATCH[func_name]
                    try:
                        observation = tool_func(**args)
                    except Exception as err:
                        observation = {"status": "error", "message": f"Tool execution failed: {str(err)}"}
                else:
                    observation = {"status": "error", "message": f"Unknown tool: {func_name}"}

                # Return observation as tool message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": func_name,
                    "content": json.dumps(observation)
                })

            # Call LLM again to synthesize final answer from observations
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
