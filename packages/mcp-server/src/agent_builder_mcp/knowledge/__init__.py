# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Knowledge base router - uses lite by default, full if available."""

import os

USE_FULL = os.getenv("ATX_DEV_FULL", "0") == "1"

if USE_FULL:
    try:
        from ._full import get_hybrid_retriever as get_hybrid_retriever  # noqa: F401
        from ._full import get_index as get_index  # noqa: F401
        from ._full import setup_kb as setup_kb  # noqa: F401

        def get_documents():
            raise NotImplementedError("Use get_hybrid_retriever() with full mode")

        LITE_MODE = False
    except ImportError:
        USE_FULL = False

if not USE_FULL:
    from ._lite import get_documents as get_documents  # noqa: F401,F811
    from ._lite import setup_kb as setup_kb  # noqa: F401,F811

    LITE_MODE = True
