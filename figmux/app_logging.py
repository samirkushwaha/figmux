from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "payload", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_logging() -> logging.Logger:
    level_name = os.environ.get("FIGMUX_LOG_LEVEL", "info").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger("figmux")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
    return root


def get_logger(name: str) -> logging.LoggerAdapter[logging.Logger]:
    logger = logging.getLogger(f"figmux.{name}")
    return logging.LoggerAdapter(logger, {})


def log_event(logger: logging.LoggerAdapter[logging.Logger], message: str, **payload: Any) -> None:
    logger.log(logging.INFO, message, extra={"payload": payload})
