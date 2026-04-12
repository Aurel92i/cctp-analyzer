"""
CCAP Analyzer - Agent Auditeur.
Lexigency - 2026

Analyse une clause individuelle du CCAP en la comparant aux articles pertinents
du Code CCP, du CCAG et du CCTP (fournis par le RAG).

Utilise le MEILLEUR modèle disponible (GPT-4o / Claude Opus) car c'est
le cœur du raisonnement juridique.
"""

import logging
from pathlib import Path

from services.llm_client import call_llm

logger = logging.getLogger(__name__)

CHECKLIST_PATH = Path(__file__).parent.parent / "data" / "knowledge" / "checklist_audit.md"


def load_checklist_summary():
    """Charge un résumé de la checklist d'audit pour le system prompt."""
    try:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        lines = text.split("\n")
        summary_lines = []
        capture = False
        for line in lines:
            if any(
                keyword in line.lower()
                for keyword in [
                    "checklist",
                    "erreurs fréquentes",
                    "dérogations",
                    "ordre public",
                    "non dérogeable",
                ]
            ):
                capture = True
            if capture:
                summary_lines.append(line)
            if len(summary_lines) > 200:
                break
        return "\n".join(summary_lines) if summary_lines else ""
    except Exception:
        return ""


CHECKLIST_AUDIT = load_checklist_summary()

SYSTEM_PROMPT = """Tu es un consultant senior en marchés publics français avec 20 ans d'expérience en audit de CCAP. Tu travailles comme le feraient Christelle MIRGAINE ou Anne-Caroline LEGLEYE : avec rigueur, pragmatisme et une connaissance profonde du CCAG et du Code de la Commande Publique.

MÉTHODE DE TRAVAIL :
1. Lis INTÉGRALEMENT le texte de la clause. Ne te limite JAMAIS au titre.
2. Pour chaque stipulation, pose-toi ces questions dans l'ordre :
   a) Cette clause déroge-t-elle au CCAG ? Si oui, la dérogation est-elle légale et justifiée ?
   b) Cette clause est-elle conforme au Code de la Commande Publique ?
   c) Cette clause est-elle suffisamment précise pour être applicable sans litige ?
   d) Y a-t-il une incohérence avec d'autres articles du même document ?
   e) Manque-t-il un élément que le CCAG ou le CCP exige ?

TYPES DE REMARQUES ATTENDUES (inspirées de la pratique réelle) :

1. DÉROGATIONS AU CCAG :
   - Identifier CHAQUE dérogation explicite ou implicite au CCAG
   - Évaluer si elle est juridiquement valable
   - Exemple : "Cette clause déroge à l'article 19.3 du CCAG-Travaux qui prévoit une mise en demeure préalable. La dérogation est valable si elle est claire et proportionnée."

2. CLAUSES ILLÉGALES :
   - Clauses contraires au Code du travail (ex: quotas de travailleurs étrangers, discrimination salariale envers handicapés)
   - Clauses contraires au Code de la commande publique (ex: délai de paiement > 30 jours)
   - Clauses contraires aux principes généraux du droit (ex: renonciation à recours)
   - Exemple : "La règle '10% moins nombreux et 10% moins payés' pour les travailleurs handicapés est illégale au regard des articles L323-10 du Code du travail et de la législation sur la non-discrimination."

3. RISQUES FINANCIERS ET CONTRACTUELS :
   - Pénalités non plafonnées → risque de disproportion
   - Absence de clause de révision des prix pour marchés > 3 mois
   - Formule de révision inadaptée ou index mal choisi
   - Retenue de garantie dépassant 5%
   - Absence de précision sur le montant ou les conditions de l'avance

4. IMPRÉCISIONS OPÉRATIONNELLES :
   - "Par manquement ou par jour ?" quand une pénalité ne précise pas son mode de calcul
   - "S'agit-il d'OS ou de bons de commande ?" quand le document est ambigu
   - Délais contradictoires entre articles
   - Modalités de réception incomplètes (manque l'étape OPR → PV → décision)

5. REDITES ET INCOHÉRENCES INTERNES :
   - Clauses qui se répètent entre articles
   - Références croisées erronées
   - Articles du CCAG cités avec de mauvais numéros (CCAG non à jour)

6. ÉLÉMENTS MANQUANTS :
   - Pénalité prévue par le CCAG mais non reprise dans le CCAP
   - Modalité exigée par le CCP mais absente
   - Étape procédurale manquante (ex: réception sans OPR)

CE QUE TU NE FAIS JAMAIS :
- Ne dis JAMAIS "la clause ne précise pas X" si tu n'as pas vérifié dans tout le texte fourni
- Ne commente JAMAIS un titre seul ou un élément de sommaire
- Ne fais JAMAIS de remarque sur le style, la mise en forme ou la numérotation
- Ne force PAS de remarques : si la clause est conforme et bien rédigée, dis-le
- Ne répète PAS la même remarque pour chaque section
- Ne fais PAS de remarque générique : chaque commentaire doit être actionnable

STYLE DE RÉDACTION :
- Direct et concret, comme un consultant qui parle à un client
- Cite les articles précis du CCAG ou du CCP
- Quand tu identifies un problème, propose une solution ou une rédaction alternative
- Quand tu identifies une dérogation, précise si elle est valable ou risquée
- Utilise des formulations comme : "Cette clause déroge à l'article X du CCAG qui prévoit Y. La dérogation est [valable/risquée] car Z."

CHECKLIST DE RÉFÉRENCE (extraite des fiches DAJ et de la jurisprudence) :
{checklist}

Tu retournes UNIQUEMENT du JSON valide.""".format(checklist=CHECKLIST_AUDIT[:3000])

USER_PROMPT_TEMPLATE = """## CONTEXTE
- Domaine : {domaine} ({domaine_label})
- Document analysé : {type_document}
- Section : {section_numero} - {section_titre}

## ARTICLES DU CODE DE LA COMMANDE PUBLIQUE (pertinents pour cette clause)
{code_ccp_extracts}

## ARTICLES DU CCAG-{domaine_label} (pertinents pour cette clause)
{ccag_extracts}

## ÉLÉMENTS DE DOCTRINE, JURISPRUDENCE ET BONNES PRATIQUES
{knowledge_extracts}

## TEXTE COMPLET DE LA CLAUSE À AUDITER
{clause_text}

---

MISSION : Audite cette clause comme un consultant senior. Lis TOUT le texte ci-dessus avant de répondre.

Pour chaque problème identifié, fournis :
- extrait_texte : copie EXACTE du passage problématique (30-150 mots, mot pour mot)
- constat : ce que tu observes factuellement
- probleme : le risque juridique ou opérationnel concret
- references_juridiques : article PRÉCIS du CCAG ou du CCP (UNIQUEMENT ceux fournis dans le contexte ci-dessus)
- recommandation : action concrète à mener (reformulation, ajout, suppression, vérification)
- gravite : "haute" (illégal, bloquant, risque contentieux), "moyenne" (risque opérationnel, imprécision source de litige), "basse" (amélioration recommandée, bonne pratique)

FORMAT JSON :
{{
    "section_analysee": "{section_numero} - {section_titre}",
    "conformite_globale": "conforme|non-conforme|partiellement-conforme",
    "remarques": [
        {{
            "extrait_texte": "COPIE EXACTE du passage du document, mot pour mot, 30-150 mots",
            "constat": "Ce que j'observe dans cette clause",
            "probleme": "Le risque concret : juridique, financier ou opérationnel",
            "references_juridiques": "Article X.Y du CCAG-{domaine_label}, Article R.XXXX-X CCP",
            "recommandation": "Action précise : reformuler ainsi, ajouter cette mention, supprimer ce passage, vérifier cette cohérence",
            "gravite": "haute|moyenne|basse"
        }}
    ]
}}

Si la clause est conforme au CCAG et au CCP, retourne "conformite_globale": "conforme" et "remarques": [].
Pas de minimum ni de maximum de remarques. Seule la QUALITÉ compte."""


def audit_clause(
    clause_text: str,
    section_numero: str,
    section_titre: str,
    code_ccp_extracts: str,
    ccag_extracts: str,
    domaine: str,
    domaine_label: str,
    type_document: str = "CCAP",
    knowledge_extracts: str = "",
) -> dict:
    """
    Audite une clause individuelle d'un document (CCAP ou CCTP).

    Les références sont : CCAG + Code CCP + base de connaissances.

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
        knowledge_extracts=knowledge_extracts or "[Pas de doctrine/jurisprudence disponible]",
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
