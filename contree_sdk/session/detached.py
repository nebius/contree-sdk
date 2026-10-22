"""Serialization hooks for operation contexts without retaining local input sources."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from typing import Any, cast

from contree_client.models import InstanceNetworking, InstanceResourcesLimits, OperationResponse

from contree_sdk.execution import OperationContext, RunRequest
from contree_sdk.session.records import OperationRecord


def operation_record(uuid: str, context: OperationContext, *, endpoint: str) -> OperationRecord:
    if context.parent_id is None or context.branch is None:
        raise ValueError("detached operations require a source history entry and branch")
    request = context.request
    data = {
        field.name: getattr(request, field.name) for field in fields(request) if field.name not in {"stdin", "files"}
    }
    data["args"] = list(request.args)
    data["timeout"] = request.timeout_seconds
    data["env"] = None if request.env is None else dict(request.env)
    for key in ("resources_limits", "networking"):
        value = data[key]
        data[key] = None if value is None else value.to_dict()
    return OperationRecord(
        endpoint=endpoint,
        created_at=context.created_at,
        node_id=context.node_id,
        session_cwd=context.session_cwd,
        session_env=dict(context.session_env),
        uuid=uuid,
        session_id=context.session_id,
        image_uuid=context.image_uuid,
        parent_id=context.parent_id,
        branch=context.branch,
        title=request.title,
        disposable=request.disposable,
        request=data,
        files=context.files,
        attachments=context.attachments,
    )


def operation_context(record: OperationRecord) -> OperationContext:
    data = cast("dict[str, Any]", deepcopy(record.request))
    for key, model in (("resources_limits", InstanceResourcesLimits), ("networking", InstanceNetworking)):
        if data.get(key) is not None:
            data[key] = model.from_dict(data[key])
    return OperationContext(
        RunRequest(**data),
        record.session_id,
        record.image_uuid,
        record.parent_id,
        record.branch,
        record.files,
        record.attachments,
        detached=True,
        created_at=record.created_at,
        node_id=record.node_id,
        session_cwd=record.session_cwd,
        session_env=record.session_env,
    )


def decode_response(record: OperationRecord) -> OperationResponse:
    if record.response is None:
        raise ValueError("operation is still pending")
    return OperationResponse.from_dict(cast("dict[str, Any]", deepcopy(record.response)))
