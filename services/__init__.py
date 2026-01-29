"""
CCTP Analyzer - Services
Chardonnet Conseil - Janvier 2026
"""

from .document_extractor import (
    extract_text_from_docx,
    extract_ccag,
    extract_cctp,
    load_code_commande_publique,
    get_document_info
)

from .gpt_analyzer import analyze_cctp

from .word_annotator import annotate_document

__all__ = [
    # Document extractor (Étape 5)
    "extract_text_from_docx",
    "extract_ccag",
    "extract_cctp",
    "load_code_commande_publique",
    "get_document_info",
    # GPT Analyzer (Étape 6)
    "analyze_cctp",
    # Word Annotator (Étape 7)
    "annotate_document",
]
