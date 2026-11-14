# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import asyncio
import copy
import json
import logging
import re
from collections.abc import AsyncGenerator, Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from strands import Agent, tool
from strands.hooks import AfterToolCallEvent
from strands.models import Model
from strands.types.exceptions import StorageError
from strands.vended_plugins.context_offloader import ContextOffloader

from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
from agent_builder_sdk.orchestrator_strands.tool_output_offloader import (
    DEFAULT_KEEP_IN_CONTEXT_TOOLS,
    ToolOutputOffloader,
)

THRESHOLD = 400
PREVIEW = 20
BIG = "\n".join(f"line {i}" for i in range(1, 201))
IMAGE: dict[str, Any] = {"image": {"format": "png", "source": {"bytes": b"\x89PNG"}}}
DOCUMENT: dict[str, Any] = {"document": {"format": "pdf", "name": "d", "source": {"bytes": b"%PDF"}}}

Messages = list[dict[str, Any]]
Turn = Callable[[Messages], list[dict[str, Any]]]


class _ScriptedModel(Model):
    """Plays scripted turns, records what each call received, and counts one token per character."""

    def __init__(self, turns: Sequence[Turn] = ()) -> None:
        self.turns = list(turns)
        self.seen: list[Messages] = []

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> dict[str, Any]:
        return {}

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        raise NotImplementedError
        yield

    async def stream(self, messages: Messages, *args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        self.seen.append(copy.deepcopy(messages))
        for event in self.turns.pop(0)(messages):
            yield event

    async def count_tokens(self, messages: Messages, *args: Any, **kwargs: Any) -> int:
        await asyncio.sleep(0)  # a real suspension, so that concurrent tool results interleave here
        return len(str(messages))


def _tool_use(name: str, tool_input: Optional[dict[str, Any]] = None, tool_use_id: str = "t1") -> Turn:
    events = [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {"toolUse": {"toolUseId": tool_use_id, "name": name}}}},
        {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_input or {})}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "tool_use"}},
    ]
    return lambda messages: events


def _text(text: str) -> Turn:
    events = [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]
    return lambda messages: events


def _last_tool_result_text(messages: Messages) -> str:
    return str(messages[-1]["content"][0]["toolResult"]["content"][0]["text"])


def _reference(placeholder: str) -> str:
    return placeholder.split("[Stored references:]")[1].split()[0]


def _retrieve_lines(start: int, end: int, placeholder: Callable[[Messages], str] = _last_tool_result_text) -> Turn:
    """A turn that reads a line range of the reference in a placeholder: by default the last tool result."""

    def turn(messages: Messages) -> list[dict[str, Any]]:
        tool_input = {"reference": _reference(placeholder(messages)), "line_range": {"start": start, "end": end}}
        return _tool_use("retrieve_offloaded_content", tool_input, tool_use_id="t2")(messages)

    return turn


@tool
def big_output_tool() -> str:
    """Return 200 numbered lines."""
    return BIG


@tool
def small_output_tool() -> str:
    """Return one word."""
    return "ok"


def _agent(storage_dir: Path, **options: Any) -> tuple[Agent, ToolOutputOffloader]:
    offloader = ToolOutputOffloader(
        storage_dir=str(storage_dir), max_result_tokens=THRESHOLD, preview_tokens=PREVIEW, **options
    )
    return Agent(model=_ScriptedModel(), plugins=[offloader], callback_handler=None), offloader


def _event(
    agent: Agent,
    content: list[dict[str, Any]],
    tool_name: str = "big_output_tool",
    tool_use_id: str = "tu-1",
) -> AfterToolCallEvent:
    return AfterToolCallEvent(
        agent=agent,
        selected_tool=None,
        tool_use={"name": tool_name, "toolUseId": tool_use_id, "input": {}},
        invocation_state={},
        result={"toolUseId": tool_use_id, "status": "success", "content": content},
    )


async def _after_tool_call(agent: Agent, content: list[dict[str, Any]], **event_fields: Any) -> dict[str, Any]:
    """Run the agent's registered AfterToolCallEvent hooks on a tool result and return the result."""
    event = _event(agent, content, **event_fields)
    await agent.hooks.invoke_callbacks_async(event)
    return dict(event.result)


async def _retrieve(offloader: ToolOutputOffloader, agent: Agent, reference: str, **options: Any) -> Any:
    return await offloader.retrieve_offloaded_content(
        reference=reference, tool_context=SimpleNamespace(agent=agent), **options
    )


def _files(storage_dir: Path) -> list[Path]:
    return sorted(path for path in storage_dir.rglob("*") if path.is_file())


async def test_orchestrator_model_gets_a_preview_and_reads_the_rest_with_the_retrieval_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_runs = 0
    parent_handler = ContextOffloader._handle_tool_result

    async def counting_handler(self: ContextOffloader, event: AfterToolCallEvent) -> None:
        nonlocal parent_runs
        parent_runs += 1
        await parent_handler(self, event)

    monkeypatch.setattr(ContextOffloader, "_handle_tool_result", counting_handler)
    model = _ScriptedModel([_tool_use("big_output_tool"), _retrieve_lines(150, 151), _text("done")])
    offloader = ToolOutputOffloader(storage_dir=str(tmp_path), max_result_tokens=THRESHOLD, preview_tokens=PREVIEW)
    orchestrator = AsyncBaseOrchestrator(
        "", model=model, custom_tools=[big_output_tool], plugins=[offloader], callback_handler=None
    )

    await orchestrator.invoke_async("Show me the output.")

    placeholder = _last_tool_result_text(model.seen[1])
    assert placeholder.startswith("[Offloaded: 1 blocks")
    assert "line 1\nline 2\n" in placeholder
    assert "line 150" not in placeholder
    retrieved = _last_tool_result_text(model.seen[2])
    assert "line 150" in retrieved and "line 151" in retrieved and "line 152" not in retrieved
    assert parent_runs == 2  # once per tool call: the handler is registered exactly once
    assert [path.read_bytes().endswith(BIG.encode()) for path in _files(tmp_path)] == [True]
    assert Path(offloader.offload_dir) in _files(tmp_path)[0].parents


async def test_small_result_is_untouched(tmp_path: Path) -> None:
    agent, _ = _agent(tmp_path)

    result = await _after_tool_call(agent, [{"text": "small"}])

    assert result["content"] == [{"text": "small"}]
    assert _files(tmp_path) == []


async def test_json_result_is_offloaded_and_retrieved_whole(tmp_path: Path) -> None:
    agent, offloader = _agent(tmp_path)
    payload = {"stdout": BIG}

    result = await _after_tool_call(agent, [{"json": payload}])

    full = await _retrieve(offloader, agent, _reference(result["content"][0]["text"]))
    assert full["content"] == [{"json": payload}]


async def test_one_line_json_text_is_stored_one_value_per_line_and_is_readable_by_pattern(tmp_path: Path) -> None:
    agent, offloader = _agent(tmp_path)
    batches = [
        [{"name": f"pkg-{i}", "version": f"{i}.0.0"} for i in range(first, first + 60)] for first in (100, 200)
    ]
    texts = [json.dumps(batch, separators=(",", ":")) for batch in batches]
    blocks = [{"text": text} for text in texts]

    results = await asyncio.gather(*[_after_tool_call(agent, [block]) for block in blocks])

    assert blocks == [{"text": text} for text in texts]
    for batch, result in zip(batches, results):
        reference = _reference(result["content"][0]["text"])
        stored = await _retrieve(offloader, agent, reference)
        assert json.loads(stored) == batch
        assert max(len(line) for line in stored.splitlines()) < 40
        last = batch[-1]
        found = await _retrieve(offloader, agent, reference, pattern=f'"{last["name"]}"')
        assert f'"version": "{last["version"]}"' in found and "truncated" not in found


async def test_json_text_that_is_over_the_limit_only_when_indented_stays_in_context(tmp_path: Path) -> None:
    agent, _ = _agent(tmp_path)
    text = json.dumps([{"a": i} for i in range(24)], separators=(",", ":"))
    assert len(json.dumps(json.loads(text), indent=2)) > THRESHOLD

    result = await _after_tool_call(agent, [{"text": text}])

    assert result["content"] == [{"text": text}]
    assert _files(tmp_path) == []


@pytest.mark.parametrize(
    "text",
    ["[INFO] start\n" + BIG, json.dumps("\u00e9" * 300), json.dumps([{"note": "\ud83d"}] * 60), "[" * 100_000 + "]" * 100_000],
    ids=["not JSON", "JSON string", "JSON with an escaped lone surrogate", "JSON nested too deeply"],
)
async def test_text_that_is_not_indented_as_json_is_stored_as_returned_without_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, text: str
) -> None:
    agent, offloader = _agent(tmp_path)

    with caplog.at_level(logging.WARNING):
        result = await _after_tool_call(agent, [{"text": text}])

    assert await _retrieve(offloader, agent, _reference(result["content"][0]["text"])) == text
    assert caplog.records == []


async def test_media_and_unknown_blocks_follow_the_preview_and_empty_text_is_dropped(tmp_path: Path) -> None:
    agent, _ = _agent(tmp_path)
    video = {"video": {"format": "mp4", "source": {"bytes": b"\x00\x00\x00\x18ftyp"}}}

    result = await _after_tool_call(agent, [IMAGE, {"text": ""}, {"text": BIG}, DOCUMENT, video])

    assert result["content"][0]["text"].startswith("[Offloaded: 1 blocks")
    assert BIG not in result["content"][0]["text"]
    assert result["content"][1:] == [IMAGE, DOCUMENT, video]
    assert len(_files(tmp_path)) == 1


async def test_result_with_only_media_blocks_is_untouched(tmp_path: Path) -> None:
    agent, _ = _agent(tmp_path)
    large_image = {"image": {"format": "png", "source": {"bytes": b"\x89PNG" * 1000}}}

    result = await _after_tool_call(agent, [large_image])

    assert result["content"] == [large_image]
    assert _files(tmp_path) == []


@pytest.mark.parametrize(
    ("options", "tool_name", "offloaded"),
    [
        ({}, "skills", False),
        ({}, "my_tool", True),
        ({"keep_in_context_tools": DEFAULT_KEEP_IN_CONTEXT_TOOLS | {"my_tool"}}, "my_tool", False),
        ({"keep_in_context_tools": set()}, "skills", True),
    ],
)
async def test_results_of_keep_in_context_tools_are_not_offloaded(
    tmp_path: Path, options: dict[str, Any], tool_name: str, offloaded: bool
) -> None:
    agent, _ = _agent(tmp_path, **options)

    result = await _after_tool_call(agent, [{"text": BIG}], tool_name=tool_name)

    assert (result["content"] != [{"text": BIG}]) is offloaded
    assert len(_files(tmp_path)) == int(offloaded)


async def test_offloaded_file_is_still_retrievable_after_many_agent_cycles(tmp_path: Path) -> None:
    model = _ScriptedModel()
    model.turns = [
        _tool_use("big_output_tool"),
        *[_tool_use("small_output_tool") for _ in range(30)],
        _retrieve_lines(200, 200, placeholder=lambda messages: _last_tool_result_text(model.seen[1])),
        _text("done"),
    ]
    offloader = ToolOutputOffloader(storage_dir=str(tmp_path), max_result_tokens=THRESHOLD, preview_tokens=PREVIEW)
    agent = Agent(model=model, tools=[big_output_tool, small_output_tool], plugins=[offloader], callback_handler=None)

    await agent.invoke_async("go")

    assert "line 200" in _last_tool_result_text(model.seen[-1])


async def test_reference_is_retrievable_by_another_offloader_on_the_same_storage_dir(tmp_path: Path) -> None:
    agent_a, _ = _agent(tmp_path)
    agent_b, offloader_b = _agent(tmp_path)

    result = await _after_tool_call(agent_a, [{"text": BIG}])

    assert await _retrieve(offloader_b, agent_b, _reference(result["content"][0]["text"])) == BIG


async def test_file_names_are_generated_so_unsafe_or_reused_tool_use_ids_cannot_collide_or_escape(
    tmp_path: Path,
) -> None:
    storage_dir = tmp_path / "job"
    agent, offloader = _agent(storage_dir)
    first, second = BIG + "\nfirst", BIG + "\nsecond"

    results = await asyncio.gather(
        _after_tool_call(agent, [{"text": first}], tool_use_id="../../escape"),
        _after_tool_call(agent, [{"text": second}], tool_use_id="../../escape"),
    )

    files = _files(tmp_path)
    assert len(files) == 2
    assert all(Path(offloader.offload_dir) in path.parents for path in files)
    assert all("escape" not in path.name for path in files)
    assert [result["toolUseId"] for result in results] == ["../../escape"] * 2
    retrieved = [await _retrieve(offloader, agent, _reference(r["content"][0]["text"])) for r in results]
    assert retrieved == [first, second]


@pytest.mark.parametrize("reference", ["../../../outside", "{absolute}"])
async def test_retrieval_cannot_read_a_file_outside_the_offload_dir(tmp_path: Path, reference: str) -> None:
    agent, offloader = _agent(tmp_path / "job")
    await _after_tool_call(agent, [{"text": BIG}])
    outside = tmp_path / "outside"
    _files(tmp_path)[0].rename(outside)  # a file in the stored format, so only its location protects it

    try:
        retrieved = await _retrieve(offloader, agent, reference.format(absolute=outside))
    except (ValueError, StorageError):
        return
    assert BIG not in str(retrieved)  # the oldest supported Strands returns an error text instead of raising


async def test_failed_file_write_keeps_the_whole_result_in_context_and_logs_the_cause_and_the_tool(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    agent, offloader = _agent(tmp_path)
    Path(offloader.offload_dir).write_text("a file where the offload directory should be")

    with caplog.at_level(logging.DEBUG):
        result = await _after_tool_call(agent, [IMAGE, {"text": BIG}])

    assert result["content"] == [IMAGE, {"text": BIG}]
    assert "NotADirectoryError" in caplog.text
    warning = next(record.getMessage() for record in caplog.records if record.levelno == logging.WARNING)
    offload_id = re.search(r"[0-9a-f]{32}", warning)
    assert offload_id is not None
    debug_lines = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert any(
        offload_id.group() in line and "'big_output_tool'" in line and "'tu-1'" in line for line in debug_lines
    )


async def test_failed_token_count_keeps_the_whole_result_in_context_and_logs_the_tool(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, _ = _agent(tmp_path)

    async def no_tokenizer(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("no tokenizer")

    monkeypatch.setattr(agent.model, "count_tokens", no_tokenizer)

    with caplog.at_level(logging.WARNING):
        result = await _after_tool_call(agent, [IMAGE, {"text": BIG}])

    assert result["content"] == [IMAGE, {"text": BIG}]
    assert _files(tmp_path) == []
    assert "'big_output_tool'" in caplog.text and "no tokenizer" in caplog.text


async def test_cancellation_during_offload_leaves_the_result_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, _ = _agent(tmp_path)

    async def cancelled(*args: Any, **kwargs: Any) -> int:
        raise asyncio.CancelledError

    monkeypatch.setattr(agent.model, "count_tokens", cancelled)
    event = _event(agent, [IMAGE, {"text": BIG}])

    with pytest.raises(asyncio.CancelledError):
        await agent.hooks.invoke_callbacks_async(event)

    assert event.result["content"] == [IMAGE, {"text": BIG}]


def test_empty_storage_dir_is_rejected() -> None:
    with pytest.raises(ValueError, match="storage_dir"):
        ToolOutputOffloader(storage_dir="")
