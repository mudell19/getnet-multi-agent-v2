"""Input guardrails (pre-LLM) and PII masking helpers."""

import re

from getnet_multi_agent.contracts import Lang, Refusal, RefusalReason

_CARD_RE = re.compile(r"(?<!\d)\d(?:[ .-]?\d){12,18}(?!\d)")
_CPF_RE = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_MERCHANT_RE = re.compile(r"cliente\d+", re.IGNORECASE)
_INJECTION = [re.compile(p, re.IGNORECASE) for p in (
    r"ignore\s+(all|your|previous|the)\b.{0,30}instructions",
    r"disregard\s+(the\s+)?(above|previous|all)",
    r"\byou\s+are\s+now\b",
    r"\bact\s+as\b",
    r"system\s+prompt",
    r"reveal\s+your\s+(prompt|instructions)",
    r"developer\s+mode",
    r"jailbreak",
    r"ignor[ea]\s+(as|suas|todas\s+as|minhas|essas)\s+(suas\s+)?instru[çc][õo]es",
    r"esque[çc]a\s+(as|suas|todas\s+as)\s+(suas\s+)?instru[çc][õo]es",
    r"\bfinja\s+que\b",
    r"revele\s+(o|seu|o\s+seu)\s+prompt",
    r"modo\s+desenvolvedor",
    r"a\s+partir\s+de\s+agora\s+voc[êe]\s+[ée]",
)]
_PT_WORDS = {
    "você", "voce", "não", "nao", "minha", "meu", "quando", "como", "qual", "para", "vendas",
    "maquininha", "obrigado", "obrigada", "olá", "uma", "com", "por", "que", "preciso",
}
_PT_ACCENTS = re.compile(r"[ãõçáéíóúâê]", re.IGNORECASE)

_MESSAGES: dict[str, dict[str, str]] = {
    "too_long": {
        "en": "Your message is too long. Please shorten it and send it again.",
        "pt": "Sua mensagem é muito longa. Por favor, resuma e envie novamente.",
    },
    "sensitive_data": {
        "en": "For your security, please do not share card numbers or CPF in the chat. "
              "Remove them and ask again.",
        "pt": "Para sua segurança, não compartilhe números de cartão ou CPF no chat. "
              "Remova esses dados e pergunte novamente.",
    },
    "other_merchant": {
        "en": "I can only help with your own account. I cannot share information about "
              "other merchants.",
        "pt": "Só posso ajudar com a sua própria conta. Não posso compartilhar informações "
              "de outros lojistas.",
    },
    "prompt_injection": {
        "en": "I cannot follow that request. I can help with questions about Getnet "
              "products, your sales and your terminals.",
        "pt": "Não posso atender a esse pedido. Posso ajudar com dúvidas sobre produtos "
              "Getnet, suas vendas e suas maquininhas.",
    },
    "unsafe": {
        "en": "Sorry, I cannot help with that request.",
        "pt": "Desculpe, não posso ajudar com esse pedido.",
    },
    "out_of_scope": {
        "en": "I can only help with Getnet products, your sales and your terminals.",
        "pt": "Só posso ajudar com produtos Getnet, suas vendas e suas maquininhas.",
    },
}


def refusal_message(reason: RefusalReason | str, lang: Lang | str) -> str:
    return _MESSAGES[reason]["pt" if lang == "pt" else "en"]


def detect_lang(text: str) -> Lang:
    if _PT_ACCENTS.search(text):
        return "pt"
    words = set(re.findall(r"\w+", text.lower()))
    return "pt" if words & _PT_WORDS else "en"


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _valid_card(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    return digits if 13 <= len(digits) <= 19 and _luhn(digits) else None


def _valid_cpf(raw: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", raw)]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        check = (sum(d[i] * (n + 1 - i) for i in range(n)) * 10 % 11) % 10
        if d[n] != check:
            return False
    return True


def mask(text: str) -> str:
    def card(m: re.Match) -> str:
        digits = _valid_card(m.group())
        return f"[CARD ****{digits[-4:]}]" if digits else m.group()

    text = _CARD_RE.sub(card, text)
    return _CPF_RE.sub(lambda m: "[CPF]" if _valid_cpf(m.group()) else m.group(), text)


def _has_sensitive(text: str) -> bool:
    return mask(text) != text


def check(message: str, principal_sub: str, settings) -> Refusal | None:
    def refuse(reason: RefusalReason) -> Refusal:
        lang = detect_lang(message)
        return Refusal(reason=reason, message=refusal_message(reason, lang), lang=lang)

    if len(message) > settings.MAX_MESSAGE_CHARS:
        return refuse("too_long")
    if _has_sensitive(message):
        return refuse("sensitive_data")
    own = principal_sub.lower()
    if any(m.group().lower() != own for m in _MERCHANT_RE.finditer(message)):
        return refuse("other_merchant")
    if any(p.search(message) for p in _INJECTION):
        return refuse("prompt_injection")
    return None
