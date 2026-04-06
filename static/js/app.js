/**
 * CCAP Analyzer - Frontend JavaScript
 * Lexigency - 2026
 */

// =============================================================================
// STATE
// =============================================================================

let sessionId = null;
let ccagFile = null;
let cctpFile = null;  // optionnel (référence technique)
let ccapFile = null;   // document à analyser
let jobId = null;
let isAnalyzing = false;
let pollInterval = null;

// =============================================================================
// DOM ELEMENTS
// =============================================================================

const elements = {
    // Dropzones
    ccagDropzone: document.getElementById('ccag-dropzone'),
    cctpDropzone: document.getElementById('cctp-dropzone'),
    ccapDropzone: document.getElementById('ccap-dropzone'),
    ccagInput: document.getElementById('ccag-input'),
    cctpInput: document.getElementById('cctp-input'),
    ccapInput: document.getElementById('ccap-input'),

    // Success states
    ccagSuccess: document.getElementById('ccag-success'),
    cctpSuccess: document.getElementById('cctp-success'),
    ccapSuccess: document.getElementById('ccap-success'),
    ccagFilename: document.getElementById('ccag-filename'),
    cctpFilename: document.getElementById('cctp-filename'),
    ccapFilename: document.getElementById('ccap-filename'),

    // Domain select
    domaineSelect: document.getElementById('domaine-select'),

    // Analyze button
    btnAnalyze: document.getElementById('btn-analyze'),

    // Sections
    uploadSection: document.getElementById('upload-section'),
    resultsSection: document.getElementById('results-section'),

    // Progress
    progressContainer: document.getElementById('progress-container'),
    progressFill: document.getElementById('progress-fill'),
    progressPercentage: document.getElementById('progress-percentage'),
    progressStep: document.getElementById('progress-step'),

    // Results
    resultsContainer: document.getElementById('results-container'),
    riskBadge: document.getElementById('risk-badge'),
    riskValue: document.getElementById('risk-value'),
    statTotal: document.getElementById('stat-total'),
    statHaute: document.getElementById('stat-haute'),
    statMoyenne: document.getElementById('stat-moyenne'),
    statBasse: document.getElementById('stat-basse'),
    synthesisBox: document.getElementById('synthesis-box'),
    synthesisText: document.getElementById('synthesis-text'),
    btnDownload: document.getElementById('btn-download'),

    // Error
    errorContainer: document.getElementById('error-container'),
    errorMessage: document.getElementById('error-message')
};

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initDropzones();
    initAnalyzeButton();
    initDomainSelect();
});

// =============================================================================
// DROPZONES
// =============================================================================

function initDropzones() {
    setupDropzone(elements.ccagDropzone, elements.ccagInput, 'ccag');
    setupDropzone(elements.cctpDropzone, elements.cctpInput, 'cctp');
    setupDropzone(elements.ccapDropzone, elements.ccapInput, 'ccap');
}

function setupDropzone(dropzone, input, type) {
    dropzone.addEventListener('click', (e) => {
        if (!e.target.classList.contains('btn-change')) {
            input.click();
        }
    });

    input.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0], type);
        }
    });

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
            handleFile(e.dataTransfer.files[0], type);
        }
    });
}

function handleFile(file, type) {
    if (!file.name.toLowerCase().endsWith('.docx')) {
        showNotification('Format invalide. Utilisez un fichier .docx', 'error');
        return;
    }

    if (file.size > 20 * 1024 * 1024) {
        showNotification('Fichier trop volumineux (max 20 MB)', 'error');
        return;
    }

    const dropzoneEl = document.getElementById(`${type}-dropzone`);
    const filenameEl = document.getElementById(`${type}-filename`);

    if (type === 'ccag') {
        ccagFile = file;
    } else if (type === 'cctp') {
        cctpFile = file;
    } else {
        ccapFile = file;
    }

    dropzoneEl.classList.add('has-file');
    filenameEl.textContent = file.name;

    uploadFile(file, type);
    updateAnalyzeButton();
}

async function uploadFile(file, type) {
    const formData = new FormData();
    formData.append('file', file);

    if (type === 'ccag') {
        formData.append('domaine', elements.domaineSelect.value);
    }

    try {
        const response = await fetch(`/upload/${type}`, {
            method: 'POST',
            headers: sessionId ? { 'X-Session-ID': sessionId } : {},
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            sessionId = data.session_id;
            showNotification(`${type.toUpperCase()} uploadé avec succès`, 'success');
        } else {
            throw new Error(data.error || 'Erreur upload');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showNotification(`Erreur upload ${type.toUpperCase()}: ${error.message}`, 'error');
        resetFile(type);
    }
}

function resetFile(type) {
    const dropzoneEl = document.getElementById(`${type}-dropzone`);
    const inputEl = document.getElementById(`${type}-input`);

    if (type === 'ccag') {
        ccagFile = null;
    } else if (type === 'cctp') {
        cctpFile = null;
    } else {
        ccapFile = null;
    }

    dropzoneEl.classList.remove('has-file');
    inputEl.value = '';
    updateAnalyzeButton();
}

// =============================================================================
// DOMAIN SELECT
// =============================================================================

function initDomainSelect() {
    elements.domaineSelect.addEventListener('change', () => {
        if (ccagFile) {
            uploadFile(ccagFile, 'ccag');
        }
    });
}

// =============================================================================
// ANALYZE BUTTON
// =============================================================================

function initAnalyzeButton() {
    elements.btnAnalyze.addEventListener('click', startAnalysis);
}

function updateAnalyzeButton() {
    // CCAG + CCAP requis, CCTP optionnel
    const canAnalyze = ccagFile && ccapFile && !isAnalyzing;
    elements.btnAnalyze.disabled = !canAnalyze;
}

async function startAnalysis() {
    if (isAnalyzing) return;

    isAnalyzing = true;
    elements.btnAnalyze.classList.add('loading');
    updateAnalyzeButton();

    showResultsSection('progress');

    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': sessionId
            },
            body: JSON.stringify({ session_id: sessionId })
        });

        const data = await response.json();

        if (data.success) {
            jobId = data.job_id;
            startPolling();
        } else {
            throw new Error(data.error || 'Erreur lors du lancement');
        }
    } catch (error) {
        console.error('Analysis error:', error);
        showError(error.message);
    }
}

// =============================================================================
// POLLING
// =============================================================================

function startPolling() {
    pollInterval = setInterval(pollStatus, 1000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

async function pollStatus() {
    try {
        const response = await fetch(`/status/${jobId}`, {
            headers: sessionId ? { 'X-Session-ID': sessionId } : {}
        });

        const data = await response.json();

        if (data.success) {
            updateProgress(data);

            if (data.status === 'completed') {
                stopPolling();
                showResults(data);
            } else if (data.status === 'error') {
                stopPolling();
                showError(data.error);
            }
        }
    } catch (error) {
        console.error('Poll error:', error);
    }
}

// =============================================================================
// PROGRESS
// =============================================================================

function updateProgress(data) {
    const progress = data.progress || 0;
    const step = data.step || 'En cours...';

    elements.progressFill.style.width = `${progress}%`;
    elements.progressPercentage.textContent = `${progress}%`;
    elements.progressStep.textContent = step;

    updatePhases(progress);
}

function updatePhases(progress) {
    const phases = document.querySelectorAll('.phase');

    phases.forEach((phase, index) => {
        const phaseNum = index + 1;

        if (progress >= phaseNum * 33) {
            phase.classList.add('completed');
            phase.classList.remove('active');
        } else if (progress >= (phaseNum - 1) * 33) {
            phase.classList.add('active');
            phase.classList.remove('completed');
        } else {
            phase.classList.remove('active', 'completed');
        }
    });
}

// =============================================================================
// RESULTS
// =============================================================================

function showResultsSection(mode) {
    elements.resultsSection.classList.add('active');

    elements.progressContainer.classList.remove('active');
    elements.resultsContainer.classList.remove('active');
    elements.errorContainer.classList.remove('active');

    if (mode === 'progress') {
        elements.progressContainer.classList.add('active');
    } else if (mode === 'results') {
        elements.resultsContainer.classList.add('active');
    } else if (mode === 'error') {
        elements.errorContainer.classList.add('active');
    }

    elements.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showResults(data) {
    isAnalyzing = false;
    elements.btnAnalyze.classList.remove('loading');

    const stats = data.stats || {};
    const niveauRisque = data.niveau_risque || 'modéré';
    const synthese = data.synthese || '';

    animateCounter(elements.statTotal, stats.total || 0);
    animateCounter(elements.statHaute, stats.haute || 0);
    animateCounter(elements.statMoyenne, stats.moyenne || 0);
    animateCounter(elements.statBasse, stats.basse || 0);

    elements.riskValue.textContent = niveauRisque.charAt(0).toUpperCase() + niveauRisque.slice(1);
    elements.riskValue.className = 'risk-value';
    if (niveauRisque === 'faible') {
        elements.riskValue.classList.add('risk-low');
    } else if (niveauRisque === 'élevé') {
        elements.riskValue.classList.add('risk-high');
    }

    if (synthese) {
        elements.synthesisBox.classList.add('active');
        elements.synthesisText.textContent = synthese;
    } else {
        elements.synthesisBox.classList.remove('active');
    }

    elements.btnDownload.onclick = () => downloadResult();

    showResultsSection('results');
}

function animateCounter(element, target) {
    const duration = 1000;
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeProgress = 1 - Math.pow(1 - progress, 3);

        element.textContent = Math.round(target * easeProgress);

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

function downloadResult() {
    if (jobId) {
        window.location.href = `/download/${jobId}`;
    }
}

// =============================================================================
// ERROR
// =============================================================================

function showError(message) {
    isAnalyzing = false;
    elements.btnAnalyze.classList.remove('loading');
    updateAnalyzeButton();

    elements.errorMessage.textContent = message || 'Une erreur inattendue est survenue';
    showResultsSection('error');
}

// =============================================================================
// RESET
// =============================================================================

function resetAnalysis() {
    stopPolling();

    isAnalyzing = false;
    jobId = null;
    ccagFile = null;
    cctpFile = null;
    ccapFile = null;

    elements.btnAnalyze.classList.remove('loading');

    ['ccag', 'cctp', 'ccap'].forEach(type => {
        const dz = document.getElementById(`${type}-dropzone`);
        const input = document.getElementById(`${type}-input`);
        if (dz) dz.classList.remove('has-file');
        if (input) input.value = '';
    });

    elements.resultsSection.classList.remove('active');

    elements.progressFill.style.width = '0%';
    elements.progressPercentage.textContent = '0%';
    elements.progressStep.textContent = 'Initialisation...';

    document.querySelectorAll('.phase').forEach(phase => {
        phase.classList.remove('active', 'completed');
    });

    updateAnalyzeButton();

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// =============================================================================
// NOTIFICATIONS
// =============================================================================

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()">&times;</button>
    `;

    if (!document.getElementById('notification-styles')) {
        const styles = document.createElement('style');
        styles.id = 'notification-styles';
        styles.textContent = `
            .notification {
                position: fixed;
                bottom: 24px;
                right: 24px;
                padding: 16px 20px;
                background: rgba(15, 15, 26, 0.95);
                border: 1px solid var(--border);
                border-radius: 12px;
                display: flex;
                align-items: center;
                gap: 12px;
                font-size: 0.95rem;
                z-index: 1000;
                animation: slideIn 0.3s ease;
                backdrop-filter: blur(10px);
            }
            .notification-success { border-color: var(--success); color: var(--success); }
            .notification-error { border-color: var(--danger); color: var(--danger); }
            .notification button {
                background: none; border: none; color: inherit;
                font-size: 1.2rem; cursor: pointer; opacity: 0.7;
                transition: opacity 0.2s;
            }
            .notification button:hover { opacity: 1; }
            @keyframes slideIn {
                from { opacity: 0; transform: translateX(20px); }
                to { opacity: 1; transform: translateX(0); }
            }
        `;
        document.head.appendChild(styles);
    }

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}

// Make functions globally available
window.resetFile = resetFile;
window.resetAnalysis = resetAnalysis;
