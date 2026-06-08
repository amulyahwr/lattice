"""Round-trip PII redaction for cloud LLM paths.

Flow: redact(text) → send redacted text to cloud LLM → restore(response) → real names back.
Atoms on disk always contain real values. Names never leave the machine in plaintext.

Active when: LLM_PROVIDER != "ollama" AND LATTICE_PII_SCRUB != "0"/"false".
Ollama path: skip entirely — data stays local.

NER path (LATTICE_NER_MODEL set): Ollama NER model identifies persons + orgs for consistent
cross-segment entity numbering. Regex-only path (default): emails + phones only.
"""
from __future__ import annotations

import json
import os
import re

_SCRUB_ACTIVE = os.environ.get("LATTICE_PII_SCRUB", "true").lower() not in ("0", "false", "no")
_NER_MODEL = os.environ.get("LATTICE_NER_MODEL", "")

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b")

_NER_SYSTEM = (
    "Extract all person names and organization names from the text. "
    'Return JSON with exactly two keys: "persons" (list of full person names) '
    'and "orgs" (list of organization names). '
    "Return empty lists if none found. Never extract dates, locations, or numbers."
)


def is_active() -> bool:
    """True when PII scrubbing should run on this call."""
    if not _SCRUB_ACTIVE:
        return False
    return os.environ.get("LLM_PROVIDER", "ollama") != "ollama"


def _apply_replacements(text: str, replacements: dict[str, str]) -> str:
    """Replace originals with tags; longest-first to avoid partial-name collisions."""
    for original in sorted(replacements, key=len, reverse=True):
        text = text.replace(original, replacements[original])
    return text


class EntityRedactor:
    """Stateless redactor — all state lives in the returned entity_map."""

    def redact_batch(self, texts: list[str]) -> tuple[list[str], dict[str, str]]:
        """Redact PII across multiple texts using one shared entity_map.

        Returns (redacted_texts, entity_map). entity_map maps tag → original for restore.
        No-op when not active.
        """
        if not is_active() or not texts:
            return texts, {}

        # replacements: original → tag  (for substitution)
        # entity_map:   tag → original  (for restore)
        replacements: dict[str, str] = {}
        entity_map: dict[str, str] = {}
        counter: dict[str, int] = {}

        def _add(prefix: str, original: str) -> None:
            if not original.strip() or original in replacements:
                return
            tag = f"{prefix}_{counter.get(prefix, 0)}"
            counter[prefix] = counter.get(prefix, 0) + 1
            replacements[original] = tag
            entity_map[tag] = original

        # NER pass: one LLM call across all texts → consistent numbering
        if _NER_MODEL:
            combined = "\n\n---\n\n".join(t[:4000] for t in texts)
            ner = self._run_ner(combined)
            for name in ner.get("persons", []):
                _add("PER", name.strip())
            for name in ner.get("orgs", []):
                _add("ORG", name.strip())

        # Regex pass: emails + phones across all texts
        all_text = "\n".join(texts)
        for m in _EMAIL_RE.finditer(all_text):
            _add("EMAIL", m.group(0))
        for m in _PHONE_RE.finditer(all_text):
            val = m.group(0).strip()
            if len(re.sub(r"\D", "", val)) >= 10:
                _add("PHONE", val)

        if not replacements:
            return texts, {}

        return [_apply_replacements(t, replacements) for t in texts], entity_map

    def redact(self, text: str) -> tuple[str, dict[str, str]]:
        texts, entity_map = self.redact_batch([text])
        return texts[0], entity_map

    def restore(self, text: str, entity_map: dict[str, str]) -> str:
        if not entity_map:
            return text
        for tag, original in entity_map.items():
            text = text.replace(tag, original)
        return text

    def _run_ner(self, text: str) -> dict:
        try:
            from lattice.llm import make_llm_client
            client = make_llm_client(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )
            resp = client.chat.completions.create(
                model=_NER_MODEL,
                messages=[
                    {"role": "system", "content": _NER_SYSTEM},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
                extra_body={"num_ctx": 4096, "think": False},
            )
            return json.loads(resp.choices[0].message.content or "{}")
        except Exception:
            return {}
