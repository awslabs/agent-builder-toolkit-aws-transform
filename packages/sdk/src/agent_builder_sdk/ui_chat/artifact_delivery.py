# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Link the customer deliverables a turn verifies from the agent's reply.

``ArtifactDeliveryHookProvider`` records each artifact a ``get_artifact_metadata`` result shows as
ready for the customer on ``agent.state``; the reply funnels call
``reply_with_artifact_deeplinks`` to append a ``Deeplinks.artifact`` link for each one the reply
does not link yet.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, TypeGuard

from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    CURRENT_SOURCE_TYPE_KEY,
    MessageSourceType,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_type,
)
from agent_builder_sdk.ui_chat.deeplinks import Deeplinks

logger = logging.getLogger(__name__)

DELIVERED_ARTIFACTS_STATE_KEY = "agent_builder_sdk.delivered_artifacts"

_DEFAULT_TITLE = "View file"
_CUSTOMER_OUTPUT = "CUSTOMER_OUTPUT"
_VERIFY_TOOL = "get_artifact_metadata"
_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9_-]+$")
# Zero-width and bidirectional-control characters can hide or reorder the visible link text.
_INVISIBLE = re.compile(r"[\u061c\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
# Characters that could end the link text, open a code span, or start an autolink or HTML tag.
_MARKDOWN_SPECIAL = re.compile(r"([\\\[\]`<>])")


def delivered_artifacts_in_tool_result(tool_name: str, result: Any) -> List[Dict[str, Any]]:
    """The customer deliverables a successful ``get_artifact_metadata`` result verifies, as
    ``{"artifact_id": str, "title": Optional[str]}`` items.

    An artifact counts when its ``artifactType.categoryType`` is ``CUSTOMER_OUTPUT`` and
    ``isS3ObjectPresent.publicBucket`` is true; a completed upload or the category alone does not
    prove that the customer can download the file. A lookup of an earlier upload counts the same as
    a fresh one. The tool-name match is exact, so an MCP client mounted with a tool prefix records
    nothing. Results of other tools are not parsed; failed results and malformed payloads yield
    ``[]``.
    """
    if (
        tool_name != _VERIFY_TOOL
        or not isinstance(result, dict)
        or result.get("status") != "success"
    ):
        return []
    delivered: List[Dict[str, Any]] = []
    for payload in _payloads(result):
        if not _in_public_bucket(payload):
            continue
        artifact = payload.get("artifact")
        if not isinstance(artifact, dict) or not _valid_id(artifact.get("artifactId")):
            continue
        artifact_type = artifact.get("artifactType")
        category = artifact_type.get("categoryType") if isinstance(artifact_type, dict) else None
        if category == _CUSTOMER_OUTPUT:
            delivered.append({"artifact_id": artifact["artifactId"], "title": _title(artifact)})
    return delivered


def _valid_id(artifact_id: Any) -> TypeGuard[str]:
    return isinstance(artifact_id, str) and _ARTIFACT_ID.fullmatch(artifact_id) is not None


def _in_public_bucket(payload: Dict[str, Any]) -> bool:
    present = payload.get("isS3ObjectPresent")
    return isinstance(present, dict) and present.get("publicBucket") is True


def _payloads(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        payloads.append(structured)
    content = result.get("content")
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        payload = block.get("json")
        if payload is None and isinstance(block.get("text"), str):
            try:
                payload = json.loads(block["text"])
            except (ValueError, RecursionError):
                payload = None
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _links(reply_text: str, artifact_id: str) -> bool:
    """True when the reply already links the artifact: a Markdown link (not an image, not escaped,
    not in a code span that starts at the link) whose target ends at the id, or an autolink in angle
    brackets. A bare ``aws-transform://`` URI is plain text in Markdown, so it does not count."""
    if artifact_id not in reply_text:
        return False
    url = rf"aws-transform://[^\s()<>\[\]]*artifacts/{re.escape(artifact_id)}"
    title = r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?"
    pattern = rf"(?<![!\\`])\[[^\[\]]*\]\(\s*<?{url}>?{title}\s*\)|<{url}>"
    return re.search(pattern, reply_text) is not None


def _title(artifact: Dict[str, Any]) -> Optional[str]:
    label = artifact.get("artifactLabel")
    if isinstance(label, str) and label:
        return label
    file_metadata = artifact.get("fileMetadata")
    path = file_metadata.get("path") if isinstance(file_metadata, dict) else None
    return os.path.basename(path) if isinstance(path, str) and path else None


def _link_text(title: Any) -> str:
    """The title as one line of Markdown link text; the default title when nothing is left."""
    text = " ".join(_INVISIBLE.sub("", title if isinstance(title, str) else "").split())
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text) if text else _DEFAULT_TITLE


def append_artifact_deeplinks(reply_text: str, delivered: List[Any]) -> str:
    """Append a deeplink for each delivered artifact the reply does not link yet.

    ``delivered`` holds ``{"artifact_id", "title"}`` items; an item without a valid id is skipped
    and a repeated id is linked once. Only a Markdown link or an autolink whose target is the
    artifact's deeplink counts as already linked; prose that names the id, a path or the bare URI
    still gets its link. A blank reply is returned unchanged, with no links.
    """
    if not reply_text.strip():
        return reply_text
    links: List[str] = []
    seen: set[str] = set()
    for item in delivered:
        artifact_id = item.get("artifact_id") if isinstance(item, dict) else None
        if not _valid_id(artifact_id) or artifact_id in seen or _links(reply_text, artifact_id):
            continue
        seen.add(artifact_id)
        links.append(Deeplinks.artifact(_link_text(item.get("title")), artifact_id=artifact_id))
    if not links:
        return reply_text
    block = links[0] if len(links) == 1 else "\n".join(f"- {link}" for link in links)
    return f"{reply_text}\n\n{block}"


def reply_with_artifact_deeplinks(reply_text: str, agent: Any) -> str:
    """The reply with deeplinks for the artifacts recorded on ``agent.state``, for a turn the user
    sent; a reply to a subagent or a notification is read by a machine and goes out unchanged.

    The turn's source is the ``conversation_source_type`` ContextVar, which the orchestrator sets
    per turn. The ``agent.state`` copy serves a caller outside the turn's context, such as the queue
    worker after a sync orchestrator ran on another thread. A turn with no recorded source counts
    as a user turn. Any failure is logged and the reply goes out unchanged.
    """
    try:
        state = getattr(agent, "state", None)
        if state is None:
            return reply_text
        source = conversation_source_type.get(None)
        if source is None:
            source = state.get(CURRENT_SOURCE_TYPE_KEY)
        if source is not None and source != MessageSourceType.USER:
            return reply_text
        delivered = state.get(DELIVERED_ARTIFACTS_STATE_KEY)
        if not isinstance(delivered, list) or not delivered:
            return reply_text
        return append_artifact_deeplinks(reply_text, delivered)
    except Exception:
        logger.exception("Failed to append artifact deeplinks; the reply goes out without them")
        return reply_text
