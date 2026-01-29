"""
CCTP Analyzer - Application Flask
Chardonnet Conseil - Janvier 2026

Application web d'analyse automatisée de CCTP pour les marchés publics.
Déploiement sur Render.
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import (
    Flask, 
    request, 
    jsonify, 
    render_template, 
    send_file,
    abort
)
from werkzeug.utils import secure_filename

from config import (
    get_config,
    UPLOADS_CCAG_DIR,
    UPLOADS_CCTP_DIR,
    OUTPUTS_DIR,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_MB,
    DOMAINES_CCAG
)

# =============================================================================
# CONFIGURATION DE L'APPLICATION
# =============================================================================

app = Flask(__name__)
app.config.from_object(get_config())

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# STOCKAGE EN MÉMOIRE DES JOBS (simplifié pour Render)
# =============================================================================

# Structure: { job_id: { status, progress, step, ccag_path, cctp_path, output_path, error, ... } }
jobs = {}

# Structure: { session_id: { ccag_filename, cctp_filename, ccag_path, cctp_path, domaine } }
sessions = {}

# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def allowed_file(filename):
    """Vérifie si l'extension du fichier est autorisée."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_session_id():
    """Génère un ID de session unique."""
    return str(uuid.uuid4())


def generate_job_id():
    """Génère un ID de job unique."""
    return str(uuid.uuid4())


def get_session_id():
    """Récupère ou crée un ID de session depuis les headers/cookies."""
    session_id = request.headers.get('X-Session-ID') or request.cookies.get('session_id')
    if not session_id:
        session_id = generate_session_id()
    return session_id


def cleanup_old_files(directory, max_age_hours=24):
    """Supprime les fichiers plus vieux que max_age_hours."""
    try:
        now = datetime.now()
        for filepath in Path(directory).glob('*'):
            if filepath.is_file() and filepath.name != '.gitkeep':
                file_age = now - datetime.fromtimestamp(filepath.stat().st_mtime)
                if file_age.total_seconds() > max_age_hours * 3600:
                    filepath.unlink()
                    logger.info(f"Fichier supprimé (ancien): {filepath}")
    except Exception as e:
        logger.error(f"Erreur cleanup: {e}")


# =============================================================================
# ROUTES - PAGES HTML
# =============================================================================

@app.route('/')
def index():
    """Page d'accueil avec l'interface d'upload."""
    return render_template('index.html', domaines=DOMAINES_CCAG)


@app.route('/health')
def health():
    """Health check pour Render."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })


# =============================================================================
# ROUTES - UPLOAD DES FICHIERS
# =============================================================================

@app.route('/upload/ccag', methods=['POST'])
def upload_ccag():
    """
    Upload du fichier CCAG (référentiel).
    
    Attend:
    - Fichier dans request.files['file']
    - Domaine dans request.form['domaine'] (optionnel)
    
    Retourne:
    - { success: true, filename: "...", session_id: "..." }
    """
    try:
        # Vérifier la présence du fichier
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "Aucun fichier fourni"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"success": False, "error": "Nom de fichier vide"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "success": False, 
                "error": f"Extension non autorisée. Utilisez: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Récupérer le domaine
        domaine = request.form.get('domaine', 'travaux')
        if domaine not in DOMAINES_CCAG:
            domaine = 'travaux'
        
        # Générer/récupérer la session
        session_id = get_session_id()
        
        # Sauvegarder le fichier
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{session_id}_{timestamp}_{filename}"
        filepath = UPLOADS_CCAG_DIR / unique_filename
        
        file.save(filepath)
        logger.info(f"CCAG uploadé: {filepath}")
        
        # Mettre à jour la session
        if session_id not in sessions:
            sessions[session_id] = {}
        
        sessions[session_id].update({
            "ccag_filename": filename,
            "ccag_path": str(filepath),
            "domaine": domaine,
            "ccag_uploaded_at": datetime.now().isoformat()
        })
        
        return jsonify({
            "success": True,
            "filename": filename,
            "domaine": domaine,
            "domaine_label": DOMAINES_CCAG[domaine],
            "session_id": session_id
        })
        
    except Exception as e:
        logger.error(f"Erreur upload CCAG: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/upload/cctp', methods=['POST'])
def upload_cctp():
    """
    Upload du fichier CCTP (à analyser).
    
    Attend:
    - Fichier dans request.files['file']
    
    Retourne:
    - { success: true, filename: "...", session_id: "..." }
    """
    try:
        # Vérifier la présence du fichier
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "Aucun fichier fourni"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"success": False, "error": "Nom de fichier vide"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "success": False, 
                "error": f"Extension non autorisée. Utilisez: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Générer/récupérer la session
        session_id = get_session_id()
        
        # Sauvegarder le fichier
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{session_id}_{timestamp}_{filename}"
        filepath = UPLOADS_CCTP_DIR / unique_filename
        
        file.save(filepath)
        logger.info(f"CCTP uploadé: {filepath}")
        
        # Mettre à jour la session
        if session_id not in sessions:
            sessions[session_id] = {}
        
        sessions[session_id].update({
            "cctp_filename": filename,
            "cctp_path": str(filepath),
            "cctp_uploaded_at": datetime.now().isoformat()
        })
        
        return jsonify({
            "success": True,
            "filename": filename,
            "session_id": session_id
        })
        
    except Exception as e:
        logger.error(f"Erreur upload CCTP: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# ROUTES - ANALYSE
# =============================================================================

@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Lance l'analyse du CCTP.
    
    Attend:
    - session_id dans le body JSON ou header
    
    Retourne:
    - { success: true, job_id: "...", status: "processing" }
    """
    try:
        # Récupérer la session
        data = request.get_json() or {}
        session_id = data.get('session_id') or get_session_id()
        
        if session_id not in sessions:
            return jsonify({
                "success": False, 
                "error": "Session invalide. Veuillez uploader les fichiers."
            }), 400
        
        session = sessions[session_id]
        
        # Vérifier que les deux fichiers sont présents
        if not session.get('ccag_path'):
            return jsonify({
                "success": False, 
                "error": "CCAG manquant. Veuillez uploader le CCAG."
            }), 400
        
        if not session.get('cctp_path'):
            return jsonify({
                "success": False, 
                "error": "CCTP manquant. Veuillez uploader le CCTP."
            }), 400
        
        # Vérifier que les fichiers existent toujours
        if not Path(session['ccag_path']).exists():
            return jsonify({
                "success": False, 
                "error": "CCAG introuvable. Veuillez le ré-uploader."
            }), 400
        
        if not Path(session['cctp_path']).exists():
            return jsonify({
                "success": False, 
                "error": "CCTP introuvable. Veuillez le ré-uploader."
            }), 400
        
        # Créer un job d'analyse
        job_id = generate_job_id()
        
        jobs[job_id] = {
            "status": "processing",
            "progress": 0,
            "step": "Initialisation...",
            "session_id": session_id,
            "ccag_path": session['ccag_path'],
            "cctp_path": session['cctp_path'],
            "domaine": session.get('domaine', 'travaux'),
            "created_at": datetime.now().isoformat(),
            "output_path": None,
            "error": None,
            "remarques": None
        }
        
        logger.info(f"Job créé: {job_id} pour session {session_id}")
        
        # Lancer l'analyse en arrière-plan
        # NOTE: Pour l'instant, on fait l'analyse de manière synchrone
        # Dans une version future, on pourrait utiliser Celery ou threading
        run_analysis(job_id)
        
        return jsonify({
            "success": True,
            "job_id": job_id,
            "status": jobs[job_id]["status"]
        })
        
    except Exception as e:
        logger.error(f"Erreur lancement analyse: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def run_analysis(job_id):
    """
    Exécute l'analyse du CCTP.
    
    Étape 5 : Extraction du texte ✅
    Étape 6 : Analyse GPT-4 (à implémenter)
    Étape 7 : Annotation Word (à implémenter)
    """
    from services.document_extractor import extract_ccag, extract_cctp, load_code_commande_publique
    import shutil
    
    job = jobs[job_id]
    
    try:
        # === ÉTAPE 5 : Extraction du texte ===
        
        # Extraction CCAG
        job["progress"] = 10
        job["step"] = "Extraction du texte du CCAG..."
        logger.info(f"[{job_id}] Extraction CCAG depuis {job['ccag_path']}")
        
        ccag_text = extract_ccag(job["ccag_path"])
        job["ccag_chars"] = len(ccag_text)
        logger.info(f"[{job_id}] CCAG extrait: {len(ccag_text)} caractères")
        
        # Extraction CCTP
        job["progress"] = 20
        job["step"] = "Extraction du texte du CCTP..."
        logger.info(f"[{job_id}] Extraction CCTP depuis {job['cctp_path']}")
        
        cctp_text = extract_cctp(job["cctp_path"])
        job["cctp_chars"] = len(cctp_text)
        logger.info(f"[{job_id}] CCTP extrait: {len(cctp_text)} caractères")
        
        # Chargement Code de la Commande Publique
        job["progress"] = 30
        job["step"] = "Chargement du Code de la Commande Publique..."
        logger.info(f"[{job_id}] Chargement Code CCP")
        
        code_ccp_text = load_code_commande_publique()
        job["code_ccp_chars"] = len(code_ccp_text)
        logger.info(f"[{job_id}] Code CCP chargé: {len(code_ccp_text)} caractères")
        
        # Stocker les textes pour l'étape 6
        job["extracted_texts"] = {
            "ccag": ccag_text,
            "cctp": cctp_text,
            "code_ccp": code_ccp_text
        }
        
        # === ÉTAPE 6 : Analyse GPT-4 MULTI-PASSES ===
        job["progress"] = 35
        job["step"] = "Analyse multi-passes en cours (découpage en sections)..."
        logger.info(f"[{job_id}] Lancement analyse GPT-4 MULTI-PASSES")
        
        from services.gpt_analyzer import analyze_cctp
        
        result = analyze_cctp(
            ccag_text=ccag_text,
            cctp_text=cctp_text,
            code_ccp_text=code_ccp_text,
            domaine=job["domaine"]
        )
        
        if not result["success"]:
            raise Exception(result.get("error", "Erreur inconnue lors de l'analyse GPT-4"))
        
        job["remarques"] = result.get("remarques", [])
        job["synthese"] = result.get("synthese", "")
        job["statistiques"] = result.get("statistiques", {})
        job["niveau_risque"] = result.get("niveau_risque", "modéré")
        job["points_critiques"] = result.get("points_critiques", [])
        
        sections_analysees = result.get("statistiques", {}).get("sections_analysees", 0)
        logger.info(f"[{job_id}] Analyse GPT-4 terminée: {len(job['remarques'])} remarques sur {sections_analysees} sections")
        
        job["progress"] = 70
        job["step"] = "Préparation de l'annotation Word..."
        
        # === ÉTAPE 7 : Annotation Word ===
        job["progress"] = 80
        job["step"] = "Insertion des annotations dans le document..."
        logger.info(f"[{job_id}] Annotation Word avec {len(job['remarques'])} remarques")
        
        from services.word_annotator import annotate_document
        
        output_filename = f"CCTP_annote_{job_id[:8]}.docx"
        output_path = OUTPUTS_DIR / output_filename
        
        annotation_result = annotate_document(
            cctp_path=job["cctp_path"],
            remarques=job["remarques"],
            output_path=str(output_path)
        )
        
        if not annotation_result["success"]:
            raise Exception(annotation_result.get("error", "Erreur lors de l'annotation"))
        
        job["output_path"] = str(output_path)
        job["annotation_stats"] = {
            "highlights_added": annotation_result.get("highlights_added", 0),
            "highlights_not_found": annotation_result.get("highlights_not_found", 0)
        }
        
        logger.info(f"[{job_id}] Annotation terminée: {annotation_result.get('highlights_added', 0)} passages surlignés")
        
        # Terminé
        job["progress"] = 100
        job["step"] = "Analyse terminée !"
        job["status"] = "completed"
        logger.info(f"[{job_id}] Analyse terminée avec succès")
        logger.info(f"[{job_id}] Stats: CCAG={job.get('ccag_chars',0)} chars, CCTP={job.get('cctp_chars',0)} chars, CCP={job.get('code_ccp_chars',0)} chars")
        
    except FileNotFoundError as e:
        logger.error(f"[{job_id}] Fichier non trouvé: {e}")
        job["status"] = "error"
        job["error"] = f"Fichier non trouvé: {e}"
        job["step"] = "Erreur: fichier manquant"
        
    except ValueError as e:
        logger.error(f"[{job_id}] Erreur de format: {e}")
        job["status"] = "error"
        job["error"] = f"Erreur de format: {e}"
        job["step"] = "Erreur: format invalide"
        
    except Exception as e:
        logger.error(f"[{job_id}] Erreur inattendue: {e}")
        job["status"] = "error"
        job["error"] = str(e)
        job["step"] = f"Erreur: {e}"


# =============================================================================
# ROUTES - STATUT ET TÉLÉCHARGEMENT
# =============================================================================

@app.route('/status/<job_id>')
def get_status(job_id):
    """
    Retourne le statut d'un job d'analyse.
    
    Retourne:
    - { status: "processing|completed|error", progress: 0-100, step: "...", ... }
    """
    if job_id not in jobs:
        return jsonify({"success": False, "error": "Job introuvable"}), 404
    
    job = jobs[job_id]
    
    response = {
        "success": True,
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "step": job["step"]
    }
    
    if job["status"] == "completed":
        response["remarques_count"] = len(job.get("remarques", []))
        # Compter par gravité
        remarques = job.get("remarques", [])
        response["stats"] = {
            "total": len(remarques),
            "haute": len([r for r in remarques if r.get("gravite") == "haute"]),
            "moyenne": len([r for r in remarques if r.get("gravite") == "moyenne"]),
            "basse": len([r for r in remarques if r.get("gravite") == "basse"])
        }
        # Nouvelles infos multi-passes
        response["niveau_risque"] = job.get("niveau_risque", "modéré")
        response["synthese"] = job.get("synthese", "")
        response["points_critiques"] = job.get("points_critiques", [])
    
    if job["status"] == "error":
        response["error"] = job["error"]
    
    return jsonify(response)


@app.route('/download/<job_id>')
def download(job_id):
    """
    Télécharge le CCTP annoté.
    
    Retourne:
    - Fichier .docx
    """
    if job_id not in jobs:
        return jsonify({"success": False, "error": "Job introuvable"}), 404
    
    job = jobs[job_id]
    
    if job["status"] != "completed":
        return jsonify({
            "success": False, 
            "error": "Analyse non terminée",
            "status": job["status"]
        }), 400
    
    if not job.get("output_path") or not Path(job["output_path"]).exists():
        return jsonify({
            "success": False, 
            "error": "Fichier de sortie introuvable"
        }), 404
    
    # Nom du fichier pour le téléchargement
    original_filename = Path(job["cctp_path"]).stem
    download_filename = f"{original_filename}_ANALYSE.docx"
    
    return send_file(
        job["output_path"],
        as_attachment=True,
        download_name=download_filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


# =============================================================================
# ROUTES - UTILITAIRES
# =============================================================================

@app.route('/session/info')
def session_info():
    """Retourne les infos de la session courante (pour debug)."""
    session_id = get_session_id()
    
    if session_id not in sessions:
        return jsonify({
            "success": True,
            "session_id": session_id,
            "has_ccag": False,
            "has_cctp": False
        })
    
    session = sessions[session_id]
    
    return jsonify({
        "success": True,
        "session_id": session_id,
        "has_ccag": bool(session.get("ccag_path")),
        "has_cctp": bool(session.get("cctp_path")),
        "ccag_filename": session.get("ccag_filename"),
        "cctp_filename": session.get("cctp_filename"),
        "domaine": session.get("domaine")
    })


@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Nettoie les fichiers anciens (admin)."""
    try:
        cleanup_old_files(UPLOADS_CCAG_DIR)
        cleanup_old_files(UPLOADS_CCTP_DIR)
        cleanup_old_files(OUTPUTS_DIR)
        return jsonify({"success": True, "message": "Nettoyage effectué"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# GESTION DES ERREURS
# =============================================================================

@app.errorhandler(413)
def request_entity_too_large(error):
    """Erreur fichier trop gros."""
    return jsonify({
        "success": False,
        "error": f"Fichier trop volumineux. Maximum: {MAX_FILE_SIZE_MB} MB"
    }), 413


@app.errorhandler(404)
def not_found(error):
    """Erreur page non trouvée."""
    return jsonify({
        "success": False,
        "error": "Ressource non trouvée"
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Erreur serveur."""
    logger.error(f"Erreur 500: {error}")
    return jsonify({
        "success": False,
        "error": "Erreur interne du serveur"
    }), 500


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == '__main__':
    # Nettoyage au démarrage
    cleanup_old_files(UPLOADS_CCAG_DIR, max_age_hours=24)
    cleanup_old_files(UPLOADS_CCTP_DIR, max_age_hours=24)
    cleanup_old_files(OUTPUTS_DIR, max_age_hours=24)
    
    # Démarrage du serveur
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    logger.info(f"Démarrage de CCTP Analyzer sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
