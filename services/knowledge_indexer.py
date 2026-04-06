"""
CCTP Analyzer V2 - Indexation vectorielle des documents de référence légale.
Chardonnet Conseil - 2026

Utilise ChromaDB (stockage local, sans serveur) pour indexer le Code de la
Commande Publique et les CCAG uploadés par l'utilisateur.

Usage :
    # Indexer le Code CCP (une seule fois ou au démarrage)
    index_code_commande_publique("data/code_commande_publique.txt")

    # Indexer un CCAG uploadé
    index_ccag("uploads/ccag/ccag_travaux.docx", domaine="travaux", session_id="abc123")
"""

import re
import logging
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)

# Répertoire de stockage persistant
VECTOR_STORE_DIR = Path(__file__).parent.parent / "data" / "vector_store"
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

# Client ChromaDB persistant
client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))


def index_code_commande_publique(filepath: str, force_reindex: bool = False):
    """
    Indexe le Code de la Commande Publique en chunks structurés.

    Chaque article devient un chunk avec ses métadonnées :
    - numero_article : "L. 2111-1", "R. 2112-13", etc.
    - partie : "Législative" ou "Réglementaire"

    La collection ChromaDB s'appelle "code_ccp".
    """
    collection_name = "code_ccp"

    # Vérifier si déjà indexé
    try:
        collection = client.get_collection(collection_name)
        if collection.count() > 0 and not force_reindex:
            logger.info(
                f"Collection '{collection_name}' déjà indexée "
                f"({collection.count()} articles)"
            )
            return collection
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"description": "Code de la Commande Publique - Articles indexés"},
    )

    # Lire et parser le fichier
    text = Path(filepath).read_text(encoding="utf-8")

    # Parser les articles du Code CCP.
    # Format réel dans le fichier :
    #   L. 1111-1 Ordonnance n° 2018-1074 ...
    #   [contenu de l'article]
    # Le numéro apparaît en début de ligne, suivi de la source législative.
    article_pattern = (
        r'^((?:L|R|D)\.\s*\d{4}-\d+(?:-\d+)?)\s+'  # Numéro d'article
        r'(?:Ordonnance|Décret|LOI|Loi|Code|Créé)[^\n]*\n'  # Ligne source
        r'(.*?)'  # Contenu
        r'(?=^(?:L|R|D)\.\s*\d{4}-\d+\s+(?:Ordonnance|Décret|LOI|Loi|Code|Créé)|'
        r'^p\.\d+\s|'  # Pagination
        r'^Partie\s|^PREMIÈRE|^DEUXIÈME|^TROISIÈME|'  # Parties
        r'\Z)'
    )

    articles = re.findall(article_pattern, text, re.DOTALL | re.MULTILINE)

    if not articles:
        # Fallback : découper en chunks de ~2000 chars avec overlap
        logger.warning(
            "Pas d'articles détectés par regex, découpage en chunks"
        )
        chunks = chunk_text_with_overlap(text, chunk_size=2000, overlap=200)
        for i, chunk in enumerate(chunks):
            collection.add(
                documents=[chunk],
                metadatas=[{"type": "chunk", "index": i}],
                ids=[f"chunk_{i}"],
            )
        logger.info(
            f"Code CCP indexé en chunks : {collection.count()} dans '{collection_name}'"
        )
        return collection

    # Indexer chaque article
    documents = []
    metadatas = []
    ids = []

    for numero, contenu in articles:
        numero = numero.strip()
        contenu = _clean_article_content(contenu.strip())
        if len(contenu) < 20:
            continue

        partie = (
            "Législative"
            if numero.startswith("L")
            else "Réglementaire"
            if numero.startswith("R")
            else "Décret"
        )

        documents.append(f"Article {numero}\n{contenu}")
        metadatas.append(
            {
                "numero_article": numero,
                "partie": partie,
                "type": "article",
            }
        )
        ids.append(f"art_{numero.replace(' ', '_').replace('.', '_')}")

    if documents:
        # ChromaDB recommande des batch <= 5000
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            collection.add(
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
                ids=ids[i : i + batch_size],
            )

    logger.info(
        f"Code CCP indexé : {collection.count()} articles dans '{collection_name}'"
    )
    return collection


def index_ccag(filepath: str, domaine: str, session_id: str):
    """
    Indexe un CCAG uploadé en chunks structurés.

    Chaque article du CCAG devient un chunk.
    La collection s'appelle "ccag_{session_id}" pour isoler par session.

    Args:
        filepath: chemin vers le .docx du CCAG
        domaine: "travaux", "fournitures", "pi", "tic", "moe", "industriel"
        session_id: identifiant de session pour isoler les données
    """
    from services.document_extractor import extract_text_from_docx

    collection_name = f"ccag_{session_id}"

    # Supprimer si existe
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"domaine": domaine, "type": "ccag"},
    )

    text = extract_text_from_docx(filepath)

    # Parser les articles du CCAG
    # Pattern : "Article 1", "Article 2.1", "ARTICLE 14", etc.
    article_pattern = (
        r'(?:ARTICLE|Article)\s+(\d+(?:\.\d+)?(?:\.\d+)?)'
        r'\s*[-–:.)]?\s*'
        r'(.*?)'
        r'(?=(?:ARTICLE|Article)\s+\d+|$)'
    )
    articles = re.findall(article_pattern, text, re.DOTALL | re.IGNORECASE)

    if not articles:
        # Fallback chunks
        chunks = chunk_text_with_overlap(text, chunk_size=2000, overlap=200)
        for i, chunk in enumerate(chunks):
            collection.add(
                documents=[chunk],
                metadatas=[{"type": "chunk", "domaine": domaine, "index": i}],
                ids=[f"ccag_chunk_{i}"],
            )
        logger.info(
            f"CCAG {domaine} indexé en chunks : {collection.count()} chunks"
        )
        return collection

    documents = []
    metadatas = []
    ids = []

    for numero, contenu in articles:
        contenu = contenu.strip()
        if len(contenu) < 20:
            continue
        documents.append(f"Article {numero} CCAG-{domaine}\n{contenu}")
        metadatas.append(
            {
                "numero_article": numero,
                "domaine": domaine,
                "type": "article_ccag",
            }
        )
        ids.append(f"ccag_{domaine}_art_{numero.replace('.', '_')}")

    if documents:
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            collection.add(
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
                ids=ids[i : i + batch_size],
            )

    logger.info(f"CCAG {domaine} indexé : {collection.count()} articles")
    return collection


def cleanup_session_collections(session_id: str):
    """Supprime les collections associées à une session."""
    for prefix in ("ccag_", "cctp_ref_"):
        try:
            client.delete_collection(f"{prefix}{session_id}")
            logger.info(f"Collection {prefix}{session_id} supprimée")
        except Exception:
            pass


def chunk_text_with_overlap(
    text: str, chunk_size: int = 2000, overlap: int = 200
) -> list:
    """Découpe un texte en chunks avec chevauchement."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def _clean_article_content(content: str) -> str:
    """Nettoie le contenu d'un article (supprime pagination, liens, etc.)."""
    # Supprimer les lignes de pagination "p.XX Code de la commande publique"
    content = re.sub(r'p\.\d+\s+Code de la commande publique\s*', '', content)
    # Supprimer les lignes de référence externe
    content = re.sub(r'^(?:service-public\.fr|Récemment au Bulletin)[^\n]*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^>\s+[^\n]*$', '', content, flags=re.MULTILINE)
    # Supprimer les lignes vides multiples
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()
