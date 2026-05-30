/**
 * Adaptive Quiz Generator - Main JavaScript
 */

// ============ Utility Functions ============

/**
 * Format time in MM:SS format
 */
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
}

/**
 * Format file size
 */
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    document.body.appendChild(container);
    return container;
}

// ============ API Functions ============

/**
 * Submit answer via AJAX
 */
async function submitAnswer(quizId, questionId, answer, attemptId) {
    try {
        const response = await fetch('/api/submit-answer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                quiz_id: quizId,
                question_id: questionId,
                answer: answer,
                attempt_id: attemptId,
                time_taken: 0
            })
        });
        
        return await response.json();
    } catch (error) {
        console.error('Error submitting answer:', error);
        return null;
    }
}

/**
 * Get next adaptive question
 */
async function getNextQuestion(quizId, attemptId, answeredQuestions) {
    try {
        const response = await fetch('/api/get-next-question', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                quiz_id: quizId,
                attempt_id: attemptId,
                answered_questions: answeredQuestions
            })
        });
        
        return await response.json();
    } catch (error) {
        console.error('Error getting next question:', error);
        return null;
    }
}

/**
 * Get concept mastery data
 */
async function getConceptMastery() {
    try {
        const response = await fetch('/api/concept-mastery');
        return await response.json();
    } catch (error) {
        console.error('Error getting mastery:', error);
        return null;
    }
}

/**
 * Get knowledge graph data
 */
async function getKnowledgeGraph(docId) {
    try {
        const response = await fetch(`/api/knowledge-graph/${docId}`);
        return await response.json();
    } catch (error) {
        console.error('Error getting knowledge graph:', error);
        return null;
    }
}

// ============ Quiz Functions ============

/**
 * Initialize quiz timer
 */
function initQuizTimer(elementId) {
    let seconds = 0;
    const timerElement = document.getElementById(elementId);
    
    if (!timerElement) return;
    
    setInterval(() => {
        seconds++;
        timerElement.textContent = formatTime(seconds);
    }, 1000);
    
    return () => seconds;
}

/**
 * Update quiz progress bar
 */
function updateQuizProgress(answered, total) {
    const progressBar = document.getElementById('progressBar');
    if (progressBar) {
        const percentage = (answered / total) * 100;
        progressBar.style.width = `${percentage}%`;
    }
}

// ============ Knowledge Graph Visualization ============

/**
 * Initialize knowledge graph visualization
 */
function initKnowledgeGraph(containerId, data, masteryData = {}) {
    // Check if vis.js is available
    if (typeof vis === 'undefined') {
        console.warn('vis.js not loaded. Knowledge graph visualization disabled.');
        return;
    }
    
    const container = document.getElementById(containerId);
    if (!container) return;
    
    // Prepare nodes with mastery colors
    const nodes = data.nodes.map(node => {
        const mastery = masteryData[node.label] || 0.5;
        let color = '#607D8B'; // default gray
        
        if (mastery >= 0.7) {
            color = '#4CAF50'; // green for mastered
        } else if (mastery >= 0.4) {
            color = '#FFC107'; // yellow for learning
        } else {
            color = '#F44336'; // red for weak
        }
        
        return {
            id: node.id,
            label: node.label,
            color: color,
            title: `${node.label}\nMastery: ${(mastery * 100).toFixed(0)}%`
        };
    });
    
    // Create vis.js network
    const network = new vis.Network(container, {
        nodes: new vis.DataSet(nodes),
        edges: new vis.DataSet(data.edges)
    }, {
        nodes: {
            shape: 'dot',
            size: 20,
            font: {
                size: 14
            }
        },
        edges: {
            smooth: {
                type: 'continuous'
            }
        },
        physics: {
            stabilization: {
                iterations: 100
            }
        }
    });
    
    return network;
}

// ============ Form Validation ============

/**
 * Validate quiz form before submission
 */
function validateQuizForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;
    
    const questions = form.querySelectorAll('.question-card');
    let allAnswered = true;
    
    questions.forEach(card => {
        const inputs = card.querySelectorAll('input[type="radio"]:checked, input[type="hidden"][value], textarea');
        let hasAnswer = false;
        
        inputs.forEach(input => {
            if (input.value && input.value.trim()) {
                hasAnswer = true;
            }
        });
        
        if (!hasAnswer) {
            allAnswered = false;
            card.classList.add('border-warning');
        } else {
            card.classList.remove('border-warning');
        }
    });
    
    return allAnswered;
}

// ============ Mastery Chart ============

/**
 * Initialize mastery progress chart
 */
function initMasteryChart(canvasId, data) {
    // Check if Chart.js is available
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js not loaded. Mastery chart disabled.');
        return;
    }
    
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    const concepts = Object.keys(data);
    const values = Object.values(data).map(v => v * 100);
    const colors = values.map(v => {
        if (v >= 70) return '#4CAF50';
        if (v >= 40) return '#FFC107';
        return '#F44336';
    });
    
    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: concepts,
            datasets: [{
                label: 'Mastery %',
                data: values,
                backgroundColor: colors,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}

// ============ Document Ready ============

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(el => new bootstrap.Tooltip(el));
    
    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(el => new bootstrap.Popover(el));
    
    // Add fade-in animation to cards
    document.querySelectorAll('.card').forEach((card, index) => {
        card.style.animationDelay = `${index * 0.1}s`;
        card.classList.add('fade-in');
    });
    
    console.log('Adaptive Quiz Generator initialized');
});
