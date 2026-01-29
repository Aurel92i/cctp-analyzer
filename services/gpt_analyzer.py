"""
CCTP Analyzer - Service d'analyse GPT-4 MULTI-PASSES
Chardonnet Conseil - Janvier 2026

Architecture améliorée :
1. Découpage du CCTP en sections
2. Analyse section par section
3. Synthèse finale de cohérence

Cette approche garantit une analyse de qualité professionnelle.
"""

import json
import logging
import re
import requests
from typing import List, Dict, Optional, Tuple

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    GPT_MAX_TOKENS,
    GPT_TEMPERATURE,
    GPT_TIMEOUT,
    DOMAINES_CCAG,
    MAX_CHARS_PER_SECTION
)

logger = logging.getLogger(__name__)

# =============================================================================
# PROMPTS SPÉCIALISÉS
# =============================================================================

PROMPT_DECOUPE_SECTIONS = """Tu es un expert en analyse de documents de marchés publics.

Analyse ce CCTP et identifie sa structure en sections principales.

Pour chaque section, retourne :
- Le titre de la section
- Le numéro (I, II, III ou 1, 2, 3 ou Article 1, etc.)
- La position de début (premiers mots distinctifs)
- La position de fin (derniers mots avant la section suivante)

CCTP À ANALYSER :
{cctp_text}

Réponds UNIQUEMENT en JSON :
{{
    "sections": [
        {{
            "numero": "I",
            "titre": "Dispositions générales",
            "debut": "Les premiers mots de la section...",
            "fin": "Les derniers mots de la section..."
        }}
    ]
}}"""

PROMPT_ANALYSE_SECTION = """Tu es un expert juridique en marchés publics français.

CONTEXTE :
- Domaine : {domaine}
- Section analysée : {section_titre}

DOCUMENTS DE RÉFÉRENCE :

## CCAG - {domaine_label} (extraits pertinents)
{ccag_extract}

## CODE DE LA COMMANDE PUBLIQUE (extraits pertinents)
{ccp_extract}

## SECTION DU CCTP À ANALYSER
{section_text}

---

MISSION : Analyse cette section du CCTP avec une extrême rigueur. Identifie :
1. Les non-conformités au CCAG
2. Les violations du Code de la Commande Publique
3. Les clauses abusives ou déséquilibrées
4. Les imprécisions juridiques risquées
5. Les clauses manquantes obligatoires

RÈGLES :
- Cite TOUJOURS l'extrait EXACT du CCTP (copie mot pour mot)
- L'extrait doit être assez long (20-100 mots) pour être retrouvé dans le document
- Référence les articles précis (Article X du CCAG, Article L.XXXX-X CCP)
- Classe par gravité : "haute" (bloquant/illégal), "moyenne" (risque important), "basse" (amélioration)
- Sois exhaustif : ne rate aucun problème
- Sois précis : évite les remarques vagues

FORMAT JSON OBLIGATOIRE :
{{
    "remarques": [
        {{
            "extrait_texte": "Copie EXACTE et LONGUE du passage du CCTP concerné",
            "constat": "Description factuelle précise",
            "probleme": "Explication du risque juridique concret",
            "references_juridiques": "Article X CCAG, Article L.XXXX-X CCP",
            "recommandation": "Correction précise à apporter",
            "gravite": "haute|moyenne|basse"
        }}
    ]
}}

Réponds UNIQUEMENT avec le JSON, sans texte avant ou après."""

PROMPT_SYNTHESE_FINALE = """Tu es un expert juridique senior en marchés publics français.

Tu as analysé un CCTP section par section. Voici toutes les remarques identifiées :

{all_remarques}

---

MISSION FINALE :
1. Vérifie la cohérence globale des remarques
2. Identifie les problèmes TRANSVERSAUX (qui touchent plusieurs sections)
3. Ajoute les remarques GLOBALES manquantes (structure du document, cohérence générale)
4. Priorise les remarques les plus critiques

Retourne :
- Les remarques transversales à ajouter
- Une synthèse globale du document
- Le niveau de risque global (élevé/modéré/faible)

FORMAT JSON :
{{
    "remarques_transversales": [
        {{
            "extrait_texte": "Élément concerné ou 'Document global'",
            "constat": "Constat transversal",
            "probleme": "Problème de cohérence globale",
            "references_juridiques": "Références",
            "recommandation": "Recommandation",
            "gravite": "haute|moyenne|basse"
        }}
    ],
    "synthese_globale": "Analyse globale du CCTP en 3-5 phrases",
    "niveau_risque_global": "élevé|modéré|faible",
    "points_critiques": ["Point 1", "Point 2", "Point 3"]
}}"""


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def analyze_cctp(ccag_text: str, cctp_text: str, code_ccp_text: str, domaine: str = "travaux") -> dict:
    """
    Analyse le CCTP avec l'architecture MULTI-PASSES.
    
    1. Découpe le CCTP en sections
    2. Analyse chaque section individuellement
    3. Synthèse finale pour cohérence globale
    
    Args:
        ccag_text: Texte complet du CCAG
        cctp_text: Texte complet du CCTP
        code_ccp_text: Texte du Code de la Commande Publique
        domaine: Domaine du CCAG
    
    Returns:
        dict: Résultat complet de l'analyse
    """
    
    if not OPENROUTER_API_KEY:
        return {
            "success": False,
            "error": "Clé API OpenRouter non configurée",
            "remarques": [],
            "statistiques": {"total_remarques": 0, "haute": 0, "moyenne": 0, "basse": 0}
        }
    
    domaine_label = DOMAINES_CCAG.get(domaine, "Travaux")
    all_remarques = []
    
    logger.info("=" * 60)
    logger.info("DÉMARRAGE ANALYSE MULTI-PASSES")
    logger.info(f"CCAG: {len(ccag_text)} chars | CCTP: {len(cctp_text)} chars | CCP: {len(code_ccp_text)} chars")
    logger.info("=" * 60)
    
    # =========================================================================
    # PHASE 1 : DÉCOUPAGE EN SECTIONS
    # =========================================================================
    
    logger.info("PHASE 1: Découpage du CCTP en sections...")
    sections = split_cctp_into_sections(cctp_text)
    logger.info(f"  → {len(sections)} sections identifiées")
    
    for i, section in enumerate(sections):
        logger.info(f"     Section {i+1}: {section['titre'][:50]}... ({len(section['texte'])} chars)")
    
    # =========================================================================
    # PHASE 2 : ANALYSE SECTION PAR SECTION
    # =========================================================================
    
    logger.info("PHASE 2: Analyse section par section...")
    
    for i, section in enumerate(sections):
        logger.info(f"  Analyse section {i+1}/{len(sections)}: {section['titre'][:40]}...")
        
        # Extraire les parties pertinentes du CCAG et CCP
        ccag_extract = extract_relevant_context(ccag_text, section['titre'], max_chars=15000)
        ccp_extract = extract_relevant_context(code_ccp_text, section['titre'], max_chars=10000)
        
        # Analyser cette section
        section_result = analyze_single_section(
            section_text=section['texte'],
            section_titre=section['titre'],
            ccag_extract=ccag_extract,
            ccp_extract=ccp_extract,
            domaine=domaine,
            domaine_label=domaine_label
        )
        
        if section_result['success']:
            remarques = section_result.get('remarques', [])
            all_remarques.extend(remarques)
            logger.info(f"     → {len(remarques)} remarques trouvées")
        else:
            logger.warning(f"     → Erreur: {section_result.get('error', 'Inconnue')}")
    
    logger.info(f"  TOTAL après phase 2: {len(all_remarques)} remarques")
    
    # =========================================================================
    # PHASE 3 : SYNTHÈSE FINALE
    # =========================================================================
    
    logger.info("PHASE 3: Synthèse finale et vérification de cohérence...")
    
    synthese_result = generate_final_synthesis(all_remarques)
    
    if synthese_result['success']:
        # Ajouter les remarques transversales
        remarques_transversales = synthese_result.get('remarques_transversales', [])
        all_remarques.extend(remarques_transversales)
        logger.info(f"  → {len(remarques_transversales)} remarques transversales ajoutées")
        
        synthese_globale = synthese_result.get('synthese_globale', '')
        niveau_risque = synthese_result.get('niveau_risque_global', 'modéré')
        points_critiques = synthese_result.get('points_critiques', [])
    else:
        synthese_globale = "Analyse terminée."
        niveau_risque = "modéré"
        points_critiques = []
    
    # =========================================================================
    # RÉSULTAT FINAL
    # =========================================================================
    
    # Dédupliquer les remarques (au cas où)
    all_remarques = deduplicate_remarques(all_remarques)
    
    # Calculer les statistiques
    stats = {
        "total_remarques": len(all_remarques),
        "haute": len([r for r in all_remarques if r.get("gravite") == "haute"]),
        "moyenne": len([r for r in all_remarques if r.get("gravite") == "moyenne"]),
        "basse": len([r for r in all_remarques if r.get("gravite") == "basse"]),
        "sections_analysees": len(sections)
    }
    
    logger.info("=" * 60)
    logger.info("ANALYSE TERMINÉE")
    logger.info(f"  Total remarques: {stats['total_remarques']}")
    logger.info(f"  - Haute: {stats['haute']} | Moyenne: {stats['moyenne']} | Basse: {stats['basse']}")
    logger.info(f"  Niveau de risque global: {niveau_risque}")
    logger.info("=" * 60)
    
    return {
        "success": True,
        "remarques": all_remarques,
        "synthese": synthese_globale,
        "niveau_risque": niveau_risque,
        "points_critiques": points_critiques,
        "statistiques": stats
    }


# =============================================================================
# DÉCOUPAGE EN SECTIONS
# =============================================================================

def split_cctp_into_sections(cctp_text: str) -> List[Dict]:
    """
    Découpe le CCTP en sections logiques.
    
    Détecte les patterns courants :
    - ARTICLE 1, ARTICLE 2...
    - I. , II. , III. ...
    - CHAPITRE 1, CHAPITRE 2...
    - 1. , 2. , 3. ...
    - TITRE I, TITRE II...
    """
    
    sections = []
    
    # Patterns de détection des sections (ordre de priorité)
    section_patterns = [
        # Articles numérotés
        (r'\n\s*(ARTICLE\s+\d+[.\s:-]*[^\n]*)', 'ARTICLE'),
        # Chapitres
        (r'\n\s*(CHAPITRE\s+[IVXLC\d]+[.\s:-]*[^\n]*)', 'CHAPITRE'),
        # Titres romains
        (r'\n\s*(TITRE\s+[IVXLC]+[.\s:-]*[^\n]*)', 'TITRE'),
        # Numéros romains seuls
        (r'\n\s*([IVXLC]+\s*[.\-–]\s*[A-Z][^\n]*)', 'ROMAIN'),
        # Numéros arabes avec point
        (r'\n\s*(\d+\s*[.\-–]\s*[A-Z][^\n]{10,})', 'NUMERO'),
    ]
    
    # Essayer chaque pattern
    best_splits = []
    best_pattern_name = ""
    
    for pattern, pattern_name in section_patterns:
        matches = list(re.finditer(pattern, cctp_text, re.IGNORECASE))
        if len(matches) >= 3 and len(matches) > len(best_splits):
            best_splits = matches
            best_pattern_name = pattern_name
    
    if best_splits:
        logger.info(f"  Pattern détecté: {best_pattern_name} ({len(best_splits)} sections)")
        
        for i, match in enumerate(best_splits):
            titre = match.group(1).strip()
            start = match.start()
            
            # Fin = début de la section suivante ou fin du document
            if i < len(best_splits) - 1:
                end = best_splits[i + 1].start()
            else:
                end = len(cctp_text)
            
            section_text = cctp_text[start:end].strip()
            
            # Limiter la taille de la section si trop grande
            if len(section_text) > MAX_CHARS_PER_SECTION:
                # Découper en sous-sections
                sub_sections = split_large_section(section_text, titre)
                sections.extend(sub_sections)
            else:
                sections.append({
                    "titre": titre[:100],
                    "texte": section_text
                })
    
    # Si aucun pattern trouvé, découper par taille
    if not sections:
        logger.info("  Aucun pattern de section détecté, découpage par taille")
        sections = split_by_size(cctp_text, MAX_CHARS_PER_SECTION)
    
    return sections


def split_large_section(text: str, titre: str) -> List[Dict]:
    """Découpe une section trop grande en sous-parties."""
    sub_sections = []
    
    # Découper par paragraphes
    paragraphs = text.split('\n\n')
    current_text = ""
    part_num = 1
    
    for para in paragraphs:
        if len(current_text) + len(para) > MAX_CHARS_PER_SECTION:
            if current_text:
                sub_sections.append({
                    "titre": f"{titre} (partie {part_num})",
                    "texte": current_text.strip()
                })
                part_num += 1
                current_text = para
        else:
            current_text += "\n\n" + para
    
    if current_text.strip():
        sub_sections.append({
            "titre": f"{titre} (partie {part_num})" if part_num > 1 else titre,
            "texte": current_text.strip()
        })
    
    return sub_sections


def split_by_size(text: str, max_size: int) -> List[Dict]:
    """Découpe un texte en sections de taille fixe."""
    sections = []
    
    # Découper par paragraphes
    paragraphs = text.split('\n\n')
    current_text = ""
    section_num = 1
    
    for para in paragraphs:
        if len(current_text) + len(para) > max_size:
            if current_text:
                sections.append({
                    "titre": f"Section {section_num}",
                    "texte": current_text.strip()
                })
                section_num += 1
                current_text = para
        else:
            current_text += "\n\n" + para
    
    if current_text.strip():
        sections.append({
            "titre": f"Section {section_num}",
            "texte": current_text.strip()
        })
    
    return sections


# =============================================================================
# EXTRACTION DE CONTEXTE PERTINENT
# =============================================================================

def extract_relevant_context(reference_text: str, section_titre: str, max_chars: int = 15000) -> str:
    """
    Extrait les parties du CCAG/CCP pertinentes pour une section donnée.
    
    Utilise des mots-clés du titre de section pour trouver les passages pertinents.
    """
    
    # Mots-clés à rechercher basés sur le titre
    keywords = extract_keywords(section_titre)
    
    # Découper le texte de référence en paragraphes
    paragraphs = reference_text.split('\n\n')
    
    # Scorer chaque paragraphe
    scored_paragraphs = []
    for para in paragraphs:
        if len(para.strip()) < 50:
            continue
        
        score = 0
        para_lower = para.lower()
        
        for keyword in keywords:
            if keyword.lower() in para_lower:
                score += 2
        
        # Bonus pour les articles/dispositions
        if re.search(r'article\s+\d+|article\s+[livxlc]+', para_lower):
            score += 1
        
        if score > 0:
            scored_paragraphs.append((score, para))
    
    # Trier par score et prendre les meilleurs
    scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
    
    result = ""
    for score, para in scored_paragraphs:
        if len(result) + len(para) > max_chars:
            break
        result += para + "\n\n"
    
    # Si pas assez de contenu pertinent, prendre le début du document
    if len(result) < max_chars // 2:
        result = reference_text[:max_chars]
    
    return result.strip()


def extract_keywords(titre: str) -> List[str]:
    """Extrait les mots-clés significatifs d'un titre."""
    
    # Mots à ignorer
    stopwords = {'le', 'la', 'les', 'de', 'du', 'des', 'et', 'ou', 'un', 'une', 
                 'au', 'aux', 'en', 'pour', 'par', 'sur', 'avec', 'dans', 'ce',
                 'cette', 'ces', 'article', 'chapitre', 'titre', 'section',
                 'partie', 'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'}
    
    # Nettoyer et découper
    words = re.findall(r'\b[a-zéèêëàâäùûüôöîïç]+\b', titre.lower())
    
    # Filtrer
    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    
    # Ajouter des mots-clés techniques courants
    technical_keywords = {
        'travaux': ['exécution', 'chantier', 'délais', 'réception', 'garantie'],
        'prix': ['paiement', 'révision', 'avance', 'acompte', 'facturation'],
        'qualité': ['contrôle', 'essais', 'conformité', 'normes'],
        'sécurité': ['hygiène', 'protection', 'prévention', 'risques'],
        'délais': ['planning', 'pénalités', 'retard', 'prolongation'],
        'réception': ['réserves', 'parfait achèvement', 'garantie'],
        'sous-traitance': ['sous-traitant', 'agrément', 'paiement direct'],
        'assurance': ['responsabilité', 'dommages', 'garantie'],
    }
    
    for key, related in technical_keywords.items():
        if key in titre.lower():
            keywords.extend(related)
    
    return list(set(keywords))


# =============================================================================
# ANALYSE D'UNE SECTION
# =============================================================================

def analyze_single_section(section_text: str, section_titre: str, 
                          ccag_extract: str, ccp_extract: str,
                          domaine: str, domaine_label: str) -> dict:
    """
    Analyse une seule section du CCTP.
    """
    
    prompt = PROMPT_ANALYSE_SECTION.format(
        domaine=domaine,
        domaine_label=domaine_label,
        section_titre=section_titre,
        ccag_extract=ccag_extract,
        ccp_extract=ccp_extract,
        section_text=section_text
    )
    
    return call_gpt_api(prompt)


# =============================================================================
# SYNTHÈSE FINALE
# =============================================================================

def generate_final_synthesis(all_remarques: List[Dict]) -> dict:
    """
    Génère la synthèse finale et les remarques transversales.
    """
    
    if not all_remarques:
        return {
            "success": True,
            "remarques_transversales": [],
            "synthese_globale": "Aucune remarque identifiée.",
            "niveau_risque_global": "faible",
            "points_critiques": []
        }
    
    # Formater les remarques pour le prompt
    remarques_text = json.dumps(all_remarques, ensure_ascii=False, indent=2)
    
    prompt = PROMPT_SYNTHESE_FINALE.format(all_remarques=remarques_text)
    
    result = call_gpt_api(prompt)
    
    if result['success']:
        return {
            "success": True,
            "remarques_transversales": result.get('remarques_transversales', []),
            "synthese_globale": result.get('synthese_globale', ''),
            "niveau_risque_global": result.get('niveau_risque_global', 'modéré'),
            "points_critiques": result.get('points_critiques', [])
        }
    
    return result


# =============================================================================
# APPEL API GPT
# =============================================================================

def call_gpt_api(prompt: str) -> dict:
    """
    Appelle l'API GPT-4 via OpenRouter.
    """
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://cctp-analyzer.chardonnet-conseil.fr",
        "X-Title": "CCTP Analyzer - Chardonnet Conseil"
    }
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": GPT_MAX_TOKENS,
        "temperature": GPT_TEMPERATURE
    }
    
    try:
        response = requests.post(
            OPENROUTER_BASE_URL,
            headers=headers,
            json=payload,
            timeout=GPT_TIMEOUT
        )
        
        if response.status_code != 200:
            error_msg = f"Erreur API: {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail.get('error', {}).get('message', '')}"
            except:
                pass
            return {"success": False, "error": error_msg, "remarques": []}
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        return parse_gpt_response(content)
        
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Timeout API", "remarques": []}
    except Exception as e:
        return {"success": False, "error": str(e), "remarques": []}


def parse_gpt_response(content: str) -> dict:
    """
    Parse la réponse JSON de GPT.
    """
    
    content = content.strip()
    
    # Nettoyer les balises markdown
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    
    content = content.strip()
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Erreur parsing JSON: {e}")
        logger.error(f"Contenu: {content[:500]}...")
        return {"success": False, "error": f"Parsing JSON: {e}", "remarques": []}
    
    # Extraire et valider les remarques
    remarques = data.get("remarques", [])
    validated = []
    
    for r in remarques:
        if isinstance(r, dict) and r.get("extrait_texte"):
            validated.append({
                "extrait_texte": r.get("extrait_texte", ""),
                "constat": r.get("constat", ""),
                "probleme": r.get("probleme", ""),
                "references_juridiques": r.get("references_juridiques", ""),
                "recommandation": r.get("recommandation", ""),
                "gravite": r.get("gravite", "moyenne").lower()
            })
    
    return {
        "success": True,
        "remarques": validated,
        "remarques_transversales": data.get("remarques_transversales", []),
        "synthese_globale": data.get("synthese_globale", ""),
        "niveau_risque_global": data.get("niveau_risque_global", "modéré"),
        "points_critiques": data.get("points_critiques", [])
    }


# =============================================================================
# DÉDUPLICATION
# =============================================================================

def deduplicate_remarques(remarques: List[Dict]) -> List[Dict]:
    """
    Supprime les remarques en double.
    """
    
    seen = set()
    unique = []
    
    for r in remarques:
        # Clé basée sur l'extrait (premiers 100 caractères)
        key = r.get("extrait_texte", "")[:100].lower().strip()
        
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    
    return unique


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Module gpt_analyzer MULTI-PASSES ===")
    print(f"Clé API: {'Configurée' if OPENROUTER_API_KEY else 'Non configurée'}")
    print(f"Modèle: {OPENROUTER_MODEL}")
