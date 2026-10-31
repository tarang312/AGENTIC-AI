import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from tabulate import tabulate
from src.config import LOGS_DIR
from src.memory import redact_sensitive_credentials

class TraceRecord(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    scenario_id: str
    question: str
    student_id: Optional[str] = None
    success: bool
    tools_used: List[str] = Field(default_factory=list)
    tool_assessment: str = "Appropriate"
    latency_sec: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    retrieved_evidence: List[str] = Field(default_factory=list)
    final_response: str = ""
    evaluation_notes: str = ""

class ExecutionTracer:
    """
    Collects, logs, and formats structured agent traces across test runs.
    Outputs evaluation metrics (Task accuracy, Tools used, Latency, Token usage, Evidence).
    Ensures zero credential leakage by scrubbing sensitive tokens from traces.
    """
    def __init__(self, log_filename: str = "agent_trace_log.jsonl"):
        self.log_file = LOGS_DIR / log_filename
        self.traces: List[TraceRecord] = []

    def record_trace(self, trace: TraceRecord):
        # Scrub any passwords/secrets before writing to persistent trace log
        clean_question, _, _ = redact_sensitive_credentials(trace.question)
        clean_response, _, _ = redact_sensitive_credentials(trace.final_response)
        
        safe_trace = trace.model_copy(update={
            "question": clean_question,
            "final_response": clean_response
        })

        self.traces.append(safe_trace)
        # Append to jsonl file
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(safe_trace.model_dump_json() + "\n")

    def generate_summary_table(self) -> str:
        """
        Generate a formatted table matching the assignment's Tracing and Measurement rubric.
        """
        table_rows = []
        for t in self.traces:
            tools_str = ", ".join(t.tools_used) if t.tools_used else "None (Direct / RAG)"
            evidence_str = "; ".join(t.retrieved_evidence) if t.retrieved_evidence else "None"
            # Truncate evidence if too long for terminal display
            if len(evidence_str) > 40:
                evidence_str = evidence_str[:37] + "..."

            status_str = "PASS" if t.success else "FAIL"
            table_rows.append([
                t.scenario_id,
                t.question[:30] + ("..." if len(t.question) > 30 else ""),
                status_str,
                f"{tools_str} ({t.tool_assessment})",
                f"{t.latency_sec:.2f}s",
                f"{t.prompt_tokens} in / {t.completion_tokens} out ({t.total_tokens} tot)",
                evidence_str
            ])

        headers = [
            "Scenario",
            "Question",
            "Status",
            "Tools Used & Assessment",
            "Latency",
            "Token Usage (In/Out/Tot)",
            "Retrieved Evidence"
        ]

        return tabulate(table_rows, headers=headers, tablefmt="grid")

    def compute_aggregate_metrics(self) -> Dict[str, Any]:
        """Compute summary statistics across all traces."""
        if not self.traces:
            return {}

        total_runs = len(self.traces)
        successful_runs = sum(1 for t in self.traces if t.success)
        avg_latency = sum(t.latency_sec for t in self.traces) / total_runs
        total_prompt_tokens = sum(t.prompt_tokens for t in self.traces)
        total_completion_tokens = sum(t.completion_tokens for t in self.traces)
        total_tokens = sum(t.total_tokens for t in self.traces)

        return {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "accuracy_pct": round((successful_runs / total_runs) * 100, 1),
            "avg_latency_sec": round(avg_latency, 2),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        }
