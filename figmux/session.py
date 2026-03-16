from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from figmux.url_policy import can_restore_url


@dataclass(slots=True)
class SessionTabState:
    id: str
    url: str
    title: str


@dataclass(slots=True)
class SessionState:
    active_tab_id: str | None
    tabs: list[SessionTabState]


def load_session(path: Path) -> SessionState:
    if not path.exists():
        return SessionState(active_tab_id=None, tabs=[])
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return SessionState(active_tab_id=None, tabs=[])

    tabs: list[SessionTabState] = []
    for item in data.get("tabs", []):
        url = item.get("url")
        if not can_restore_url(url):
            continue
        tabs.append(
            SessionTabState(
                id=str(item.get("id") or ""),
                url=url,
                title=str(item.get("title") or "Figma"),
            )
        )

    active_tab_id = data.get("active_tab_id")
    return SessionState(active_tab_id=active_tab_id if isinstance(active_tab_id, str) else None, tabs=tabs)


def save_session(path: Path, state: SessionState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_tab_id": state.active_tab_id,
        "tabs": [asdict(tab) for tab in state.tabs],
    }
    path.write_text(json.dumps(payload, indent=2), "utf-8")
