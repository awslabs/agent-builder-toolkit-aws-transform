# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging


def configure_logging(level: int | str = logging.INFO) -> None:
    """Configure progress logging for the `harness_evolver` package.

    Idempotent: re-calls update the level but don't add duplicate handlers.
    Only attaches a handler to the package root logger; doesn't touch the
    global root logger, so it won't fight with anyone else's logging setup.
    """
    logger = logging.getLogger("harness_evolver")
    logger.setLevel(level)
    if not any(getattr(h, "_harness_evolver", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
        )
        handler._harness_evolver = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.propagate = False
