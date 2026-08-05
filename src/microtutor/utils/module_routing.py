"""Hard route: frontend module id → backend agent tool name.

Matches V4 src_simplified module→agent mapping (Ask Docent uses route_to=tutor).
"""

from __future__ import annotations

import re
from typing import Optional

# UI module id → registered tool name
MODULE_AGENT_MAP: dict[str, str] = {
    "history_taking": "patient",
    "differential_diagnosis": "socratic",  # V4: ddx_deep_dive → DdxAgent
    "management": "tests_management",  # V4: tx_deep_dive → TxAgent
    "pathophys_epi": "pathophys_epi",  # V4: pathophys_epi → PathophysEpiAgent
}

# Friendly labels (DocentID + V4) → module id
MODULE_LABEL_TO_ID: dict[str, str] = {
    "history taking": "history_taking",
    "history": "history_taking",
    "differential diagnosis": "differential_diagnosis",
    "ddx deep dive": "differential_diagnosis",
    "differential diagnosis deep dive": "differential_diagnosis",
    "ddx": "differential_diagnosis",
    "management": "management",
    "management deep dive": "management",
    "tx deep dive": "management",
    "treatment": "management",
    "pathophys & epidemiology": "pathophys_epi",
    "pathophys and epidemiology": "pathophys_epi",
    "pathophys epi": "pathophys_epi",
    "pathophys & epi": "pathophys_epi",
    "pathophys and epi": "pathophys_epi",
    "pathophysiology": "pathophys_epi",
    "pathophys": "pathophys_epi",
}

MODULE_KICKOFF_TEACHING = (
    "This is the start of the module. Introduce the case briefly "
    "(the student can see case context) and give your first teaching question."
)

MODULE_KICKOFF_HISTORY = (
    "The student just switched to the History Taking module. "
    "Continue the bedside encounter in character (patient/family/nurse as appropriate). "
    "Invite them to continue gathering history, exam, or investigations."
)


def module_agent_for(active_module: Optional[str]) -> Optional[str]:
    if not active_module:
        return None
    return MODULE_AGENT_MAP.get(active_module.strip())


def parse_module_transition(message: Optional[str]) -> Optional[str]:
    """Parse V4-style 'Let's move onto module/phase: …' (and light skip phrasing)."""
    if not message:
        return None
    text = message.strip().lower()

    cmd_match = re.search(r"let'?s move onto (?:phase|module):\s*(.+)$", text)
    if cmd_match:
        label = re.sub(r"\s+", " ", cmd_match.group(1)).strip()
        # Strip trailing punctuation
        label = label.rstrip(".!?")
        return MODULE_LABEL_TO_ID.get(label)

    skip_match = re.search(
        r"\b(?:skip|jump|move|start|switch)\s+(?:ahead\s+)?(?:to|into)?\s*"
        r"(history taking|differential diagnosis(?: deep dive)?|ddx deep dive|"
        r"management(?: deep dive)?|tx deep dive|treatment|"
        r"pathophys(?:iology)?(?:\s*(?:&|and)\s*(?:epi|epidemiology))?)\b",
        text,
    )
    if skip_match:
        label = re.sub(r"\s+", " ", skip_match.group(1)).strip().replace("&", "and")
        return MODULE_LABEL_TO_ID.get(label)
    return None


def kickoff_message_for_module(module_id: str) -> str:
    if module_id == "history_taking":
        return MODULE_KICKOFF_HISTORY
    return MODULE_KICKOFF_TEACHING
