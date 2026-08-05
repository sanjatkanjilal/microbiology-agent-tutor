"""
PathophysEpiTool - pathophysiology & epidemiology deep-dive agent.

Ported from V4 src_simplified PathophysEpiAgent into the ToolUniverse pattern.
"""

import logging
from typing import Dict, Any

from microtutor.schemas.tools.tool_models import AgenticTool
from microtutor.schemas.tools.tool_errors import ToolLLMError
from microtutor.core.llm.llm_router import chat_complete
from microtutor.prompts.pathophys_epi_prompts import get_pathophys_epi_system_prompt
from microtutor.utils.csv_guidance import csv_guidance
from microtutor.utils.conversation_utils import prepare_llm_messages

logger = logging.getLogger(__name__)


class PathophysEpiTool(AgenticTool):
    """Runs mechanism-first pathophys / epi teaching for the pathophys_epi module."""

    def _call_llm(self, prompt: str, **kwargs) -> str:
        try:
            model = kwargs.get("model", self.llm_config.get("model", "gpt-5"))
            case = kwargs.get("case", "")
            conversation_history = kwargs.get("conversation_history", [])
            organism = kwargs.get("organism", "")

            csv_guidance_text = csv_guidance.format_factors_for_prompt(organism)
            system_prompt = get_pathophys_epi_system_prompt().format(
                case=case,
                csv_guidance=csv_guidance_text,
            )

            clean_history = (
                conversation_history if isinstance(conversation_history, list) else []
            )
            llm_messages = prepare_llm_messages(clean_history, system_prompt)

            response = chat_complete(
                system_prompt="",
                user_prompt="",
                model=model,
                conversation_history=llm_messages,
            )

            if not response or not response.strip():
                raise ToolLLMError("LLM returned empty response", tool_name=self.name)

            return response

        except ToolLLMError:
            raise
        except Exception as e:
            logger.error("LLM call failed in %s: %s", self.name, e)
            raise ToolLLMError(
                f"Failed to generate pathophys/epi response: {e}",
                tool_name=self.name,
            )

    def _execute(self, arguments: Dict[str, Any]) -> str:
        return self._call_llm(
            "",
            case=arguments.get("case", ""),
            input_text=arguments.get("input_text", ""),
            conversation_history=arguments.get("conversation_history", []),
            model=arguments.get("model", "gpt-5"),
            organism=arguments.get("organism", ""),
        )


def run_pathophys_epi(
    input_text: str,
    case: str,
    conversation_history: list = None,
    model: str = None,
    organism: str = "",
) -> str:
    """Legacy function - use PathophysEpiTool directly instead."""
    from microtutor.tools.registry import get_tool_instance
    from pathlib import Path
    import json

    tool = get_tool_instance("pathophys_epi")

    if not tool:
        logger.warning("Pathophys epi tool not registered, loading config manually")
        config_path = Path(__file__).parent / "pathophys_epi_tool.json"
        if not config_path.exists():
            raise RuntimeError("Pathophys epi tool not available and config not found")
        with open(config_path) as f:
            config = json.load(f)
        tool = PathophysEpiTool(config)

    result = tool.run(
        {
            "input_text": input_text,
            "case": case,
            "conversation_history": conversation_history or [],
            "model": model or "gpt-5",
            "organism": organism or "",
        }
    )

    if result["success"]:
        return result["result"]
    raise RuntimeError(
        f"Pathophys epi tool failed: {result.get('error', {}).get('message', 'Unknown error')}"
    )
