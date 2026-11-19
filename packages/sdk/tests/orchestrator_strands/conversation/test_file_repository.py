# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the FileMultiSourceConversationRepository class."""

import copy
import os
import tempfile
from typing import Any, List, Tuple, cast
from unittest.mock import Mock

import pytest
from strands.agent import Agent
from strands.types.content import ContentBlock, Message, Role

from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    DEFAULT_SOURCE_ID,
    MessageSourceType,
)
from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
    FileMultiSourceConversationRepository,
)
from agent_builder_sdk.orchestrator_strands.conversation.message_type import (
    ConversationMessage,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_id,
    conversation_source_type,
)
from agent_builder_sdk.utils import INTERRUPTED_TURN_TEXT


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture
def repository(temp_dir):
    """Create a FileMultiSourceConversationRepository instance."""
    return FileMultiSourceConversationRepository(storage_dir=temp_dir)


@pytest.fixture
def mock_agent():
    """Create a mock Agent instance."""
    agent = Mock(spec=Agent)
    agent.state = {}
    return agent


def test_initialization_with_storage_dir(temp_dir):
    """Test repository initialization with storage directory."""
    repo = FileMultiSourceConversationRepository(storage_dir=temp_dir)
    assert repo.storage_dir == temp_dir
    assert os.path.exists(temp_dir)


def test_initialization_without_storage_dir():
    """Test repository initialization without storage directory."""
    repo = FileMultiSourceConversationRepository()
    expected_dir = os.path.join(tempfile.gettempdir(), "orchestrator", "conversations")
    assert repo.storage_dir == expected_dir
    assert os.path.exists(expected_dir)


def test_add_message_for_agent_user(repository, mock_agent):
    """Test adding a user message."""
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")

    message = Message(role="user", content=[ContentBlock(text="Test message")])
    repository.add_message_for_agent(message, mock_agent)

    # Verify message was stored
    assert len(repository.conversations[MessageSourceType.USER.value]["test-user"]) == 1
    stored_message = repository.conversations[MessageSourceType.USER.value]["test-user"][0]
    assert isinstance(stored_message, ConversationMessage)
    assert stored_message.to_message()["role"] == "user"
    assert stored_message.to_message()["content"][0]["text"] == "Test message"


def test_add_message_for_agent_notification(repository, mock_agent):
    """Test adding a notification message."""
    conversation_source_type.set(MessageSourceType.NOTIFICATION)
    conversation_source_id.set("any-id")  # Should use DEFAULT_SOURCE_ID

    message = Message(role="assistant", content=[ContentBlock(text="Test notification")])
    repository.add_message_for_agent(message, mock_agent)

    # Verify message was stored with default source ID
    notifications = repository.conversations[MessageSourceType.NOTIFICATION.value][
        DEFAULT_SOURCE_ID
    ]
    assert len(notifications) == 1
    assert notifications[0].to_message()["content"][0]["text"] == "Test notification"


def test_get_conversation_history_for_agent_user(repository, mock_agent):
    """Test retrieving conversation history for a user."""
    # Add a user message
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    user_message = Message(role="user", content=[ContentBlock(text="User message")])
    repository.add_message_for_agent(user_message, mock_agent)

    # Add a notification
    conversation_source_type.set(MessageSourceType.NOTIFICATION)
    conversation_source_id.set(DEFAULT_SOURCE_ID)
    notification = Message(role="assistant", content=[ContentBlock(text="Notification")])
    repository.add_message_for_agent(notification, mock_agent)

    # Get history for user
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    history = repository.get_conversation_history_for_agent(mock_agent)

    # Should include the user message (closed by the unanswered-turn placeholder) and notification
    assert len(history) == 3
    assert history[0]["content"][0]["text"] == "User message"
    assert history[1]["content"][0]["text"] == INTERRUPTED_TURN_TEXT
    assert history[2]["content"][0]["text"] == "Notification"


def test_aborted_notification_turn_is_closed_on_its_own(repository, mock_agent):
    """An aborted notification turn gets its own placeholder, so the user's history does not end
    with an unanswered notification."""
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    repository.add_message_for_agent(
        Message(role="user", content=[ContentBlock(text="q")]), mock_agent
    )
    repository.add_message_for_agent(
        Message(role="assistant", content=[ContentBlock(text="a")]), mock_agent
    )
    conversation_source_type.set(MessageSourceType.NOTIFICATION)
    conversation_source_id.set(DEFAULT_SOURCE_ID)
    repository.add_message_for_agent(
        Message(role="user", content=[ContentBlock(text="job finished")]), mock_agent
    )

    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    history = repository.get_conversation_history_for_agent(mock_agent)

    assert [m["content"][0]["text"] for m in history] == [
        "q",
        "a",
        "job finished",
        INTERRUPTED_TURN_TEXT,
    ]


def test_pending_interrupt_leaves_notifications_unrepaired(repository, mock_agent):
    """With a Strands interrupt pending, history is returned as stored, notifications included."""
    mock_agent._interrupt_state = Mock(activated=True)
    conversation_source_type.set(MessageSourceType.NOTIFICATION)
    conversation_source_id.set(DEFAULT_SOURCE_ID)
    repository.add_message_for_agent(
        Message(role="user", content=[ContentBlock(text="job finished")]), mock_agent
    )

    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    history = repository.get_conversation_history_for_agent(mock_agent)

    assert [m["content"][0]["text"] for m in history] == ["job finished"]


def test_get_conversation_history_returns_fresh_list_each_call(repository, mock_agent):
    """Each call returns a NEW list object, not a shared/aliased instance.

    This is load-bearing for concurrent streaming: the returned list becomes
    agent.messages and is mutated by Strands OUTSIDE the repo lock. If one shared
    repository is used by several agents for the same source, aliasing one list would
    let concurrent invocations clobber each other's in-flight history. The durable
    store stays consistent; only the returned working copy must be per-call.
    """
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    repository.add_message_for_agent(
        Message(role="user", content=[ContentBlock(text="hi")]), mock_agent
    )
    repository.add_message_for_agent(
        Message(role="assistant", content=[ContentBlock(text="hello")]), mock_agent
    )

    h1 = repository.get_conversation_history_for_agent(mock_agent)
    h2 = repository.get_conversation_history_for_agent(mock_agent)

    # distinct list objects with identical contents
    assert h1 is not h2
    assert h1 == h2
    # mutating one working copy (as Strands would) does not affect the next call
    h1.append(Message(role="user", content=[ContentBlock(text="scratch")]))
    h3 = repository.get_conversation_history_for_agent(mock_agent)
    assert len(h3) == 2  # durable store unchanged by the in-place mutation


def test_save_and_load(repository, temp_dir, mock_agent):
    """Test saving and loading conversations."""
    # Add some messages
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    message = Message(role="user", content=[ContentBlock(text="Test message")])
    repository.add_message_for_agent(message, mock_agent)

    # Create new repository instance to load saved data
    new_repository = FileMultiSourceConversationRepository(storage_dir=temp_dir)

    # Verify messages were loaded
    assert len(new_repository.conversations[MessageSourceType.USER.value]["test-user"]) == 1
    loaded_message = new_repository.conversations[MessageSourceType.USER.value]["test-user"][0]
    assert loaded_message.to_message()["content"][0]["text"] == "Test message"


def test_corrupted_file_handling(temp_dir):
    """Test handling of corrupted conversation file."""
    # Create corrupted JSON file
    file_path = os.path.join(temp_dir, "conversations.json")
    with open(file_path, "w") as f:
        f.write("{ invalid json")

    # Repository should handle corrupted file gracefully
    repository = FileMultiSourceConversationRepository(storage_dir=temp_dir)

    # Verify backup was created
    assert os.path.exists(file_path + ".corrupted")

    # Verify empty conversations were initialized
    assert MessageSourceType.USER.value in repository.conversations
    assert MessageSourceType.NOTIFICATION.value in repository.conversations
    assert DEFAULT_SOURCE_ID in repository.conversations[MessageSourceType.NOTIFICATION.value]


def test_has_reentrant_lock(repository):
    """The repo guards its maps + file writes with a reentrant lock (add() calls
    save() while holding it; also load-bearing when a shared instance is written by
    concurrent streaming agents on separate threads)."""
    import threading

    assert isinstance(repository._lock, type(threading.RLock()))


def test_concurrent_distinct_users_no_history_loss(temp_dir):
    """One shared repo instance written by many threads (distinct users, as in
    concurrent streaming) keeps every user's partition — no save() overwrites another."""
    import threading

    repo = FileMultiSourceConversationRepository(storage_dir=temp_dir)
    agent = Mock(spec=Agent)
    agent.state = {}
    n_users = 20
    msgs_per_user = 5

    def write_user(uid):
        # each thread starts with a fresh context; set its own source
        conversation_source_type.set(MessageSourceType.USER)
        conversation_source_id.set(uid)
        for i in range(msgs_per_user):
            repo.add_message_for_agent(
                Message(role="user", content=[ContentBlock(text=f"{uid}-{i}")]), agent
            )

    threads = [threading.Thread(target=write_user, args=(f"user{u}",)) for u in range(n_users)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # every user's partition is present with all its messages — no loss/overwrite
    users = repo.conversations[MessageSourceType.USER.value]
    assert len(users) == n_users
    for u in range(n_users):
        assert len(users[f"user{u}"]) == msgs_per_user

    # and the persisted file agrees (last save wrote the whole, consistent dict)
    reloaded = FileMultiSourceConversationRepository(storage_dir=temp_dir)
    persisted = reloaded.conversations[MessageSourceType.USER.value]
    assert len(persisted) == n_users
    for u in range(n_users):
        assert len(persisted[f"user{u}"]) == msgs_per_user


def test_get_conversation_history_repairs_dangling_tool_use(repository, mock_agent):
    """An interrupted turn persists a toolUse with no result; the load path repairs it."""
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    repository.add_message_for_agent(
        Message(role="user", content=[ContentBlock(text="run it")]), mock_agent
    )
    repository.add_message_for_agent(
        Message(
            role="assistant",
            content=[
                cast(
                    ContentBlock,
                    {"toolUse": {"name": "execute", "toolUseId": "tool-1", "input": {}}},
                )
            ],
        ),
        mock_agent,
    )

    conversation_source_type.set(MessageSourceType.NOTIFICATION)
    conversation_source_id.set(DEFAULT_SOURCE_ID)
    repository.add_message_for_agent(
        Message(role="assistant", content=[ContentBlock(text="Notification")]), mock_agent
    )

    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    history = repository.get_conversation_history_for_agent(mock_agent)

    assert history[2]["content"][0]["toolResult"]["toolUseId"] == "tool-1"
    assert history[2]["content"][0]["toolResult"]["status"] == "error"
    assert history[3]["content"][0]["text"] == INTERRUPTED_TURN_TEXT
    assert history[4]["content"][0]["text"] == "Notification"


def test_get_conversation_history_leaves_well_formed_messages_identical(repository, mock_agent):
    """A healthy history round-trips with the SAME message objects, not copies.

    The repair runs unflagged for every consumer, so it must be observably a no-op here.
    """
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    for message in (
        Message(role="user", content=[ContentBlock(text="run it")]),
        Message(
            role="assistant",
            content=[
                cast(
                    ContentBlock,
                    {"toolUse": {"name": "execute", "toolUseId": "tool-1", "input": {}}},
                )
            ],
        ),
        Message(
            role="user",
            content=[
                cast(
                    ContentBlock,
                    {"toolResult": {"toolUseId": "tool-1", "content": [], "status": "success"}},
                )
            ],
        ),
        Message(role="assistant", content=[ContentBlock(text="done")]),
    ):
        repository.add_message_for_agent(message, mock_agent)

    stored = repository.conversations[MessageSourceType.USER.value]["test-user"]
    history = repository.get_conversation_history_for_agent(mock_agent)

    assert len(history) == 4
    assert all(actual is original.to_message() for actual, original in zip(history, stored))


def test_get_conversation_history_leaves_tool_use_unpaired_during_an_interrupt(
    repository, mock_agent
):
    """An interrupt resume supplies the real toolResult, so the pending toolUse must stay as-is.

    Repairing it would put a synthetic result and the real one after the same toolUse.
    """
    mock_agent._interrupt_state = Mock(activated=True)
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    repository.add_message_for_agent(
        Message(role="user", content=[ContentBlock(text="run it")]), mock_agent
    )
    repository.add_message_for_agent(
        Message(
            role="assistant",
            content=[
                cast(
                    ContentBlock,
                    {"toolUse": {"name": "execute", "toolUseId": "tool-1", "input": {}}},
                )
            ],
        ),
        mock_agent,
    )

    history = repository.get_conversation_history_for_agent(mock_agent)

    assert len(history) == 2
    assert "toolResult" not in str(history)


TOOL_REPAIR_TEXT = "Tool did not complete; the turn was interrupted."


def _as_source(source_type: MessageSourceType, source_id: str) -> None:
    conversation_source_type.set(source_type)
    conversation_source_id.set(source_id)


def _text(role: Role, text: str) -> Message:
    return Message(role=role, content=[ContentBlock(text=text)])


def _tool_uses(*tool_use_ids: str) -> Message:
    return Message(
        role="assistant",
        content=[
            ContentBlock(toolUse={"name": "preflight", "toolUseId": tool_use_id, "input": {}})
            for tool_use_id in tool_use_ids
        ],
    )


def _tool_results(*tool_use_ids: str) -> Message:
    return Message(
        role="user",
        content=[
            ContentBlock(
                toolResult={
                    "toolUseId": tool_use_id,
                    "content": [{"text": "ok"}],
                    "status": "success",
                }
            )
            for tool_use_id in tool_use_ids
        ],
    )


def _pairing_errors(messages: List[Message]) -> List[str]:
    """Bedrock's rule for a request: the toolResult blocks of a message answer exactly the toolUse
    blocks of the message right before it, so no toolUse may come last."""

    def ids(message: Message, kind: str) -> List[str]:
        blocks = cast(List[Any], message["content"])
        return sorted(block[kind]["toolUseId"] for block in blocks if kind in block)

    errors = []
    open_tool_uses: List[str] = []
    for index, message in enumerate(messages):
        if ids(message, "toolResult") != open_tool_uses:
            errors.append(f"messages.{index} does not answer exactly {open_tool_uses}")
        open_tool_uses = ids(message, "toolUse")
    if open_tool_uses:
        errors.append(f"the last message leaves {open_tool_uses} open")
    return errors


def _tool_result_texts(messages: List[Message]) -> List[Tuple[str, str, str]]:
    """(toolUseId, status, text) of every toolResult, in order."""
    return [
        (result["toolUseId"], result["status"], cast(str, result["content"][0]["text"]))
        for message in messages
        for block in message["content"]
        if (result := block.get("toolResult")) is not None
    ]


def _stored(repository: FileMultiSourceConversationRepository) -> Tuple[bytes, Any]:
    """What the repository holds: the bytes on disk and a copy of the conversations in memory."""
    with open(os.path.join(repository.storage_dir, "conversations.json"), "rb") as file:
        return file.read(), copy.deepcopy(repository.conversations)


def _store_notifications_beside_a_user_turn(
    repository: FileMultiSourceConversationRepository, agent: Agent, *notifications: Message
) -> None:
    """userA has had a turn and the notification conversation holds ``notifications``; userA is
    the source again afterwards."""
    _as_source(MessageSourceType.USER, "userA")
    repository.add_message_for_agent(_text("user", "hi"), agent)
    repository.add_message_for_agent(_text("assistant", "hello"), agent)
    _as_source(MessageSourceType.NOTIFICATION, DEFAULT_SOURCE_ID)
    for message in notifications:
        repository.add_message_for_agent(message, agent)
    _as_source(MessageSourceType.USER, "userA")


def test_user_view_answers_a_notification_tool_use_left_open_at_the_end(
    repository: FileMultiSourceConversationRepository, mock_agent: Agent
) -> None:
    """A notification turn that stopped inside a tool leaves its toolUse last in the notification
    conversation. Every later user turn still gets a request Bedrock accepts, and nothing stored
    changes."""
    _store_notifications_beside_a_user_turn(
        repository, mock_agent, _text("user", "HITL task 1 is submitted"), _tool_uses("N1")
    )

    for prompt in ("any news?", "hello?"):
        before = _stored(repository)
        history = repository.get_conversation_history_for_agent(mock_agent)

        assert _stored(repository) == before
        assert _pairing_errors([*history, _text("user", prompt)]) == []
        assert _tool_result_texts(history) == [("N1", "error", TOOL_REPAIR_TEXT)]
        assert history[-1] == _text("assistant", INTERRUPTED_TURN_TEXT)
        repository.add_message_for_agent(_text("user", prompt), mock_agent)
        repository.add_message_for_agent(_text("assistant", "nothing yet"), mock_agent)


def test_user_view_answers_a_notification_tool_use_left_open_before_a_later_notification(
    repository: FileMultiSourceConversationRepository, mock_agent: Agent
) -> None:
    """The open toolUse of an earlier notification turn is answered in place, ahead of the
    notification turns stored after it."""
    _store_notifications_beside_a_user_turn(
        repository,
        mock_agent,
        _text("user", "an earlier notification"),
        _tool_uses("open"),
        _text("user", "HITL task 1 is submitted"),
        _tool_uses("N2"),
        _tool_results("N2"),
        _text("assistant", "done"),
    )
    before = _stored(repository)

    history = repository.get_conversation_history_for_agent(mock_agent)

    assert _stored(repository) == before
    assert _pairing_errors([*history, _text("user", "any news?")]) == []
    assert [message["role"] for message in history] == ["user", "assistant"] * 5
    assert _tool_result_texts(history) == [
        ("open", "error", TOOL_REPAIR_TEXT),
        ("N2", "success", "ok"),
    ]
    assert history[5] == _text("assistant", INTERRUPTED_TURN_TEXT)


@pytest.mark.parametrize("answered", [(), ("B",)], ids=["none answered", "one answered"])
def test_user_view_answers_every_open_tool_use_of_one_notification_message(
    repository: FileMultiSourceConversationRepository, mock_agent: Agent, answered: Tuple[str, ...]
) -> None:
    """One assistant message can call several tools. Each call without a stored result gets one,
    in the same message as the results that did arrive."""
    notifications = [_text("user", "HITL task 1 is submitted"), _tool_uses("A", "B", "C")]
    if answered:
        notifications.append(_tool_results(*answered))
    _store_notifications_beside_a_user_turn(repository, mock_agent, *notifications)
    before = _stored(repository)

    history = repository.get_conversation_history_for_agent(mock_agent)

    assert _stored(repository) == before
    assert _pairing_errors([*history, _text("user", "any news?")]) == []
    assert sorted(_tool_result_texts(history[4:5])) == [
        ("A", "error", TOOL_REPAIR_TEXT),
        ("B", "success", "ok") if answered else ("B", "error", TOOL_REPAIR_TEXT),
        ("C", "error", TOOL_REPAIR_TEXT),
    ]


def test_user_view_leaves_answered_notification_tool_uses_identical(
    repository: FileMultiSourceConversationRepository, mock_agent: Agent
) -> None:
    """A well-formed notification conversation reaches the user's view as the same message
    objects, with nothing added."""
    _store_notifications_beside_a_user_turn(
        repository,
        mock_agent,
        _text("user", "HITL task 1 is submitted"),
        _tool_uses("N1"),
        _tool_results("N1"),
        _text("assistant", "done"),
    )
    stored = repository.conversations[MessageSourceType.NOTIFICATION.value][DEFAULT_SOURCE_ID]

    history = repository.get_conversation_history_for_agent(mock_agent)

    assert len(history) == 6
    assert all(actual is original.to_message() for actual, original in zip(history[2:], stored))
