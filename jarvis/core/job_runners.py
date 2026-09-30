"""Background job runners for chat and workflow jobs."""
import json
import logging

from jarvis.core import jobs, workflows
from jarvis.core.runtime import brain
from jarvis.core.tracing import record_event, reset_trace_id, set_trace_id, trace_span

logger = logging.getLogger("jarvis.server")


def serialize_job(job: jobs.JobRecord) -> dict:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "payload": job.payload,
        "result": job.result,
        "error": job.error,
        "trace_id": job.trace_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


async def run_chat_job(job_id: str, message: str) -> None:
    job = jobs.get_job(job_id)
    if job is None or job.status == jobs.JobStatus.CANCELLED.value:
        return

    token = set_trace_id(job.trace_id)
    try:
        jobs.mark_running(job_id)
        record_event("job.started", job_id=job_id, kind=job.kind)
        with trace_span("job.chat", job_id=job_id):
            result = await brain.process(message)
        latest = jobs.get_job(job_id)
        if latest is not None and latest.status == jobs.JobStatus.CANCELLED.value:
            record_event("job.cancelled", job_id=job_id)
            return
        jobs.mark_completed(job_id, result)
        record_event("job.completed", job_id=job_id)
    except Exception as exc:
        logger.exception("Background job %s failed", job_id)
        jobs.mark_failed(job_id, str(exc))
        record_event("job.failed", job_id=job_id, error=str(exc))
    finally:
        reset_trace_id(token)


async def run_workflow_job(
    job_id: str,
    workflow_id: str,
    dry_run: bool = False,
    release_channel: str | None = None,
) -> None:
    job = jobs.get_job(job_id)
    if job is None or job.status == jobs.JobStatus.CANCELLED.value:
        return

    token = set_trace_id(job.trace_id)
    try:
        jobs.mark_running(job_id)
        record_event("job.started", job_id=job_id, kind=job.kind, workflow_id=workflow_id)
        run = await workflows.run_workflow(
            workflow_id,
            runner=brain.process if not dry_run else None,
            triggered_by="background",
            dry_run=dry_run,
            release_channel=release_channel,
        )
        latest = jobs.get_job(job_id)
        if latest is not None and latest.status == jobs.JobStatus.CANCELLED.value:
            record_event("job.cancelled", job_id=job_id)
            return
        if run is None:
            jobs.mark_failed(job_id, "Workflow not found.")
            return
        jobs.mark_completed(job_id, json.dumps(run, sort_keys=True, default=str))
        record_event("job.completed", job_id=job_id, workflow_id=workflow_id)
    except Exception as exc:
        logger.exception("Workflow job %s failed", job_id)
        jobs.mark_failed(job_id, str(exc))
        record_event("job.failed", job_id=job_id, error=str(exc))
    finally:
        reset_trace_id(token)
