__all__ = ("HitlNotifier",)

import asyncio
import logging
from collections import defaultdict
from functools import partial

from agent_builder_sdk.custom_types.notification_types import (
    HitlTaskStatus,
    HitlTaskStatusChangeDetail,
)

Future = asyncio.Future[HitlTaskStatusChangeDetail]

log = logging.getLogger(__name__)


class HitlNotifier:
    """Manage notifications about HITL (Human-In-The-Loop) task status changes."""

    def __init__(self):
        self._futures: defaultdict[HitlTaskStatus, dict[str, Future]] = defaultdict(dict)

    async def wait(self, hitl_task_id: str, status: HitlTaskStatus) -> HitlTaskStatusChangeDetail:
        """Wait for a HITL task to be a certain status."""
        if hitl_task_id in self._futures[status]:
            raise ValueError(f"A waiter for {status} HITL {hitl_task_id} already exists")

        future: Future = asyncio.Future()
        future.add_done_callback(partial(self._future_done_callback, hitl_task_id, status))
        self._futures[status][hitl_task_id] = future

        log.debug("Waiting on future for HITL %s", hitl_task_id)
        return await future

    def notify(self, notification: HitlTaskStatusChangeDetail) -> bool:
        """Notify the waiter, if any, that a HITL task's status has changed.

        Return true if there is a waiter for the task ID with the new status.
        """
        id_ = notification.hitl_task_id
        status = notification.new_status

        if future := self._futures[status].get(id_):
            log.debug("Setting result for future for %s HITL %s", status, id_)
            try:
                future.set_result(notification)
            except asyncio.InvalidStateError:
                log.debug("Cannot set result for %s HITL %s: future is already done", status, id_)

            return True
        else:
            log.debug("No future found for %s HITL %s in %s", status, id_, self._futures)
            return False

    def _future_done_callback(self, hitl_task_id: str, status: HitlTaskStatus, _: Future) -> None:
        log.debug("Removing done future for %s HITL %s", status, hitl_task_id)
        self._futures[status].pop(hitl_task_id)
