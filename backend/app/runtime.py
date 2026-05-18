"""
Console / progress-bar tuning for long-running pipeline jobs.

On Windows, a minimized terminal throttles console redraws. VideoDB uses tqdm
during indexing (show_progress=True), which can block the whole pipeline when
the window is minimized. Disable those bars unless explicitly opted in.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def should_disable_tqdm() -> bool:
    """
    Default: disable tqdm (fast & stable on Windows consoles).
    Set CONTINUUM_SHOW_PROGRESS=1 to keep VideoDB progress bars in the terminal.
    """
    if _env_truthy("CONTINUUM_SHOW_PROGRESS"):
        return False
    if _env_truthy("CONTINUUM_DISABLE_TQDM", "1"):
        return True
    # Legacy tqdm env
    return _env_truthy("TQDM_DISABLE")


def bootstrap_runtime() -> None:
    """Call once at process start, before importing videodb."""
    if should_disable_tqdm():
        os.environ["TQDM_DISABLE"] = "1"
    else:
        os.environ.pop("TQDM_DISABLE", None)

    if _env_truthy("CONTINUUM_LOG_TO_FILE"):
        _attach_file_logging()


def _attach_file_logging() -> None:
    root = Path(__file__).resolve().parents[2]
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "backend.log"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    root_logger = logging.getLogger()
    if not any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", "") == str(log_path)
        for h in root_logger.handlers
    ):
        root_logger.addHandler(file_handler)

    # Fewer synchronous console writes (helps minimized terminals).
    if _env_truthy("CONTINUUM_QUIET_CONSOLE", "1" if os.name == "nt" else "0"):
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream in (
                sys.stdout,
                sys.stderr,
            ):
                handler.setLevel(logging.WARNING)

    logger.info("File logging enabled: %s", log_path)
