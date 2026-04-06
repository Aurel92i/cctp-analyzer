"""
CCTP Analyzer V2 - Client LLM unifié.
Chardonnet Conseil - 2026

Abstrait les appels à OpenRouter avec différents modèles selon le rôle :
- light  : modèle pas cher pour extraction de structure (GPT-4o-mini)
- medium : modèle intermédiaire pour synthèse (Claude Sonnet)
- expert : meilleur modèle pour audit juridique (GPT-4o)
"""

import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Modèles par rôle — configurable via variables d'environnement
MODELS = {
    "light": os.getenv("MODEL_LIGHT", "openai/gpt-4o-mini"),
    "medium": os.getenv("MODEL_MEDIUM", "anthropic/claude-sonnet-4-20250514"),
    "expert": os.getenv("MODEL_EXPERT", "openai/gpt-4o"),
}


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model_role: str = "expert",
    max_tokens: int = 6000,
    temperature: float = 0.2,
) -> dict:
    """
    Appelle un LLM via OpenRouter et parse la réponse JSON.

    Args:
        system_prompt: instruction système
        user_prompt: message utilisateur
        model_role: "light", "medium", ou "expert"
        max_tokens: tokens max de réponse
        temperature: 0.0-1.0

    Returns:
        dict parsé depuis la réponse JSON du LLM, avec "success": True/False ajouté.
    """
    if not OPENROUTER_API_KEY:
        return {"success": False, "error": "Clé API OpenRouter non configurée"}

    model = MODELS.get(model_role, MODELS["expert"])

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://cctp-analyzer.chardonnet-conseil.fr",
        "X-Title": "CCTP Analyzer V2",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        logger.debug(f"Appel LLM [{model_role}] model={model}")
        response = requests.post(
            OPENROUTER_BASE_URL,
            headers=headers,
            json=payload,
            timeout=300,
        )

        if response.status_code != 200:
            error_msg = f"Erreur API ({response.status_code})"
            try:
                detail = response.json()
                error_msg += f": {detail.get('error', {}).get('message', '')}"
            except Exception:
                pass
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Nettoyer les blocs markdown JSON
        content = _strip_json_markdown(content)

        parsed = json.loads(content)
        parsed["success"] = True
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"JSON invalide du LLM: {e}")
        return {"success": False, "error": f"Réponse LLM non-JSON: {e}"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Timeout API (300s)"}
    except Exception as e:
        logger.error(f"Erreur LLM: {e}")
        return {"success": False, "error": str(e)}


def _strip_json_markdown(content: str) -> str:
    """Retire les balises ```json ... ``` autour du JSON."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()
