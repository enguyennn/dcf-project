#!/usr/bin/env python3
"""Retry helpers for transient network-facing subprocess calls."""

import logging
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)


def run_with_retry(
    cmd: list[str], *, max_retries: int = 3, backoff_base: int = 2, **kwargs: Any
) -> subprocess.CompletedProcess:
    """Run subprocess with exponential backoff retry on failure.

    Retries on non-zero exit codes or subprocess.SubprocessError exceptions.
    Raises subprocess.SubprocessError on final failure.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(cmd, **kwargs)
            if result.returncode == 0:
                return result
            last_error = f"Exit code {result.returncode}"
        except subprocess.SubprocessError as exc:
            last_error = str(exc)

        if attempt < max_retries:
            wait = backoff_base ** attempt
            logger.warning(
                "Attempt %s/%s failed (%s), retrying in %ss...",
                attempt + 1,
                max_retries + 1,
                last_error,
                wait,
            )
            time.sleep(wait)

    raise subprocess.SubprocessError(
        f"All {max_retries + 1} attempts failed. Last error: {last_error}"
    )
