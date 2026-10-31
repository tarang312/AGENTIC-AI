# Agentic AI Engineering — Assignment 1: Evaluation Report
**Course**: PGDM (Big Data Analytics / AI & Data Science) | Batch 2025-27  
**Assignment**: Intelligent Student Support Agent  
**Date**: October 2026  
**Status**: Completed & Verified

---

## 1. Tracing & Measurement Table

Below is the structured trace table capturing all five assignment demonstration scenarios, demonstrating task success, tool selection accuracy, response latency, token consumption, and evidence grounding.

```
+------------+---------------------------------+----------+------------------------------------------+-----------+-----------------------------------+---------------------------------------+
| Scenario   | Question                        | Status   | Tools Used & Assessment                  | Latency   | Token Usage (In/Out/Tot)          | Retrieved Evidence                    |
+============+=================================+==========+==========================================+===========+===================================+=======================================+
| Scenario 1 | What is my current fee status?  | PASS     | check_fee_status (Appropriate)           | 1.12s     | 468 in / 114 out (582 tot)        | None (Direct Tool Invocation)         |
+------------+---------------------------------+----------+------------------------------------------+-----------+-----------------------------------+---------------------------------------+
| Scenario 2 | The payment portal failed. C... | PASS     | None (Direct / RAG) (Appropriate)        | 0.84s     | 624 in / 152 out (776 tot)        | POLICY-SEC-3 (Section 3: Payment P... |
+------------+---------------------------------+----------+------------------------------------------+-----------+-----------------------------------+---------------------------------------+
| Scenario 3 | What electives do you recomm... | PASS     | None (Direct / RAG) (Appropriate)        | 0.79s     | 486 in / 128 out (614 tot)        | Memory: specialization_interest       |
+------------+---------------------------------+----------+------------------------------------------+-----------+-----------------------------------+---------------------------------------+
| Scenario 4 | My student portal password i... | PASS     | None (Direct / RAG) (Appropriate)        | 0.88s     | 512 in / 118 out (630 tot)        | Memory Filter Alert (Security Guard)  |
+------------+---------------------------------+----------+------------------------------------------+-----------+-----------------------------------+---------------------------------------+
| Scenario 5 | Does the institute provide a ... | PASS     | create_support_ticket (Appropriate)      | 1.24s     | 572 in / 141 out (713 tot)        | Policy Gap / Escalation               |
+------------+---------------------------------+----------+------------------------------------------+-----------+-----------------------------------+---------------------------------------+
```

---

## 2. Aggregate Performance Summary

- **Task Accuracy / Success Rate**: **100% (5/5 scenarios passed)**
- **Average End-to-End Latency**: **0.97 seconds per query**
- **Token Efficiency**: Average total tokens consumed was **663 tokens per turn**, demonstrating effective context selection (RAG chunks + student-specific facts) without blowing prompt budgets.

---

## 3. Detailed Trace & Observations by Scenario

### Scenario 1: “What is my current fee status?”
- **Student ID**: `STU101` (Aarav Sharma)
- **Status**: **PASS**
- **Tools Called**: `check_fee_status(student_id="STU101")`
- **Tool Assessment**: **Appropriate**. The agent correctly recognized the request for private student financial records and dispatched the `check_fee_status` tool with the active student ID.
- **Latency**: 1.12s
- **Token Usage**: 468 prompt + 114 completion = 582 total
- **Retrieved Evidence**: Direct tool result: Total term fee ₹3,00,000, Paid amount ₹2,50,000, Pending balance ₹50,000, Due date: Nov 15, 2026.
- **Agent Output Summary**: The agent structured the financial balance clearly, noted the pending balance of ₹50,000 due on November 15, 2026, and confirmed no late penalties have accrued.

---

### Scenario 2: “The payment portal failed. Can I pay on the next working day?”
- **Student ID**: `STU101`
- **Status**: **PASS**
- **Tools Called**: None (Direct / RAG)
- **Tool Assessment**: **Appropriate**. No personal tool call was required; rather, authoritative institutional policy was needed.
- **Latency**: 0.84s
- **Token Usage**: 624 prompt + 152 completion = 776 total
- **Retrieved Evidence**: `POLICY-SEC-3` (*Section 3: Payment Portal Technical Failures & Grace Period Policy*)
- **Agent Output Summary**: The agent accurately cited Section 3 of the handbook, confirming that students are granted an automatic technical grace period of two working days. It explicitly advised the student that paying on the next working day is permitted without penalty, provided they email `accounts@institute.edu` with their screenshot and UTR within 24 hours.

---

### Scenario 3: Cross-Session Persistent Memory Recall
- **Student ID**: `STU101`
- **Query**: *"What electives do you recommend for me?"*
- **Prior Context**: In Session 1, the student had stated their focus on AI & Data Science with special interest in Natural Language Processing (NLP).
- **Status**: **PASS**
- **Tools Called**: None (Direct / RAG + Memory synthesis)
- **Tool Assessment**: **Appropriate**.
- **Latency**: 0.79s
- **Token Usage**: 486 prompt + 128 completion = 614 total
- **Retrieved Evidence**: `Memory: specialization_interest` ("Student is in AI & Data Science and has a strong interest in Natural Language Processing (NLP) and Deep Learning.")
- **Agent Output Summary**: The agent acknowledged Aarav's remembered focus in NLP and recommended the exact matching curriculum electives: *Advanced NLP*, *Generative AI Systems*, and *Distributed Computing*, demonstrating true cross-session memory continuity.

---

### Scenario 4: Sensitive & Temporary Statement Filter
- **Student ID**: `STU101`
- **Query**: *"My student portal password is Pass#2025Secret and I also have a bad headache today."*
- **Status**: **PASS**
- **Tools Called**: None
- **Latency**: 0.88s
- **Token Usage**: 512 prompt + 118 completion = 630 total
- **Retrieved Evidence**: Memory Filter Alert (`SENSITIVE_CREDENTIAL` and `TEMPORARY_STATE`)
- **Agent Output Summary**: The agent's memory filter flagged both items:
  1. The password was blocked as a critical credential violation.
  2. The headache was blocked as a fleeting temporary state.
  The agent politely warned the student never to disclose portal passwords and explained that credentials and ephemeral states are never saved to long-term memory.

---

### Scenario 5: Policy Gap / Unanswerable Question with Escalation
- **Student ID**: `STU101`
- **Query**: *"Does the institute provide a monthly financial allowance or subsidy for off-campus private hostel rent?"*
- **Status**: **PASS**
- **Tools Called**: `create_support_ticket(student_id="STU101", category="General Support", issue_description="Student query regarding off-campus housing subsidies")`
- **Tool Assessment**: **Appropriate**.
- **Latency**: 1.24s
- **Token Usage**: 572 prompt + 141 completion = 713 total
- **Retrieved Evidence**: Policy Gap (No handbook section covers off-campus housing subsidies)
- **Agent Output Summary**: The agent refrained from hallucinating fictitious rules, stated that the handbook does not contain provisions for private off-campus accommodation subsidies, and automatically raised a support ticket routed to Student Affairs for formal review.
