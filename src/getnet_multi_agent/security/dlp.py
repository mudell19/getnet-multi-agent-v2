"""Output DLP: mask card/CPF and other merchants' ids in answers, logs and stored data."""

import re
from typing import Any

from getnet_multi_agent.security.guardrails import mask

_MERCHANT_RE = re.compile(r"cliente\d+", re.IGNORECASE)


def dlp_check(answer: str, principal_sub: str) -> str:
    own = principal_sub.lower()
    answer = _MERCHANT_RE.sub(
        lambda m: m.group() if m.group().lower() == own else "[MERCHANT]", answer
    )
    return mask(answer)


def mask_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(mask_obj(v) for v in obj)
    return obj
