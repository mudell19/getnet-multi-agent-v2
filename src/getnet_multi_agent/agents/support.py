"""Customer Support agent: function-calling loop over the two tools."""

from datetime import timedelta

from getnet_multi_agent.agents.prompts.support import SYSTEM
from getnet_multi_agent.agents.tools import TOOL_SPECS, run_tool
from getnet_multi_agent.contracts import Observation, Principal, Step
from getnet_multi_agent.core.llm import LLMClient, Message
from getnet_multi_agent.merchants import today_brt

LANG = {"en": "English", "pt": "Brazilian Portuguese"}


def system_prompt(lang: str) -> str:
    t = today_brt()
    return SYSTEM.format(today=t.isoformat(), yesterday=(t - timedelta(days=1)).isoformat(),
                         language=LANG.get(lang, "English"))


def support(step: Step, principal: Principal, lang: str, llm: LLMClient, settings) -> Observation:
    messages = [Message(role="user", text=step.query)]
    data: dict = {}
    usage = []
    answer = ""
    for i in range(settings.MAX_TOOL_ITERATIONS + 1):
        tools = TOOL_SPECS if i < settings.MAX_TOOL_ITERATIONS else None
        res = llm.generate("support", messages, tools=tools, system=system_prompt(lang))
        usage.append(res.usage)
        if not res.function_calls:
            answer = res.text.strip()
            break
        messages.append(res.as_message())  # whole model content: keeps thought signatures
        for fc in res.function_calls:
            result = run_tool(fc.name, fc.args, settings.data_path, principal.sub)
            data[fc.name] = result
            messages.append(Message(role="tool", tool_name=fc.name,
                                    tool_response={"untrusted_data": result}))
    not_found = any(isinstance(v, dict) and v.get("merchant_found") is False for v in data.values())
    status = "answered" if answer else "failed"
    return Observation(step_id=step.id, agent="support", status=status, answer=answer, data=data,
                       usage=usage, unanswered=[] if answer else [step.query],
                       error=None if answer else "no answer after tool loop",
                       evidence=[] if not not_found else [])
