"""Personality: brand voice under a code-checked fact lock (numbers and URLs equal both ways)."""

import re

from getnet_multi_agent.agents.prompts.personality import SYSTEM
from getnet_multi_agent.core.llm import BudgetExceeded, LLMClient, LLMUnavailable

LANG = {"en": "English", "pt": "Brazilian Portuguese"}
_URL = re.compile(r"https?://[^\s)>\]]+")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def facts(text: str) -> tuple[set[str], set[str]]:
    urls = {u.rstrip(".,;") for u in _URL.findall(text)}
    numbers = {n for n in _NUM.findall(_URL.sub(" ", text))}
    return numbers, urls


def fact_lock_ok(draft: str, styled: str) -> bool:
    return facts(draft) == facts(styled)


def personality(draft: str, lang: str, llm: LLMClient) -> tuple[str, list, str]:
    """Returns (text, usages, note). On violation or failure the draft is returned unchanged."""
    try:
        res = llm.generate("personality", f"<draft>\n{draft}\n</draft>",
                           system=SYSTEM.format(language=LANG.get(lang, "English")))
    except (LLMUnavailable, BudgetExceeded) as e:
        return draft, [], f"personality skipped: {type(e).__name__}"
    styled = res.text.strip()
    if not styled or not fact_lock_ok(draft, styled):
        return draft, [res.usage], "personality rejected by fact lock; draft returned"
    return styled, [res.usage], "personality applied"
