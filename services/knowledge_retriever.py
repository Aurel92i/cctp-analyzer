"""
CCAP Analyzer - Recherche vectorielle dans les documents de référence.
Lexigency - 2026

Pour chaque clause du CCAP à analyser, récupère les articles
les plus pertinents du Code CCP, du CCAG et du CCTP via ChromaDB.
"""

import os
import logging
from pathlib import Path

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

logger = logging.getLogger(__name__)

VECTOR_STORE_DIR = Path(__file__).parent.parent / "data" / "vector_store"
client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))


def get_embedding_function():
    """Retourne une embedding function API (OpenRouter/OpenAI) au lieu d'un modèle local."""
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        api_base="https://openrouter.ai/api/v1",
        model_name="openai/text-embedding-3-small",
    )


def retrieve_relevant_context(
    clause_text: str,
    session_id: str,
    n_results_ccp: int = 7,
    n_results_ccag: int = 5,
    n_results_cctp: int = 3,
) -> dict:
    """
    Pour une clause donnée, récupère les articles pertinents
    du Code CCP, du CCAG et du CCTP.

    Returns:
        {
            "code_ccp_extracts": "...",
            "ccag_extracts": "...",
            "cctp_extracts": "...",
            "sources": [...]
        }
    """
    result = {
        "code_ccp_extracts": "",
        "ccag_extracts": "",
        "cctp_extracts": "",
        "sources": [],
    }

    # 1. Recherche dans le Code CCP
    try:
        ccp_collection = client.get_collection(
            "code_ccp", embedding_function=get_embedding_function()
        )
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
        ccag_collection = client.get_collection(
            f"ccag_{session_id}", embedding_function=get_embedding_function()
        )
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

    # 3. Recherche dans le CCTP de la session (référence technique)
    try:
        cctp_collection = client.get_collection(
            f"cctp_{session_id}", embedding_function=get_embedding_function()
        )
        cctp_results = cctp_collection.query(
            query_texts=[clause_text],
            n_results=min(n_results_cctp, cctp_collection.count()),
        )

        if (
            cctp_results
            and cctp_results["documents"]
            and cctp_results["documents"][0]
        ):
            extracts = []
            for doc, meta, distance in zip(
                cctp_results["documents"][0],
                cctp_results["metadatas"][0],
                cctp_results["distances"][0],
            ):
                extracts.append(doc)
                result["sources"].append(
                    {
                        "source": "CCTP",
                        "numero": f"Chunk {meta.get('index', 'N/A')}",
                        "score": round(1 - distance, 3),
                    }
                )

            result["cctp_extracts"] = "\n\n---\n\n".join(extracts)

    except Exception as e:
        logger.debug(f"CCTP non indexé pour cette session: {e}")
        result["cctp_extracts"] = ""

    return result
