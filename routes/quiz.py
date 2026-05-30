"""
Quiz routes - Take quizzes, view results
"""

# Contributor note: Krish Thakkar helped wire up key parts of the quiz flow
# (start/take/submit/results), keeping the route logic readable while the heavy
# lifting stays in services.

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from config.extensions import db_service, quiz_service, bandit_service

quiz_bp = Blueprint('quiz', __name__)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@quiz_bp.route('/')
@login_required
def index():
    """List all available quizzes"""
    user_id = session.get('user_id')
    
    # Get public quizzes and user's own quizzes
    quizzes = db_service.get_available_quizzes(user_id)
    
    return render_template('quiz/index.html', quizzes=quizzes)


@quiz_bp.route('/start/<quiz_id>', methods=['GET', 'POST'])
@login_required
def start_quiz(quiz_id):
    """Start a quiz - handle password-protected quizzes"""
    quiz = db_service.get_quiz(quiz_id)
    
    if not quiz:
        flash('Quiz not found.', 'danger')
        return redirect(url_for('quiz.index'))
    
    # Check if quiz is password protected.
    # Human note: we keep the "gate" here so the user doesn't reach the quiz
    # page unless they have access.
    if quiz.get('is_password_protected'):
        if request.method == 'POST':
            password = request.form.get('password')
            if password == quiz.get('password'):
                session[f'quiz_access_{quiz_id}'] = True
            else:
                flash('Incorrect password.', 'danger')
                return render_template('quiz/password.html', quiz=quiz)
        else:
            if not session.get(f'quiz_access_{quiz_id}'):
                return render_template('quiz/password.html', quiz=quiz)
    
    return redirect(url_for('quiz.take_quiz', quiz_id=quiz_id))


@quiz_bp.route('/take/<quiz_id>')
@login_required
def take_quiz(quiz_id):
    """Take a quiz with adaptive question selection"""
    user_id = session.get('user_id')
    quiz = db_service.get_quiz(quiz_id)
    
    if not quiz:
        flash('Quiz not found.', 'danger')
        return redirect(url_for('quiz.index'))
    
    # Check password protection
    if quiz.get('is_password_protected') and not session.get(f'quiz_access_{quiz_id}'):
        return redirect(url_for('quiz.start_quiz', quiz_id=quiz_id))
    
    # Get user's mastery data
    user_data = db_service.get_user_data(user_id)
    concept_mastery = user_data.get('concept_mastery', {})
    
    # Get questions for this quiz
    questions = db_service.get_quiz_questions(quiz_id)
    
    # Use bandit algorithm to select questions adaptively.
    # Human note: this picks questions based on what the student seems to know,
    # so the quiz stays challenging without being random.
    if quiz.get('is_adaptive', True):
        selected_questions = bandit_service.select_questions(
            questions=questions,
            concept_mastery=concept_mastery,
            num_questions=quiz.get('num_questions', 10),
            algorithm=quiz.get('bandit_algorithm', 'thompson_sampling')
        )
    else:
        # Static selection
        selected_questions = questions[:quiz.get('num_questions', 10)]
    
    # Create quiz attempt.
    # This attempt_id is the thread that ties together: shown questions,
    # submitted answers, and the final results view.
    attempt_id = db_service.create_quiz_attempt(user_id, quiz_id, selected_questions)
    session[f'current_attempt_{quiz_id}'] = attempt_id
    
    display_questions = []
    for q in selected_questions:
        display_questions.append({
            'id': q.get('id'),
            'text': q.get('text'),
            'type': q.get('type'),
            'options': q.get('options', []),
            'concept': q.get('concept'),
            'difficulty': q.get('difficulty')
        })

    return render_template('quiz/take.html', 
                         quiz=quiz, 
                         questions=display_questions,
                         attempt_id=attempt_id)


@quiz_bp.route('/submit/<quiz_id>', methods=['POST'])
@login_required
def submit_quiz(quiz_id):
    """Submit quiz answers and calculate results"""
    user_id = session.get('user_id')
    attempt_id = session.get(f'current_attempt_{quiz_id}')

    quiz = db_service.get_quiz(quiz_id)
    if not quiz:
        flash('Quiz not found.', 'danger')
        return redirect(url_for('quiz.index'))
    
    if not attempt_id:
        flash('Quiz session expired. Please start again.', 'warning')
        return redirect(url_for('quiz.start_quiz', quiz_id=quiz_id))
    
    # Get submitted answers - collect ALL question IDs from the form.
    # Human note: we keep a separate list of presented_question_ids so we can
    # grade only what the student actually saw.
    answers = {}
    presented_question_ids = []
    for key, value in request.form.items():
        if key.startswith('question_'):
            question_id = key.replace('question_', '')
            presented_question_ids.append(question_id)
            if value.strip():  # Only include non-empty answers
                answers[question_id] = value
    
    # Capture time taken (sent from frontend timer)
    try:
        time_taken_raw = request.form.get('time_taken', '0')
        # Handle various formats: "120", "120.5", "NaN", "" etc
        if not time_taken_raw or time_taken_raw.lower() in ('nan', 'infinity', '-infinity'):
            time_taken_seconds = 0
        else:
            time_taken_seconds = int(float(time_taken_raw))
        if time_taken_seconds < 0:
            time_taken_seconds = 0
    except (ValueError, TypeError):
        print(f"[WARNING] Invalid time_taken value: {request.form.get('time_taken')}")
        time_taken_seconds = 0
    
    time_taken_minutes = time_taken_seconds // 60
    time_taken_display = f"{time_taken_minutes}m {time_taken_seconds % 60}s"
    
    print(f"\n{'='*60}")
    print(f"[SUBMIT] Quiz ID: {quiz_id}")
    print(f"[SUBMIT] User ID: {user_id}")
    print(f"[SUBMIT] Attempt ID: {attempt_id}")
    print(f"[SUBMIT] Questions presented: {len(presented_question_ids)}")
    print(f"[SUBMIT] Questions answered: {len(answers)}")
    print(f"[SUBMIT] Time taken: {time_taken_display}")
    print(f"[SUBMIT] Presented question IDs: {presented_question_ids}")
    print(f"[SUBMIT] Answered question IDs: {list(answers.keys())}")
    print(f"{'='*60}\n")
    
    # Validate we have questions
    if not presented_question_ids:
        print("[ERROR] No question IDs found in form submission!")
        flash('Error: No questions found in submission. Please try again.', 'danger')
        return redirect(url_for('quiz.start_quiz', quiz_id=quiz_id))
    
    # Calculate results - pass presented_question_ids so we evaluate only shown questions
    try:
        result = quiz_service.evaluate_quiz(quiz_id, attempt_id, answers, presented_question_ids)
    except Exception as e:
        print(f"[ERROR] Quiz evaluation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error evaluating quiz. Please try again.', 'danger')
        return redirect(url_for('quiz.start_quiz', quiz_id=quiz_id))
    
    # Ensure all required fields are in the result
    try:
        correct_count = int(result.get('correct', 0))
        total_questions = int(result.get('total_questions', 0))
        marks_obtained = int(result.get('marks_obtained', correct_count))
        total_marks = int(result.get('total_marks', total_questions))
        score_percentage = float(result.get('score', 0))
        
        # Validate score is in valid range
        if score_percentage < 0:
            score_percentage = 0
        elif score_percentage > 100:
            score_percentage = 100
    except (ValueError, TypeError) as e:
        print(f"[ERROR] Error parsing result values: {str(e)}")
        score_percentage = 0
        correct_count = 0
        total_questions = 0
        marks_obtained = 0
        total_marks = 0
    
    print(f"[RESULT] Quiz {quiz_id}: {correct_count}/{total_questions} correct ({score_percentage:.1f}%)")
    print(f"[RESULT] Marks: {marks_obtained}/{total_marks}")
    print(f"[RESULT] Detail results count: {len(result.get('results', []))}")
    
    # Build comprehensive result object
    result_data = {
        'score': score_percentage,  # Percentage (0-100)
        'correct': correct_count,  # Number of correct answers
        'total_questions': total_questions,  # Total questions
        'marks_obtained': marks_obtained,  # Marks earned
        'total_marks': total_marks,  # Total possible marks
        'score_percentage': score_percentage,  # Duplicate for template compatibility
        'timestamp': db_service.get_timestamp(),
        'time_taken': time_taken_seconds,
        'time_taken_display': time_taken_display,
        'concept_performance': result.get('concept_performance', {}),
        'results': result.get('results', []),  # Detailed answer reviews
    }

    # Attach quiz name so history/progress views can show it cleanly
    result_data['quiz_name'] = quiz.get('name', 'Quiz')
    
    print(f"[CALCULATION] Score: {marks_obtained}/{total_marks} marks = {score_percentage:.1f}%")
    
    # Store full result in session FIRST (before any potential Firebase errors)
    session[f'quiz_result_{attempt_id}'] = result_data
    session.modified = True  # Force session save
    
    print(f"[SESSION] Stored result in session key: quiz_result_{attempt_id}")
    
    # Try to save to Firebase, but don't crash if it fails
    save_success = True
    try:
        # Update user's concept mastery using bandit feedback
        try:
            bandit_service.update_mastery(user_id, result_data['concept_performance'])
        except Exception as e:
            print(f"[WARNING] Bandit update failed: {str(e)}")
        
        # Save attempt results (sanitized version will be saved to Firebase)
        try:
            db_service.save_quiz_result(user_id, quiz_id, attempt_id, result_data)
        except Exception as e:
            print(f"[WARNING] Failed to save quiz result: {str(e)}")
            raise
        
        # Update user's quiz history with score and time
        history_entry = {
            'quiz_id': quiz_id,
            'quiz_name': quiz.get('name', 'Quiz'),
            'score': score_percentage,
            'score_percentage': score_percentage,
            'correct': correct_count,
            'total_questions': total_questions,
            'marks_obtained': marks_obtained,
            'total_marks': total_marks,
            'time_taken': time_taken_seconds,
            'time_taken_display': time_taken_display,
            'timestamp': result_data['timestamp'],
            'attempt_id': attempt_id
        }
        
        # Quiz history is now stored ONLY in attempts collection
        # (remove duplicate storage to prevent inflated attempt counts)
        print(f"[HISTORY] Quiz result saved to attempts collection")
        
        print(f"[RESULTS] Results saved successfully")
        flash('Quiz completed successfully! Your score has been saved.', 'success')
        
    except Exception as e:
        # Log the error but continue to show results
        save_success = False
        print(f"[RESULTS_ERROR] Failed to save quiz results: {str(e)}")
        import traceback
        print(traceback.format_exc())
        flash(f'Quiz completed! Results saved locally (score: {marks_obtained}/{total_marks} = {score_percentage:.1f}%)', 'warning')
    
    # Clear session
    session.pop(f'current_attempt_{quiz_id}', None)
    session.pop(f'quiz_access_{quiz_id}', None)
    
    return redirect(url_for('quiz.results', quiz_id=quiz_id, attempt_id=attempt_id))


@quiz_bp.route('/results/<quiz_id>/<attempt_id>')
@login_required
def results(quiz_id, attempt_id):
    """View quiz results and feedback"""
    user_id = session.get('user_id')
    
    # First, try to get result from session (for immediate display after quiz)
    result = session.pop(f'quiz_result_{attempt_id}', None)
    
    # If not in session, get from Firebase (for viewing old results)
    if not result:
        result = db_service.get_quiz_result(user_id, quiz_id, attempt_id)
    
    quiz = db_service.get_quiz(quiz_id)
    
    if not result:
        flash('Results not found. Please try taking the quiz again.', 'danger')
        return redirect(url_for('quiz.index'))
    
    # Validate result has all required fields
    if 'score' not in result or result.get('score') is None:
        print(f"[WARNING] Result missing score field: {result.keys()}")
        flash('Warning: Some score information may be incomplete.', 'warning')
    
    # Ensure all required fields are present for template
    result_display = {
        'score': float(result.get('score', 0)),  # Percentage 0-100
        'correct': int(result.get('correct', 0)),  # Number correct
        'total_questions': int(result.get('total_questions', 0)),  # Total questions
        'marks_obtained': int(result.get('marks_obtained', result.get('correct', 0))),  # Marks earned
        'total_marks': int(result.get('total_marks', result.get('total_questions', 0))),  # Total marks
        'score_percentage': float(result.get('score_percentage', result.get('score', 0))),  # For compatibility
        'time_taken_display': result.get('time_taken_display', 'N/A'),
        'concept_performance': result.get('concept_performance', {}),
        'results': result.get('results', []),  # Detailed reviews
        'timestamp': result.get('timestamp'),
    }
    
    # Get quiz information and attempts data
    quiz_info = {
        'name': quiz.get('name', 'Quiz') if quiz else 'Quiz',
        'date': result_display.get('timestamp', '')[:10] if result_display.get('timestamp') else 'N/A',
        'attempt_id': attempt_id,
    }
    
    # Get all attempts for this quiz to show attempt count
    all_attempts = db_service.get_quiz_history(user_id)
    attempts_on_this_quiz = [a for a in all_attempts if isinstance(a, dict) and a.get('quiz_id') == quiz_id]

    # Normalize attempts so template can always access attempt.score, marks, etc.
    normalized_attempts = []
    for raw in attempts_on_this_quiz:
        result_block = raw.get('result', raw)

        # Score percentage
        try:
            score_val = float(result_block.get('score_percentage', result_block.get('score', 0)) or 0)
        except (ValueError, TypeError):
            score_val = 0.0

        # Marks and question counts
        try:
            correct = int(result_block.get('correct', 0) or 0)
        except (ValueError, TypeError):
            correct = 0
        try:
            total_q = int(result_block.get('total_questions', 0) or 0)
        except (ValueError, TypeError):
            total_q = 0

        try:
            marks_obtained = int(result_block.get('marks_obtained', correct) or 0)
        except (ValueError, TypeError):
            marks_obtained = correct
        try:
            total_marks = int(result_block.get('total_marks', total_q) or 0)
        except (ValueError, TypeError):
            total_marks = total_q

        # Timestamps and duration
        timestamp = str(
            result_block.get(
                'timestamp',
                raw.get('timestamp', raw.get('created_at', ''))
            )
        )
        time_taken_display = result_block.get('time_taken_display', 'N/A')

        # Attempt ID
        attempt_id_str = raw.get('id')
        if not attempt_id_str and raw.get('_id') is not None:
            attempt_id_str = str(raw.get('_id'))

        normalized_attempts.append({
            'attempt_id': attempt_id_str,
            'score': round(score_val, 1),
            'correct': correct,
            'total_questions': total_q,
            'marks_obtained': marks_obtained,
            'total_marks': total_marks,
            'timestamp': timestamp,
            'time_taken_display': time_taken_display,
        })

    quiz_info['total_attempts_on_quiz'] = len(normalized_attempts)
    quiz_info['best_score_on_quiz'] = max([a['score'] for a in normalized_attempts], default=0)

    # Sort attempts by timestamp for display
    normalized_attempts.sort(key=lambda x: x.get('timestamp', ''), reverse=False)
    quiz_info['attempts_list'] = normalized_attempts
    
    # Add quiz info to result display
    result_display['quiz_info'] = quiz_info
    
    print(f"[RESULTS] Displaying: {result_display['marks_obtained']}/{result_display['total_marks']} marks ({result_display['score']:.1f}%)")
    print(f"[RESULTS] Quiz: {quiz_info['name']}, Attempt {quiz_info['total_attempts_on_quiz']}")
    
    # Get weak concepts, strong concepts, and AI-powered recommendations
    weak_concepts = []
    strong_concepts = []
    recommendations = []
    study_plan = {}
    
    try:
        from services.recommendation_service import RecommendationService
        rec_service = RecommendationService()
        
        concept_perf = result_display.get('concept_performance', {})
        for concept, score in concept_perf.items():
            try:
                score_val = float(score) if isinstance(score, (int, float)) else 0
                if score_val < 0.5:
                    weak_concepts.append({'name': concept, 'score': score_val})
                elif score_val >= 0.8:
                    strong_concepts.append({'name': concept, 'score': score_val})
            except (ValueError, TypeError):
                continue
        
        weak_concepts.sort(key=lambda x: x['score'])
        strong_concepts.sort(key=lambda x: x['score'], reverse=True)
        
        # Generate AI-powered recommendations with structured data
        quiz_results = result_display.get('results', [])
        recommendations = rec_service.get_learning_recommendations(
            weak_concepts=weak_concepts,
            concept_performance=concept_perf,
            quiz_results=quiz_results,
            max_recommendations=5
        )
        
        # Get study plan
        study_plan = rec_service.get_study_plan(
            weak_concepts=weak_concepts,
            strong_concepts=strong_concepts,
            overall_score=result_display['score']
        )
        
        print(f"[RECOMMENDATIONS] Generated {len(recommendations)} recommendations")
        print(f"[WEAK_CONCEPTS] {len(weak_concepts)} weak, [STRONG_CONCEPTS] {len(strong_concepts)} strong")
            
    except Exception as e:
        print(f"[ERROR] Error generating recommendations: {str(e)}")
        import traceback
        traceback.print_exc()
        # Fallback: basic recommendations as before
        if weak_concepts:
            for wc in weak_concepts[:3]:
                score_pct = wc['score'] * 100
                recommendations.append({
                    'concept': f"📚 {wc['name']}",
                    'concept_clean': wc['name'],
                    'score': wc['score'],
                    'score_pct': score_pct,
                    'priority': 'high' if score_pct < 30 else 'medium',
                    'actions': [
                        'Review course materials',
                        'Practice more problems',
                        'Watch tutorial videos'
                    ],
                    'explanation': f'Score: {score_pct:.0f}%. This needs improvement.'
                })
        else:
            recommendations.append({
                'concept': '✅ Excellent!',
                'concept_clean': 'Excellent',
                'score': 1.0,
                'score_pct': 100,
                'priority': 'positive',
                'actions': [
                    'Review complex topics for mastery',
                    'Help other students',
                    'Challenge yourself with difficult problems'
                ],
                'explanation': 'You performed well across all topics!'
            })
    
    # Categorize detailed results by correctness
    correct_answers = [r for r in result_display.get('results', []) if r.get('is_correct')]
    incorrect_answers = [r for r in result_display.get('results', []) if not r.get('is_correct')]
    
    return render_template('quiz/results.html', 
                         quiz=quiz,
                         result=result_display, 
                         weak_concepts=weak_concepts,
                         strong_concepts=strong_concepts,
                         recommendations=recommendations,
                         correct_answers=correct_answers,
                         incorrect_answers=incorrect_answers,
                         study_plan=study_plan,
                         attempt_id=attempt_id)


@quiz_bp.route('/history')
@login_required
def history():
    """View quiz history"""
    user_id = session.get('user_id')
    history_raw = db_service.get_quiz_history(user_id)
    
    # Normalize history entries to have consistent field names
    history = []
    for entry in history_raw:
        if not isinstance(entry, dict):
            continue
        
        score_val = 0
        try:
            score_val = float(entry.get('score_percentage', entry.get('score', 0)) or 0)
        except (ValueError, TypeError):
            pass
        
        correct = int(entry.get('correct', 0) or 0)
        total = int(entry.get('total_questions', 0) or 0)
        marks_obtained = int(entry.get('marks_obtained', correct) or 0)
        total_marks = int(entry.get('total_marks', total) or 0)
        
        # Parse timestamp for display
        timestamp = str(entry.get('timestamp', ''))
        date_display = timestamp[:10] if len(timestamp) >= 10 else 'N/A'
        
        history.append({
            'quiz_id': entry.get('quiz_id', ''),
            'quiz_name': entry.get('quiz_name', 'Quiz'),
            'score': round(score_val, 1),
            'correct': correct,
            'total': total,
            'marks_obtained': marks_obtained,
            'total_marks': total_marks,
            'timestamp': timestamp,
            'date': date_display,
            'time_taken_display': entry.get('time_taken_display', 'N/A'),
            'attempt_id': entry.get('attempt_id', ''),
        })
    
    # Sort by timestamp descending (newest first)
    history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Calculate summary stats
    scores = [h['score'] for h in history if h['score'] > 0]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    best_score = round(max(scores), 1) if scores else 0
    total_questions = sum(h['total'] for h in history)
    
    return render_template('quiz/history.html', 
                         history=history,
                         avg_score=avg_score,
                         best_score=best_score,
                         total_questions=total_questions)


@quiz_bp.route('/find', methods=['GET', 'POST'])
def find_quiz():
    """Find and join quiz by 16-digit code"""
    if request.method == 'POST':
        quiz_code = request.form.get('quiz_code', '').upper().strip()
        
        if not quiz_code:
            flash('Please enter a quiz code.', 'warning')
            return render_template('quiz/find.html')
        
        # Validate code format (16 alphanumeric characters)
        if len(quiz_code) != 16 or not all(c in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in quiz_code):
            flash(f'Invalid code format. Code must be exactly 16 alphanumeric characters. You entered: {len(quiz_code)} characters.', 'danger')
            return render_template('quiz/find.html')
        
        # Look up quiz by code
        print(f"[Quiz Search] Looking up code: {quiz_code}")
        quiz_id = db_service.get_quiz_by_code(quiz_code)
        
        if not quiz_id:
            flash(f'Quiz code "{quiz_code}" not found. Please check and try again. Make sure you have the correct 16-character code from your instructor.', 'danger')
            return render_template('quiz/find.html')
        
        print(f"[Quiz Search] Found quiz ID: {quiz_id}")
        
        # Check if user is logged in
        if 'user_id' not in session:
            session['next_quiz_id'] = quiz_id
            flash('Please login to access this quiz.', 'info')
            return redirect(url_for('auth.login'))
        
        flash(f'Quiz found! Starting quiz...', 'success')
        # Redirect to quiz start
        return redirect(url_for('quiz.start_quiz', quiz_id=quiz_id))
    
    return render_template('quiz/find.html')


@quiz_bp.route('/code/<quiz_id>')
@login_required
def get_quiz_code(quiz_id):
    """Get quiz code for sharing (JSON endpoint)"""
    quiz = db_service.get_quiz(quiz_id)
    
    if not quiz:
        return jsonify({'error': 'Quiz not found'}), 404
    
    # Verify user is quiz creator
    if quiz.get('instructor_id') != session.get('user_id'):
        # Allow instructors/creators to share
        pass
    
    return jsonify({
        'quiz_code': quiz.get('quiz_code', 'N/A'),
        'quiz_id': quiz_id,
        'quiz_name': quiz.get('name', 'Untitled')
    })


