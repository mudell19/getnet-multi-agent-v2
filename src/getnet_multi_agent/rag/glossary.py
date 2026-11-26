"""Alias groups (accent- and case-insensitive) that bridge pt/en vocabulary."""

import re
import unicodedata

GROUPS: list[tuple[str, ...]] = [
    ("get clássica", "get classica", "get classic"),
    ("get smart",),
    ("link de pagamento", "payment link", "link get pay"),
    ("antecipação", "antecipacao", "receivables advance", "advance", "antecipar",
     "antecipação de vendas"),
    ("crediário", "crediario", "parcelas", "parcelamento", "installments", "installment"),
    ("pix",),
    ("conta bancária", "conta bancaria", "bank account", "conta de recebimento",
     "domicílio bancário", "conta digital", "get conta"),
    ("internet", "connection", "conexão", "conexao", "chip", "teste de comunicação",
     "teste de comunicacao", "wi-fi", "wifi", "sinal"),
    ("whatsapp", "rede social", "redes sociais", "social media", "social network"),
]


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


_PATTERNS = [
    re.compile(r"(?<!\w)(?:" + "|".join(re.escape(_fold(a)) for a in g) + r")(?!\w)")
    for g in GROUPS
]


def matched_groups(text: str) -> set[int]:
    folded = _fold(text)
    return {i for i, p in enumerate(_PATTERNS) if p.search(folded)}


def expand(query: str) -> str:
    extra = [a for i in sorted(matched_groups(query)) for a in GROUPS[i]]
    return " ".join([query, *extra])
