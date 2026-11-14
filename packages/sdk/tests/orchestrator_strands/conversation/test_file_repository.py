# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the FileMultiSourceConversationRepository class."""

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Iterator, List, cast
from unittest.mock import Mock

import pytest
from strands.agent import Agent
from strands.types.content import ContentBlock, Message, Role

from agent_builder_sdk.orchestrator_strands.conversation import file_repository
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
    ConversationRepository,
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


def _as_source(source_type: MessageSourceType, source_id: str) -> None:
    conversation_source_type.set(source_type)
    conversation_source_id.set(source_id)


def _text(role: Role, text: str) -> Message:
    return Message(role=role, content=[ContentBlock(text=text)])


def _texts(messages: List[Message]) -> List[str]:
    return [message["content"][0]["text"] for message in messages]


def _seed(
    repository: FileMultiSourceConversationRepository,
    agent: Mock,
    source_type: MessageSourceType,
    source_id: str,
    count: int,
) -> List[ConversationMessage]:
    """Store ``count`` messages m0, m1, ... (user first, roles alternate); the stored entries."""
    _as_source(source_type, source_id)
    for i in range(count):
        repository.add_message_for_agent(
            _text("user" if i % 2 == 0 else "assistant", f"m{i}"), agent
        )
    return repository.conversations[source_type.value][source_id]


def _stored_texts(
    repository: FileMultiSourceConversationRepository,
    source_type: MessageSourceType,
    source_id: str,
) -> List[str]:
    return _texts(
        [entry.message for entry in repository.conversations[source_type.value][source_id]]
    )


def _persisted_texts(
    repository: FileMultiSourceConversationRepository,
    source_type: MessageSourceType,
    source_id: str,
) -> List[str]:
    """What a new repository reads back from the same directory."""
    reloaded = FileMultiSourceConversationRepository(storage_dir=repository.storage_dir)
    return _stored_texts(reloaded, source_type, source_id)


@pytest.mark.parametrize("source_type", [MessageSourceType.USER, MessageSourceType.SUBAGENT])
def test_fold_replaces_the_folded_messages_and_keeps_the_rest(
    repository: FileMultiSourceConversationRepository,
    mock_agent: Mock,
    source_type: MessageSourceType,
) -> None:
    stored = _seed(repository, mock_agent, source_type, "s1", 6)
    oldest_at, kept = stored[0].created_at, stored[4:]
    view = repository.get_conversation_history_for_agent(mock_agent)

    assert repository.fold_history_for_agent(view[:4], [_text("user", "summary")], mock_agent)

    after = repository.conversations[source_type.value]["s1"]
    assert _stored_texts(repository, source_type, "s1") == ["summary", "m4", "m5"]
    assert after[0].created_at == oldest_at
    assert all(entry is original for entry, original in zip(after[1:], kept))
    assert _persisted_texts(repository, source_type, "s1") == ["summary", "m4", "m5"]


@pytest.mark.parametrize("strands_owns_the_key", [True, False])
def test_fold_finds_the_stored_original_of_a_copy_the_load_repair_made(
    repository: FileMultiSourceConversationRepository,
    mock_agent: Mock,
    monkeypatch: pytest.MonkeyPatch,
    strands_owns_the_key: bool,
) -> None:
    monkeypatch.setattr(file_repository, "_STRANDS_OWNS_TRACKING_ID", strands_owns_the_key)

    def tool_use(tool_use_id: str) -> ContentBlock:
        return cast(
            ContentBlock, {"toolUse": {"name": "run", "toolUseId": tool_use_id, "input": {}}}
        )

    answer_a = {"toolResult": {"toolUseId": "a", "content": [{"text": "ok"}]}}
    _as_source(MessageSourceType.USER, "u1")
    for message in (
        _text("user", "run both"),
        Message(role="assistant", content=[tool_use("a"), tool_use("b")]),
        Message(role="user", content=[cast(ContentBlock, answer_a)]),  # "b" never answered
        _text("assistant", "done"),
        _text("user", "next"),
        _text("assistant", "ok"),
    ):
        repository.add_message_for_agent(message, mock_agent)
    stored = repository.conversations[MessageSourceType.USER.value]["u1"]
    view = repository.get_conversation_history_for_agent(mock_agent)
    assert view[2] is not stored[2].message and len(view[2]["content"]) == 2

    assert repository.fold_history_for_agent(view[:4], [_text("user", "summary")], mock_agent)

    assert _stored_texts(repository, MessageSourceType.USER, "u1") == ["summary", "next", "ok"]


def test_fold_ignores_messages_the_source_does_not_store(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    _as_source(MessageSourceType.NOTIFICATION, DEFAULT_SOURCE_ID)
    repository.add_message_for_agent(_text("user", "event"), mock_agent)
    repository.add_message_for_agent(_text("assistant", "noted"), mock_agent)
    _seed(repository, mock_agent, MessageSourceType.USER, "u1", 3)
    view = repository.get_conversation_history_for_agent(mock_agent)
    # The user's own history, the placeholder for its unanswered turn, then the notifications.
    assert _texts(view) == ["m0", "m1", "m2", INTERRUPTED_TURN_TEXT, "event", "noted"]

    assert repository.fold_history_for_agent(view, [_text("user", "summary")], mock_agent)

    assert _stored_texts(repository, MessageSourceType.USER, "u1") == ["summary"]
    assert _stored_texts(repository, MessageSourceType.NOTIFICATION, DEFAULT_SOURCE_ID) == [
        "event",
        "noted",
    ]


def test_fold_from_a_stale_view_leaves_one_replacement_at_the_start(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    _seed(repository, mock_agent, MessageSourceType.USER, "u1", 8)
    stale_view = repository.get_conversation_history_for_agent(mock_agent)
    first = [_text("user", "summary A"), _text("assistant", "understood")]
    assert repository.fold_history_for_agent(stale_view[:4], first, mock_agent)
    assert _stored_texts(repository, MessageSourceType.USER, "u1") == [
        "summary A",
        "understood",
        "m4",
        "m5",
        "m6",
        "m7",
    ]

    assert repository.fold_history_for_agent(
        stale_view[:6], [_text("user", "summary B")], mock_agent
    )

    assert _stored_texts(repository, MessageSourceType.USER, "u1") == ["summary B", "m6", "m7"]


def test_fold_keeps_turns_appended_after_the_view_was_read(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    _seed(repository, mock_agent, MessageSourceType.USER, "u1", 4)
    view = repository.get_conversation_history_for_agent(mock_agent)
    repository.add_message_for_agent(_text("user", "late question"), mock_agent)
    repository.add_message_for_agent(_text("assistant", "late answer"), mock_agent)

    assert repository.fold_history_for_agent(view, [_text("user", "summary")], mock_agent)

    expected = ["summary", "late question", "late answer"]
    assert _stored_texts(repository, MessageSourceType.USER, "u1") == expected
    assert _persisted_texts(repository, MessageSourceType.USER, "u1") == expected


def test_fold_loses_no_message_another_thread_appends_meanwhile(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    _seed(repository, mock_agent, MessageSourceType.USER, "u1", 4)
    view = repository.get_conversation_history_for_agent(mock_agent)
    scanned, appended = threading.Event(), threading.Event()

    class PausesOnFirstRead(List[Message]):
        """Read by the fold after its scan of the store: gives the appender 0.2 s to run."""

        def __iter__(self) -> Iterator[Message]:
            if not scanned.is_set():
                scanned.set()
                appended.wait(0.2)
            return super().__iter__()

    def append() -> None:
        _as_source(MessageSourceType.USER, "u1")  # a new thread starts with an empty context
        scanned.wait(5)
        repository.add_message_for_agent(_text("assistant", "late"), mock_agent)
        appended.set()

    appender = threading.Thread(target=append)
    appender.start()
    try:
        stored = repository.fold_history_for_agent(
            view, PausesOnFirstRead([_text("user", "summary")]), mock_agent
        )
    finally:
        appender.join(timeout=5)

    assert stored and scanned.is_set() and not appender.is_alive()
    assert _stored_texts(repository, MessageSourceType.USER, "u1") == ["summary", "late"]
    assert _persisted_texts(repository, MessageSourceType.USER, "u1") == ["summary", "late"]


@pytest.mark.parametrize("failure", ["serialization stops partway", "rename fails"])
def test_fold_whose_write_fails_leaves_memory_and_file_as_they_were(
    repository: FileMultiSourceConversationRepository,
    mock_agent: Mock,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    stored = _seed(repository, mock_agent, MessageSourceType.USER, "u1", 4)
    before = list(stored)
    path = Path(repository.storage_dir, "conversations.json")
    on_disk = path.read_bytes()
    summary = _text("user", "summary")
    if failure == "serialization stops partway":
        # A set is not JSON: the dump raises after part of the document is in the temporary file.
        summary["content"].append(cast(ContentBlock, {"text": {"not", "json"}}))
    else:
        monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("disk full")))

    folded = [entry.message for entry in stored[:2]]
    assert repository.fold_history_for_agent(folded, [summary], mock_agent) is False

    after = repository.conversations[MessageSourceType.USER.value]["u1"]
    assert len(after) == 4 and all(entry is original for entry, original in zip(after, before))
    assert path.read_bytes() == on_disk


@pytest.mark.parametrize("folded", [[], [_text("assistant", "never stored")]])
def test_fold_of_no_stored_message_stores_nothing(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock, folded: List[Message]
) -> None:
    stored = _seed(repository, mock_agent, MessageSourceType.USER, "u1", 2)
    before = list(stored)

    assert (
        repository.fold_history_for_agent(folded, [_text("user", "summary")], mock_agent) is False
    )

    assert _stored_texts(repository, MessageSourceType.USER, "u1") == ["m0", "m1"]
    assert repository.conversations[MessageSourceType.USER.value]["u1"] == before


def test_fold_reaches_only_the_history_of_the_current_source(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    _seed(repository, mock_agent, MessageSourceType.USER, "u1", 2)
    view = repository.get_conversation_history_for_agent(mock_agent)
    _as_source(MessageSourceType.USER, "u2")

    assert repository.fold_history_for_agent(view, [_text("user", "summary")], mock_agent) is False

    assert _stored_texts(repository, MessageSourceType.USER, "u1") == ["m0", "m1"]
    assert "u2" not in repository.conversations[MessageSourceType.USER.value]


def test_fold_never_replaces_the_notification_history(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    stored = _seed(repository, mock_agent, MessageSourceType.NOTIFICATION, DEFAULT_SOURCE_ID, 2)
    folded = [entry.message for entry in stored]

    assert (
        repository.fold_history_for_agent(folded, [_text("user", "summary")], mock_agent) is False
    )

    assert _stored_texts(repository, MessageSourceType.NOTIFICATION, DEFAULT_SOURCE_ID) == [
        "m0",
        "m1",
    ]


def test_fold_with_an_empty_replacement_stores_a_trim(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    stored = _seed(repository, mock_agent, MessageSourceType.USER, "u1", 4)

    assert repository.fold_history_for_agent(
        [entry.message for entry in stored[:2]], [], mock_agent
    )

    assert _stored_texts(repository, MessageSourceType.USER, "u1") == ["m2", "m3"]
    assert _persisted_texts(repository, MessageSourceType.USER, "u1") == ["m2", "m3"]


def test_a_summary_before_a_users_message_needs_an_assistant_message_after_it(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    stored = _seed(repository, mock_agent, MessageSourceType.USER, "u1", 4)
    summary = _text("user", "summary")
    repository.fold_history_for_agent(
        [entry.message for entry in stored[:2]], [summary], mock_agent
    )
    # Two user messages in a row: the next view answers the summary as an interrupted turn.
    assert _texts(repository.get_conversation_history_for_agent(mock_agent)) == [
        "summary",
        INTERRUPTED_TURN_TEXT,
        "m2",
        "m3",
    ]

    repository.fold_history_for_agent([summary], [summary, _text("assistant", "ok")], mock_agent)

    assert _texts(repository.get_conversation_history_for_agent(mock_agent)) == [
        "summary",
        "ok",
        "m2",
        "m3",
    ]


@pytest.mark.parametrize("strands_owns_the_key", [True, False])
def test_a_stored_message_gets_a_tracking_id_only_where_strands_owns_the_key(
    repository: FileMultiSourceConversationRepository,
    mock_agent: Mock,
    monkeypatch: pytest.MonkeyPatch,
    strands_owns_the_key: bool,
) -> None:
    monkeypatch.setattr(file_repository, "_STRANDS_OWNS_TRACKING_ID", strands_owns_the_key)
    _as_source(MessageSourceType.USER, "u1")
    plain, other, summary = _text("user", "q"), _text("user", "q"), _text("user", "summary")
    tracked = cast(Message, {**_text("assistant", "a"), "tracking_id": "set-by-strands"})

    for message in (plain, other, tracked):
        repository.add_message_for_agent(message, mock_agent)
    assert repository.fold_history_for_agent([plain], [summary], mock_agent)

    assert tracked["tracking_id"] == "set-by-strands"
    if strands_owns_the_key:
        assert plain["tracking_id"] and other["tracking_id"] and summary["tracking_id"]
        assert len({plain["tracking_id"], other["tracking_id"], summary["tracking_id"]}) == 3
    else:
        assert plain == _text("user", "q") == other and summary == _text("user", "summary")


def test_fold_matches_by_object_identity_messages_that_have_no_tracking_id(
    repository: FileMultiSourceConversationRepository,
    mock_agent: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_repository, "_STRANDS_OWNS_TRACKING_ID", False)
    _as_source(MessageSourceType.USER, "u1")
    for message in (
        _text("user", "m0"),
        Message(role="assistant", content=[]),  # no content block to match by either
        _text("user", "m2"),
        _text("assistant", "m3"),
    ):
        repository.add_message_for_agent(message, mock_agent)
    view = repository.get_conversation_history_for_agent(mock_agent)
    assert not any("tracking_id" in message for message in view)

    assert repository.fold_history_for_agent(view[:2], [_text("user", "summary")], mock_agent)

    assert _stored_texts(repository, MessageSourceType.USER, "u1") == ["summary", "m2", "m3"]
    assert _persisted_texts(repository, MessageSourceType.USER, "u1") == ["summary", "m2", "m3"]


def test_fold_does_not_match_messages_by_a_shared_block_that_is_not_a_dict(
    repository: FileMultiSourceConversationRepository, mock_agent: Mock
) -> None:
    _as_source(MessageSourceType.USER, "u1")
    block = cast(ContentBlock, "one str object")  # equal str objects can share an id
    first, second = Message(role="user", content=[block]), Message(role="user", content=[block])
    repository.add_message_for_agent(first, mock_agent)
    repository.add_message_for_agent(second, mock_agent)

    assert repository.fold_history_for_agent([first], [], mock_agent)

    stored = repository.conversations[MessageSourceType.USER.value]["u1"]
    assert len(stored) == 1 and stored[0].message is second


@pytest.mark.parametrize("strands_owns_the_key", [True, False])
def test_fold_matches_a_deep_copy_only_by_its_tracking_id(
    repository: FileMultiSourceConversationRepository,
    mock_agent: Mock,
    monkeypatch: pytest.MonkeyPatch,
    strands_owns_the_key: bool,
) -> None:
    monkeypatch.setattr(file_repository, "_STRANDS_OWNS_TRACKING_ID", strands_owns_the_key)
    _seed(repository, mock_agent, MessageSourceType.USER, "u1", 4)
    folded = copy.deepcopy(repository.get_conversation_history_for_agent(mock_agent)[:2])

    stored = repository.fold_history_for_agent(folded, [_text("user", "summary")], mock_agent)

    assert stored is strands_owns_the_key
    expected = ["summary", "m2", "m3"] if strands_owns_the_key else ["m0", "m1", "m2", "m3"]
    assert _stored_texts(repository, MessageSourceType.USER, "u1") == expected


@pytest.mark.parametrize("strands_owns_the_key", [True, False])
def test_load_gives_a_tracking_id_only_where_strands_owns_the_key(
    temp_dir: str, monkeypatch: pytest.MonkeyPatch, strands_owns_the_key: bool
) -> None:
    monkeypatch.setattr(file_repository, "_STRANDS_OWNS_TRACKING_ID", strands_owns_the_key)

    def entry(message: object) -> dict:
        return {"message": message, "created_at": "2026-01-01T00:00:00+00:00"}

    conversations = {
        MessageSourceType.USER.value: {
            "u1": [
                entry({"role": "user", "content": [{"text": "old"}]}),
                entry(None),  # not a message: left as it is, and the rest still loads
                entry({"role": "assistant", "content": [{"text": "kept"}], "tracking_id": "t-1"}),
            ]
        }
    }
    with open(os.path.join(temp_dir, "conversations.json"), "w", encoding="utf-8") as fh:
        json.dump({"conversations": conversations, "saved_at": "then"}, fh)

    loaded = FileMultiSourceConversationRepository(storage_dir=temp_dir)

    old, not_a_message, kept = (
        stored.message for stored in loaded.conversations[MessageSourceType.USER.value]["u1"]
    )
    assert bool(old.get("tracking_id")) is strands_owns_the_key
    assert not_a_message is None
    assert kept["tracking_id"] == "t-1"


def test_a_repository_that_does_not_implement_the_fold_says_so(mock_agent: Mock) -> None:
    class AppendOnlyRepository(ConversationRepository):
        def add_message_for_agent(self, message: Message, agent: Agent) -> None:
            pass

        def get_conversation_history_for_agent(self, agent: Agent) -> List[Message]:
            return []

        def save(self) -> None:
            pass

        def load(self) -> None:
            pass

    with pytest.raises(NotImplementedError, match="AppendOnlyRepository"):
        AppendOnlyRepository().fold_history_for_agent([], [], mock_agent)
