"""Serialization hooks for operation contexts without retaining local input sources."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from typing import Any, cast

from contree_client.models import InstanceResourcesLimits, OperationResponse

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
    data["network_policy"] = None if request.network_policy is None else list(request.network_policy)
    limits = request.resources_limits
    data["resources_limits"] = None if limits is None else limits.to_dict()
    return OperationRecord(
        endpoint=endpoint,
        created_at=context.created_at,
        node_id=context.node_id,
        session_cwd=context.session_cwd,
        session_env=dict(context.session_env),
        session_network_enabled=context.session_network_enabled,
        session_network_policy_uuids=context.session_network_policy_uuids,
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
    if "networking" in data:
        # Backward compatibility: SDK 0.5.x and earlier used the networking field.
        networking = data.pop("networking") or {}
        data.setdefault("network_enabled", networking.get("enabled", True))
        data.setdefault("network_policy", networking.get("policy", []))

    if data.get("resources_limits") is not None:
        data["resources_limits"] = InstanceResourcesLimits.from_dict(data["resources_limits"])
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
        session_network_enabled=record.session_network_enabled,
        session_network_policy_uuids=record.session_network_policy_uuids,
    )


def decode_response(record: OperationRecord) -> OperationResponse:
    if record.response is None:
        raise ValueError("operation is still pending")
    return OperationResponse.from_dict(cast("dict[str, Any]", deepcopy(record.response)))
