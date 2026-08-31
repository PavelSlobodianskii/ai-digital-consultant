from __future__ import annotations

import re

from app.schema import AssessRequest, RubricResult

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "they", "have",
    "been", "will", "would", "could", "should", "into", "about", "there",
    "their", "which", "when", "where", "what", "process", "business",
    "our", "are", "was", "were", "can", "may", "also", "than", "then",
    "each", "other", "more", "some", "such", "only", "just", "very",
}

RULES_PATTERNS = [
    r"\bif\b.+\bthen\b",
    r"\bpolicy\b",
    r"\bthreshold\b",
    r"\bchecklist\b",
    r"\bspreadsheet\b",
    r"\bexcel\b",
    r"\berp\b",
    r"\bsap\b",
    r"\bpurchase order\b",
    r"\binvoice number\b",
    r"\bpo number\b",
    r"\bsla\b",
    r"\brouting rule\b",
    r"\bworkflow\b",
    r"\bmanager approval\b",
    r"\bfixed amount\b",
    r"\bunder \$?\d",
    r"\bover \$?\d",
    r"\bstatus (is|=|equals)\b",
    r"\bform field\b",
    r"\bdropdown\b",
    r"\balways\b",
    r"\bnever allow\b",
    r"\bthree-?way match\b",
    r"\bpurchase-to-pay\b",
    r"\bpassword reset\b",
    r"\baccess request\b",
    r"\bticket categor(y|ies) from a list\b",
]

AI_PATTERNS = [
    r"\bemail(s)?\b",
    r"\binbox\b",
    r"\bfree[- ]text\b",
    r"\bunstructured\b",
    r"\bpdf\b",
    r"\bscan(ned)?\b",
    r"\bimage(s)?\b",
    r"\btranscript\b",
    r"\bconversation(s)?\b",
    r"\bsentiment\b",
    r"\bsummariz(e|ing|ation)\b",
    r"\bambiguous\b",
    r"\bjudgment\b",
    r"\binterpret(ing|ation)?\b",
    r"\bnatural language\b",
    r"\bcontract language\b",
    r"\bhandwritten\b",
    r"\bcall notes\b",
    r"\bintent\b",
    r"\bclassify (tickets|emails|documents)\b",
    r"\bextract(ion)? from (pdf|email|document)\b",
    r"\bvoice of (the )?customer\b",
]

HYBRID_HINTS = [
    r"\bexception(s)?\b",
    r"\bedge case(s)?\b",
    r"\b80/?20\b",
    r"\bmost(ly)? (follow|handled by) (the )?rule",
    r"\bhuman review\b",
    r"\bescalat",
    r"\bclaims?\b",
    r"\bunderwriting\b",
]

DOMAIN_TAGS = {
    "invoice": ("invoice", "accounts payable", "ap clerk", "vendor bill"),
    "procurement": ("purchase order", "procurement", "vendor", "three-way"),
    "support": ("customer support", "ticket", "helpdesk", "inbox"),
    "hr": ("onboarding", "hr ", "human resources", "leave request"),
    "sales": ("crm", "lead", "quote", "sales"),
    "logistics": ("shipment", "warehouse", "logistics", "inventory"),
    "claims": ("claim", "insurance", "adjuster"),
    "it_ops": ("password reset", "access request", "it service"),
    "contracts": ("contract", "clause", "legal review"),
}


def _count_hits(text: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if re.search(p, text, flags=re.I | re.S))


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", (text or "").lower())
    return {w for w in words if w not in STOPWORDS}


def extract_tags(text: str, extra: list[str] | None = None) -> list[str]:
    lowered = (text or "").lower()
    tags: set[str] = set(extra or [])
    for tag, needles in DOMAIN_TAGS.items():
        if any(n in lowered for n in needles):
            tags.add(tag)
    tokens = tokenize(text)
    # Keep distinctive content tokens for lexical overlap.
    for tok in sorted(tokens, key=len, reverse=True)[:24]:
        if len(tok) >= 4:
            tags.add(tok)
    return sorted(tags)


def evaluate_rubric(req: AssessRequest) -> RubricResult:
    text = req.process_text
    rules_hits = _count_hits(text, RULES_PATTERNS)
    ai_hits = _count_hits(text, AI_PATTERNS)
    hybrid_hits = _count_hits(text, HYBRID_HINTS)

    rules_score = min(1.0, rules_hits / 4.0)
    ai_score = min(1.0, ai_hits / 4.0)

    if req.data_shape == "structured":
        rules_score = min(1.0, rules_score + 0.35)
        ai_score = max(0.0, ai_score - 0.15)
    elif req.data_shape == "unstructured":
        ai_score = min(1.0, ai_score + 0.35)
        rules_score = max(0.0, rules_score - 0.1)
    elif req.data_shape == "mixed":
        rules_score = min(1.0, rules_score + 0.15)
        ai_score = min(1.0, ai_score + 0.15)

    if req.judgment_level == "rare":
        rules_score = min(1.0, rules_score + 0.2)
        ai_score = max(0.0, ai_score - 0.1)
    elif req.judgment_level == "frequent":
        ai_score = min(1.0, ai_score + 0.25)
        hybrid_hits += 1

    if hybrid_hits:
        # Exceptions pull both scores toward a mixed pattern.
        rules_score = min(1.0, rules_score + 0.1)
        ai_score = min(1.0, ai_score + 0.1)

    delta = abs(ai_score - rules_score)
    both_low = rules_score < 0.25 and ai_score < 0.25
    both_high = rules_score >= 0.45 and ai_score >= 0.45

    if both_high or hybrid_hits >= 2:
        classification = "hybrid"
        confidence = "clear" if both_high or hybrid_hits >= 2 else "unclear"
    elif both_low:
        classification = "hybrid"
        confidence = "unclear"
    elif rules_score >= ai_score + 0.2:
        classification = "rules"
        confidence = "clear" if delta >= 0.28 and rules_score >= 0.4 else "unclear"
    elif ai_score >= rules_score + 0.2:
        classification = "ai"
        confidence = "clear" if delta >= 0.28 and ai_score >= 0.4 else "unclear"
    else:
        classification = "hybrid"
        confidence = "unclear"

    if classification == "rules" and confidence == "clear":
        confidence = "clear"

    tags = extract_tags(
        " ".join(
            filter(
                None,
                [text, req.industry or "", req.tools_note or "", req.volume_note or ""],
            )
        ),
        extra=[
            classification,
            req.data_shape,
            req.judgment_level,
            *( [req.industry.lower()] if req.industry else [] ),
        ],
    )

    return RubricResult(
        classification=classification,
        confidence=confidence,
        rules_score=round(rules_score, 3),
        ai_score=round(ai_score, 3),
        signals={
            "rules_hits": float(rules_hits),
            "ai_hits": float(ai_hits),
            "hybrid_hits": float(hybrid_hits),
        },
        tags=tags,
        veto_chatbot_for_rules=classification == "rules" and confidence == "clear",
    )


def complexity_band(score_1_to_5: int | float) -> str:
    n = float(score_1_to_5)
    if n <= 2:
        return "Low"
    if n <= 3.5:
        return "Medium"
    return "High"
