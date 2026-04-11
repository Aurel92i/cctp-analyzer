"""
CCAP Analyzer - Configuration centralisée
Lexigency - 2026
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# =============================================================================
# CHEMINS
# =============================================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_CCTP_DIR = UPLOADS_DIR / "cctp"
UPLOADS_CCAP_DIR = UPLOADS_DIR / "ccap"
OUTPUTS_DIR = BASE_DIR / "outputs"

# Base vectorielle
VECTOR_STORE_DIR = DATA_DIR / "vector_store"

# CCAG pré-chargés (jamais uploadés par le client)
CCAG_DIR = DATA_DIR / "ccag"

# Code de la Commande Publique
CODE_COMMANDE_PUBLIQUE_FILE = DATA_DIR / "code_commande_publique.txt"

# Créer les dossiers s'ils n'existent pas
for directory in [DATA_DIR, UPLOADS_CCTP_DIR, UPLOADS_CCAP_DIR, OUTPUTS_DIR, VECTOR_STORE_DIR, CCAG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# =============================================================================
# API OPENROUTER
# =============================================================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# =============================================================================
# MODÈLES LLM PAR RÔLE
# =============================================================================
MODEL_LIGHT = os.getenv("MODEL_LIGHT", "openai/gpt-4o-mini")
MODEL_MEDIUM = os.getenv("MODEL_MEDIUM", "anthropic/claude-sonnet-4-20250514")
MODEL_EXPERT = os.getenv("MODEL_EXPERT", "openai/gpt-4o")

# =============================================================================
# PARAMÈTRES LLM
# =============================================================================
GPT_MAX_TOKENS = 8000
GPT_TEMPERATURE = 0.2
GPT_TIMEOUT = 300

# =============================================================================
# LIMITES DE CARACTÈRES
# =============================================================================
MAX_CHARS_CCAG = 400000
MAX_CHARS_CCTP = 400000
MAX_CHARS_CODE_CCP = 200000
MAX_CHARS_PER_SECTION = 30000

# =============================================================================
# UPLOAD
# =============================================================================
MAX_FILE_SIZE_MB = 20
ALLOWED_EXTENSIONS = {"docx", "pdf"}
ALLOWED_MIMETYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
}

# =============================================================================
# DOMAINES CCAG
# =============================================================================
DOMAINES_CCAG = {
    "travaux": "Travaux",
    "fournitures": "Fournitures courantes et services",
    "pi": "Prestations intellectuelles",
    "tic": "Techniques de l'information et de la communication",
    "moe": "Maîtrise d'œuvre",
    "industriel": "Marchés industriels",
}

# =============================================================================
# APPLICATION FLASK
# =============================================================================
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_MB * 1024 * 1024

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}

def get_config():
    env = os.getenv("FLASK_ENV", "development")
    return config.get(env, config["default"])
