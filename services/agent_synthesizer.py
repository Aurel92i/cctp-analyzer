"""
CCAP Analyzer - Agent Synthétiseur.
Lexigency - 2026

Compile les résultats de tous les audits de clauses et produit
une synthèse globale + remarques transversales.
"""

import logging
from typing import List, Dict

from services.llm_client import call_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un expert juridique senior qui produit des synthèses d'audit de CCAP pour les marchés publics.
Tu reçois les résultats d'un audit clause par clause et tu dois :
1. Identifier les problèmes transversaux (qui touchent plusieurs sections)
2. Vérifier la cohérence globale du CCAP
3. Signaler les clauses obligatoires absentes du CCAP entier
4. Produire une synthèse exécutive

Tu retournes UNIQUEMENT du JSON valide."""

USER_PROMPT_TEMPLATE = """## RÉSULTATS D'AUDIT CLAUSE PAR CLAUSE

{audit_results_summary}

## DOMAINE : {domaine_label}

---

MISSION : Produis la synthèse finale de cet audit de CCAP.

FORMAT JSON :
{{
    "synthese_globale": "Analyse globale du CCAP en 3-5 phrases",
    "niveau_risque_global": "élevé|modéré|faible",
    "points_critiques": ["Point critique 1", "Point critique 2", "..."],
    "remarques_transversales": [
        {{
            "extrait_texte": "Document global",
            "constat": "Constat transversal",
            "probleme": "Problème de cohérence ou manque global",
            "references_juridiques": "Références",
            "recommandation": "Recommandation",
            "gravite": "haute|moyenne|basse",
            "section_source": "Synthèse globale"
        }}
    ],
    "statistiques": {{
        "sections_analysees": {nb_sections},
        "sections_conformes": 0,
        "sections_non_conformes": 0,
        "total_remarques": 0,
        "haute": 0,
        "moyenne": 0,
        "basse": 0
    }}
}}"""


def synthesize(
    audit_results: list,
    domaine_label: str,
    all_remarques: list,
) -> dict:
    """Produit la synthèse finale à partir des résultats d'audit du CCAP."""
    summary_parts = []
    for ar in audit_results:
        section = ar.get("section_analysee", "?")
        conformite = ar.get("conformite_globale", "?")
        nb_remarques = len(ar.get("remarques", []))
        gravites: Dict[str, int] = {}
        for r in ar.get("remarques", []):
            g = r.get("gravite", "moyenne")
            gravites[g] = gravites.get(g, 0) + 1

        summary_parts.append(
            f"- {section} : {conformite} | {nb_remarques} remarques "
            f"(haute: {gravites.get('haute', 0)}, "
            f"moyenne: {gravites.get('moyenne', 0)}, "
            f"basse: {gravites.get('basse', 0)})"
        )

    summary = "\n".join(summary_parts)

    prompt = USER_PROMPT_TEMPLATE.format(
        audit_results_summary=summary,
        domaine_label=domaine_label,
        nb_sections=len(audit_results),
    )

    result = call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        model_role="medium",
        max_tokens=4000,
        temperature=0.2,
    )

    if not result["success"]:
        return _mechanical_synthesis(audit_results, all_remarques, domaine_label)

    transversales = result.get("remarques_transversales", [])

    return {
        "success": True,
        "synthese": result.get("synthese_globale", ""),
        "niveau_risque": result.get("niveau_risque_global", "modéré"),
        "points_critiques": result.get("points_critiques", []),
        "remarques_transversales": transversales,
        "statistiques": result.get("statistiques", {}),
    }


def _mechanical_synthesis(
    audit_results: list,
    all_remarques: list,
    domaine_label: str,
) -> dict:
    """Synthèse mécanique si le LLM échoue."""
    haute = len([r for r in all_remarques if r.get("gravite") == "haute"])
    moyenne = len([r for r in all_remarques if r.get("gravite") == "moyenne"])
    basse = len([r for r in all_remarques if r.get("gravite") == "basse"])

    if haute >= 3:
        niveau = "élevé"
    elif haute >= 1 or moyenne >= 5:
        niveau = "modéré"
    else:
        niveau = "faible"

    return {
        "success": True,
        "synthese": (
            f"Audit CCAP {domaine_label} : {len(all_remarques)} remarques identifiées "
            f"({haute} haute, {moyenne} moyenne, {basse} basse)."
        ),
        "niveau_risque": niveau,
        "points_critiques": [
            r["constat"]
            for r in all_remarques
            if r.get("gravite") == "haute"
        ][:5],
        "remarques_transversales": [],
        "statistiques": {
            "sections_analysees": len(audit_results),
            "total_remarques": len(all_remarques),
            "haute": haute,
            "moyenne": moyenne,
            "basse": basse,
        },
    }
