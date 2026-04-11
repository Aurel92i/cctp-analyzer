"""
CCAP Analyzer - Application Flask
Lexigency - 2026

Application web d'analyse automatisée de CCAP pour les marchés publics.

Documents de RÉFÉRENCE (zone gauche) : CCAG (pré-chargé) + CCTP (uploadé)
Document à ANALYSER et ANNOTER (zone droite) : CCAP (uploadé)
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_file,
)
from werkzeug.utils import secure_filename

from config import (
    get_config,
    UPLOADS_CCTP_DIR,
    UPLOADS_CCAP_DIR,
    OUTPUTS_DIR,
    CCAG_DIR,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_MB,
    DOMAINES_CCAG,
)

# =============================================================================
# CONFIGURATION DE L'APPLICATION
# =============================================================================

app = Flask(__name__)
app.config.from_object(get_config())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# =============================================================================
# STOCKAGE EN MÉMOIRE DES JOBS
# =============================================================================

jobs = {}
sessions = {}

# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_session_id():
    return str(uuid.uuid4())


def generate_job_id():
    return str(uuid.uuid4())


def get_session_id():
    session_id = request.headers.get("X-Session-ID") or request.cookies.get("session_id")
    if not session_id:
        session_id = generate_session_id()
    return session_id


def cleanup_old_files(directory, max_age_hours=24):
    try:
        now = datetime.now()
        for filepath in Path(directory).glob("*"):
            if filepath.is_file() and filepath.name != ".gitkeep":
                file_age = now - datetime.fromtimestamp(filepath.stat().st_mtime)
                if file_age.total_seconds() > max_age_hours * 3600:
                    filepath.unlink()
                    logger.info(f"Fichier supprimé (ancien): {filepath}")
    except Exception as e:
        logger.error(f"Erreur cleanup: {e}")


def _upload_file(upload_dir, session_key_prefix):
    """Logique commune d'upload pour CCTP et CCAP."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "Aucun fichier fourni"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"success": False, "error": "Nom de fichier vide"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Extension non autorisée. Utilisez .docx ou .pdf"}), 400

    session_id = get_session_id()
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_filename = f"{session_id}_{timestamp}_{filename}"
    filepath = upload_dir / unique_filename

    file.save(filepath)
    logger.info(f"{session_key_prefix.upper()} uploadé: {filepath}")

    # Si c'est un PDF, conversion automatique en DOCX.
    # Le reste du pipeline (orchestrator, word_annotator) reçoit toujours un .docx.
    if filepath.suffix.lower() == ".pdf":
        try:
            from services.document_extractor import convert_pdf_to_docx
            logger.info(f"Conversion PDF → DOCX pour {session_key_prefix.upper()}: {filepath.name}")
            docx_path = convert_pdf_to_docx(filepath)
            logger.info(f"{session_key_prefix.upper()} converti en DOCX: {docx_path}")
            effective_path = docx_path
        except Exception as e:
            logger.error(f"Erreur conversion PDF → DOCX ({session_key_prefix}): {e}")
            return jsonify({
                "success": False,
                "error": f"Erreur lors de la conversion du PDF en DOCX: {e}",
            }), 500
    else:
        effective_path = filepath

    if session_id not in sessions:
        sessions[session_id] = {}

    sessions[session_id].update({
        f"{session_key_prefix}_filename": filename,
        f"{session_key_prefix}_path": str(effective_path),
        f"{session_key_prefix}_uploaded_at": datetime.now().isoformat(),
    })

    return jsonify({"success": True, "filename": filename, "session_id": session_id})


# =============================================================================
# ROUTES - PAGES HTML
# =============================================================================


@app.route("/")
def index():
    return render_template("index.html", domaines=DOMAINES_CCAG)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat(), "version": "2.0.0"})


# =============================================================================
# ROUTES - UPLOAD DES FICHIERS
# =============================================================================
# PAS de route /upload/ccag : le CCAG est pré-chargé depuis data/ccag/


@app.route("/upload/cctp", methods=["POST"])
def upload_cctp():
    """Upload du fichier CCTP (document de référence technique)."""
    try:
        return _upload_file(UPLOADS_CCTP_DIR, "cctp")
    except Exception as e:
        logger.error(f"Erreur upload CCTP: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/upload/ccap", methods=["POST"])
def upload_ccap():
    """Upload du fichier CCAP (document à analyser et annoter)."""
    try:
        return _upload_file(UPLOADS_CCAP_DIR, "ccap")
    except Exception as e:
        logger.error(f"Erreur upload CCAP: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# ROUTES - ANALYSE
# =============================================================================


@app.route("/analyze", methods=["POST"])
def analyze():
    """Lance l'analyse du CCAP."""
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id") or get_session_id()
        domaine = data.get("domaine", "travaux")

        # Valider le domaine
        if domaine not in DOMAINES_CCAG:
            domaine = "travaux"

        if session_id not in sessions:
            return jsonify({"success": False, "error": "Session invalide. Veuillez uploader les fichiers."}), 400

        session = sessions[session_id]

        # Le CCAP est obligatoire (uploadé par le client)
        if not session.get("ccap_path"):
            return jsonify({"success": False, "error": "CCAP manquant. Veuillez uploader le CCAP."}), 400

        if not Path(session["ccap_path"]).exists():
            return jsonify({"success": False, "error": "CCAP introuvable. Veuillez le ré-uploader."}), 400

        # Vérifier que le CCAG existe dans data/ccag/
        ccag_file = CCAG_DIR / f"{domaine}.docx"
        if not ccag_file.exists():
            return jsonify({
                "success": False,
                "error": f"CCAG '{DOMAINES_CCAG[domaine]}' introuvable sur le serveur. Contactez l'administrateur.",
            }), 500

        # Le CCTP est optionnel
        cctp_path = session.get("cctp_path")
        if cctp_path and not Path(cctp_path).exists():
            cctp_path = None

        job_id = generate_job_id()

        jobs[job_id] = {
            "status": "processing",
            "progress": 0,
            "step": "Initialisation...",
            "session_id": session_id,
            "cctp_path": cctp_path,
            "ccap_path": session["ccap_path"],
            "domaine": domaine,
            "created_at": datetime.now().isoformat(),
            "output_path": None,
            "error": None,
            "remarques": None,
        }

        logger.info(f"Job créé: {job_id} pour session {session_id} (domaine: {domaine})")

        import threading

        thread = threading.Thread(target=run_analysis, args=(job_id,))
        thread.daemon = True
        thread.start()

        return jsonify({"success": True, "job_id": job_id, "status": jobs[job_id]["status"]})

    except Exception as e:
        logger.error(f"Erreur lancement analyse: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def run_analysis(job_id):
    """Exécute l'analyse du CCAP avec l'architecture multi-agents + RAG."""
    job = jobs[job_id]

    try:

        def progress_callback(progress, step):
            job["progress"] = progress
            job["step"] = step

        from services.orchestrator import run_full_analysis

        result = run_full_analysis(
            ccap_path=job["ccap_path"],
            cctp_path=job.get("cctp_path"),
            domaine=job["domaine"],
            session_id=job["session_id"],
            progress_callback=progress_callback,
        )

        if not result["success"]:
            raise Exception(result.get("error", "Erreur inconnue"))

        job["remarques"] = result.get("remarques", [])
        job["synthese"] = result.get("synthese", "")
        job["statistiques"] = result.get("statistiques", {})
        job["niveau_risque"] = result.get("niveau_risque", "modéré")
        job["points_critiques"] = result.get("points_critiques", [])

        # Annotation Word sur le CCAP
        job["progress"] = 92
        job["step"] = "Insertion des commentaires dans le CCAP..."

        from services.word_annotator import annotate_document

        output_filename = f"CCAP_annote_{job_id[:8]}.docx"
        output_path = OUTPUTS_DIR / output_filename

        annotation_result = annotate_document(
            ccap_path=job["ccap_path"],
            remarques=job["remarques"],
            output_path=str(output_path),
        )

        if not annotation_result["success"]:
            raise Exception(annotation_result.get("error", "Erreur annotation"))

        job["output_path"] = str(output_path)
        job["annotation_stats"] = {
            "comments_added": annotation_result.get("comments_added", 0),
            "comments_not_found": annotation_result.get("comments_not_found", 0),
        }

        logger.info(
            f"[{job_id}] Annotation terminée: "
            f"{annotation_result.get('comments_added', 0)} commentaires ajoutés"
        )

        job["progress"] = 100
        job["step"] = "Analyse terminée !"
        job["status"] = "completed"
        logger.info(f"[{job_id}] Analyse terminée avec succès")

    except Exception as e:
        import traceback

        logger.error(f"[{job_id}] Erreur: {e}")
        traceback.print_exc()
        job["status"] = "error"
        job["error"] = str(e)
        job["step"] = f"Erreur: {e}"


# =============================================================================
# ROUTES - STATUT ET TÉLÉCHARGEMENT
# =============================================================================


@app.route("/status/<job_id>")
def get_status(job_id):
    if job_id not in jobs:
        return jsonify({"success": False, "error": "Job introuvable"}), 404

    job = jobs[job_id]

    response = {
        "success": True,
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "step": job["step"],
    }

    if job["status"] == "completed":
        remarques = job.get("remarques", [])
        response["remarques_count"] = len(remarques)
        response["stats"] = {
            "total": len(remarques),
            "haute": len([r for r in remarques if r.get("gravite") == "haute"]),
            "moyenne": len([r for r in remarques if r.get("gravite") == "moyenne"]),
            "basse": len([r for r in remarques if r.get("gravite") == "basse"]),
        }
        response["niveau_risque"] = job.get("niveau_risque", "modéré")
        response["synthese"] = job.get("synthese", "")
        response["points_critiques"] = job.get("points_critiques", [])

    if job["status"] == "error":
        response["error"] = job["error"]

    return jsonify(response)


@app.route("/download/<job_id>")
def download(job_id):
    """Télécharge le CCAP annoté."""
    if job_id not in jobs:
        return jsonify({"success": False, "error": "Job introuvable"}), 404

    job = jobs[job_id]

    if job["status"] != "completed":
        return jsonify({"success": False, "error": "Analyse non terminée", "status": job["status"]}), 400

    if not job.get("output_path") or not Path(job["output_path"]).exists():
        return jsonify({"success": False, "error": "Fichier de sortie introuvable"}), 404

    original_filename = Path(job["ccap_path"]).stem
    download_filename = f"{original_filename}_ANALYSE.docx"

    return send_file(
        job["output_path"],
        as_attachment=True,
        download_name=download_filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# =============================================================================
# ROUTES - UTILITAIRES
# =============================================================================


@app.route("/session/info")
def session_info():
    session_id = get_session_id()

    if session_id not in sessions:
        return jsonify({"success": True, "session_id": session_id, "has_cctp": False, "has_ccap": False})

    session = sessions[session_id]

    return jsonify({
        "success": True,
        "session_id": session_id,
        "has_cctp": bool(session.get("cctp_path")),
        "has_ccap": bool(session.get("ccap_path")),
        "cctp_filename": session.get("cctp_filename"),
        "ccap_filename": session.get("ccap_filename"),
    })


@app.route("/cleanup", methods=["POST"])
def cleanup():
    try:
        cleanup_old_files(UPLOADS_CCTP_DIR)
        cleanup_old_files(UPLOADS_CCAP_DIR)
        cleanup_old_files(OUTPUTS_DIR)
        return jsonify({"success": True, "message": "Nettoyage effectué"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# GESTION DES ERREURS
# =============================================================================


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"success": False, "error": f"Fichier trop volumineux. Maximum: {MAX_FILE_SIZE_MB} MB"}), 413


@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "Ressource non trouvée"}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Erreur 500: {error}")
    return jsonify({"success": False, "error": "Erreur interne du serveur"}), 500


@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"Erreur non gérée: {error}")
    return jsonify({"success": False, "error": str(error)}), 500


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    cleanup_old_files(UPLOADS_CCTP_DIR, max_age_hours=24)
    cleanup_old_files(UPLOADS_CCAP_DIR, max_age_hours=24)
    cleanup_old_files(OUTPUTS_DIR, max_age_hours=24)

    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_ENV") == "development"

    logger.info(f"Démarrage de CCAP Analyzer sur le port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
