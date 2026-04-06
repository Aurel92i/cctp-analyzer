"""
CCTP Analyzer V2 - Agent Auditeur.
Chardonnet Conseil - 2026

Analyse une clause individuelle en la comparant aux articles pertinents
du Code CCP et du CCAG (fournis par le RAG).

Utilise le MEILLEUR modèle disponible (GPT-4o / Claude Opus) car c'est
le cœur du raisonnement juridique.

Chaque appel ne reçoit que ~10-15k tokens de contexte
(la clause + les 5-10 articles pertinents), pas les documents entiers.
"""

import logging

from services.llm_client import call_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un expert juridique senior en marchés publics français, spécialisé dans l'audit de conformité des documents contractuels.

Tu analyses une clause spécifique d'un document client (CCAP ou CCTP) en la comparant aux articles pertinents du CCAG et du Code de la Commande Publique qui te sont fournis.

RÈGLES ABSOLUES :
1. Ne cite QUE des articles qui sont EFFECTIVEMENT dans le contexte fourni. Ne JAMAIS inventer de référence.
2. L'extrait_texte doit être une copie EXACTE et LONGUE (30-100 mots) du passage du document client. C'est CRITIQUE pour le retrouver ensuite dans le fichier Word.
3. Chaque remarque doit avoir une base juridique solide, pas juste une opinion.
4. Classe la gravité avec rigueur : "haute" = illégal ou bloquant pour le marché, "moyenne" = risque juridique concret, "basse" = amélioration recommandée.
5. Si la clause est conforme, dis-le explicitement : ne force pas des remarques là où il n'y en a pas.

Tu retournes UNIQUEMENT du JSON valide."""

USER_PROMPT_TEMPLATE = """## CONTEXTE
- Domaine : {domaine} ({domaine_label})
- Document analysé : {type_document}
- Section : {section_numero} - {section_titre}

## ARTICLES DU CODE DE LA COMMANDE PUBLIQUE (pertinents)
{code_ccp_extracts}

## ARTICLES DU CCAG-{domaine_label} (pertinents)
{ccag_extracts}

## CLAUSE À ANALYSER
{clause_text}

---

MISSION : Audite cette clause. Identifie :
1. Non-conformités au CCAG (dérogations non justifiées, contradictions)
2. Violations du Code de la Commande Publique (clauses illégales)
3. Clauses abusives ou déséquilibrées
4. Imprécisions juridiques créant un risque
5. Clauses manquantes obligatoires dans cette section

FORMAT JSON :
{{
    "section_analysee": "{section_numero} - {section_titre}",
    "conformite_globale": "conforme|non-conforme|partiellement-conforme",
    "remarques": [
        {{
            "extrait_texte": "COPIE EXACTE ET LONGUE (30-100 mots) du passage problématique, mot pour mot tel qu'il apparaît dans le document",
            "constat": "Description factuelle du problème",
            "probleme": "Explication du risque juridique concret",
            "references_juridiques": "Article X CCAG, Article L.XXXX-X CCP (UNIQUEMENT ceux du contexte fourni)",
            "recommandation": "Correction précise à apporter",
            "gravite": "haute|moyenne|basse"
        }}
    ]
}}

Si aucun problème n'est détecté, retourne un JSON avec "remarques": [] et "conformite_globale": "conforme"."""


def audit_clause(
    clause_text: str,
    section_numero: str,
    section_titre: str,
    code_ccp_extracts: str,
    ccag_extracts: str,
    domaine: str,
    domaine_label: str,
    type_document: str = "CCAP/CCTP",
) -> dict:
    """
    Audite une clause individuelle.

    Returns:
        {
            "success": True/False,
            "section_analysee": "Article 4 - Pièces du marché",
            "conformite_globale": "non-conforme",
            "remarques": [...]
        }
    """
    prompt = USER_PROMPT_TEMPLATE.format(
        domaine=domaine,
        domaine_label=domaine_label,
        type_document=type_document,
        section_numero=section_numero,
        section_titre=section_titre,
        code_ccp_extracts=code_ccp_extracts or "[Aucun article CCP pertinent trouvé]",
        ccag_extracts=ccag_extracts or "[Aucun article CCAG pertinent trouvé]",
        clause_text=clause_text,
    )

    result = call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        model_role="expert",
        max_tokens=6000,
        temperature=0.15,
    )

    if not result["success"]:
        return {
            "success": False,
            "error": result.get("error", "Erreur LLM"),
            "remarques": [],
        }

    # Valider et nettoyer les remarques
    remarques = result.get("remarques", [])
    validated = []
    for r in remarques:
        if isinstance(r, dict) and r.get("extrait_texte") and len(r["extrait_texte"]) >= 20:
            validated.append(
                {
                    "extrait_texte": r["extrait_texte"],
                    "constat": r.get("constat", ""),
                    "probleme": r.get("probleme", ""),
                    "references_juridiques": r.get("references_juridiques", ""),
                    "recommandation": r.get("recommandation", ""),
                    "gravite": r.get("gravite", "moyenne").lower(),
                    "section_source": f"{section_numero} - {section_titre}",
                }
            )

    return {
        "success": True,
        "section_analysee": result.get(
            "section_analysee", f"{section_numero} - {section_titre}"
        ),
        "conformite_globale": result.get("conformite_globale", "inconnu"),
        "remarques": validated,
    }
