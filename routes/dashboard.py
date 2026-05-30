"""
Dashboard routes - User dashboard, progress tracking
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify
from functools import wraps
from config.extensions import db_service, progress_service

dashboard_bp = Blueprint('dashboard', __name__)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard"""
    user_id = session.get('user_id')
    user_data = db_service.get_user_data(user_id)
    
    # Get summary statistics from attempts collection (single source of truth)
    quiz_history_raw = db_service.get_quiz_history(user_id)
    quiz_history_list = normalize_quiz_history_entries(quiz_history_raw)

    stats = {
        'total_quizzes': len(quiz_history_list),
        'average_score': calculate_average_score(quiz_history_list),
        'concepts_mastered': count_mastered_concepts(user_data.get('concept_mastery', {})),
        'total_concepts': len(user_data.get('concept_mastery', {}))
    }
    
    # Get recent activity (newest attempts first)
    recent_quizzes = sorted(
        quiz_history_list,
        key=lambda x: x.get('timestamp', ''),
        reverse=True
    )[:5]
    
    # Get weak concepts for review
    weak_concepts = get_weak_concepts(user_data.get('concept_mastery', {}))
    
    return render_template('dashboard/index.html', 
                         user=user_data,
                         stats=stats,
                         recent_quizzes=recent_quizzes,
                         weak_concepts=weak_concepts)


@dashboard_bp.route('/progress')
@login_required
def progress():
    """Detailed progress view"""
    user_id = session.get('user_id')
    user_data = db_service.get_user_data(user_id)
    
    # Get concept mastery details
    concept_mastery = user_data.get('concept_mastery', {})
    
    # Get quiz history from attempts collection (single source of truth)
    quiz_history_raw = db_service.get_quiz_history(user_id)
    quiz_history = normalize_quiz_history_entries(quiz_history_raw)
    
    # Sort quiz history by timestamp (oldest to newest for trend)
    quiz_history_sorted = sorted(
        quiz_history, 
        key=lambda x: x.get('timestamp', ''), 
        reverse=False
    ) if quiz_history else []
    
    # Get statistics including total time
    total_time_seconds = sum(q.get('time_taken', 0) for q in quiz_history)
    total_time_hours = total_time_seconds // 3600
    total_time_minutes = (total_time_seconds % 3600) // 60
    if total_time_hours > 0:
        total_time_display = f"{total_time_hours}h {total_time_minutes}m"
    elif total_time_minutes > 0:
        total_time_display = f"{total_time_minutes}m"
    else:
        total_time_display = "0m"
    
    # Calculate best score
    all_scores = []
    for q in quiz_history:
        try:
            s = float(q.get('score_percentage', q.get('score', 0)) or 0)
            all_scores.append(s)
        except (ValueError, TypeError):
            pass
    
    best_score = max(all_scores) if all_scores else 0
    
    stats = {
        'total_quizzes': len(quiz_history),
        'avg_score': calculate_average_score(quiz_history),
        'concepts_mastered': count_mastered_concepts(concept_mastery),
        'total_time': total_time_display,
        'best_score': round(best_score, 1),
        'total_correct': sum(q.get('correct', 0) for q in quiz_history),
        'total_questions_attempted': sum(q.get('total_questions', 0) for q in quiz_history)
    }
    
    # Prepare mastery chart data with ML-enhanced analytics
    # Calculate detailed concept performance metrics
    try:
        concept_performance = calculate_concept_performance(quiz_history, concept_mastery)
    except Exception as e:
        print(f"Error calculating concept performance: {e}")
        concept_performance = {}
    
    mastery_labels = []
    mastery_data = []
    mastery_trend = []  # Learning trend indicator
    mastery_predicted = []  # Predicted next performance
    
    if concept_mastery:
        mastery_labels = [str(c)[:40] for c in list(concept_mastery.keys())[:10]]
        
        for c in list(concept_mastery.keys())[:10]:
            val = concept_mastery.get(c, 0)
            try:
                val = float(val) * 100
                val = min(max(val, 0), 100)  # Clamp 0-100
            except (ValueError, TypeError):
                val = 0
            mastery_data.append(round(val, 1))
            
            # Calculate learning trend (positive/negative growth)
            perf = concept_performance.get(c, {})
            mastery_trend.append(perf.get('trend', 0))
            mastery_predicted.append(perf.get('predicted', val))
    
    # Prepare performance over time chart data with quiz names and dates
    performance_labels = []
    performance_data = []
    
    for i, q in enumerate(quiz_history_sorted):
        # Format: "Quiz Name (MM/DD)" or just "Quiz #" if no name
        quiz_name = str(q.get('quiz_name', f'Quiz {i+1}'))
        timestamp = str(q.get('timestamp', ''))
        
        # Shorten quiz name if too long
        if len(quiz_name) > 20:
            quiz_name = quiz_name[:17] + '...'
        
        # Add date if available
        if timestamp and len(timestamp) >= 10:
            date_str = timestamp[:10]  # Get YYYY-MM-DD
            try:
                date_parts = date_str.split('-')
                if len(date_parts) == 3:
                    label = f"{quiz_name} ({date_parts[1]}/{date_parts[2]})"
                else:
                    label = quiz_name
            except:
                label = quiz_name
        else:
            label = quiz_name
        
        performance_labels.append(label)
        try:
            score = float(q.get('score_percentage', q.get('score', 0)) or 0)
        except (ValueError, TypeError):
            score = 0
        performance_data.append(round(score, 1))
    
    # Get top concepts (highest mastery)
    top_concepts = sorted(
        [{'name': c, 'mastery': int(m * 100)} for c, m in concept_mastery.items()],
        key=lambda x: x['mastery'],
        reverse=True
    )[:5]
    
    # Get weak concepts
    weak_concepts = get_weak_concepts(concept_mastery)
    
    # Debug output
    print(f"[Progress Page Debug]")
    print(f"  Total quizzes: {len(quiz_history)}")
    print(f"  Concepts tracked: {len(concept_mastery)}")
    print(f"  Mastery labels: {len(mastery_labels)}")
    print(f"  Mastery data points: {len(mastery_data)}")
    print(f"  Has data for graph: {len(mastery_labels) > 0 and len(mastery_data) > 0}")
    if mastery_labels:
        print(f"  First concept: {mastery_labels[0]} = {mastery_data[0]}%")
    
    return render_template('dashboard/progress.html',
                         stats=stats,
                         concept_mastery=concept_mastery,
                         quiz_history=quiz_history,
                         mastery_labels=mastery_labels,
                         mastery_data=mastery_data,
                         mastery_trend=mastery_trend,
                         mastery_predicted=mastery_predicted,
                         performance_labels=performance_labels,
                         performance_data=performance_data,
                         top_concepts=top_concepts,
                         weak_concepts=weak_concepts,
                         concept_performance=concept_performance)


@dashboard_bp.route('/knowledge-graph')
@login_required
def knowledge_graph():
    """View concept knowledge graph with mastery overlay"""
    user_id = session.get('user_id')
    user_data = db_service.get_user_data(user_id)
    
    concept_mastery = user_data.get('concept_mastery', {})
    
    # Get knowledge graph data (will be populated when user uploads notes)
    graph_data = db_service.get_user_knowledge_graph(user_id)
    
    return render_template('dashboard/knowledge_graph.html',
                         graph_data=graph_data,
                         concept_mastery=concept_mastery)


@dashboard_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile with embedded progress view"""
    user_id = session.get('user_id')
    user_data = db_service.get_user_data(user_id)

    # --- Compute the same progress data as the progress() route ---
    concept_mastery = user_data.get('concept_mastery', {})
    # Get quiz history from attempts collection (single source of truth)
    quiz_history_raw = db_service.get_quiz_history(user_id)
    quiz_history = normalize_quiz_history_entries(quiz_history_raw)

    # Sort by timestamp
    quiz_history_sorted = sorted(
        quiz_history,
        key=lambda x: x.get('timestamp', ''),
        reverse=False,
    ) if quiz_history else []

    # Time calculation
    total_time_seconds = sum(q.get('time_taken', 0) for q in quiz_history)
    total_time_hours = total_time_seconds // 3600
    total_time_minutes = (total_time_seconds % 3600) // 60
    if total_time_hours > 0:
        total_time_display = f"{total_time_hours}h {total_time_minutes}m"
    elif total_time_minutes > 0:
        total_time_display = f"{total_time_minutes}m"
    else:
        total_time_display = "0m"

    # Best score
    all_scores = []
    for q in quiz_history:
        try:
            s = float(q.get('score_percentage', q.get('score', 0)) or 0)
            all_scores.append(s)
        except (ValueError, TypeError):
            pass
    best_score = max(all_scores) if all_scores else 0

    stats = {
        'total_quizzes': len(quiz_history),
        'avg_score': calculate_average_score(quiz_history),
        'concepts_mastered': count_mastered_concepts(concept_mastery),
        'total_time': total_time_display,
        'best_score': round(best_score, 1),
        'total_correct': sum(q.get('correct', 0) for q in quiz_history),
        'total_questions_attempted': sum(q.get('total_questions', 0) for q in quiz_history),
    }

    # Concept performance / mastery chart data
    try:
        concept_performance = calculate_concept_performance(quiz_history, concept_mastery)
    except Exception:
        concept_performance = {}

    mastery_labels, mastery_data, mastery_trend, mastery_predicted = [], [], [], []
    if concept_mastery:
        mastery_labels = [str(c)[:40] for c in list(concept_mastery.keys())[:10]]
        for c in list(concept_mastery.keys())[:10]:
            val = concept_mastery.get(c, 0)
            try:
                val = float(val) * 100
                val = min(max(val, 0), 100)
            except (ValueError, TypeError):
                val = 0
            mastery_data.append(round(val, 1))
            perf = concept_performance.get(c, {})
            mastery_trend.append(perf.get('trend', 0))
            mastery_predicted.append(perf.get('predicted', val))

    # Performance over time
    performance_labels, performance_data = [], []
    for i, q in enumerate(quiz_history_sorted):
        quiz_name = str(q.get('quiz_name', f'Quiz {i+1}'))
        timestamp = str(q.get('timestamp', ''))
        if len(quiz_name) > 20:
            quiz_name = quiz_name[:17] + '...'
        if timestamp and len(timestamp) >= 10:
            date_str = timestamp[:10]
            try:
                parts = date_str.split('-')
                label = f"{quiz_name} ({parts[1]}/{parts[2]})" if len(parts) == 3 else quiz_name
            except Exception:
                label = quiz_name
        else:
            label = quiz_name
        performance_labels.append(label)
        try:
            score = float(q.get('score_percentage', q.get('score', 0)) or 0)
        except (ValueError, TypeError):
            score = 0
        performance_data.append(round(score, 1))

    # Top / weak concepts
    top_concepts = sorted(
        [{'name': c, 'mastery': int(m * 100)} for c, m in concept_mastery.items()],
        key=lambda x: x['mastery'], reverse=True,
    )[:5]
    weak_concepts = get_weak_concepts(concept_mastery)

    return render_template('dashboard/profile.html',
                         user=user_data,
                         stats=stats,
                         quiz_history=quiz_history,
                         mastery_labels=mastery_labels,
                         mastery_data=mastery_data,
                         mastery_trend=mastery_trend,
                         mastery_predicted=mastery_predicted,
                         performance_labels=performance_labels,
                         performance_data=performance_data,
                         top_concepts=top_concepts,
                         weak_concepts=weak_concepts)


# Helper functions
def calculate_average_score(quiz_history):
    """Calculate average score from quiz history"""
    if not quiz_history:
        return 0
    
    # Filter to only dictionary items and extract scores
    scores = [q.get('score', 0) for q in quiz_history if isinstance(q, dict) and 'score' in q]
    return sum(scores) / len(scores) if scores else 0


def count_mastered_concepts(concept_mastery):
    """Count concepts with mastery >= 0.7"""
    return sum(1 for score in concept_mastery.values() if score >= 0.7)


def get_weak_concepts(concept_mastery, threshold=0.5, limit=5):
    """Get concepts with mastery below threshold"""
    weak = [(concept, score) for concept, score in concept_mastery.items() 
            if score < threshold]
    weak.sort(key=lambda x: x[1])
    return weak[:limit]


def calculate_concept_performance(quiz_history, concept_mastery):
    """Calculate ML-enhanced performance metrics for each concept"""
    try:
        import numpy as np
    except ImportError:
        print("NumPy not available, using basic calculations")
        # Fallback to basic calculations without NumPy
        performance = {}
        for concept, current_mastery in concept_mastery.items():
            current_percent = float(current_mastery) * 100
            performance[concept] = {
                'current': round(current_percent, 1),
                'trend': 0,
                'predicted': round(current_percent, 1),
                'learning_rate': 0,
                'consistency': 50,
                'attempts': 0
            }
        return performance
    
    from collections import defaultdict
    
    performance = {}
    concept_history = defaultdict(list)
    
    # Collect historical performance for each concept
    for quiz in quiz_history:
        if not isinstance(quiz, dict):
            continue
        
        quiz_concepts = quiz.get('concepts', [])
        score = quiz.get('score_percentage', quiz.get('score', 0)) or 0
        
        # If quiz doesn't track individual concepts, use overall concepts
        if not quiz_concepts:
            quiz_concepts = list(concept_mastery.keys())
        
        for concept in quiz_concepts:
            concept_history[concept].append(float(score))
    
    # Calculate metrics for each concept
    for concept, current_mastery in concept_mastery.items():
        scores = concept_history.get(concept, [])
        current_percent = float(current_mastery) * 100
        
        if len(scores) >= 2:
            # Calculate learning trend (slope of performance over time)
            x = np.arange(len(scores))
            y = np.array(scores)
            
            # Simple linear regression for trend
            if len(x) > 1:
                slope = np.polyfit(x, y, 1)[0]
                trend = round(slope, 2)
                
                # Predict next performance using trend
                predicted = current_percent + (trend * 2)
                predicted = min(max(predicted, 0), 100)
            else:
                trend = 0
                predicted = current_percent
            
            # Calculate learning rate (recent improvement)
            if len(scores) >= 3:
                recent_avg = np.mean(scores[-3:])
                early_avg = np.mean(scores[:3]) if len(scores) > 3 else scores[0]
                learning_rate = recent_avg - early_avg
            else:
                learning_rate = 0
            
            # Calculate consistency (standard deviation - lower is more consistent)
            consistency = 100 - min(np.std(scores), 100)
            
        else:
            trend = 0
            predicted = current_percent
            learning_rate = 0
            consistency = 50
        
        performance[concept] = {
            'current': round(current_percent, 1),
            'trend': trend,
            'predicted': round(predicted, 1),
            'learning_rate': round(learning_rate, 1),
            'consistency': round(consistency, 1),
            'attempts': len(scores)
        }
    
    return performance


def normalize_quiz_history_entries(quiz_history_raw):
    """Normalize raw attempt documents into a consistent shape for templates and stats.

    Ensures fields like score, marks, timestamps, and IDs are always present
    at the top level so views can treat history as real quiz attempts.
    """
    normalized = []

    for item in quiz_history_raw or []:
        if not isinstance(item, dict):
            continue

        result_block = item.get('result', {}) or {}
        base = result_block if result_block else item

        # Score (percentage 0-100)
        try:
            score_pct = float(base.get('score_percentage', base.get('score', item.get('score', 0))) or 0)
        except (ValueError, TypeError):
            score_pct = 0.0

        # Correct / total questions
        try:
            correct = int(base.get('correct', item.get('correct', 0)) or 0)
        except (ValueError, TypeError):
            correct = 0
        try:
            total_questions = int(base.get('total_questions', item.get('total_questions', 0)) or 0)
        except (ValueError, TypeError):
            total_questions = 0

        # Marks
        try:
            marks_obtained = int(base.get('marks_obtained', correct) or 0)
        except (ValueError, TypeError):
            marks_obtained = correct
        try:
            total_marks = int(base.get('total_marks', total_questions) or 0)
        except (ValueError, TypeError):
            total_marks = total_questions

        # Timing
        try:
            time_taken = int(base.get('time_taken', item.get('time_taken', 0)) or 0)
        except (ValueError, TypeError):
            time_taken = 0
        time_taken_display = base.get('time_taken_display', item.get('time_taken_display', 'N/A'))

        # Timestamps
        timestamp = str(
            base.get(
                'timestamp',
                item.get('timestamp', item.get('created_at', ''))
            )
        )

        # IDs and names
        attempt_id = item.get('attempt_id') or item.get('id')
        quiz_id = item.get('quiz_id')
        quiz_name = base.get('quiz_name', item.get('quiz_name', 'Quiz'))

        # Concepts for analytics (optional)
        concepts = []
        concept_perf = base.get('concept_performance', {})
        if isinstance(concept_perf, dict):
            concepts = list(concept_perf.keys())

        normalized.append({
            'id': attempt_id,
            'attempt_id': attempt_id,
            'quiz_id': quiz_id,
            'quiz_name': quiz_name,
            'timestamp': timestamp,
            'time_taken': time_taken,
            'time_taken_display': time_taken_display,
            'score': round(score_pct, 1),
            'score_percentage': round(score_pct, 1),
            'correct': correct,
            'total_questions': total_questions,
            'marks_obtained': marks_obtained,
            'total_marks': total_marks,
            'concepts': concepts,
        })

    return normalized
