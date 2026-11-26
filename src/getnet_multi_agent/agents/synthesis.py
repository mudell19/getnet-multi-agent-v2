"""Synthesis of several step answers, and the rolling conversation summary."""

from getnet_multi_agent.agents.prompts.summary import SYSTEM as SUMMARY_SYSTEM
from getnet_multi_agent.agents.prompts.synthesis import SYSTEM
from getnet_multi_agent.contracts import Observation
from getnet_multi_agent.core.llm import LLMClient
from getnet_multi_agent.merchants import today_brt

LANG = {"en": "English", "pt": "Brazilian Portuguese"}


def synthesize(message: str, observations: list[Observation], lang: str, llm: LLMClient):
    body = f"<user_message>\n{message}\n</user_message>\n" + "\n".join(
        f'<agent_answer step="{o.step_id}" agent="{o.agent}">\n{o.answer}\n</agent_answer>'
        for o in observations)
    res = llm.generate("synthesis", body, system=SYSTEM.format(
        today=today_brt().isoformat(), language=LANG.get(lang, "English")))
    text = res.text.strip()
    if not text:  # never lose answered parts
        text = "\n\n".join(o.answer for o in observations)
    return text, res.usage


def summarize(previous: str, turns: list[dict], llm: LLMClient) -> str:
    convo = "\n".join(f"{t['role']}: {t['text'][:800]}" for t in turns)
    res = llm.generate("summary", f"<previous_summary>\n{previous or '(none)'}\n</previous_summary>\n"
                       f"<new_turns>\n{convo}\n</new_turns>",
                       system=SUMMARY_SYSTEM.format(today=today_brt().isoformat()))
    return res.text.strip()
