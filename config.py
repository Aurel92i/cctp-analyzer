"""
CCTP Analyzer - Configuration
Chardonnet Conseil - Janvier 2026
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
UPLOADS_CCAG_DIR = UPLOADS_DIR / "ccag"
UPLOADS_CCTP_DIR = UPLOADS_DIR / "cctp"
UPLOADS_CCAP_DIR = UPLOADS_DIR / "ccap"
OUTPUTS_DIR = BASE_DIR / "outputs"

# Créer les dossiers s'ils n'existent pas
for directory in [DATA_DIR, UPLOADS_CCAG_DIR, UPLOADS_CCTP_DIR, UPLOADS_CCAP_DIR, OUTPUTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# =============================================================================
# API OPENROUTER
# =============================================================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4-turbo")

# =============================================================================
# MODÈLES LLM PAR RÔLE (V2 multi-agents)
# =============================================================================
MODEL_LIGHT = os.getenv("MODEL_LIGHT", "openai/gpt-4o-mini")
MODEL_MEDIUM = os.getenv("MODEL_MEDIUM", "anthropic/claude-sonnet-4-20250514")
MODEL_EXPERT = os.getenv("MODEL_EXPERT", "openai/gpt-4o")

# =============================================================================
# PARAMÈTRES GPT-4
# =============================================================================
GPT_MAX_TOKENS = 8000
GPT_TEMPERATURE = 0.2  # Précision pour l'analyse juridique
GPT_TIMEOUT = 300  # 5 minutes max par appel (multi-passes = plusieurs appels)

# =============================================================================
# LIMITES DE CARACTÈRES (augmentées pour analyse complète)
# =============================================================================
MAX_CHARS_CCAG = 400000      # ~100k tokens pour le CCAG complet
MAX_CHARS_CCTP = 400000      # ~100k tokens pour le CCTP complet
MAX_CHARS_CODE_CCP = 200000  # ~50k tokens pour le Code CCP

# Limite par section pour l'analyse multi-passes
MAX_CHARS_PER_SECTION = 30000  # ~7.5k tokens par section

# =============================================================================
# FICHIERS FIXES
# =============================================================================
CODE_COMMANDE_PUBLIQUE_FILE = DATA_DIR / "code_commande_publique.txt"

# =============================================================================
# BASE VECTORIELLE
# =============================================================================
VECTOR_STORE_DIR = DATA_DIR / "vector_store"
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# UPLOAD
# =============================================================================
MAX_FILE_SIZE_MB = 20
ALLOWED_EXTENSIONS = {"docx"}
ALLOWED_MIMETYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
    "industriel": "Marchés industriels"
}

# =============================================================================
# APPLICATION FLASK
# =============================================================================
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_MB * 1024 * 1024  # En bytes
    
class DevelopmentConfig(Config):
    DEBUG = True
    
class ProductionConfig(Config):
    DEBUG = False

# Sélection de la config selon l'environnement
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig
}

def get_config():
    env = os.getenv("FLASK_ENV", "development")
    return config.get(env, config["default"])
