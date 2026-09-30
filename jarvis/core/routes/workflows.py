"""Workflow builder, runs, approvals, releases and the product overview."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from jarvis.core import app_lifecycle, calendar_accounts, jobs, team, workflow_scheduler, workflows
from jarvis.core.api_models import (
    SchedulerRunRequest,
    WorkflowApprovalRequest,
    WorkflowAssertionRunRequest,
    WorkflowEditPresenceRequest,
    WorkflowPackageImportRequest,
    WorkflowPublishRequest,
    WorkflowReplayRequest,
    WorkflowRequest,
    WorkflowRunRequest,
    WorkflowTemplateRequest,
    WorkflowVersionRestoreRequest,
)
from jarvis.core.http_security import require_auth
from jarvis.core.job_runners import run_workflow_job, serialize_job
from jarvis.core.runtime import brain, spawn_background
from jarvis.core.tracing import get_trace_id

router = APIRouter()


@router.get("/workflows/overview", dependencies=[Depends(require_auth)])
async def workflow_overview():
    """Get workflow-builder foundation status."""
    return {
        **workflows.get_overview(),
        "scheduler": workflow_scheduler.get_scheduler_status(),
    }


@router.get("/product/overview", dependencies=[Depends(require_auth)])
async def product_overview(status: str = "", dry_run: bool | None = None):
    """Return the product console's common data in one low-chatter payload."""
    runs = workflows.list_runs(status=status, dry_run=dry_run, limit=8)
    workflow_items = workflows.list_workflows(include_disabled=True)
    approvals = workflows.list_approvals(status="pending", limit=8)
    return {
        "templates": workflows.list_templates(),
        "workflows": workflow_items,
        "workflow_count": len(workflow_items),
        "runs": runs,
        "run_count": len(runs),
        "analytics": workflows.get_run_analytics(limit=200),
        "team": team.get_team(),
        "calendar": calendar_accounts.get_state(),
        "scheduler": workflow_scheduler.get_scheduler_status(),
        "approvals": approvals,
        "approval_count": len(approvals),
        "lifecycle": app_lifecycle.get_status(),
    }


@router.get("/workflows/scheduler/status", dependencies=[Depends(require_auth)])
async def workflow_scheduler_status():
    """Get scheduled workflow runner status."""
    return workflow_scheduler.get_scheduler_status()


@router.post("/workflows/scheduler/run-due", dependencies=[Depends(require_auth)])
async def run_due_workflows(request: SchedulerRunRequest):
    """Run workflows due in the current minute.

    Defaults to dry-run so the UI can preview due work without spending API
    budget. Pass dry_run=false for an explicit manual execution.
    """
    runs = await workflow_scheduler.run_due_workflows(
        runner=brain.process if not request.dry_run else None,
        dry_run=request.dry_run,
    )
    return {"runs": runs, "count": len(runs)}


@router.get("/workflows/templates", dependencies=[Depends(require_auth)])
async def workflow_templates():
    """List starter workflow templates."""
    return {"templates": workflows.list_templates()}


@router.get("/workflows", dependencies=[Depends(require_auth)])
async def list_workflows(include_disabled: bool = True):
    """List saved workflows."""
    items = workflows.list_workflows(include_disabled=include_disabled)
    return {"workflows": items, "count": len(items)}


@router.post("/workflows", dependencies=[Depends(require_auth)])
async def create_workflow(request: WorkflowRequest):
    """Create a workflow definition for the workflow builder."""
    if not request.name.strip():
        return JSONResponse(status_code=400, content={"error": "Workflow name is required."})
    workflow = workflows.create_workflow(
        name=request.name,
        description=request.description,
        trigger=request.trigger,
        actions=request.actions,
        assertions=request.assertions,
        budget=request.budget,
        enabled=request.enabled,
        tags=request.tags,
        owner_id=request.owner_id,
        visibility=request.visibility,
        permissions=request.permissions,
        actor_id=request.actor_id,
        note=request.version_note,
    )
    return workflow


@router.post("/workflows/from-template", dependencies=[Depends(require_auth)])
async def create_workflow_from_template(request: WorkflowTemplateRequest):
    """Create a workflow from a starter template."""
    workflow = workflows.create_workflow_from_template(
        request.template_id,
        owner_id=request.owner_id,
        actor_id=request.actor_id,
    )
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow template not found."})
    return workflow


@router.get("/workflows/templates/{template_id}/package", dependencies=[Depends(require_auth)])
async def export_workflow_template_package(template_id: str):
    """Export a starter workflow template as a portable workflow package."""
    package = workflows.export_template_package(template_id)
    if package is None:
        return JSONResponse(status_code=404, content={"error": "Workflow template not found."})
    return {"package": package}


@router.post("/workflows/import-package", dependencies=[Depends(require_auth)])
async def import_workflow_package(request: WorkflowPackageImportRequest):
    """Import a portable workflow package as a new workflow."""
    result = workflows.import_workflow_package(
        request.package,
        owner_id=request.owner_id,
        actor_id=request.actor_id,
        name=request.name,
    )
    if result["status"] == "invalid":
        return JSONResponse(
            status_code=400,
            content={
                "error": "; ".join(result.get("validation", {}).get("errors", [])) or "Invalid workflow package.",
                **result,
            },
        )
    return result


@router.get("/workflows/runs", dependencies=[Depends(require_auth)])
async def list_workflow_runs(
    workflow_id: str = "",
    limit: int = 50,
    status: str = "",
    dry_run: bool | None = None,
    release_channel: str = "",
    workflow_version_id: str = "",
    workflow_version: int | None = None,
    started_after: float | None = None,
    started_before: float | None = None,
):
    """List workflow execution history."""
    runs = workflows.list_runs(
        workflow_id=workflow_id,
        limit=limit,
        status=status,
        dry_run=dry_run,
        release_channel=release_channel,
        workflow_version_id=workflow_version_id,
        workflow_version=workflow_version,
        started_after=started_after,
        started_before=started_before,
    )
    return {"runs": runs, "count": len(runs)}


@router.get("/workflows/analytics", dependencies=[Depends(require_auth)])
async def workflow_run_analytics(
    workflow_id: str = "",
    started_after: float | None = None,
    started_before: float | None = None,
    limit: int = 500,
):
    """Summarize workflow run health, latency, and failure patterns."""
    return workflows.get_run_analytics(
        workflow_id=workflow_id,
        started_after=started_after,
        started_before=started_before,
        limit=limit,
    )


@router.get("/workflows/runs/{run_id}", dependencies=[Depends(require_auth)])
async def get_workflow_run(run_id: str):
    """Get one workflow run with its timeline/audit trace."""
    run = workflows.get_run(run_id)
    if run is None:
        return JSONResponse(status_code=404, content={"error": "Workflow run not found."})
    return run


@router.post("/workflows/runs/{run_id}/replay", dependencies=[Depends(require_auth)])
async def replay_workflow_run(run_id: str, request: WorkflowReplayRequest):
    """Replay a previous workflow run, preferring its original version snapshot."""
    result = await workflows.replay_run(
        run_id,
        runner=brain.process if not request.dry_run else None,
        dry_run=request.dry_run,
    )
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Workflow run not found."})
    if result.get("replay_run") is None:
        return JSONResponse(status_code=400, content={"error": "; ".join(result.get("warnings", [])), **result})
    return result


@router.get("/workflows/approvals", dependencies=[Depends(require_auth)])
async def list_workflow_approvals(status: str = "pending", limit: int = 50):
    """List workflow approvals waiting for a user decision."""
    approvals = workflows.list_approvals(status=status, limit=limit)
    return {"approvals": approvals, "count": len(approvals)}


@router.post("/workflows/approvals/{approval_id}/approve", dependencies=[Depends(require_auth)])
async def approve_workflow_approval(approval_id: str, request: WorkflowApprovalRequest):
    """Approve a pending workflow action and execute supported actions."""
    approval = await workflows.approve_approval(approval_id, actor=request.actor, note=request.note)
    if approval is None:
        return JSONResponse(status_code=404, content={"error": "Approval not found."})
    return approval


@router.post("/workflows/approvals/{approval_id}/reject", dependencies=[Depends(require_auth)])
async def reject_workflow_approval(approval_id: str, request: WorkflowApprovalRequest):
    """Reject a pending workflow action."""
    approval = workflows.reject_approval(approval_id, actor=request.actor, note=request.note)
    if approval is None:
        return JSONResponse(status_code=404, content={"error": "Approval not found."})
    return approval


@router.get("/workflows/releases", dependencies=[Depends(require_auth)])
async def list_workflow_releases(workflow_id: str = "", channel: str = "", limit: int = 50):
    """List workflow release channel history."""
    releases = workflows.list_workflow_releases(workflow_id=workflow_id, channel=channel, limit=limit)
    return {"releases": releases, "count": len(releases)}


@router.get("/workflows/release-policies", dependencies=[Depends(require_auth)])
async def workflow_release_policies():
    """List workflow release promotion policies."""
    return {"policies": workflows.get_release_policies()}


@router.get("/workflows/{workflow_id}/versions", dependencies=[Depends(require_auth)])
async def list_workflow_versions(workflow_id: str, limit: int = 50):
    """List version history for one workflow."""
    workflow = workflows.get_workflow(workflow_id)
    versions = workflows.list_workflow_versions(workflow_id, limit=limit)
    if workflow is None and not versions:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    versions = [
        {
            **version,
            "release_readiness": workflows.get_release_readiness(
                workflow_id,
                str(version.get("id") or ""),
                channel="stable",
                note="Promoted from workflow history.",
            ),
        }
        for version in versions
    ]
    return {"versions": versions, "count": len(versions)}


@router.get("/workflows/{workflow_id}/versions/{version_id}", dependencies=[Depends(require_auth)])
async def get_workflow_version(workflow_id: str, version_id: str):
    """Get one workflow version snapshot."""
    version = workflows.get_workflow_version(workflow_id, version_id)
    if version is None:
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    return version


@router.get("/workflows/{workflow_id}/versions/{version_id}/readiness", dependencies=[Depends(require_auth)])
async def get_workflow_version_readiness(workflow_id: str, version_id: str, channel: str = "stable", note: str = ""):
    """Get release gate readiness for one workflow version."""
    readiness = workflows.get_release_readiness(workflow_id, version_id, channel=channel, note=note)
    if readiness["status"] == "missing_version":
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    return readiness


@router.post("/workflows/{workflow_id}/versions/{version_id}/dry-run", dependencies=[Depends(require_auth)])
async def dry_run_workflow_version(workflow_id: str, version_id: str):
    """Dry-run a specific workflow version as release gate evidence."""
    run = await workflows.run_workflow_version(workflow_id, version_id, dry_run=True)
    if run is None:
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    return {"run": run}


@router.post("/workflows/{workflow_id}/versions/{version_id}/assertions/run", dependencies=[Depends(require_auth)])
async def run_workflow_version_assertions(
    workflow_id: str,
    version_id: str,
    request: WorkflowAssertionRunRequest,
):
    """Run release assertions against a workflow version's latest dry run."""
    result = workflows.run_workflow_assertion_suite(workflow_id, version_id, run_id=request.run_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    if not result.get("passed") and result.get("status") in {"missing_run", "wrong_workflow"}:
        return JSONResponse(status_code=400, content={"error": result.get("message", "Assertions could not run."), "result": result})
    return {"result": result}


@router.get("/workflows/{workflow_id}/presence", dependencies=[Depends(require_auth)])
async def get_workflow_presence(workflow_id: str, actor_id: str = "", session_id: str = ""):
    """Get active edit presence for one workflow."""
    presence = workflows.get_workflow_presence(
        workflow_id,
        actor_id=actor_id,
        current_session_id=session_id,
    )
    if presence is None:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    return presence


@router.post("/workflows/{workflow_id}/presence", dependencies=[Depends(require_auth)])
async def start_workflow_edit_presence(workflow_id: str, request: WorkflowEditPresenceRequest):
    """Start or refresh an advisory workflow edit session."""
    result = workflows.start_workflow_edit(
        workflow_id,
        actor_id=request.actor_id,
        actor_name=request.actor_name,
        session_id=request.session_id,
        ttl_seconds=request.ttl_seconds,
    )
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    return result


@router.post("/workflows/{workflow_id}/presence/{session_id}/heartbeat", dependencies=[Depends(require_auth)])
async def heartbeat_workflow_edit_presence(workflow_id: str, session_id: str, request: WorkflowEditPresenceRequest):
    """Refresh a workflow edit session lease."""
    result = workflows.heartbeat_workflow_edit(
        workflow_id,
        session_id,
        actor_id=request.actor_id,
        ttl_seconds=request.ttl_seconds,
    )
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Workflow edit session not found."})
    return result


@router.delete("/workflows/{workflow_id}/presence/{session_id}", dependencies=[Depends(require_auth)])
async def end_workflow_edit_presence(workflow_id: str, session_id: str, actor_id: str = ""):
    """End an advisory workflow edit session."""
    if not workflows.end_workflow_edit(workflow_id, session_id, actor_id=actor_id):
        return JSONResponse(status_code=404, content={"error": "Workflow edit session not found."})
    presence = workflows.get_workflow_presence(workflow_id, actor_id=actor_id)
    return {"status": "ended", "presence": presence}


@router.post("/workflows/{workflow_id}/versions/{version_id}/restore", dependencies=[Depends(require_auth)])
async def restore_workflow_version(workflow_id: str, version_id: str, request: WorkflowVersionRestoreRequest):
    """Restore a workflow from a version snapshot."""
    workflow = workflows.restore_workflow_version(
        workflow_id,
        version_id,
        actor_id=request.actor_id,
        note=request.note,
    )
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    return workflow


@router.post("/workflows/{workflow_id}/versions/{version_id}/publish", dependencies=[Depends(require_auth)])
async def publish_workflow_version(workflow_id: str, version_id: str, request: WorkflowPublishRequest):
    """Request or execute a workflow version release promotion."""
    result = workflows.request_workflow_release_approval(
        workflow_id,
        version_id,
        channel=request.channel,
        actor_id=request.actor_id,
        note=request.note,
        activate=request.activate,
        require_approval=request.require_approval,
    )
    if result is None:
        assessment = workflows.assess_release_request(
            workflow_id,
            version_id,
            channel=request.channel,
            note=request.note,
        )
        blockers = assessment.get("blockers", [])
        status_code = 400 if blockers else 404
        return JSONResponse(
            status_code=status_code,
            content={"error": "; ".join(blockers) or "Workflow version not found."},
        )
    return result


@router.get("/workflows/{workflow_id}", dependencies=[Depends(require_auth)])
async def get_workflow(workflow_id: str):
    """Get one workflow definition."""
    workflow = workflows.get_workflow(workflow_id)
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    return workflow


@router.get("/workflows/{workflow_id}/package", dependencies=[Depends(require_auth)])
async def export_workflow_package(workflow_id: str, version_id: str = ""):
    """Export a saved workflow or version as a portable workflow package."""
    package = workflows.export_workflow_package(workflow_id, version_id=version_id)
    if package is None:
        return JSONResponse(status_code=404, content={"error": "Workflow or workflow version not found."})
    return {"package": package}


@router.put("/workflows/{workflow_id}", dependencies=[Depends(require_auth)])
async def update_workflow(workflow_id: str, request: WorkflowRequest):
    """Update a workflow definition."""
    updates = {
        "name": request.name,
        "description": request.description,
        "trigger": request.trigger,
        "actions": request.actions,
        "assertions": request.assertions,
        "budget": request.budget,
        "enabled": request.enabled,
        "tags": request.tags,
        "visibility": request.visibility,
        "permissions": request.permissions,
    }
    if request.active_release_channel is not None:
        updates["active_release_channel"] = request.active_release_channel
    result = workflows.update_workflow_with_conflict_check(
        workflow_id,
        updates,
        actor_id=request.actor_id,
        note=request.version_note,
        base_version=request.base_version,
        edit_session_id=request.edit_session_id,
        conflict_strategy=request.conflict_strategy,
    )
    if result["status"] == "conflict":
        conflict = dict(result.get("conflict") or {})
        return JSONResponse(
            status_code=409,
            content={
                "error": conflict.get("message") or "Workflow edit conflict.",
                "conflict": conflict,
            },
        )
    workflow = result.get("workflow")
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    return workflow


@router.delete("/workflows/{workflow_id}", dependencies=[Depends(require_auth)])
async def delete_workflow(workflow_id: str, actor_id: str = "local-owner", note: str = ""):
    """Delete a workflow definition."""
    if not workflows.delete_workflow(workflow_id, actor_id=actor_id, note=note):
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    return {"status": "deleted"}


@router.post("/workflows/{workflow_id}/run", dependencies=[Depends(require_auth)])
async def run_workflow(workflow_id: str, request: WorkflowRunRequest):
    """Run a workflow now, either inline or in a durable background job."""
    workflow = workflows.get_workflow(workflow_id)
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    if request.background:
        job = jobs.create_job(
            "workflow",
            {"workflow_id": workflow_id, "dry_run": request.dry_run, "release_channel": request.release_channel},
            trace_id=get_trace_id(),
        )
        spawn_background(
            run_workflow_job(job.id, workflow_id, request.dry_run, request.release_channel),
            name=f"workflow-job-{job.id}",
        )
        return {"workflow": workflow, "job": serialize_job(job)}
    run = await workflows.run_workflow(
        workflow_id,
        runner=brain.process if not request.dry_run else None,
        triggered_by="manual",
        dry_run=request.dry_run,
        release_channel=request.release_channel,
    )
    return {"workflow": workflows.get_workflow(workflow_id), "run": run}
