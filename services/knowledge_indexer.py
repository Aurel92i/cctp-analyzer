"""
CCAP Analyzer - Indexation vectorielle des documents de référence légale.
Lexigency - 2026

Utilise ChromaDB (stockage local, sans serveur) pour indexer :
- Le Code de la Commande Publique (collection "code_ccp")
- Le CCAG du domaine (collection "ccag_{session_id}")
- Le CCTP uploadé (collection "cctp_{session_id}")
"""

import os
import re
import logging
from pathlib import Path

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

logger = logging.getLogger(__name__)

# Répertoire de stockage persistant
VECTOR_STORE_DIR = Path(__file__).parent.parent / "data" / "vector_store"
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

# Client ChromaDB persistant
client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))


def get_embedding_function():
    """Retourne une embedding function API (OpenRouter/OpenAI) au lieu d'un modèle local."""
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        api_base="https://openrouter.ai/api/v1",
        model_name="openai/text-embedding-3-small",
    )


def index_code_commande_publique(filepath: str, force_reindex: bool = False):
    """
    Indexe le Code de la Commande Publique en chunks structurés.
    Collection ChromaDB : "code_ccp".
    """
    collection_name = "code_ccp"

    try:
        collection = client.get_collection(
            collection_name, embedding_function=get_embedding_function()
        )
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
        embedding_function=get_embedding_function(),
    )

    text = Path(filepath).read_text(encoding="utf-8")

    # Parser les articles du Code CCP
    article_pattern = (
        r"^((?:L|R|D)\.\s*\d{4}-\d+(?:-\d+)?)\s+"
        r"(?:Ordonnance|Décret|LOI|Loi|Code|Créé)[^\n]*\n"
        r"(.*?)"
        r"(?=^(?:L|R|D)\.\s*\d{4}-\d+\s+(?:Ordonnance|Décret|LOI|Loi|Code|Créé)|"
        r"^p\.\d+\s|"
        r"^Partie\s|^PREMIÈRE|^DEUXIÈME|^TROISIÈME|"
        r"\Z)"
    )

    articles = re.findall(article_pattern, text, re.DOTALL | re.MULTILINE)

    if not articles:
        logger.warning("Pas d'articles détectés par regex, découpage en chunks")
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
    Indexe un CCAG en chunks structurés.
    Le fichier CCAG provient de data/ccag/{domaine}.docx (pré-chargé).
    Collection : "ccag_{session_id}".
    """
    from services.document_extractor import extract_text_from_docx

    collection_name = f"ccag_{session_id}"

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"domaine": domaine, "type": "ccag"},
        embedding_function=get_embedding_function(),
    )

    text = extract_text_from_docx(filepath)

    # Parser les articles du CCAG
    article_pattern = (
        r"(?:ARTICLE|Article)\s+(\d+(?:\.\d+)?(?:\.\d+)?)"
        r"\s*[-–:.)]?\s*"
        r"(.*?)"
        r"(?=(?:ARTICLE|Article)\s+\d+|$)"
    )
    articles = re.findall(article_pattern, text, re.DOTALL | re.IGNORECASE)

    if not articles:
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


def index_cctp(filepath: str, session_id: str):
    """
    Indexe le CCTP uploadé comme document de référence technique.
    Collection : "cctp_{session_id}".
    """
    from services.document_extractor import extract_text_from_docx

    collection_name = f"cctp_{session_id}"

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"type": "cctp_reference"},
        embedding_function=get_embedding_function(),
    )

    text = extract_text_from_docx(filepath)
    chunks = chunk_text_with_overlap(text, chunk_size=2000, overlap=200)

    for i, chunk in enumerate(chunks):
        collection.add(
            documents=[chunk],
            metadatas=[{"type": "cctp_ref", "index": i}],
            ids=[f"cctp_ref_{i}"],
        )

    logger.info(f"CCTP référence indexé : {collection.count()} chunks")
    return collection


def index_knowledge_base(force_reindex=False):
    """
    Indexe les fichiers de la base de connaissances (checklist, jurisprudence, fiches DAJ)
    dans une collection ChromaDB persistante appelée "knowledge_base".

    Cette collection est permanente (comme code_ccp), pas liée à une session.
    """
    collection_name = "knowledge_base"

    try:
        collection = client.get_collection(
            collection_name, embedding_function=get_embedding_function()
        )
        if collection.count() > 0 and not force_reindex:
            logger.info(
                f"Collection '{collection_name}' déjà indexée "
                f"({collection.count()} éléments)"
            )
            return collection
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"description": "Base de connaissances Lexigency - Checklist, jurisprudence, fiches DAJ"},
        embedding_function=get_embedding_function(),
    )

    knowledge_dir = Path(__file__).parent.parent / "data" / "knowledge"

    documents = []
    metadatas = []
    ids = []

    # Indexer les fichiers markdown
    for filepath in knowledge_dir.glob("*.md"):
        text = filepath.read_text(encoding="utf-8")
        sections = split_by_headings(text)
        for i, section in enumerate(sections):
            if len(section.strip()) > 50:
                documents.append(section)
                metadatas.append({
                    "source": filepath.stem,
                    "type": "knowledge",
                    "index": i,
                })
                ids.append(f"kb_{filepath.stem}_{i}")

    # Indexer la jurisprudence (séparateur ---)
    juris_path = knowledge_dir / "jurisprudence_ccap.txt"
    if juris_path.exists():
        text = juris_path.read_text(encoding="utf-8")
        arrets = text.split("---")
        for i, arret in enumerate(arrets):
            if len(arret.strip()) > 50:
                documents.append(arret.strip())
                metadatas.append({
                    "source": "jurisprudence",
                    "type": "arret",
                    "index": i,
                })
                ids.append(f"kb_juris_{i}")

    if documents:
        batch_size = 50
        for i in range(0, len(documents), batch_size):
            collection.add(
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
                ids=ids[i : i + batch_size],
            )

    logger.info(
        f"Base de connaissances indexée : {collection.count()} éléments "
        f"dans '{collection_name}'"
    )
    return collection


def split_by_headings(text):
    """Découpe un texte markdown en sections par titres ## ou ###."""
    sections = re.split(r"\n(?=#{2,3}\s)", text)
    return [s.strip() for s in sections if s.strip()]


def cleanup_session_collections(session_id: str):
    """Supprime les collections associées à une session."""
    for prefix in ("ccag_", "cctp_"):
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
    """Nettoie le contenu d'un article."""
    content = re.sub(r"p\.\d+\s+Code de la commande publique\s*", "", content)
    content = re.sub(
        r"^(?:service-public\.fr|Récemment au Bulletin)[^\n]*$",
        "",
        content,
        flags=re.MULTILINE,
    )
    content = re.sub(r"^>\s+[^\n]*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()
