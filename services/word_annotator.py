"""
CCTP Analyzer - Service d'annotation Word avec COMMENTAIRES NATIFS
Chardonnet Conseil - Janvier 2026

Ce module insère de VRAIS commentaires Word (panneau Révisions)
dans le CCTP à partir des remarques générées par l'analyse GPT-4.

Les commentaires apparaissent dans le panneau latéral de Word,
comme des commentaires de révision classiques.
"""

import logging
import re
import zipfile
import shutil
import tempfile
import os
from datetime import datetime
from pathlib import Path
from copy import deepcopy

from docx import Document
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement
from lxml import etree

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTES
# =============================================================================

COMMENT_AUTHOR = "CCTP Analyzer"
COMMENT_INITIALS = "CA"

GRAVITY_HEADERS = {
    "haute": "🔴 GRAVITÉ HAUTE",
    "moyenne": "🟠 GRAVITÉ MOYENNE",
    "basse": "🟢 GRAVITÉ BASSE"
}

# Namespaces XML pour Word
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

WORD_NSMAP = {
    'w': W_NS,
    'r': R_NS,
}


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def annotate_document(cctp_path: str, remarques: list, output_path: str) -> dict:
    """
    Annote un document CCTP avec de VRAIS commentaires Word natifs.
    
    Les commentaires apparaissent dans le panneau "Révisions" de Word.
    
    Args:
        cctp_path: Chemin vers le CCTP original
        remarques: Liste des remarques de l'analyse GPT-4
        output_path: Chemin de sortie pour le CCTP annoté
    
    Returns:
        dict: Statistiques d'annotation
    """
    try:
        logger.info(f"Annotation du document: {cctp_path}")
        logger.info(f"Nombre de remarques: {len(remarques)}")
        
        if not remarques:
            # Pas de remarques, copier simplement le document
            shutil.copy(cctp_path, output_path)
            return {
                "success": True,
                "output_path": str(output_path),
                "comments_added": 0,
                "comments_not_found": 0,
                "total_remarques": 0
            }
        
        # Créer l'annotateur
        annotator = WordCommentAnnotator(cctp_path)
        
        # Ajouter chaque remarque comme commentaire
        comments_added = 0
        comments_not_found = 0
        
        for i, remarque in enumerate(remarques):
            success = annotator.add_comment(remarque, comment_id=i)
            if success:
                comments_added += 1
            else:
                comments_not_found += 1
        
        # Sauvegarder le document
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        annotator.save(output_path)
        
        logger.info(f"Document annoté sauvegardé: {output_path}")
        logger.info(f"Commentaires ajoutés: {comments_added}/{len(remarques)}")
        
        return {
            "success": True,
            "output_path": str(output_path),
            "comments_added": comments_added,
            "comments_not_found": comments_not_found,
            "total_remarques": len(remarques)
        }
        
    except Exception as e:
        logger.error(f"Erreur annotation: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "comments_added": 0,
            "comments_not_found": 0
        }


# =============================================================================
# CLASSE D'ANNOTATION AVEC COMMENTAIRES NATIFS
# =============================================================================

class WordCommentAnnotator:
    """
    Classe pour ajouter des commentaires Word natifs à un document.
    
    Manipule directement le XML OOXML pour insérer des commentaires
    qui apparaissent dans le panneau Révisions de Word.
    """
    
    def __init__(self, docx_path: str):
        """
        Initialise l'annotateur.
        
        Args:
            docx_path: Chemin vers le document DOCX
        """
        self.docx_path = Path(docx_path)
        self.doc = Document(docx_path)
        self.comments = []  # Liste des commentaires à ajouter
        self.next_comment_id = 0
    
    def _format_comment_text(self, remarque: dict) -> str:
        """
        Formate le texte du commentaire à partir d'une remarque.
        
        Args:
            remarque: Dictionnaire de la remarque
        
        Returns:
            str: Texte formaté pour le commentaire
        """
        gravite = remarque.get("gravite", "moyenne")
        header = GRAVITY_HEADERS.get(gravite, "🟠 GRAVITÉ MOYENNE")
        
        parts = [
            header,
            "━" * 25,
            "",
            "📋 CONSTAT:",
            remarque.get("constat", "N/A"),
            "",
            "⚠️ PROBLÈME:",
            remarque.get("probleme", "N/A"),
            "",
            "📖 RÉFÉRENCES:",
            remarque.get("references_juridiques", "N/A"),
            "",
            "✅ RECOMMANDATION:",
            remarque.get("recommandation", "N/A")
        ]
        
        return "\n".join(parts)
    
    def _normalize_text(self, text: str) -> str:
        """Normalise un texte pour la comparaison."""
        if not text:
            return ""
        # Supprimer espaces multiples, convertir en minuscules
        return ' '.join(text.lower().split())

    def _iter_all_paragraphs(self):
        """Itère sur tous les paragraphes du document (corps + tableaux)."""
        for para in self.doc.paragraphs:
            yield para
        for table in self.doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        yield para

    def _find_paragraph_with_text(self, search_text: str):
        """
        Trouve le paragraphe contenant le texte recherché.
        Utilise un matching flou (SequenceMatcher) pour tolérer les
        différences mineures entre l'extrait LLM et le texte réel.

        Returns:
            tuple: (paragraph, found) ou (None, False)
        """
        from difflib import SequenceMatcher

        if not search_text or len(search_text) < 10:
            return None, False

        search_normalized = self._normalize_text(search_text)

        # Stratégie 1 : recherche exacte (rapide)
        for para in self._iter_all_paragraphs():
            para_normalized = self._normalize_text(para.text)
            if search_normalized in para_normalized:
                return para, True

        # Stratégie 2 : recherche par les 50 premiers caractères
        search_start = search_normalized[:50]
        for para in self._iter_all_paragraphs():
            para_normalized = self._normalize_text(para.text)
            if len(para_normalized) > 20 and search_start in para_normalized:
                return para, True

        # Stratégie 3 : matching flou (SequenceMatcher)
        best_match = None
        best_score = 0
        threshold = 0.65

        for para in self._iter_all_paragraphs():
            para_normalized = self._normalize_text(para.text)
            if len(para_normalized) < 20:
                continue

            # Comparer des fenêtres glissantes si le paragraphe est long
            if len(para_normalized) > len(search_normalized) * 2:
                window = len(search_normalized)
                for start in range(0, len(para_normalized) - window + 1, 20):
                    chunk = para_normalized[start:start + window]
                    score = SequenceMatcher(
                        None, search_normalized[:100], chunk[:100]
                    ).ratio()
                    if score > best_score:
                        best_score = score
                        best_match = para
            else:
                score = SequenceMatcher(
                    None, search_normalized[:100], para_normalized[:100]
                ).ratio()
                if score > best_score:
                    best_score = score
                    best_match = para

        if best_match and best_score >= threshold:
            return best_match, True

        return None, False
    
    def _create_comment_element(self, comment_id: int, text: str) -> etree._Element:
        """
        Crée l'élément XML du commentaire.
        
        Args:
            comment_id: ID unique du commentaire
            text: Texte du commentaire
        
        Returns:
            Element XML w:comment
        """
        # Créer l'élément comment
        comment = OxmlElement('w:comment')
        comment.set(qn('w:id'), str(comment_id))
        comment.set(qn('w:author'), COMMENT_AUTHOR)
        comment.set(qn('w:initials'), COMMENT_INITIALS)
        comment.set(qn('w:date'), datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
        
        # Ajouter le texte du commentaire (chaque ligne dans un paragraphe)
        for line in text.split('\n'):
            p = OxmlElement('w:p')
            r = OxmlElement('w:r')
            t = OxmlElement('w:t')
            t.set(qn('xml:space'), 'preserve')
            t.text = line
            r.append(t)
            p.append(r)
            comment.append(p)
        
        return comment
    
    def _add_comment_to_paragraph(self, para, comment_id: int, comment_text: str):
        """
        Ajoute les marqueurs de commentaire à un paragraphe.
        
        Args:
            para: Paragraphe python-docx
            comment_id: ID du commentaire
            comment_text: Texte du commentaire
        """
        p = para._element
        
        # Créer commentRangeStart
        range_start = OxmlElement('w:commentRangeStart')
        range_start.set(qn('w:id'), str(comment_id))
        
        # Créer commentRangeEnd
        range_end = OxmlElement('w:commentRangeEnd')
        range_end.set(qn('w:id'), str(comment_id))
        
        # Créer la référence au commentaire (le marqueur visible)
        comment_ref_run = OxmlElement('w:r')
        comment_ref = OxmlElement('w:commentReference')
        comment_ref.set(qn('w:id'), str(comment_id))
        comment_ref_run.append(comment_ref)
        
        # Insérer au début du paragraphe
        if len(p) > 0:
            p.insert(0, range_start)
        else:
            p.append(range_start)
        
        # Ajouter la fin et la référence à la fin
        p.append(range_end)
        p.append(comment_ref_run)
        
        # Stocker le commentaire pour l'ajout ultérieur
        comment_element = self._create_comment_element(comment_id, comment_text)
        self.comments.append(comment_element)
    
    def add_comment(self, remarque: dict, comment_id: int = None) -> bool:
        """
        Ajoute un commentaire pour une remarque.
        
        Args:
            remarque: Dictionnaire de la remarque
            comment_id: ID optionnel du commentaire
        
        Returns:
            True si le commentaire a été ajouté, False sinon
        """
        extrait = remarque.get("extrait_texte", "")
        
        if not extrait:
            logger.warning("Remarque sans extrait de texte, ignorée")
            return False
        
        # Trouver le paragraphe
        para, found = self._find_paragraph_with_text(extrait)
        
        if not found:
            logger.warning(f"Texte non trouvé: {extrait[:80]}...")
            return False
        
        # Générer l'ID si non fourni
        if comment_id is None:
            comment_id = self.next_comment_id
        self.next_comment_id = max(self.next_comment_id, comment_id + 1)
        
        # Formater le texte du commentaire
        comment_text = self._format_comment_text(remarque)
        
        # Ajouter le commentaire au paragraphe
        self._add_comment_to_paragraph(para, comment_id, comment_text)
        
        logger.debug(f"Commentaire {comment_id} ajouté pour: {extrait[:50]}...")
        return True
    
    def _inject_comments_part(self, docx_path: str):
        """
        Injecte la partie comments.xml dans le document DOCX.
        
        Args:
            docx_path: Chemin vers le fichier DOCX à modifier
        """
        if not self.comments:
            return
        
        # Créer le XML des commentaires
        comments_root = etree.Element(qn('w:comments'), nsmap={'w': W_NS})
        for comment in self.comments:
            comments_root.append(comment)
        
        comments_xml = etree.tostring(
            comments_root, 
            xml_declaration=True, 
            encoding='UTF-8',
            standalone=True
        )
        
        # Ouvrir le DOCX comme ZIP et ajouter comments.xml
        with zipfile.ZipFile(docx_path, 'a') as zf:
            # Vérifier si comments.xml existe déjà
            if 'word/comments.xml' in zf.namelist():
                # Lire le contenu existant et fusionner (complexe, on remplace)
                pass
            
            # Écrire comments.xml
            zf.writestr('word/comments.xml', comments_xml)
        
        # Mettre à jour [Content_Types].xml et les relations
        self._update_content_types(docx_path)
        self._update_relationships(docx_path)
    
    def _update_content_types(self, docx_path: str):
        """Met à jour [Content_Types].xml pour inclure comments.xml."""
        try:
            with zipfile.ZipFile(docx_path, 'r') as zf:
                content_types = zf.read('[Content_Types].xml').decode('utf-8')
            
            # Vérifier si le type existe déjà
            if 'word/comments.xml' not in content_types:
                # Ajouter l'Override pour comments.xml
                override = '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>'
                
                # Insérer avant </Types>
                content_types = content_types.replace('</Types>', f'{override}\n</Types>')
                
                # Réécrire le fichier
                self._update_zip_file(docx_path, '[Content_Types].xml', content_types.encode('utf-8'))
        
        except Exception as e:
            logger.warning(f"Erreur mise à jour Content_Types: {e}")
    
    def _update_relationships(self, docx_path: str):
        """Met à jour word/_rels/document.xml.rels pour inclure comments.xml."""
        try:
            rels_path = 'word/_rels/document.xml.rels'
            
            with zipfile.ZipFile(docx_path, 'r') as zf:
                if rels_path in zf.namelist():
                    rels_content = zf.read(rels_path).decode('utf-8')
                else:
                    # Créer un fichier rels basique
                    rels_content = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
            
            # Vérifier si la relation existe déjà
            if 'comments.xml' not in rels_content:
                # Trouver un nouvel ID de relation
                import re
                existing_ids = re.findall(r'Id="rId(\d+)"', rels_content)
                next_id = max([int(x) for x in existing_ids], default=0) + 1
                
                # Ajouter la relation
                rel = f'<Relationship Id="rId{next_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>'
                
                # Insérer avant </Relationships>
                rels_content = rels_content.replace('</Relationships>', f'{rel}\n</Relationships>')
                
                # Réécrire le fichier
                self._update_zip_file(docx_path, rels_path, rels_content.encode('utf-8'))
        
        except Exception as e:
            logger.warning(f"Erreur mise à jour Relations: {e}")
    
    def _update_zip_file(self, zip_path: str, file_name: str, content: bytes):
        """
        Met à jour un fichier dans un ZIP existant.
        
        Args:
            zip_path: Chemin vers le fichier ZIP
            file_name: Nom du fichier à mettre à jour dans le ZIP
            content: Nouveau contenu
        """
        # Créer un fichier temporaire
        temp_path = zip_path + '.tmp'
        
        with zipfile.ZipFile(zip_path, 'r') as zin:
            with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.namelist():
                    if item == file_name:
                        zout.writestr(item, content)
                    else:
                        zout.writestr(item, zin.read(item))
                
                # Ajouter le fichier s'il n'existait pas
                if file_name not in zin.namelist():
                    zout.writestr(file_name, content)
        
        # Remplacer l'original
        os.replace(temp_path, zip_path)
    
    def save(self, output_path: str):
        """
        Sauvegarde le document annoté.
        
        Args:
            output_path: Chemin de sortie
        """
        # Sauvegarder le document avec les marqueurs
        self.doc.save(output_path)
        
        # Injecter la partie comments.xml
        if self.comments:
            self._inject_comments_part(output_path)
        
        logger.info(f"Document sauvegardé avec {len(self.comments)} commentaires: {output_path}")


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Test du module word_annotator ===")
    print(f"Auteur des commentaires: {COMMENT_AUTHOR}")
    print("Ce module crée de VRAIS commentaires Word natifs (panneau Révisions)")
