"""
API routes - AJAX endpoints for frontend
"""
from flask import Blueprint, request, jsonify, session
from functools import wraps
from config.extensions import db_service, quiz_service, bandit_service, concept_service

api_bp = Blueprint('api', __name__)


def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function


@api_bp.route('/submit-answer', methods=['POST'])
@api_login_required
def submit_answer():
    """Submit an individual answer during quiz"""
    data = request.json
    user_id = session.get('user_id')
    
    question_id = data.get('question_id')
    answer = data.get('answer')
    time_taken = data.get('time_taken', 0)
    quiz_id = data.get('quiz_id')
    attempt_id = data.get('attempt_id')
    
    # Evaluate answer.
    # Human note: short-answer grading can use semantic similarity (see
    # `QuizService`), which Krish Thakkar helped tune for "same meaning" answers.
    result = quiz_service.evaluate_answer(quiz_id, question_id, answer)
    
    # Update bandit with reward signal
    question = db_service.get_question(quiz_id, question_id)
    concept = question.get('concept')
    
    # Reward: 1 for correct, 0 for incorrect (can be adjusted based on time)
    reward = 1 if result['is_correct'] else 0
    bandit_service.update_arm(user_id, concept, reward)
    
    return jsonify({
        'is_correct': result['is_correct'],
        'correct_answer': result['correct_answer'] if not result['is_correct'] else None,
        'explanation': result.get('explanation')
    })


@api_bp.route('/get-next-question', methods=['POST'])
@api_login_required
def get_next_question():
    """Get next adaptive question during quiz"""
    data = request.json
    user_id = session.get('user_id')
    quiz_id = data.get('quiz_id')
    attempt_id = data.get('attempt_id')
    answered_questions = data.get('answered_questions', [])
    
    # Get remaining questions
    all_questions = db_service.get_quiz_questions(quiz_id)
    remaining = [q for q in all_questions if q['id'] not in answered_questions]
    
    if not remaining:
        return jsonify({'finished': True})
    
    # Use bandit to select next question
    user_data = db_service.get_user_data(user_id)
    concept_mastery = user_data.get('concept_mastery', {})
    
    next_question = bandit_service.select_next_question(
        remaining, concept_mastery, 'thompson_sampling'
    )
    
    return jsonify({
        'finished': False,
        'question': {
            'id': next_question['id'],
            'text': next_question['text'],
            'type': next_question['type'],
            'options': next_question.get('options', []),
            'concept': next_question.get('concept'),
            'difficulty': next_question.get('difficulty')
        }
    })


@api_bp.route('/concept-mastery', methods=['GET'])
@api_login_required
def get_concept_mastery():
    """Get user's concept mastery data"""
    user_id = session.get('user_id')
    user_data = db_service.get_user_data(user_id)
    
    return jsonify({
        'concept_mastery': user_data.get('concept_mastery', {})
    })


@api_bp.route('/knowledge-graph/<doc_id>', methods=['GET'])
@api_login_required
def get_knowledge_graph(doc_id):
    """Get knowledge graph data for visualization"""
    document = db_service.get_document(doc_id)
    
    if not document:
        return jsonify({'error': 'Document not found'}), 404
    
    # Format for visualization
    graph = document.get('knowledge_graph', {})
    
    nodes = [{'id': node, 'label': node} for node in graph.get('nodes', [])]
    edges = [{'from': e[0], 'to': e[1], 'weight': e.get('weight', 1)} 
             for e in graph.get('edges', [])]
    
    return jsonify({
        'nodes': nodes,
        'edges': edges
    })


@api_bp.route('/search-concepts', methods=['POST'])
@api_login_required
def search_concepts():
    """Search concepts in knowledge graph"""
    data = request.json
    query = data.get('query', '')
    doc_id = data.get('doc_id')
    
    document = db_service.get_document(doc_id)
    if not document:
        return jsonify({'error': 'Document not found'}), 404
    
    concepts = document.get('concepts', [])
    
    # Simple search
    matches = [c for c in concepts if query.lower() in c.lower()]
    
    return jsonify({'concepts': matches})


@api_bp.route('/quiz-stats/<quiz_id>', methods=['GET'])
@api_login_required
def get_quiz_stats(quiz_id):
    """Get statistics for a specific quiz"""
    stats = db_service.get_quiz_statistics(quiz_id)
    return jsonify(stats)
