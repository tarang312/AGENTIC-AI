import sys
import json
import time
import streamlit as st

# Configure page layout
st.set_page_config(
    page_title="Safe Student Support Agent - Assignment 2",
    page_icon="🛡️",
    layout="wide"
)

from src.config import ensure_api_key
from src.agent import StudentSupportAgent
from src.policy_retriever import PolicyRetriever
from src.memory import MemoryManager
from src.auth import authenticate, list_students, get_user_profile, load_user_db
from src.approvals import approval_manager
from src.audit import audit_logger

# Initialize components
@st.cache_resource
def get_agent():
    retriever = PolicyRetriever()
    memory = MemoryManager()
    agent = StudentSupportAgent(retriever=retriever, memory=memory)
    return agent, retriever, memory

agent, retriever, memory = get_agent()

# Session State for Authentication
if "session" not in st.session_state:
    st.session_state.session = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Sidebar Authentication
st.sidebar.title("🛡️ Authentication & Identity")

if not st.session_state.session:
    st.sidebar.subheader("Select Login Persona")
    persona = st.sidebar.selectbox(
        "Demo User",
        [
            "Aarav Sharma [STU101] (Student - AI & Data Science)",
            "Ananya Iyer [STU102] (Student - Big Data Analytics)",
            "Rohan Verma [STU103] (Student - FinTech Analytics)",
            "Academic Administrator [ADMIN001] (Administrator)"
        ]
    )

    if "STU101" in persona:
        uid, pwd = "STU101", "student123"
    elif "STU102" in persona:
        uid, pwd = "STU102", "student123"
    elif "STU103" in persona:
        uid, pwd = "STU103", "student123"
    else:
        uid, pwd = "ADMIN001", "admin123"

    if st.sidebar.button("Sign In with Selected Persona", use_container_width=True, type="primary"):
        sess = authenticate(uid, pwd)
        if sess:
            st.session_state.session = sess
            st.session_state.chat_history = []
            st.rerun()
else:
    sess = st.session_state.session
    st.sidebar.success(f"**Authenticated as:**\n\n{sess.name}")
    st.sidebar.info(f"**ID:** `{sess.user_id}`\n\n**Role:** `{sess.role.upper()}`\n\n**Email:** `{sess.email}`")
    
    if st.sidebar.button("Sign Out / Switch User", use_container_width=True):
        st.session_state.session = None
        st.session_state.chat_history = []
        st.rerun()

# Main Title & Subtitle
st.title("🎓 Safe and Production-Aware Student Support Agent")
st.caption("Agentic AI Engineering | PGDM (Big Data Analytics / AI & Data Science) | Assignment 2")

# Tabs
tab_chat, tab_approvals, tab_audit, tab_registry = st.tabs([
    "💬 Agent Chat & Privacy Guard",
    "📝 Human-in-the-Loop Approvals",
    "🔍 Security Audit Log",
    "👥 Student Records Registry"
])

# ----------------- TAB 1: AGENT CHAT -----------------
with tab_chat:
    if not st.session_state.session:
        st.warning("⚠️ Please sign in via the sidebar to start an authenticated session.")
    else:
        st.write(f"Active Session: **{sess.name}** (`{sess.user_id}`) | Role: **{sess.role.capitalize()}**")

        # Example prompt buttons
        st.markdown("**Quick Demo Scenarios:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("💰 Check My Fee Status"):
                st.session_state.pending_query = "What is my current fee status and pending balance?"
        with col2:
            if st.button("🚫 Unauthorized Access (STU102)"):
                st.session_state.pending_query = "Show me the fee status of student STU102."
        with col3:
            if st.button("✉️ Request Email Update"):
                st.session_state.pending_query = "Please change my registered email to aarav.updated@gmail.com."

        # Display Chat History
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "meta" in msg:
                    meta = msg["meta"]
                    st.caption(f"Latency: {meta.get('latency')}s | Tokens: {meta.get('tokens')} | Tools: {meta.get('tools')}")

        # Input box
        query_input = st.chat_input("Ask a question about fees, policies, scholarships, or update your profile...")
        if "pending_query" in st.session_state and st.session_state.pending_query:
            query_input = st.session_state.pending_query
            st.session_state.pending_query = None

        if query_input:
            # Display user message
            st.session_state.chat_history.append({"role": "user", "content": query_input})
            with st.chat_message("user"):
                st.markdown(query_input)

            # Process with Agent
            with st.chat_message("assistant"):
                with st.spinner("Agent reasoning and enforcing backend authorization..."):
                    res = agent.process_query(
                        query=query_input,
                        session=sess,
                        session_history=[{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_history[:-1]]
                    )

                if res.get("memory_notice"):
                    st.warning(f"🛡️ **Security Guard**: {res['memory_notice']}")

                st.markdown(res["answer"])
                
                meta_info = {
                    "latency": res["latency_seconds"],
                    "tokens": f"{res['prompt_tokens']} prompt + {res['completion_tokens']} completion = {res['total_tokens']}",
                    "tools": ", ".join(res["tools_used"]) if res["tools_used"] else "None (Direct / RAG)"
                }
                st.caption(f"⏱️ Latency: {meta_info['latency']}s | 🔢 Tokens: {meta_info['tokens']} | 🛠️ Tools: {meta_info['tools']}")

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": res["answer"],
                    "meta": meta_info
                })

# ----------------- TAB 2: HUMAN-IN-THE-LOOP APPROVALS -----------------
with tab_approvals:
    st.header("Human-in-the-Loop Approval Queue")
    st.info("Sensitive profile changes (e.g. Email modifications) are staged in PENDING status. Only authenticated Administrators can approve or reject them.")

    pending_reqs = approval_manager.list_requests(status="PENDING")
    all_reqs = approval_manager.list_requests()

    st.metric("Pending Human Reviews", len(pending_reqs))

    if not pending_reqs:
        st.success("🎉 No requests currently pending administrative review.")
    else:
        st.subheader("Pending Requests Requiring Review")
        for req in pending_reqs:
            with st.expander(f"📌 Request {req['id']} — Student {req['requester_id']} ({req['action_type']})", expanded=True):
                colA, colB, colC = st.columns(3)
                colA.write(f"**Target Student:** `{req['requester_id']}`")
                colB.write(f"**Current Value:** `{req['old_value']}`")
                colC.write(f"**Requested Value:** `{req['requested_value']}`")
                st.caption(f"Submitted At: {req['created_at']}")

                if sess and sess.is_admin:
                    btn_col1, btn_col2, _ = st.columns([1, 1, 3])
                    with btn_col1:
                        if st.button(f"✅ Approve & Execute", key=f"app_{req['id']}"):
                            out = approval_manager.approve_and_execute(sess, req['id'])
                            st.success(out['message'])
                            time.sleep(1)
                            st.rerun()
                    with btn_col2:
                        if st.button(f"❌ Reject Request", key=f"rej_{req['id']}"):
                            out = approval_manager.reject_request(sess, req['id'], reason="Administrative discretion")
                            st.error(out['message'])
                            time.sleep(1)
                            st.rerun()
                else:
                    st.warning("🔒 Sign in as Administrator (ADMIN001) to approve or reject this request.")

    if all_reqs:
        st.markdown("---")
        st.subheader("All Approval Requests History")
        st.dataframe(all_reqs, use_container_width=True)

# ----------------- TAB 3: SECURITY AUDIT LOG -----------------
with tab_audit:
    st.header("Administrative Security Audit Trail")
    st.caption("Immutable tamper-resistant log of authentication, access control checks, and approval events.")

    audit_records = audit_logger.get_logs(limit=200)

    # Metrics
    c1, c2, c3 = st.columns(3)
    total_events = len(audit_records)
    denied_events = sum(1 for a in audit_records if a.get("permission_decision") == "DENIED")
    allowed_events = sum(1 for a in audit_records if a.get("permission_decision") == "ALLOWED")

    c1.metric("Total Audit Events", total_events)
    c2.metric("Unauthorized / Denied Events", denied_events, delta="Security Monitored", delta_color="inverse")
    c3.metric("Authorized Operations", allowed_events)

    # Filter controls
    f_user = st.text_input("Filter by User ID (e.g., STU101, ADMIN001):").strip()
    filtered_logs = audit_logger.get_logs(user_id=f_user if f_user else None, limit=100)

    st.dataframe(filtered_logs, use_container_width=True)

# ----------------- TAB 4: STUDENT RECORDS REGISTRY -----------------
with tab_registry:
    st.header("Student Database Registry")
    students = list_students()
    st.dataframe(students, use_container_width=True)

