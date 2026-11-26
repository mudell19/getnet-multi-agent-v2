"""Stable pseudonym of a merchant id for logs and metrics."""

import hashlib
import hmac


def pseudonym(sub: str, settings) -> str:
    key = settings.PSEUDONYM_KEY.get_secret_value().encode()
    return hmac.new(key, sub.encode(), hashlib.sha256).hexdigest()[:16]
