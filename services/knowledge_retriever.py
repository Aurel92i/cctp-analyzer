"""
CCTP Analyzer V2 - Recherche vectorielle dans les documents de référence.
Chardonnet Conseil - 2026

Pour chaque clause du CCAP/CCTP à analyser, récupère les articles
les plus pertinents du Code CCP et du CCAG via ChromaDB.
"""

import logging
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)

VECTOR_STORE_DIR = Path(__file__).parent.parent / "data" / "vector_store"
client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))


def retrieve_relevant_context(
    clause_text: str,
    session_id: str,
    n_results_ccp: int = 7,
    n_results_ccag: int = 5,
) -> dict:
    """
    Pour une clause donnée, récupère les articles pertinents du Code CCP et du CCAG.

    Args:
        clause_text: texte de la clause à analyser
        session_id: pour retrouver le CCAG indexé de cette session
        n_results_ccp: nombre d'articles CCP à récupérer
        n_results_ccag: nombre d'articles CCAG à récupérer

    Returns:
        {
            "code_ccp_extracts": "Article L. 2111-1\\n...\\n\\nArticle R. 2112-13\\n...",
            "ccag_extracts": "Article 14 CCAG-Travaux\\n...\\n\\nArticle 15\\n...",
            "sources": [{"source": "Code CCP", "numero": "L. 2111-1", "score": 0.85}, ...]
        }
    """
    result = {
        "code_ccp_extracts": "",
        "ccag_extracts": "",
        "sources": [],
    }

    # 1. Recherche dans le Code CCP
    try:
        ccp_collection = client.get_collection("code_ccp")
        ccp_results = ccp_collection.query(
            query_texts=[clause_text],
            n_results=min(n_results_ccp, ccp_collection.count()),
        )

        if (
            ccp_results
            and ccp_results["documents"]
            and ccp_results["documents"][0]
        ):
            extracts = []
            for doc, meta, distance in zip(
                ccp_results["documents"][0],
                ccp_results["metadatas"][0],
                ccp_results["distances"][0],
            ):
                extracts.append(doc)
                result["sources"].append(
                    {
                        "source": "Code CCP",
                        "numero": meta.get("numero_article", "N/A"),
                        "score": round(1 - distance, 3),
                    }
                )

            result["code_ccp_extracts"] = "\n\n---\n\n".join(extracts)

    except Exception as e:
        logger.warning(f"Erreur recherche Code CCP: {e}")
        result["code_ccp_extracts"] = (
            "[Code CCP non indexé - analyse sans référence CCP]"
        )

    # 2. Recherche dans le CCAG de la session
    try:
        ccag_collection = client.get_collection(f"ccag_{session_id}")
        ccag_results = ccag_collection.query(
            query_texts=[clause_text],
            n_results=min(n_results_ccag, ccag_collection.count()),
        )

        if (
            ccag_results
            and ccag_results["documents"]
            and ccag_results["documents"][0]
        ):
            extracts = []
            for doc, meta, distance in zip(
                ccag_results["documents"][0],
                ccag_results["metadatas"][0],
                ccag_results["distances"][0],
            ):
                extracts.append(doc)
                result["sources"].append(
                    {
                        "source": "CCAG",
                        "numero": meta.get("numero_article", "N/A"),
                        "score": round(1 - distance, 3),
                    }
                )

            result["ccag_extracts"] = "\n\n---\n\n".join(extracts)

    except Exception as e:
        logger.warning(f"Erreur recherche CCAG: {e}")
        result["ccag_extracts"] = (
            "[CCAG non indexé - analyse sans référence CCAG]"
        )

    return result
