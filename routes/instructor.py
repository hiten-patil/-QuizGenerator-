"""
Instructor routes - Create quizzes, manage content
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from functools import wraps
from werkzeug.utils import secure_filename
import os
from config.extensions import db_service, document_service, concept_service, question_generator

instructor_bp = Blueprint('instructor', __name__)


def instructor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'instructor':
            flash('Instructor access required.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


@instructor_bp.route('/')
@instructor_required
def index():
    """Instructor dashboard"""
    user_id = session.get('user_id')
    
    # Get instructor's quizzes
    quizzes = db_service.get_instructor_quizzes(user_id)
    
    # Get uploaded documents
    documents = db_service.get_instructor_documents(user_id)
    
    return render_template('instructor/index.html', 
                         quizzes=quizzes,
                         documents=documents)


@instructor_bp.route('/upload', methods=['GET', 'POST'])
@instructor_required
def upload_document():
    """Upload lecture notes"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            # Save file locally temporarily
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            
            try:
                # Extract text from document
                text = document_service.extract_text(filepath)
                
                # Filter content for better quiz generation
                text = document_service.filter_content_for_quiz(text)
                
                # Extract concepts with error handling
                try:
                    concepts = concept_service.extract_concepts(text)
                except Exception as e:
                    print(f"Warning: Concept extraction error: {e}")
                    concepts = []
                
                # Build knowledge graph with fallback
                try:
                    if concepts:
                        knowledge_graph = concept_service.build_knowledge_graph(concepts, text)
                    else:
                        knowledge_graph = {'nodes': [], 'edges': []}
                except Exception as e:
                    print(f"Warning: Knowledge graph building error: {e}")
                    knowledge_graph = {'nodes': [], 'edges': []}
                
                # Save document info to MongoDB
                user_id = session.get('user_id')
                doc_id = db_service.save_document(user_id, {
                    'filename': filename,
                    'text': text,
                    'concepts': concepts,
                    'knowledge_graph': knowledge_graph
                })
                
                concept_count = len(concepts) if concepts else 0
                flash(f'Document uploaded successfully! Extracted {concept_count} concepts.', 'success')
                return redirect(url_for('instructor.view_document', doc_id=doc_id))
                
            except Exception as e:
                flash(f'Error processing document: {str(e)}', 'danger')
            finally:
                # Clean up local file
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Invalid file type. Please upload PDF, TXT, or DOCX.', 'danger')
    
    return render_template('instructor/upload.html')


@instructor_bp.route('/document/<doc_id>')
@instructor_required
def view_document(doc_id):
    """View uploaded document with concepts"""
    document = db_service.get_document(doc_id)
    
    if not document:
        flash('Document not found.', 'danger')
        return redirect(url_for('instructor.index'))
    
    return render_template('instructor/document.html', document=document)


@instructor_bp.route('/generate-quiz/<doc_id>', methods=['GET', 'POST'])
@instructor_required
def generate_quiz(doc_id):
    """Generate quiz from document"""
    document = db_service.get_document(doc_id)
    
    if not document:
        flash('Document not found.', 'danger')
        return redirect(url_for('instructor.index'))
    
    if request.method == 'POST':
        # Get quiz settings
        quiz_name = request.form.get('quiz_name')
        num_questions = int(request.form.get('num_questions', 10))
        # Support multi-type: checkboxes for mcq, true_false, short_answer
        question_types = request.form.getlist('question_types')
        if not question_types:
            question_types = ['mcq', 'true_false', 'short_answer']
        difficulty = request.form.get('difficulty', 'mixed')
        is_adaptive = request.form.get('is_adaptive') == 'on'
        is_password_protected = request.form.get('is_password_protected') == 'on'
        password = request.form.get('password', '')
        
        # Validate quiz settings
        if not quiz_name:
            flash('Quiz name is required.', 'danger')
            return render_template('instructor/generate_quiz.html', document=document)
        
        if num_questions < 1:
            flash('Number of questions must be at least 1.', 'danger')
            return render_template('instructor/generate_quiz.html', document=document)
        
        # Check if concepts exist
        concepts = document.get('concepts')
        if not concepts or len(concepts) == 0:
            flash('No concepts found in document. Please ensure the document has extractable content.', 'danger')
            return render_template('instructor/generate_quiz.html', document=document)
        
        try:
            # Generate questions
            questions = question_generator.generate_questions(
                text=document.get('text'),
                concepts=concepts,
                knowledge_graph=document.get('knowledge_graph', {'nodes': [], 'edges': []}),
                num_questions=num_questions,
                question_types=question_types,
                difficulty=difficulty
            )
            
            # Create quiz
            user_id = session.get('user_id')
            quiz_data = {
                'name': quiz_name,
                'document_id': doc_id,
                'instructor_id': user_id,
                'num_questions': num_questions,
                'question_types': question_types,
                'difficulty': difficulty,
                'is_adaptive': is_adaptive,
                'is_password_protected': is_password_protected,
                'password': password if is_password_protected else None
            }
            
            quiz_id = db_service.create_quiz(quiz_data, questions)
            
            flash(f'Quiz "{quiz_name}" generated successfully with {len(questions)} questions!', 'success')
            return redirect(url_for('instructor.view_quiz', quiz_id=quiz_id))
            
        except Exception as e:
            flash(f'Error generating quiz: {str(e)}', 'danger')
    
    return render_template('instructor/generate_quiz.html', document=document)


@instructor_bp.route('/quiz/<quiz_id>')
@instructor_required
def view_quiz(quiz_id):
    """View quiz details"""
    quiz = db_service.get_quiz(quiz_id)
    questions = db_service.get_quiz_questions(quiz_id)
    
    if not quiz:
        flash('Quiz not found.', 'danger')
        return redirect(url_for('instructor.index'))
    
    # Get quiz statistics
    stats = db_service.get_quiz_statistics(quiz_id)
    
    # Calculate question type counts
    question_type_counts = {
        'mcq': 0,
        'tf': 0,
        'short': 0
    }
    
    for q in questions:
        q_type = q.get('type', 'mcq')
        if q_type == 'mcq':
            question_type_counts['mcq'] += 1
        elif q_type == 'true_false':
            question_type_counts['tf'] += 1
        elif q_type == 'short_answer':
            question_type_counts['short'] += 1
    
    return render_template('instructor/view_quiz.html', 
                         quiz=quiz, 
                         questions=questions,
                         stats=stats,
                         question_type_counts=question_type_counts)


@instructor_bp.route('/quiz/<quiz_id>/edit', methods=['GET', 'POST'])
@instructor_required
def edit_quiz(quiz_id):
    """Edit quiz questions"""
    quiz = db_service.get_quiz(quiz_id)
    questions = db_service.get_quiz_questions(quiz_id)
    
    if not quiz:
        flash('Quiz not found.', 'danger')
        return redirect(url_for('instructor.index'))
    
    if request.method == 'POST':
        # Handle question edits
        for question in questions:
            q_id = question['id']
            question['text'] = request.form.get(f'question_text_{q_id}', question['text'])
            question['correct_answer'] = request.form.get(f'correct_answer_{q_id}', question.get('correct_answer'))
            
            # Update options for MCQ
            if question['type'] == 'mcq':
                options = []
                for i in range(4):
                    opt = request.form.get(f'option_{q_id}_{i}')
                    if opt:
                        options.append(opt)
                question['options'] = options
        
        db_service.update_quiz_questions(quiz_id, questions)
        flash('Quiz updated successfully!', 'success')
        return redirect(url_for('instructor.view_quiz', quiz_id=quiz_id))
    
    return render_template('instructor/edit_quiz.html', quiz=quiz, questions=questions)


@instructor_bp.route('/quiz/<quiz_id>/delete', methods=['POST'])
@instructor_required
def delete_quiz(quiz_id):
    """Delete a quiz"""
    quiz = db_service.get_quiz(quiz_id)
    
    if not quiz:
        flash('Quiz not found.', 'danger')
        return redirect(url_for('instructor.index'))
    
    # Verify user owns this quiz
    if quiz.get('instructor_id') != session.get('user_id'):
        flash('You do not have permission to delete this quiz.', 'danger')
        return redirect(url_for('instructor.index'))
    
    try:
        db_service.delete_quiz(quiz_id)
        flash(f'Quiz "{quiz.get("name", "Quiz")}" deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting quiz: {str(e)}', 'danger')
    
    return redirect(url_for('instructor.index'))


@instructor_bp.route('/analytics')
@instructor_required
def analytics():
    """View analytics across all quizzes"""
    user_id = session.get('user_id')
    
    # Get aggregated statistics
    stats = db_service.get_instructor_analytics(user_id)
    
    return render_template('instructor/analytics.html', stats=stats)


def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'pdf', 'txt', 'docx'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
