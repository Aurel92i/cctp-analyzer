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
import re
from pathlib import Path
from typing import List, Dict, Callable, Optional

from services.knowledge_indexer import (
    index_code_commande_publique,
    index_ccag,
    index_cctp,
    cleanup_session_collections,
)
from services.knowledge_retriever import retrieve_relevant_context
from services.agent_auditor import audit_clause
from services.agent_synthesizer import synthesize
from config import CODE_COMMANDE_PUBLIQUE_FILE, CCAG_DIR, DOMAINES_CCAG

logger = logging.getLogger(__name__)


def split_document_into_sections(text):
    """Découpe un document (CCAP/CCTP) en sections. Chaque section = titre + TOUT le contenu jusqu'au prochain titre."""
    patterns = [
        r'(?=(?:^|\n)\s*(Article\s+\d+(?:[.\-]\d+)*)\s*[-–:\.]\s*([^\n]+))',
        r'(?=(?:^|\n)\s*(\d+[-\.]\d+(?:[-\.]\d+)*)\s*[-–]\s*([^\n]+))',
        r'(?=(?:^|\n)\s*(ARTICLE\s+\d+(?:[.\-]\d+)*)\s*[-–:\.]\s*([^\n]+))',
    ]

    sections = []
    for pattern in patterns:
        matches = list(re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE))
        if len(matches) >= 3:
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                section_text = text[start:end].strip()

                if len(section_text) < 200:
                    continue
                if section_text.count('...') > 3 or section_text.count('\u2026') > 3:
                    continue

                sections.append({
                    "numero": match.group(1).strip(),
                    "titre": match.group(2).strip() if match.lastindex >= 2 else "",
                    "text": section_text
                })
            break

    if not sections:
        chunk_size = 5000
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            if len(chunk.strip()) > 100:
                sections.append({
                    "numero": f"Partie {i // chunk_size + 1}",
                    "titre": "",
                    "text": chunk.strip()
                })

    return sections


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
        # PHASE 3 : EXTRACTION DU TEXTE ET DÉCOUPAGE DÉTERMINISTE DU CCAP
        # =================================================================
        update_progress(15, "Extraction du texte du CCAP...")
        from services.document_extractor import extract_text_from_docx, extract_text

        ccap_text = extract_text_from_docx(ccap_path)

        update_progress(20, "Découpage du CCAP en sections...")
        sections = split_document_into_sections(ccap_text)

        if not sections:
            return {
                "success": False,
                "error": "Impossible d'identifier des sections dans le CCAP",
                "remarques": [],
            }

        logger.info(f"[{session_id}] {len(sections)} sections identifiées dans le CCAP")

        # =================================================================
        # PHASE 4 : AUDIT CLAUSE PAR CLAUSE DU CCAP (avec RAG)
        # =================================================================
        all_remarques: List[Dict] = []
        audit_results: List[Dict] = []

        for i, section in enumerate(sections):
            progress = 25 + int((i / max(len(sections), 1)) * 50)  # 25% à 75%
            update_progress(
                progress,
                f"Audit CCAP section {i + 1}/{len(sections)} : "
                f"{section.get('titre', '?')[:50]}...",
            )

            clause_text = section["text"]

            # Pas de troncature agressive — les clauses doivent être lues EN ENTIER
            max_clause_chars = 25000
            if len(clause_text) > max_clause_chars:
                clause_text = clause_text[:max_clause_chars] + "\n[... fin de section tronquée ...]"

            # Récupérer le contexte pertinent via RAG
            context = retrieve_relevant_context(
                clause_text=clause_text,
                session_id=session_id,
                n_results_ccp=10,
                n_results_ccag=8,
            )

            # Auditer la clause du CCAP
            audit_result = audit_clause(
                clause_text=clause_text,
                section_numero=section["numero"],
                section_titre=section["titre"],
                code_ccp_extracts=context["code_ccp_extracts"],
                ccag_extracts=context["ccag_extracts"],
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
        # PHASE 4b : AUDIT OPTIONNEL DU CCTP
        # =================================================================
        if cctp_path and Path(cctp_path).exists():
            update_progress(76, "Analyse du CCTP...")
            cctp_text = extract_text(cctp_path)
            cctp_sections = split_document_into_sections(cctp_text)

            for i, section in enumerate(cctp_sections):
                progress = 76 + int((i / max(len(cctp_sections), 1)) * 2)
                update_progress(
                    progress,
                    f"Audit CCTP section {i + 1}/{len(cctp_sections)}...",
                )

                clause_text = section["text"][:25000]

                context = retrieve_relevant_context(
                    clause_text=clause_text,
                    session_id=session_id,
                    n_results_ccp=5,
                    n_results_ccag=5,
                )

                audit_result = audit_clause(
                    clause_text=clause_text,
                    section_numero=section["numero"],
                    section_titre=section["titre"],
                    code_ccp_extracts=context["code_ccp_extracts"],
                    ccag_extracts=context["ccag_extracts"],
                    domaine=domaine,
                    domaine_label=domaine_label,
                    type_document="CCTP",
                )

                if audit_result.get("success") and audit_result.get("remarques"):
                    for r in audit_result["remarques"]:
                        r["document_source"] = "CCTP"
                    all_remarques.extend(audit_result["remarques"])

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
