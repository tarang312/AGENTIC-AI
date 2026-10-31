import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure root directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import ensure_api_key, STUDENTS_DB_FILE
from src.agent import StudentSupportAgent
from src.policy_retriever import PolicyRetriever
from src.memory import MemoryManager
from src.auth import authenticate, UserSession, list_students, get_user_profile
from src.approvals import approval_manager
from src.audit import audit_logger

app = FastAPI(
    title="Intelligent Student Support Portal API",
    description="Production-aware backend for student support and governance",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Agent singletons
retriever = PolicyRetriever()
memory = MemoryManager()
agent = StudentSupportAgent(retriever=retriever, memory=memory)

# In-memory session store by token for the web frontend
# Token -> UserSession
ACTIVE_SESSIONS: Dict[str, UserSession] = {}

class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    query: str
    session_history: Optional[List[Dict[str, str]]] = None

class EmailUpdateRequest(BaseModel):
    new_email: str

class DecisionRequest(BaseModel):
    request_id: str
    reason: Optional[str] = "Administrative review"

def get_current_session(request: Request) -> UserSession:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if token and token in ACTIVE_SESSIONS:
        return ACTIVE_SESSIONS[token]
    # Fallback to default student session (STU101) for seamless demo
    default_session = authenticate("STU101", "student123")
    if not default_session:
        raise HTTPException(status_code=401, detail="Authentication required")
    return default_session

# --- AUTH ENDPOINTS ---
@app.post("/api/auth/login")
def login(req: LoginRequest):
    session = authenticate(req.username, req.password)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid username or password credentials.")
    token = f"tok_{session.user_id}_{os.urandom(8).hex()}"
    ACTIVE_SESSIONS[token] = session
    return {
        "status": "success",
        "token": token,
        "user": session.model_dump()
    }

@app.post("/api/auth/logout")
def logout(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/api/auth/me")
def get_me(session: UserSession = Depends(get_current_session)):
    profile = get_user_profile(session.user_id) or {}
    return {
        "user": session.model_dump(),
        "profile": profile
    }

# --- CHAT & AGENT ENDPOINTS ---
@app.post("/api/chat")
def chat_with_agent(req: ChatRequest, session: UserSession = Depends(get_current_session)):
    try:
        agent_out = agent.process_query(
            query=req.query,
            session=session,
            session_history=req.session_history
        )
        
        trace_id = f"run-{os.urandom(5).hex()}"
        latency_ms = int(agent_out["latency_seconds"] * 1000)
        model_calls = 2 if agent_out.get("tools_used") else 1
        
        # Contextual follow-up suggestions
        q_lower = req.query.lower()
        if session.is_admin:
            suggestions = [
                "Show me fee status and pending dues of student STU101.",
                "Check academic profile and CGPA of student STU102.",
                "What is the handbook policy on payment portal failures?"
            ]
        elif "fee" in q_lower or "due" in q_lower or "balance" in q_lower:
            suggestions = [
                "The payment portal failed. Can I pay on the next working day?",
                "What is the late payment surcharge if paid after Nov 15?",
                "How do I request an official receipt for Term 1?"
            ]
        elif "email" in q_lower or "update" in q_lower or "change" in q_lower:
            suggestions = [
                "Where can I view the status of my approval request?",
                "How long does administrator approval take?",
                "What other profile details can I request to change?"
            ]
        else:
            suggestions = [
                "What is my current fee status and pending balance?",
                "What electives do you recommend for me?",
                "Please change my registered email to my personal email address."
            ]

        return {
            "status": "success",
            "answer": agent_out["answer"],
            "tools_used": agent_out["tools_used"],
            "retrieved_evidence": agent_out["retrieved_evidence"],
            "memory_notice": agent_out["memory_notice"],
            "latency_seconds": agent_out["latency_seconds"],
            "latency_ms": latency_ms,
            "model_calls": model_calls,
            "trace_id": trace_id,
            "prompt_tokens": agent_out["prompt_tokens"],
            "completion_tokens": agent_out["completion_tokens"],
            "total_tokens": agent_out["total_tokens"],
            "model_used": agent_out["model_used"],
            "suggestions": suggestions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- STUDENT DATA ENDPOINTS ---
@app.get("/api/student/dashboard")
def get_student_dashboard(session: UserSession = Depends(get_current_session)):
    profile = get_user_profile(session.user_id) or {}
    my_requests = approval_manager.list_requests(requester_id=session.user_id)
    return {
        "profile": profile,
        "requests": my_requests,
        "memory": memory.get_memory(session.user_id)
    }

@app.post("/api/student/request-email-update")
def request_email_update(req: EmailUpdateRequest, session: UserSession = Depends(get_current_session)):
    result = approval_manager.submit_email_update_request(session, req.new_email)
    return result

# --- ADMINISTRATOR ENDPOINTS ---
@app.get("/api/admin/dashboard")
def get_admin_dashboard(session: UserSession = Depends(get_current_session)):
    if not session.is_admin:
        raise HTTPException(status_code=403, detail="Administrative privileges required.")
    
    students = list_students()
    all_reqs = approval_manager.list_requests()
    pending = [r for r in all_reqs if r["status"] == "PENDING"]
    approved = [r for r in all_reqs if r["status"] in ("APPROVED", "EXECUTED")]
    rejected = [r for r in all_reqs if r["status"] == "REJECTED"]
    
    logs = audit_logger.get_logs(limit=250)
    unauthorized = [l for l in logs if l.get("permission_decision") == "DENIED"]

    return {
        "total_students": len(students),
        "pending_count": len(pending),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "unauthorized_count": len(unauthorized),
        "pending_requests": pending,
        "recent_audit_logs": logs[:25]
    }

@app.get("/api/admin/approvals")
def get_admin_approvals(session: UserSession = Depends(get_current_session)):
    if not session.is_admin:
        raise HTTPException(status_code=403, detail="Administrative privileges required.")
    return {
        "pending": approval_manager.list_requests(status="PENDING"),
        "all": approval_manager.list_requests()
    }

@app.post("/api/admin/approve")
def approve_request(req: DecisionRequest, session: UserSession = Depends(get_current_session)):
    if not session.is_admin:
        raise HTTPException(status_code=403, detail="Administrative privileges required.")
    result = approval_manager.approve_and_execute(session, req.request_id)
    return result

@app.post("/api/admin/reject")
def reject_request(req: DecisionRequest, session: UserSession = Depends(get_current_session)):
    if not session.is_admin:
        raise HTTPException(status_code=403, detail="Administrative privileges required.")
    result = approval_manager.reject_request(session, req.request_id, req.reason or "Rejected by administration")
    return result

@app.get("/api/admin/audit-logs")
def get_audit_logs(user_id: Optional[str] = None, session: UserSession = Depends(get_current_session)):
    if not session.is_admin:
        raise HTTPException(status_code=403, detail="Administrative privileges required.")
    return audit_logger.get_logs(user_id=user_id if user_id else None, limit=100)

@app.get("/api/admin/students")
def get_all_students(session: UserSession = Depends(get_current_session)):
    if not session.is_admin:
        raise HTTPException(status_code=403, detail="Administrative privileges required.")
    return list_students()

# --- POLICY HANDBOOK ENDPOINT ---
@app.get("/api/handbook/sections")
def get_handbook_sections():
    """Returns all chunked handbook policy sections for the interactive policy explorer."""
    return [
        {
            "chunk_id": c["chunk_id"],
            "title": c["title"],
            "content": c["content"]
        }
        for c in retriever.chunks
    ]

# Serve static frontend files
FRONTEND_DIR = BASE_DIR / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Student Support Portal frontend initializing...</h1>"

if __name__ == "__main__":
    import uvicorn
    ensure_api_key(interactive=False)
    print("\nStarting Student Support Portal on http://localhost:8000 ...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)

