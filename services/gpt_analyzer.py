"""
CCTP Analyzer - Service d'analyse GPT-4
Chardonnet Conseil - Janvier 2026

Ce module envoie les textes extraits à GPT-4 via OpenRouter
pour analyser le CCTP et identifier les non-conformités.
"""

import json
import logging
import requests
from typing import Optional

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    GPT_MAX_TOKENS,
    GPT_TEMPERATURE,
    GPT_TIMEOUT,
    DOMAINES_CCAG
)

logger = logging.getLogger(__name__)

# =============================================================================
# PROMPT SYSTÈME
# =============================================================================

SYSTEM_PROMPT = """Tu es un expert juridique en marchés publics français, spécialisé dans l'analyse des CCTP (Cahier des Clauses Techniques Particulières).

Tu disposes de trois sources de référence :
1. Le CCAG (Cahier des Clauses Administratives Générales) du domaine concerné
2. Le Code de la Commande Publique
3. Le CCTP à analyser

MISSION : Analyser le CCTP en le comparant au CCAG fourni et au Code de la Commande Publique. Identifie TOUTES les non-conformités, clauses manquantes, risques juridiques et recommandations d'amélioration.

RÈGLES D'ANALYSE :
1. Cite TOUJOURS l'extrait exact du CCTP concerné (pour permettre l'annotation du document)
2. Référence les articles précis du CCAG et/ou du Code de la Commande Publique
3. Classe chaque remarque par gravité : "haute" (bloquant), "moyenne" (important), "basse" (amélioration)
4. Sois exhaustif mais pertinent - ne signale que les vrais problèmes
5. Adapte ton analyse au domaine du CCAG fourni

FORMAT DE RÉPONSE OBLIGATOIRE (JSON STRICT) :
{
    "remarques": [
        {
            "extrait_texte": "Le texte EXACT du CCTP concerné (copie fidèle pour localisation)",
            "constat": "Description factuelle de ce qui est écrit ou manquant",
            "probleme": "Explication du risque juridique ou de la non-conformité",
            "references_juridiques": "Article X du CCAG, Article L.XXXX-X du Code CCP",
            "recommandation": "Action corrective recommandée",
            "gravite": "haute|moyenne|basse"
        }
    ],
    "synthese": "Résumé global de l'analyse en 2-3 phrases",
    "statistiques": {
        "total_remarques": 0,
        "haute": 0,
        "moyenne": 0,
        "basse": 0
    }
}

IMPORTANT : 
- Réponds UNIQUEMENT avec le JSON, sans texte avant ou après
- L'extrait_texte doit être une copie EXACTE du texte du CCTP pour permettre sa localisation
- Ne génère pas de remarques si le CCTP est conforme sur un point"""


# =============================================================================
# FONCTION PRINCIPALE D'ANALYSE
# =============================================================================

def analyze_cctp(ccag_text: str, cctp_text: str, code_ccp_text: str, domaine: str = "travaux") -> dict:
    """
    Analyse le CCTP en utilisant GPT-4 via OpenRouter.
    
    Args:
        ccag_text: Texte extrait du CCAG
        cctp_text: Texte extrait du CCTP
        code_ccp_text: Texte du Code de la Commande Publique
        domaine: Domaine du CCAG (travaux, fournitures, pi, tic, moe, industriel)
    
    Returns:
        dict: Résultat de l'analyse avec remarques et statistiques
        {
            "success": True/False,
            "remarques": [...],
            "synthese": "...",
            "statistiques": {...},
            "error": "..." (si erreur)
        }
    """
    
    # Vérifier la clé API
    if not OPENROUTER_API_KEY:
        logger.error("Clé API OpenRouter non configurée")
        return {
            "success": False,
            "error": "Clé API OpenRouter non configurée. Vérifiez le fichier .env",
            "remarques": [],
            "statistiques": {"total_remarques": 0, "haute": 0, "moyenne": 0, "basse": 0}
        }
    
    # Récupérer le label du domaine
    domaine_label = DOMAINES_CCAG.get(domaine, "Travaux")
    
    # Construire le message utilisateur
    user_message = f"""Voici les documents à analyser :

## 📘 CCAG - {domaine_label}

{ccag_text}

---

## 📚 CODE DE LA COMMANDE PUBLIQUE (extraits)

{code_ccp_text}

---

## 📄 CCTP À ANALYSER

{cctp_text}

---

Analyse ce CCTP et identifie toutes les non-conformités, risques juridiques et améliorations nécessaires.
Réponds UNIQUEMENT en JSON selon le format spécifié."""

    # Préparer la requête
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://cctp-analyzer.chardonnet-conseil.fr",
        "X-Title": "CCTP Analyzer - Chardonnet Conseil"
    }
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": GPT_MAX_TOKENS,
        "temperature": GPT_TEMPERATURE
    }
    
    logger.info(f"Envoi de la requête à OpenRouter (modèle: {OPENROUTER_MODEL})")
    logger.info(f"Taille du prompt: CCAG={len(ccag_text)} chars, CCTP={len(cctp_text)} chars, CCP={len(code_ccp_text)} chars")
    
    try:
        # Envoyer la requête
        response = requests.post(
            OPENROUTER_BASE_URL,
            headers=headers,
            json=payload,
            timeout=GPT_TIMEOUT
        )
        
        # Vérifier le statut HTTP
        if response.status_code != 200:
            error_msg = f"Erreur API OpenRouter: {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail.get('error', {}).get('message', response.text)}"
            except:
                error_msg += f" - {response.text[:200]}"
            
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "remarques": [],
                "statistiques": {"total_remarques": 0, "haute": 0, "moyenne": 0, "basse": 0}
            }
        
        # Parser la réponse
        response_data = response.json()
        
        # Extraire le contenu
        if "choices" not in response_data or len(response_data["choices"]) == 0:
            logger.error("Réponse OpenRouter vide ou invalide")
            return {
                "success": False,
                "error": "Réponse vide de l'API",
                "remarques": [],
                "statistiques": {"total_remarques": 0, "haute": 0, "moyenne": 0, "basse": 0}
            }
        
        content = response_data["choices"][0]["message"]["content"]
        logger.info(f"Réponse reçue: {len(content)} caractères")
        
        # Parser le JSON
        result = parse_gpt_response(content)
        
        if result["success"]:
            logger.info(f"Analyse réussie: {result['statistiques']['total_remarques']} remarques trouvées")
            logger.info(f"  - Haute: {result['statistiques']['haute']}")
            logger.info(f"  - Moyenne: {result['statistiques']['moyenne']}")
            logger.info(f"  - Basse: {result['statistiques']['basse']}")
        
        return result
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout après {GPT_TIMEOUT} secondes")
        return {
            "success": False,
            "error": f"Timeout: l'analyse a pris plus de {GPT_TIMEOUT} secondes",
            "remarques": [],
            "statistiques": {"total_remarques": 0, "haute": 0, "moyenne": 0, "basse": 0}
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion: {e}")
        return {
            "success": False,
            "error": f"Erreur de connexion à OpenRouter: {e}",
            "remarques": [],
            "statistiques": {"total_remarques": 0, "haute": 0, "moyenne": 0, "basse": 0}
        }
        
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")
        return {
            "success": False,
            "error": f"Erreur inattendue: {e}",
            "remarques": [],
            "statistiques": {"total_remarques": 0, "haute": 0, "moyenne": 0, "basse": 0}
        }


# =============================================================================
# PARSING DE LA RÉPONSE GPT
# =============================================================================

def parse_gpt_response(content: str) -> dict:
    """
    Parse la réponse JSON de GPT-4.
    
    Gère les cas où le JSON est entouré de ```json ... ```
    
    Args:
        content: Contenu de la réponse GPT
    
    Returns:
        dict: Résultat parsé avec success=True/False
    """
    
    # Nettoyer le contenu
    content = content.strip()
    
    # Enlever les balises markdown si présentes
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
        logger.error(f"Contenu reçu: {content[:500]}...")
        return {
            "success": False,
            "error": f"Erreur de parsing JSON: {e}",
            "remarques": [],
            "statistiques": {"total_remarques": 0, "haute": 0, "moyenne": 0, "basse": 0}
        }
    
    # Valider et normaliser la structure
    remarques = data.get("remarques", [])
    
    # Valider chaque remarque
    validated_remarques = []
    for i, r in enumerate(remarques):
        if not isinstance(r, dict):
            logger.warning(f"Remarque {i} ignorée: pas un dictionnaire")
            continue
        
        # Vérifier les champs requis
        validated = {
            "extrait_texte": r.get("extrait_texte", ""),
            "constat": r.get("constat", ""),
            "probleme": r.get("probleme", ""),
            "references_juridiques": r.get("references_juridiques", ""),
            "recommandation": r.get("recommandation", ""),
            "gravite": r.get("gravite", "moyenne").lower()
        }
        
        # Valider la gravité
        if validated["gravite"] not in ["haute", "moyenne", "basse"]:
            validated["gravite"] = "moyenne"
        
        # Ignorer les remarques sans extrait de texte
        if not validated["extrait_texte"]:
            logger.warning(f"Remarque {i} ignorée: pas d'extrait de texte")
            continue
        
        validated_remarques.append(validated)
    
    # Calculer les statistiques
    stats = {
        "total_remarques": len(validated_remarques),
        "haute": len([r for r in validated_remarques if r["gravite"] == "haute"]),
        "moyenne": len([r for r in validated_remarques if r["gravite"] == "moyenne"]),
        "basse": len([r for r in validated_remarques if r["gravite"] == "basse"])
    }
    
    return {
        "success": True,
        "remarques": validated_remarques,
        "synthese": data.get("synthese", "Analyse terminée."),
        "statistiques": stats
    }


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== Test du module gpt_analyzer ===")
    print(f"Clé API configurée: {'Oui' if OPENROUTER_API_KEY else 'Non'}")
    print(f"Modèle: {OPENROUTER_MODEL}")
    print(f"Timeout: {GPT_TIMEOUT}s")
    
    # Test simple
    if OPENROUTER_API_KEY:
        print("\nTest avec textes minimaux...")
        result = analyze_cctp(
            ccag_text="Article 1: Dispositions générales du CCAG Travaux.",
            cctp_text="Article 1: Le présent CCTP définit les travaux de construction.",
            code_ccp_text="Article L.2111-1: Les marchés publics sont des contrats conclus à titre onéreux.",
            domaine="travaux"
        )
        print(f"Succès: {result['success']}")
        if result['success']:
            print(f"Remarques: {result['statistiques']['total_remarques']}")
        else:
            print(f"Erreur: {result.get('error')}")
    else:
        print("\n⚠️ Clé API non configurée - test impossible")
