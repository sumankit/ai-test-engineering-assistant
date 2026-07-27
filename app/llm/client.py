"""
LLM client factory.

LLM_PROVIDER=groq   -> ChatGroq (needs GROQ_API_KEY)
LLM_PROVIDER=gemini -> ChatGoogleGenerativeAI (needs GEMINI_API_KEY)
LLM_PROVIDER=mock   -> None (agents fall back to deterministic generation,
                        see agents/nodes.py). This is the default so the
                        whole pipeline -- upload, parse, 9 agents,
                        validation, export, Mongo/Supabase persistence --
                        is runnable and demoable with zero API keys. Real
                        model reasoning is a `.env` edit away.
"""
from __future__ import annotations
import logging
from functools import lru_cache
from app.config import settings

logger = logging.getLogger(__name__)

_JSON_REPAIR_HINT = (
    "\n\nYour previous response could not be parsed as JSON. Reply again with "
    "ONLY the corrected JSON — no markdown fences, no commentary, no trailing text."
)


@lru_cache(maxsize=1)
def get_llm():
    if settings.LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=settings.GROQ_MODEL, api_key=settings.GROQ_API_KEY, temperature=0.2)

    if settings.LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=settings.GEMINI_MODEL,
                                       google_api_key=settings.GEMINI_API_KEY, temperature=0.2)

    return None  # mock mode


def run_tool_calling_agent(system_prompt: str, user_prompt: str, tools: list, max_tool_hops: int = 3) -> str:
    """
    Shared helper for the agents that reason WITH tools (Requirement
    Analyzer, Boundary & Negative, Coverage & Priority). Binds `tools`
    to the LLM, executes any tool calls it makes, feeds results back,
    and returns the final text content. Kept generic/reusable rather
    than duplicated per agent.
    """
    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

    llm = get_llm()
    if llm is None:
        raise RuntimeError("run_tool_calling_agent called in mock mode; caller should branch earlier")

    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    for hop in range(max_tool_hops):
        logger.info("run_tool_calling_agent: LLM call start (hop %d/%d)", hop + 1, max_tool_hops)
        ai_msg = llm_with_tools.invoke(messages)
        logger.info("run_tool_calling_agent: LLM call end (hop %d/%d)", hop + 1, max_tool_hops)
        messages.append(ai_msg)
        if not getattr(ai_msg, "tool_calls", None):
            return ai_msg.content
        for call in ai_msg.tool_calls:
            tool_fn = tool_map.get(call["name"])
            result = tool_fn.invoke(call["args"]) if tool_fn else f"Unknown tool {call['name']}"
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    logger.info("run_tool_calling_agent: LLM call start (final)")
    final = llm_with_tools.invoke(messages)
    logger.info("run_tool_calling_agent: LLM call end (final)")
    return final.content


def invoke_json(system_prompt: str, user_prompt: str, default, max_retries: int = 1):
    """
    Shared helper for agents that call the LLM directly (no tools) and expect
    a JSON-parseable response: ScenarioGenerator, TestCaseGenerator, EdgeCase,
    AcceptanceCriteria.

    Retry/repair logic: if the first response doesn't parse as JSON, send ONE
    follow-up turn asking the model to correct its own output before giving
    up and returning ``default``. This turns "malformed JSON from the LLM"
    from a silent data-loss event into a recoverable one, while still
    guaranteeing the agent (and the graph) never crashes — a parse failure
    after retries just falls back to ``default``, same as before.

    Kept generic/reusable rather than duplicated per agent, mirroring
    ``run_tool_calling_agent`` above.
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.agents.base import parse_json

    llm = get_llm()
    if llm is None:
        raise RuntimeError("invoke_json called in mock mode; caller should branch earlier")

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    _SENTINEL = object()

    for attempt in range(max_retries + 1):
        logger.info("invoke_json: LLM call start (attempt %d/%d)", attempt + 1, max_retries + 1)
        resp = llm.invoke(messages)
        logger.info("invoke_json: LLM call end (attempt %d/%d)", attempt + 1, max_retries + 1)
        parsed = parse_json(resp.content, _SENTINEL)
        if parsed is not _SENTINEL:
            return parsed

        logger.warning("invoke_json: malformed JSON on attempt %d/%d", attempt + 1, max_retries + 1)
        if attempt < max_retries:
            messages.append(resp)
            messages.append(HumanMessage(content=_JSON_REPAIR_HINT))

    logger.error("invoke_json: giving up after %d attempts, returning default", max_retries + 1)
    return default
