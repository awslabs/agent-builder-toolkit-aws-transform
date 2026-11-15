# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for artifact_delivery: which tool results count as delivered, and how links append."""

import contextvars
import json
import logging
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
from strands.agent.state import AgentState

from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    CURRENT_SOURCE_TYPE_KEY,
    MessageSourceType,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_type,
)
from agent_builder_sdk.ui_chat.artifact_delivery import (
    DELIVERED_ARTIFACTS_STATE_KEY,
    append_artifact_deeplinks,
    delivered_artifacts_in_tool_result,
    reply_with_artifact_deeplinks,
)

VERIFY = "get_artifact_metadata"


def _artifact(
    category: str = "CUSTOMER_OUTPUT", label: Optional[str] = "Report", path: Optional[str] = None
) -> Dict[str, Any]:
    artifact: Dict[str, Any] = {
        "artifactId": "art-1",
        "artifactType": {"categoryType": category, "fileType": "PDF"},
    }
    if label:
        artifact["artifactLabel"] = label
    if path:
        artifact["fileMetadata"] = {"path": path}
    return artifact


def _verified(artifact: Any, public: bool = True, private: bool = True) -> Dict[str, Any]:
    return {
        "artifact": artifact,
        "isS3ObjectPresent": {"publicBucket": public, "privateBucket": private},
    }


def _result(payload: Any, status: str = "success", as_json_block: bool = False) -> Dict[str, Any]:
    block = {"json": payload} if as_json_block else {"text": json.dumps(payload)}
    return {"toolUseId": "t1", "status": status, "content": [block]}


def test_customer_output_present_in_the_public_bucket_is_delivered() -> None:
    result = _result(_verified(_artifact()))
    assert delivered_artifacts_in_tool_result(VERIFY, result) == [
        {"artifact_id": "art-1", "title": "Report"}
    ]


def test_an_agent_output_is_not_delivered() -> None:
    result = _result(_verified(_artifact(category="AGENT_OUTPUT")))
    assert delivered_artifacts_in_tool_result(VERIFY, result) == []


def test_customer_output_missing_from_the_public_bucket_is_not_delivered() -> None:
    private_only = _result(_verified(_artifact(), public=False))
    assert delivered_artifacts_in_tool_result(VERIFY, private_only) == []
    unknown = _result({"artifact": _artifact(), "isS3ObjectPresent": "yes"})
    assert delivered_artifacts_in_tool_result(VERIFY, unknown) == []
    absent = _result({"artifact": _artifact()})
    assert delivered_artifacts_in_tool_result(VERIFY, absent) == []


def test_other_tools_returning_an_artifact_do_not_count() -> None:
    result = _result(_verified(_artifact()))
    assert delivered_artifacts_in_tool_result("complete_artifact_upload", result) == []
    assert delivered_artifacts_in_tool_result("prefix_get_artifact_metadata", result) == []


def test_a_relayed_delivery_marker_is_ignored_whatever_tool_returns_it() -> None:
    marker = {"copyStatus": "COMPLETED", "delivered": {"artifact_id": "art-9", "title": "T"}}
    for tool in ("copy_artifact", "shell", "send_message", VERIFY):
        assert delivered_artifacts_in_tool_result(tool, _result(marker)) == []
    structured = {
        "toolUseId": "t1",
        "status": "success",
        "content": [],
        "structuredContent": marker,
    }
    assert delivered_artifacts_in_tool_result("fetch_page", structured) == []


def test_other_tools_results_are_not_parsed() -> None:
    huge = {"toolUseId": "t1", "status": "success", "content": [{"text": "{" * 1_000_000}]}
    with patch("agent_builder_sdk.ui_chat.artifact_delivery.json.loads") as loads:
        assert delivered_artifacts_in_tool_result("shell", huge) == []
    loads.assert_not_called()


def test_title_falls_back_to_the_file_name_then_none() -> None:
    by_path = _result(_verified(_artifact(label=None, path="/tmp/out/report.pdf")))
    assert delivered_artifacts_in_tool_result(VERIFY, by_path)[0]["title"] == "report.pdf"
    bare = _result(_verified(_artifact(label=None)))
    assert delivered_artifacts_in_tool_result(VERIFY, bare)[0]["title"] is None


def test_json_block_and_structured_content_are_read() -> None:
    as_json = _result(_verified(_artifact()), as_json_block=True)
    assert len(delivered_artifacts_in_tool_result(VERIFY, as_json)) == 1
    structured = {
        "toolUseId": "t1",
        "status": "success",
        "content": [],
        "structuredContent": _verified(_artifact()),
    }
    assert len(delivered_artifacts_in_tool_result(VERIFY, structured)) == 1


def test_error_results_and_odd_shapes_yield_nothing() -> None:
    failed = _result(_verified(_artifact()), status="error")
    assert delivered_artifacts_in_tool_result(VERIFY, failed) == []
    not_json = {"status": "success", "content": [{"text": "not json"}]}
    assert delivered_artifacts_in_tool_result(VERIFY, not_json) == []
    assert delivered_artifacts_in_tool_result(VERIFY, None) == []
    assert delivered_artifacts_in_tool_result(VERIFY, {"status": "success", "content": "x"}) == []


def test_malformed_nested_artifact_fields_are_ignored() -> None:
    odd = {
        "artifactId": "art-1",
        "artifactType": "CUSTOMER_OUTPUT",
        "artifactLabel": 7,
        "fileMetadata": "x",
    }
    assert delivered_artifacts_in_tool_result(VERIFY, _result(_verified(odd))) == []
    odd_meta = _artifact(label=None)
    odd_meta["fileMetadata"] = "not-a-dict"
    delivered = delivered_artifacts_in_tool_result(VERIFY, _result(_verified(odd_meta)))
    assert delivered == [{"artifact_id": "art-1", "title": None}]


@pytest.mark.parametrize(
    "artifact_id", ["x) [evil](https://evil.example", "../art-1", 42, "art-1\n", "", None]
)
def test_crafted_or_non_string_ids_are_not_delivered(artifact_id: Any) -> None:
    artifact = _artifact()
    artifact["artifactId"] = artifact_id
    assert delivered_artifacts_in_tool_result(VERIFY, _result(_verified(artifact))) == []


def test_append_adds_a_link_the_reply_lacks() -> None:
    out = append_artifact_deeplinks("Done.", [{"artifact_id": "art-1", "title": "Report"}])
    assert out == "Done.\n\n[Report](aws-transform://~/artifacts/art-1)"


def test_append_skips_an_artifact_the_reply_already_links() -> None:
    reply = "See [the report](aws-transform://~/jobs/j1/artifacts/art-1)."
    assert append_artifact_deeplinks(reply, [{"artifact_id": "art-1", "title": "Report"}]) == reply


def test_append_lists_several_links_once_each_and_uses_the_default_title() -> None:
    out = append_artifact_deeplinks(
        "Done.",
        [
            {"artifact_id": "a", "title": None},
            {"artifact_id": "b", "title": "B"},
            {"artifact_id": "a", "title": "again"},
        ],
    )
    assert out == (
        "Done.\n\n"
        "- [View file](aws-transform://~/artifacts/a)\n"
        "- [B](aws-transform://~/artifacts/b)"
    )


def test_a_blank_reply_gets_no_links() -> None:
    delivered = [{"artifact_id": "a", "title": "A"}]
    assert append_artifact_deeplinks("", delivered) == ""
    assert append_artifact_deeplinks("  \n", delivered) == "  \n"


def test_append_does_not_mistake_a_longer_id_for_the_linked_one() -> None:
    reply = "See [it](aws-transform://~/artifacts/art-10)."
    out = append_artifact_deeplinks(reply, [{"artifact_id": "art-1", "title": "One"}])
    assert out.endswith("[One](aws-transform://~/artifacts/art-1)")


def test_items_without_a_valid_id_are_skipped_one_by_one() -> None:
    out = append_artifact_deeplinks(
        "Done.",
        [
            {"artifact_id": 42, "title": "bad"},
            {"artifact_id": "x)(https://evil.example", "title": "bad"},
            "not-a-dict",
            {"artifact_id": "ok-1", "title": "Good"},
        ],
    )
    assert out == "Done.\n\n[Good](aws-transform://~/artifacts/ok-1)"


def test_link_text_escapes_markdown_that_could_break_out_of_the_link() -> None:
    """The title comes from the model or a tool: it stays text inside this one link."""
    titles = {
        "a": "report [v2]",
        "b": "x](https://evil.example) [y",
        "c": "C:\\out\\",
        "d": "<https://evil.example>",
        "e": "`code`",
        "f": "line one\n\n# line two",
    }
    out = append_artifact_deeplinks(
        "Done.", [{"artifact_id": key, "title": title} for key, title in titles.items()]
    )
    assert out == (
        "Done.\n\n"
        "- [report \\[v2\\]](aws-transform://~/artifacts/a)\n"
        "- [x\\](https://evil.example) \\[y](aws-transform://~/artifacts/b)\n"
        "- [C:\\\\out\\\\](aws-transform://~/artifacts/c)\n"
        "- [\\<https://evil.example\\>](aws-transform://~/artifacts/d)\n"
        "- [\\`code\\`](aws-transform://~/artifacts/e)\n"
        "- [line one # line two](aws-transform://~/artifacts/f)"
    )


def test_invisible_and_bidi_characters_are_dropped_from_the_link_text() -> None:
    out = append_artifact_deeplinks(
        "Done.",
        [
            {"artifact_id": "a", "title": "\u2066Report\u2069\u061c"},
            {"artifact_id": "b", "title": "\u200b\ufeff "},
        ],
    )
    assert out == (
        "Done.\n\n"
        "- [Report](aws-transform://~/artifacts/a)\n"
        "- [View file](aws-transform://~/artifacts/b)"
    )


@pytest.mark.parametrize(
    "reply",
    [
        "Saved to artifacts/art-1.pdf.",
        "See artifacts/art-1/preview.",
        "Stored at s3://bucket/artifacts/art-1",
        "[x](aws-transform://~/artifacts/art-1/other)",
        "[R](aws-transform://~/artifacts/art-1/)",
        "[aws-transform://~/a](https://evil.example/artifacts/art-1)",
        "[aws-transform://~/artifacts/art-1](https://evil.example/x)",
        "[aws-transform://~/artifacts/art-1]",
        "Link: aws-transform://~/jobs/j/artifacts/art-1",
        "Download: aws-transform://~/artifacts/art-1.",
        "aws-transform://~/artifacts/art-1, done",
        "[it](aws-transform://~/artifacts/art-1?v=2)",
        "[it](aws-transform://~/artifacts/art-1#p)",
        "**aws-transform://~/artifacts/art-1**",
        "`aws-transform://~/artifacts/art-1`",
        "[x](aws-transform://~/artifacts/art-10)",
        "![R](aws-transform://~/artifacts/art-1)",
        "\\[R](aws-transform://~/artifacts/art-1)",
        "`[R](aws-transform://~/artifacts/art-1)`",
    ],
)
def test_a_reply_that_only_mentions_the_artifact_still_gets_its_link(reply: str) -> None:
    out = append_artifact_deeplinks(reply, [{"artifact_id": "art-1", "title": "R"}])
    assert out == f"{reply}\n\n[R](aws-transform://~/artifacts/art-1)"


@pytest.mark.parametrize(
    "reply",
    [
        "See [it](aws-transform://~/artifacts/art-1).",
        "See [it](aws-transform://workspaces/w/jobs/j/artifacts/art-1) now.",
        'See [it](aws-transform://~/artifacts/art-1 "the report").',
        "<aws-transform://~/artifacts/art-1>",
    ],
)
def test_a_markdown_link_or_autolink_to_the_artifact_counts_as_linked(reply: str) -> None:
    assert append_artifact_deeplinks(reply, [{"artifact_id": "art-1", "title": "R"}]) == reply


def test_known_commonmark_limits_of_the_link_check() -> None:
    """Pinned as they behave: these valid links are not recognised (a second link follows), and a
    link inside a code span that does not start at the link is taken as a link."""
    delivered = [{"artifact_id": "art-1", "title": "R"}]
    for reply in (
        "[see [the] report](aws-transform://~/artifacts/art-1)",
        "[![thumb](https://x.example/t.png)](aws-transform://~/artifacts/art-1)",
        "[R](aws-transform://~/artifacts/art-1 (the report))",
        "[R][1]\n\n[1]: aws-transform://~/artifacts/art-1",
    ):
        assert append_artifact_deeplinks(reply, delivered) != reply, reply
    code_span = "Use `see [R](aws-transform://~/artifacts/art-1)` verbatim."
    assert append_artifact_deeplinks(code_span, delivered) == code_span


class _Agent:
    def __init__(self, state: Any) -> None:
        self.state = state


class _State:
    def __init__(
        self,
        delivered: Optional[List[Dict[str, Any]]] = None,
        error: Optional[Exception] = None,
        source: Any = None,
    ) -> None:
        self._delivered = delivered
        self._error = error
        self._source = source

    def get(self, key: str) -> Any:
        if self._error:
            raise self._error
        if key == CURRENT_SOURCE_TYPE_KEY:
            return self._source
        return self._delivered if key == DELIVERED_ARTIFACTS_STATE_KEY else None


def _outside_a_turn(reply: str, agent: Any) -> str:
    return contextvars.Context().run(reply_with_artifact_deeplinks, reply, agent)


def test_reply_is_untouched_for_an_agent_without_state(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        assert reply_with_artifact_deeplinks("Done.", object()) == "Done."
    assert caplog.records == []


def test_reply_links_the_artifacts_recorded_on_state() -> None:
    agent = _Agent(_State([{"artifact_id": "art-1", "title": "Report"}]))
    assert _outside_a_turn("Done.", agent) == "Done.\n\n[Report](aws-transform://~/artifacts/art-1)"


@pytest.mark.parametrize("delivered", [None, [], "art-1", {"artifact_id": "art-1"}])
def test_reply_is_untouched_when_nothing_valid_is_recorded(delivered: Any) -> None:
    assert _outside_a_turn("Done.", _Agent(_State(delivered))) == "Done."


def test_reply_survives_a_failing_state_read(caplog: pytest.LogCaptureFixture) -> None:
    agent = _Agent(_State(error=RuntimeError("boom")))
    with caplog.at_level(logging.ERROR):
        assert reply_with_artifact_deeplinks("Done.", agent) == "Done."
    assert "Failed to append artifact deeplinks" in caplog.text


class _RaisingStateAgent:
    @property
    def state(self) -> Any:
        raise RuntimeError("store closed")


def test_reply_survives_a_state_accessor_that_raises(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        assert reply_with_artifact_deeplinks("Done.", _RaisingStateAgent()) == "Done."
    assert "Failed to append artifact deeplinks" in caplog.text


def test_a_partners_own_delivered_artifacts_state_is_not_read() -> None:
    state = AgentState()
    state.set("delivered_artifacts", [{"artifact_id": "theirs", "title": "T"}])
    assert _outside_a_turn("Done.", _Agent(state)) == "Done."


def test_only_a_user_turns_reply_is_linked() -> None:
    delivered = [{"artifact_id": "art-1", "title": "R"}]
    linked = "Done.\n\n[R](aws-transform://~/artifacts/art-1)"
    for source in (MessageSourceType.USER, "USER", None):
        assert _outside_a_turn("Done.", _Agent(_State(delivered, source=source))) == linked
    for source in (MessageSourceType.SUBAGENT, MessageSourceType.NOTIFICATION, "SUBAGENT"):
        assert _outside_a_turn("Done.", _Agent(_State(delivered, source=source))) == "Done."


def test_the_turns_contextvar_source_outranks_the_shared_state_copy() -> None:
    delivered = [{"artifact_id": "art-1", "title": "R"}]
    linked = "Done.\n\n[R](aws-transform://~/artifacts/art-1)"

    def decorate(contextvar_source: MessageSourceType, state_source: MessageSourceType) -> str:
        context = contextvars.Context()
        context.run(conversation_source_type.set, contextvar_source)
        agent = _Agent(_State(delivered, source=state_source))
        return context.run(reply_with_artifact_deeplinks, "Done.", agent)

    assert decorate(MessageSourceType.SUBAGENT, MessageSourceType.USER) == "Done."
    assert decorate(MessageSourceType.USER, MessageSourceType.SUBAGENT) == linked
