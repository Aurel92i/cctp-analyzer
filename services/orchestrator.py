"""
CCAP Analyzer - Orchestrateur principal.
Lexigency - 2026

Coordonne les agents pour l'analyse complète d'un CCAP.

Flow :
1. Charger le CCAG depuis data/ccag/{domaine}.docx
2. Indexer Code CCP + CCAG + CCTP en base vectorielle
3. Extraire la structure du CCAP (document à analyser)
4. Pour chaque section du CCAP : récupérer le contexte RAG + auditer
5. Synthétiser les résultats
"""

import logging
from pathlib import Path
from typing import List, Dict, Callable, Optional

from services.knowledge_indexer import (
    index_code_commande_publique,
    index_ccag,
    index_cctp,
    cleanup_session_collections,
)
from services.knowledge_retriever import retrieve_relevant_context
from services.agent_structurer import extract_structure
from services.agent_auditor import audit_clause
from services.agent_synthesizer import synthesize
from config import CODE_COMMANDE_PUBLIQUE_FILE, CCAG_DIR, DOMAINES_CCAG

logger = logging.getLogger(__name__)


def run_full_analysis(
    ccap_path: str,
    cctp_path: Optional[str],
    domaine: str,
    session_id: str,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    Exécute l'analyse complète d'un CCAP.

    Le CCAP est le document analysé et annoté.
    Le CCAG (pré-chargé), le CCTP (uploadé) et le Code CCP servent de référence.

    Args:
        ccap_path: chemin vers le fichier CCAP .docx (à analyser)
        cctp_path: chemin optionnel vers le CCTP .docx (référence technique)
        domaine: "travaux", "fournitures", "pi", "tic", "moe", "industriel"
        session_id: identifiant de session
        progress_callback: function(progress: int, step: str)

    Returns:
        {
            "success": True/False,
            "remarques": [...],
            "synthese": "...",
            "niveau_risque": "...",
            "points_critiques": [...],
            "statistiques": {...}
        }
    """
    domaine_label = DOMAINES_CCAG.get(domaine, "Travaux")

    def update_progress(progress, step):
        if progress_callback:
            progress_callback(progress, step)
        logger.info(f"[{session_id}] {progress}% - {step}")

    try:
        # =================================================================
        # PHASE 1 : CHARGEMENT DU CCAG DEPUIS data/ccag/
        # =================================================================
        update_progress(2, f"Chargement du CCAG {domaine_label}...")

        ccag_path = CCAG_DIR / f"{domaine}.docx"
        if not ccag_path.exists():
            return {
                "success": False,
                "error": (
                    f"Fichier CCAG introuvable pour le domaine '{domaine}': {ccag_path}. "
                    f"Vérifiez que le fichier data/ccag/{domaine}.docx est présent."
                ),
                "remarques": [],
            }

        logger.info(f"[{session_id}] CCAG chargé depuis: {ccag_path}")

        # =================================================================
        # PHASE 2 : INDEXATION DES DOCUMENTS DE RÉFÉRENCE
        # =================================================================
        update_progress(5, "Indexation du Code de la Commande Publique...")
        index_code_commande_publique(str(CODE_COMMANDE_PUBLIQUE_FILE))

        update_progress(10, f"Indexation du CCAG {domaine_label}...")
        index_ccag(str(ccag_path), domaine, session_id)

        # Indexer le CCTP comme document de référence supplémentaire
        if cctp_path:
            update_progress(13, "Indexation du CCTP comme référence technique...")
            index_cctp(cctp_path, session_id)

        # =================================================================
        # PHASE 3 : EXTRACTION DU TEXTE ET DE LA STRUCTURE DU CCAP
        # =================================================================
        update_progress(15, "Extraction du texte du CCAP...")
        from services.document_extractor import extract_text_from_docx

        ccap_text = extract_text_from_docx(ccap_path)

        update_progress(20, "Analyse de la structure du CCAP...")
        structure = extract_structure(ccap_text)
        sections = structure.get("sections", [])

        if not sections:
            return {
                "success": False,
                "error": "Impossible d'identifier des sections dans le CCAP",
                "remarques": [],
            }

        logger.info(f"[{session_id}] {len(sections)} sections identifiées dans le CCAP")

        # =================================================================
        # PHASE 4 : AUDIT CLAUSE PAR CLAUSE (avec RAG)
        # =================================================================
        all_remarques: List[Dict] = []
        audit_results: List[Dict] = []

        for i, section in enumerate(sections):
            progress = 25 + int((i / len(sections)) * 50)  # 25% à 75%
            update_progress(
                progress,
                f"Audit section {i + 1}/{len(sections)} : "
                f"{section.get('titre', '?')[:50]}...",
            )

            # Extraire le texte de la section
            start = section.get("start_char", 0)
            end = section.get("end_char", len(ccap_text))
            clause_text = ccap_text[start:end]

            # Limiter la taille de la clause (~3k tokens)
            max_clause_chars = 12000
            if len(clause_text) > max_clause_chars:
                clause_text = (
                    clause_text[:max_clause_chars]
                    + "\n[... section tronquée ...]"
                )

            # Récupérer le contexte pertinent via RAG
            context = retrieve_relevant_context(
                clause_text=clause_text,
                session_id=session_id,
                n_results_ccp=7,
                n_results_ccag=5,
                n_results_cctp=3,
            )

            # Auditer la clause du CCAP
            audit_result = audit_clause(
                clause_text=clause_text,
                section_numero=section.get("numero", f"Section {i + 1}"),
                section_titre=section.get("titre", "Sans titre"),
                code_ccp_extracts=context["code_ccp_extracts"],
                ccag_extracts=context["ccag_extracts"],
                cctp_extracts=context.get("cctp_extracts", ""),
                domaine=domaine,
                domaine_label=domaine_label,
            )

            audit_results.append(audit_result)

            if audit_result.get("success") and audit_result.get("remarques"):
                all_remarques.extend(audit_result["remarques"])
                logger.info(
                    f"[{session_id}] Section '{section.get('titre', '?')[:40]}' : "
                    f"{len(audit_result['remarques'])} remarques"
                )

        # =================================================================
        # PHASE 5 : DÉDUPLICATION
        # =================================================================
        update_progress(78, "Déduplication des remarques...")
        all_remarques = deduplicate_remarques(all_remarques)

        # =================================================================
        # PHASE 6 : SYNTHÈSE FINALE
        # =================================================================
        update_progress(80, "Synthèse finale...")
        synthesis = synthesize(
            audit_results=audit_results,
            domaine_label=domaine_label,
            all_remarques=all_remarques,
        )

        # Ajouter les remarques transversales
        if synthesis.get("remarques_transversales"):
            all_remarques.extend(synthesis["remarques_transversales"])

        update_progress(90, "Analyse terminée, préparation du document...")

        # Cleanup des collections de session
        cleanup_session_collections(session_id)

        return {
            "success": True,
            "remarques": all_remarques,
            "synthese": synthesis.get("synthese", ""),
            "niveau_risque": synthesis.get("niveau_risque", "modéré"),
            "points_critiques": synthesis.get("points_critiques", []),
            "statistiques": synthesis.get(
                "statistiques",
                {
                    "sections_analysees": len(sections),
                    "total_remarques": len(all_remarques),
                    "haute": len(
                        [r for r in all_remarques if r.get("gravite") == "haute"]
                    ),
                    "moyenne": len(
                        [r for r in all_remarques if r.get("gravite") == "moyenne"]
                    ),
                    "basse": len(
                        [r for r in all_remarques if r.get("gravite") == "basse"]
                    ),
                },
            ),
        }

    except Exception as e:
        logger.error(f"[{session_id}] Erreur orchestrateur: {e}")
        import traceback

        traceback.print_exc()
        cleanup_session_collections(session_id)
        return {
            "success": False,
            "error": str(e),
            "remarques": [],
        }


def deduplicate_remarques(remarques: List[Dict]) -> List[Dict]:
    """Supprime les remarques similaires basées sur l'extrait de texte."""
    seen = set()
    unique = []
    for r in remarques:
        key = r.get("extrait_texte", "")[:100].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    return unique
