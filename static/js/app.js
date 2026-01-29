/* =============================================================================
   CCTP Analyzer - JavaScript Frontend
   Chardonnet Conseil - Janvier 2026
   ============================================================================= */

// État de l'application
const state = {
    sessionId: null,
    ccagFile: null,
    cctpFile: null,
    jobId: null,
    isAnalyzing: false
};

// Éléments DOM
const elements = {
    // Dropzones
    dropzoneCcag: document.getElementById('dropzone-ccag'),
    dropzoneCctp: document.getElementById('dropzone-cctp'),
    fileCcag: document.getElementById('file-ccag'),
    fileCctp: document.getElementById('file-cctp'),
    
    // File info
    fileInfoCcag: document.getElementById('file-info-ccag'),
    fileInfoCctp: document.getElementById('file-info-cctp'),
    filenameCcag: document.getElementById('filename-ccag'),
    filenameCctp: document.getElementById('filename-cctp'),
    
    // Domaine
    domaine: document.getElementById('domaine'),
    
    // Buttons
    btnAnalyze: document.getElementById('btn-analyze'),
    btnDownload: document.getElementById('btn-download'),
    
    // Results
    resultsSection: document.getElementById('results-section'),
    progressContainer: document.getElementById('progress-container'),
    progressStep: document.getElementById('progress-step'),
    progressFill: document.getElementById('progress-fill'),
    progressPercent: document.getElementById('progress-percent'),
    
    // Stats
    statsContainer: document.getElementById('stats-container'),
    statHaute: document.getElementById('stat-haute'),
    statMoyenne: document.getElementById('stat-moyenne'),
    statBasse: document.getElementById('stat-basse'),
    
    // Download & Error
    downloadSection: document.getElementById('download-section'),
    errorMessage: document.getElementById('error-message'),
    errorText: document.getElementById('error-text')
};

// =============================================================================
// Initialisation
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initDropzones();
    initButtons();
    console.log('CCTP Analyzer initialisé');
});

// =============================================================================
// Dropzones
// =============================================================================

function initDropzones() {
    // CCAG Dropzone
    setupDropzone(elements.dropzoneCcag, elements.fileCcag, 'ccag');
    
    // CCTP Dropzone
    setupDropzone(elements.dropzoneCctp, elements.fileCctp, 'cctp');
}

function setupDropzone(dropzone, fileInput, type) {
    // Click to select file
    dropzone.addEventListener('click', () => fileInput.click());
    
    // File selected via input
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0], type);
        }
    });
    
    // Drag & Drop events
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('drag-over');
    });
    
    dropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-over');
    });
    
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-over');
        
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0], type);
        }
    });
}

function handleFileSelect(file, type) {
    // Vérifier l'extension
    if (!file.name.toLowerCase().endsWith('.docx')) {
        showError('Format non supporté. Veuillez sélectionner un fichier .docx');
        return;
    }
    
    // Vérifier la taille (20 MB max)
    if (file.size > 20 * 1024 * 1024) {
        showError('Fichier trop volumineux. Maximum: 20 MB');
        return;
    }
    
    // Stocker le fichier
    if (type === 'ccag') {
        state.ccagFile = file;
        elements.dropzoneCcag.classList.add('has-file');
        elements.filenameCcag.textContent = file.name;
        elements.fileInfoCcag.classList.add('visible');
    } else {
        state.cctpFile = file;
        elements.dropzoneCctp.classList.add('has-file');
        elements.filenameCctp.textContent = file.name;
        elements.fileInfoCctp.classList.add('visible');
    }
    
    // Uploader le fichier
    uploadFile(file, type);
    
    // Mettre à jour le bouton
    updateAnalyzeButton();
}

// =============================================================================
// Upload
// =============================================================================

async function uploadFile(file, type) {
    const formData = new FormData();
    formData.append('file', file);
    
    if (type === 'ccag') {
        formData.append('domaine', elements.domaine.value);
    }
    
    // Ajouter session ID si existant
    const headers = {};
    if (state.sessionId) {
        headers['X-Session-ID'] = state.sessionId;
    }
    
    try {
        const response = await fetch(`/upload/${type}`, {
            method: 'POST',
            headers: headers,
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Sauvegarder le session ID
            if (data.session_id) {
                state.sessionId = data.session_id;
            }
            console.log(`${type.toUpperCase()} uploadé:`, data.filename);
        } else {
            showError(data.error || 'Erreur lors de l\'upload');
            
            // Reset le fichier
            if (type === 'ccag') {
                state.ccagFile = null;
                elements.dropzoneCcag.classList.remove('has-file');
                elements.fileInfoCcag.classList.remove('visible');
            } else {
                state.cctpFile = null;
                elements.dropzoneCctp.classList.remove('has-file');
                elements.fileInfoCctp.classList.remove('visible');
            }
            updateAnalyzeButton();
        }
    } catch (error) {
        console.error('Erreur upload:', error);
        showError('Erreur de connexion au serveur');
    }
}

// =============================================================================
// Analyse
// =============================================================================

function initButtons() {
    elements.btnAnalyze.addEventListener('click', startAnalysis);
    elements.btnDownload.addEventListener('click', downloadResult);
}

function updateAnalyzeButton() {
    const canAnalyze = state.ccagFile && state.cctpFile && !state.isAnalyzing;
    elements.btnAnalyze.disabled = !canAnalyze;
}

async function startAnalysis() {
    if (state.isAnalyzing) return;
    
    state.isAnalyzing = true;
    updateAnalyzeButton();
    
    // Afficher la section résultats
    elements.resultsSection.classList.add('visible');
    elements.progressContainer.style.display = 'block';
    elements.statsContainer.classList.remove('visible');
    elements.downloadSection.classList.remove('visible');
    elements.errorMessage.classList.remove('visible');
    
    // Reset progress
    updateProgress(0, 'Démarrage de l\'analyse...');
    
    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': state.sessionId
            },
            body: JSON.stringify({
                session_id: state.sessionId
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            state.jobId = data.job_id;
            console.log('Analyse lancée, job_id:', state.jobId);
            
            // Commencer le polling du statut
            pollStatus();
        } else {
            showError(data.error || 'Erreur lors du lancement de l\'analyse');
            state.isAnalyzing = false;
            updateAnalyzeButton();
        }
    } catch (error) {
        console.error('Erreur analyse:', error);
        showError('Erreur de connexion au serveur');
        state.isAnalyzing = false;
        updateAnalyzeButton();
    }
}

async function pollStatus() {
    if (!state.jobId) return;
    
    try {
        const response = await fetch(`/status/${state.jobId}`);
        const data = await response.json();
        
        if (data.success) {
            updateProgress(data.progress, data.step);
            
            if (data.status === 'completed') {
                // Analyse terminée
                onAnalysisComplete(data);
            } else if (data.status === 'error') {
                // Erreur
                showError(data.error || 'Une erreur est survenue');
                state.isAnalyzing = false;
                updateAnalyzeButton();
            } else {
                // Encore en cours, continuer le polling
                setTimeout(pollStatus, 1000);
            }
        } else {
            showError(data.error || 'Erreur lors de la récupération du statut');
            state.isAnalyzing = false;
            updateAnalyzeButton();
        }
    } catch (error) {
        console.error('Erreur polling:', error);
        // Réessayer après un délai
        setTimeout(pollStatus, 2000);
    }
}

function updateProgress(percent, step) {
    elements.progressFill.style.width = `${percent}%`;
    elements.progressPercent.textContent = `${percent}%`;
    elements.progressStep.textContent = step;
}

function onAnalysisComplete(data) {
    console.log('Analyse terminée:', data);
    
    // Mettre à jour les stats
    if (data.stats) {
        elements.statHaute.textContent = data.stats.haute || 0;
        elements.statMoyenne.textContent = data.stats.moyenne || 0;
        elements.statBasse.textContent = data.stats.basse || 0;
        elements.statsContainer.classList.add('visible');
    }
    
    // Afficher le bouton de téléchargement
    elements.downloadSection.classList.add('visible');
    
    state.isAnalyzing = false;
    updateAnalyzeButton();
}

// =============================================================================
// Téléchargement
// =============================================================================

function downloadResult() {
    if (!state.jobId) return;
    
    // Ouvrir le lien de téléchargement
    window.location.href = `/download/${state.jobId}`;
}

// =============================================================================
// Utilitaires
// =============================================================================

function showError(message) {
    elements.errorText.textContent = message;
    elements.errorMessage.classList.add('visible');
    
    // Masquer après 5 secondes
    setTimeout(() => {
        elements.errorMessage.classList.remove('visible');
    }, 5000);
}

// =============================================================================
// Gestion du changement de domaine
// =============================================================================

elements.domaine.addEventListener('change', () => {
    // Si un CCAG est déjà uploadé, le ré-uploader avec le nouveau domaine
    if (state.ccagFile) {
        uploadFile(state.ccagFile, 'ccag');
    }
});
