# Serverless Task Coordination Patterns

MeetChi utilizes **Google Cloud Tasks** for asynchronous, high-latency AI operations (Summarization, ASR Post-Processing). This document details the architectural patterns used to coordinate these tasks.

---

## 1. Pattern: Core-Wrapper Separation

This pattern decouples the business logic from the task transport mechanism, ensuring that functions can be tested in isolation and triggered via multiple runners.

### 1.1 Structural Components

1.  **Core Logic Function (`_core`)**:
    - **Responsibility**: The actual work (e.g., calling Gemini, updating DB).
    - **Isolation**: Handles its own database sessions and logging.
    - **Naming**: `generate_summary_core(...)`.

2.  **Logic Wrapper**:
    - **Responsibility**: Maintains the original function signature for internal synchronous code calls.
    - **Implementation**: Directly calls the Core Logic Function.

3.  **HTTP Task Handler (The Adapter)**:
    - **Responsibility**: Interface for **Cloud Tasks** (HTTP POST).
    - **Security**: Verifies the `X-CloudTasks-QueueName` header to ensure the request originated from a trusted Google queue.
    - **Development Bypass**: Allows direct execution if `APP_ENV=development`.

---

## 2. Implementation Example (FastAPI)

```python
@router.post("/tasks/summarize")
async def handle_summarization_task(
    request: SummarizationRequest,
    x_cloudtasks_queuename: Optional[str] = Header(None)
):
    # 1. Security Check
    if not x_cloudtasks_queuename and os.getenv("APP_ENV") != "development":
        raise HTTPException(status_code=403, detail="Forbidden")

    # 2. Idempotency Check
    meeting = await db.get_meeting(request.meeting_id)
    if meeting.status in ["processing", "completed"]:
        return {"status": "skipped", "reason": "already processed"}

    # 3. Execution
    return await generate_summary_core(request.meeting_id)
```

---

## 3. Resilience & Resource Management

### 3.1 Idempotency
Because serverless queues have "at-least-once" delivery, handlers must check the database state before starting. If a meeting is already marked `completed`, the handler should return success immediately to avoid redundant API/GPU costs.

### 3.2 Concurrency Control
- **Quota Protection**: Use Cloud Tasks queue limits (e.g., `max_dispatches=5`) to prevent LLM/ASR quota exhaustion.
- **VRAM Deadlocks**: By offloading summarization to **Gemini API** within the background task, we avoid consuming GPU VRAM on the LLM Service, preventing deadlocks when multiple streaming ASR sessions are active.

### 3.3 Dead Letter Queues (DLQ)
Failed tasks are automatically retried with exponential backoff. After 5-10 failures, tasks are moved to a DLQ for manual audit, ensuring that problematic transcripts don't clog the production queue.

---

## 4. Operational Transition (Feb 2026)

MeetChi successfully migrated from **Celery/Redis** to this serverless pattern.
- **Cost**: Realized ~$40/mo savings by decommissioning Cloud Memorystore.
- **Complexity**: Reduced CI/CD overhead by removing the dedicated Celery Worker container.
- **Reliability**: Leverages GCP-native retry infrastructure rather than a self-managed broker.
