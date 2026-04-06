"""
CCAP Analyzer - Agent Structureur.
Lexigency - 2026

Extrait la table des matières structurée d'un CCAP.
Utilise un modèle LÉGER (GPT-4o-mini) car c'est de l'extraction
de structure, pas du raisonnement juridique.
"""

import re
import logging

from services.llm_client import call_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un parser de documents juridiques français.
Tu extrais la structure hiérarchique des documents de marchés publics.
Tu retournes UNIQUEMENT du JSON valide, sans texte avant ou après."""

USER_PROMPT = """Analyse ce document et extrais sa structure complète.

Pour chaque section/article, retourne :
- numero : le numéro (Article 1, I, 1.1, etc.)
- titre : le titre de la section
- start_char : position approximative du début (en nombre de caractères depuis le début)
- end_char : position approximative de fin

DOCUMENT :
{document_text}

Réponds UNIQUEMENT en JSON :
{{
    "type_document": "CCAP|CCTP|CCAG|autre",
    "sections": [
        {{
            "numero": "Article 1",
            "titre": "Objet du marché",
            "start_char": 0,
            "end_char": 1500
        }}
    ]
}}"""


def extract_structure(document_text: str) -> dict:
    """
    Extrait la structure d'un document CCAP.

    Returns:
        {
            "success": True/False,
            "type_document": "CCAP",
            "sections": [{"numero": "...", "titre": "...", "start_char": N, "end_char": N}]
        }
    """
    max_chars = 60000
    truncated = document_text[:max_chars]
    if len(document_text) > max_chars:
        truncated += "\n\n[... document tronqué pour extraction de structure ...]"

    prompt = USER_PROMPT.format(document_text=truncated)

    result = call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        model_role="light",
        max_tokens=4000,
        temperature=0.1,
    )

    if not result["success"]:
        logger.warning("LLM structureur échoué, fallback regex")
        return extract_structure_regex(document_text)

    sections = result.get("sections", [])
    sections = _validate_sections(sections, document_text)

    if not sections:
        logger.warning("LLM n'a retourné aucune section, fallback regex")
        return extract_structure_regex(document_text)

    return {
        "success": True,
        "type_document": result.get("type_document", "CCAP"),
        "sections": sections,
    }


def extract_structure_regex(text: str) -> dict:
    """Fallback : extraction de structure par regex."""
    patterns = [
        (r"(?:ARTICLE|Article)\s+(\d+(?:\.\d+)?)\s*[-–:\.]\s*([^\n]+)"),
        (r"^((?:I{1,3}|IV|VI{0,3}|IX|X{0,3}))\s*[-–:\.]\s*([^\n]+)"),
        (r"^(\d+(?:\.\d+)?)\s*[-–:\.]\s*([A-Z][^\n]+)"),
    ]

    sections = []
    for pattern in patterns:
        matches = list(re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE))
        if len(matches) >= 3:
            for i, match in enumerate(matches):
                start = match.start()
                end = (
                    matches[i + 1].start()
                    if i + 1 < len(matches)
                    else len(text)
                )
                sections.append(
                    {
                        "numero": match.group(1).strip(),
                        "titre": match.group(2).strip(),
                        "start_char": start,
                        "end_char": end,
                    }
                )
            break

    if not sections:
        chunk_size = 3000
        for i in range(0, len(text), chunk_size):
            sections.append(
                {
                    "numero": f"Bloc {i // chunk_size + 1}",
                    "titre": f"Partie {i // chunk_size + 1}",
                    "start_char": i,
                    "end_char": min(i + chunk_size, len(text)),
                }
            )

    return {
        "success": True,
        "type_document": "CCAP",
        "sections": sections,
    }


def _validate_sections(sections: list, full_text: str) -> list:
    """Valide et corrige les positions start_char/end_char."""
    text_len = len(full_text)
    validated = []

    for section in sections:
        numero = section.get("numero", "")
        titre = section.get("titre", "")
        start = section.get("start_char", 0)
        end = section.get("end_char", text_len)

        start = max(0, min(start, text_len))
        end = max(start + 1, min(end, text_len))

        if titre:
            idx = full_text.find(titre)
            if idx == -1:
                words = titre.split()[:4]
                search = " ".join(words)
                idx = full_text.lower().find(search.lower())
            if idx >= 0:
                start = idx

        validated.append(
            {
                "numero": numero,
                "titre": titre,
                "start_char": start,
                "end_char": end,
            }
        )

    for i in range(len(validated) - 1):
        validated[i]["end_char"] = validated[i + 1]["start_char"]
    if validated:
        validated[-1]["end_char"] = text_len

    return validated
