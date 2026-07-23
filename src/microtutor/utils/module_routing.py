"""Hard route: frontend module id → backend agent tool name."""

from __future__ import annotations

from typing import Optional

# Expand as Docent modules gain dedicated hard routes (simplified-style).
MODULE_AGENT_MAP: dict[str, str] = {
    "history_taking": "patient",
}


def module_agent_for(active_module: Optional[str]) -> Optional[str]:
    if not active_module:
        return None
    return MODULE_AGENT_MAP.get(active_module.strip())
