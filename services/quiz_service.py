"""
Quiz Service - Evaluate quiz answers and provide feedback
"""
import re
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher


class QuizService:
    """
    Service for evaluating quiz answers and generating feedback.
    """
    
    def __init__(self, db_service=None):
        self.db_service = db_service  # Can be injected for shared connections
        self._sentence_model = None
    
    def _load_sentence_model(self):
        """Load sentence transformer for semantic similarity"""
        if self._sentence_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
            except ImportError:
                self._sentence_model = None
    
    def evaluate_quiz(self, quiz_id: str, attempt_id: str,
                     answers: Dict[str, str],
                     presented_question_ids: list = None) -> Dict:
        """
        Evaluate all answers in a quiz attempt.
        
        Args:
            quiz_id: Quiz identifier
            attempt_id: Attempt identifier
            answers: Dict mapping question_id to user's answer
            presented_question_ids: List of question IDs that were shown to the user.
                If provided, only these questions are evaluated.
            
        Returns:
            Result dictionary with scores and details
        """
        try:
            # Use injected db_service if available, otherwise create new one
            db = getattr(self, 'db_service', None) or MongoDBService()
            
            all_questions = db.get_quiz_questions(quiz_id)
        except Exception as e:
            print(f"[ERROR] Failed to get questions from MongoDB: {str(e)}")
            return {
                'score': 0,
                'correct': 0,
                'total_questions': 0,
                'marks_obtained': 0,
                'total_marks': 0,
                'results': [],
                'concept_performance': {}
            }
        
        print(f"\\n[QUIZ_EVAL] All questions from MongoDB: {len(all_questions)}")
        print(f"[QUIZ_EVAL] Question IDs from MongoDB: {[q.get('id', 'NO_ID') for q in all_questions]}")
        print(f"[QUIZ_EVAL] Presented question IDs: {presented_question_ids}")
        print(f"[QUIZ_EVAL] Answer keys: {list(answers.keys())}")
        
        # If we know which questions were presented, only evaluate those
        if presented_question_ids:
            presented_set = set(presented_question_ids)
            questions = [q for q in all_questions if q.get('id') in presented_set]
            
            print(f"[QUIZ_EVAL] Matched {len(questions)} questions by ID")
            
            # If filtering gave 0 results (ID mismatch), try matching by internal id field
            if not questions:
                print(f"[QUIZ_EVAL] WARNING: No ID match! Trying fallback...")
                # Try matching by the old q_0, q_1 style IDs in case of legacy data
                questions = [q for q in all_questions 
                            if q.get('internal_id') in presented_set]
            
            # If still no match, fall back to all questions
            if not questions:
                print(f"[QUIZ_EVAL] WARNING: Using all questions as fallback")
                questions = all_questions
        else:
            questions = all_questions
        
        if not questions:
            print(f"[QUIZ_EVAL] ERROR: No questions found for quiz {quiz_id}!")
            return {
                'score': 0,
                'correct': 0,
                'total_questions': 0,
                'marks_obtained': 0,
                'total_marks': 0,
                'results': [],
                'concept_performance': {}
            }
        
        results = []
        correct_count = 0
        concept_performance = {}
        marks_obtained = 0
        total_marks = len(questions)  # 1 mark per question
        
        try:
            for question in questions:
                try:
                    q_id = question.get('id')
                    if not q_id:
                        print(f"[WARNING] Question has no ID: {question}")
                        continue
                    
                    if q_id in answers and answers[q_id].strip():
                        # User answered this question
                        user_answer = answers[q_id]
                        eval_result = self.evaluate_answer(quiz_id, q_id, user_answer, question)
                    else:
                        # User did not answer - mark as incorrect
                        eval_result = {
                            'question_id': q_id,
                            'question_text': question.get('text', question.get('question', 'Question not available')),
                            'question_type': question.get('type', 'mcq'),
                            'is_correct': False,
                            'user_answer': '(Not answered)',
                            'correct_answer': question.get('correct_answer', ''),
                            'concept': question.get('concept', 'General'),
                            'explanation': question.get('explanation', 'No explanation available.'),
                            'marks_obtained': 0,
                            'marks_total': 1,
                            'options': question.get('options', [])
                        }
                    
                    # Ensure marks info is present (1 mark per question)
                    if 'marks_obtained' not in eval_result:
                        eval_result['marks_obtained'] = 1 if eval_result['is_correct'] else 0
                        eval_result['marks_total'] = 1
                    
                    results.append(eval_result)
                    
                    if eval_result['is_correct']:
                        correct_count += 1
                        marks_obtained += 1
                    
                    # Track concept performance
                    concept = question.get('concept', 'unknown')
                    if concept not in concept_performance:
                        concept_performance[concept] = {'correct': 0, 'total': 0}
                    
                    concept_performance[concept]['total'] += 1
                    if eval_result['is_correct']:
                        concept_performance[concept]['correct'] += 1
                        
                except Exception as e:
                    print(f"[ERROR] Evaluating question {q_id}: {str(e)}")
                    # Add a failed evaluation result
                    results.append({
                        'question_id': question.get('id', 'unknown'),
                        'question_text': 'Error evaluating question',
                        'is_correct': False,
                        'user_answer': '(Not answered)',
                        'correct_answer': '',
                        'concept': 'unknown',
                        'explanation': 'Error occurred during evaluation',
                        'marks_obtained': 0,
                        'marks_total': 1,
                        'options': []
                    })
        except Exception as e:
            print(f"[ERROR] Unexpected error in evaluation loop: {str(e)}")
            import traceback
            traceback.print_exc()
        
        # Calculate concept scores
        concept_scores = {}
        try:
            for concept, perf in concept_performance.items():
                if perf.get('total', 0) > 0:
                    score_val = perf.get('correct', 0) / perf.get('total', 1)
                    # Ensure score is finite
                    if not (-1 <= score_val <= 1):
                        score_val = 0
                    concept_scores[concept] = score_val
                else:
                    concept_scores[concept] = 0
        except Exception as e:
            print(f"[ERROR] Error calculating concept scores: {str(e)}")
            concept_scores = {c: 0 for c in concept_performance.keys()}
        
        total = len(results)
        try:
            score = (correct_count / total * 100) if total > 0 else 0
            # Ensure score is valid
            if not (0 <= score <= 100):
                score = 0
        except Exception as e:
            print(f"[ERROR] Error calculating score: {str(e)}")
            score = 0
        
        print(f"\n{'='*60}")
        print(f"[QUIZ_EVAL] Quiz ID: {quiz_id}")
        print(f"[QUIZ_EVAL] Attempt ID: {attempt_id}")
        print(f"[QUIZ_EVAL] Questions evaluated: {total}")
        print(f"[QUIZ_EVAL] Correct answers: {correct_count}/{total} = {score:.1f}%")
        print(f"[QUIZ_EVAL] Marks obtained: {marks_obtained}/{total_marks}")
        print(f"[QUIZ_EVAL] Answers received for: {len(answers)} questions")
        print(f"[QUIZ_EVAL] Concept performance: {concept_scores}")
        print(f"{'='*60}\n")
        
        return {
            'score': score,
            'correct': correct_count,
            'total_questions': total,
            'marks_obtained': int(marks_obtained),
            'total_marks': int(total_marks),
            'results': results,
            'concept_performance': concept_scores
        }
    
    def evaluate_answer(self, quiz_id: str, question_id: str,
                       user_answer: str, question: Dict = None) -> Dict:
        """
        Evaluate a single answer.
        
        Args:
            quiz_id: Quiz identifier
            question_id: Question identifier
            user_answer: User's submitted answer
            question: Optional question dict (fetched if not provided)
            
        Returns:
            Evaluation result with correctness and feedback
        """
        try:
            if question is None:
                from services.firebase_service import FirebaseService
                firebase = FirebaseService()
                question = firebase.get_question(quiz_id, question_id)
            
            if not question:
                return {
                    'question_id': question_id,
                    'question_text': 'Question not available',
                    'is_correct': False,
                    'user_answer': user_answer or '(Not answered)',
                    'correct_answer': '',
                    'concept': 'General',
                    'explanation': 'Question not found',
                    'marks_obtained': 0,
                    'marks_total': 1,
                    'options': []
                }
            
            q_type = question.get('type', 'mcq')
            correct_answer = question.get('correct_answer', '')
            
            # Evaluate based on question type
            if q_type == 'mcq':
                is_correct = self._evaluate_mcq(user_answer, correct_answer)
            elif q_type == 'true_false':
                is_correct = self._evaluate_true_false(user_answer, correct_answer)
            elif q_type == 'short_answer':
                is_correct, similarity = self._evaluate_short_answer(
                    user_answer, correct_answer, question.get('keywords', [])
                )
            else:
                is_correct = user_answer.strip().lower() == correct_answer.strip().lower()

            # Resolve letter-based correct_answer to readable display text
            display_correct = correct_answer
            display_user = user_answer
            options = question.get('options', [])

            if correct_answer.strip().upper() in ('A', 'B', 'C', 'D') and options:
                letter_index = ord(correct_answer.strip().upper()) - ord('A')
                if 0 <= letter_index < len(options):
                    opt_text = re.sub(r'^[A-Da-d][.):\s]+\s*', '', str(options[letter_index]))
                    display_correct = f"{correct_answer.strip().upper()}. {opt_text}"

            # Also resolve user's answer letter to readable text
            if user_answer.strip().upper() in ('A', 'B', 'C', 'D') and options:
                u_idx = ord(user_answer.strip().upper()) - ord('A')
                if 0 <= u_idx < len(options):
                    u_text = re.sub(r'^[A-Da-d][.):\s]+\s*', '', str(options[u_idx]))
                    display_user = f"{user_answer.strip().upper()}. {u_text}"

            return {
                'question_id': question_id,
                'question_text': question.get('text', question.get('question', 'Question not available')),
                'question_type': q_type,
                'is_correct': is_correct,
                'user_answer': display_user or '(Not answered)',
                'correct_answer': display_correct,
                'concept': question.get('concept', 'General'),
                'explanation': question.get('explanation', 'No explanation available for this question.'),
                'marks_obtained': int(1 if is_correct else 0),
                'marks_total': int(1),
                'options': options
            }
        except Exception as e:
            print(f"[ERROR] Error evaluating answer for question {question_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'question_id': question_id,
                'question_text': 'Question not available',
                'is_correct': False,
                'user_answer': user_answer or '(Not answered)',
                'correct_answer': '',
                'concept': 'General',
                'explanation': 'Error evaluating answer',
                'marks_obtained': 0,
                'marks_total': 1,
                'options': []
            }
    
    def _evaluate_mcq(self, user_answer: str, correct_answer: str) -> bool:
        """Evaluate MCQ answer with robust comparison.

        Handles both letter-based answers (A/B/C/D) and full-text answers.
        The user_answer from the form may be "A. Paris" while correct_answer
        may be just "A" (new format) or the full text (legacy format).
        """
        user_clean = user_answer.strip()
        correct_clean = correct_answer.strip()

        # Direct match (case-insensitive)
        if user_clean.lower() == correct_clean.lower():
            return True

        # Extract leading letter from user answer (e.g. "A. Paris" -> "A")
        letter_match = re.match(r'^([A-Da-d])\.\s', user_clean)
        user_letter = letter_match.group(1).upper() if letter_match else None

        # If correct_answer is a single letter (new format), compare letters
        if correct_clean.upper() in ('A', 'B', 'C', 'D'):
            if user_letter and user_letter == correct_clean.upper():
                return True
            # User may have submitted just the letter
            if user_clean.upper() in ('A', 'B', 'C', 'D'):
                return user_clean.upper() == correct_clean.upper()

        # If correct_answer also has a letter prefix, compare both letters
        correct_letter_match = re.match(r'^([A-Da-d])\.\s', correct_clean)
        if correct_letter_match and user_letter:
            return user_letter == correct_letter_match.group(1).upper()

        # Fallback: strip punctuation and compare full text
        user_alpha = re.sub(r'[^a-z0-9\s]', '', user_clean.lower()).strip()
        correct_alpha = re.sub(r'[^a-z0-9\s]', '', correct_clean.lower()).strip()

        return user_alpha == correct_alpha
    
    def _evaluate_true_false(self, user_answer: str, correct_answer: str) -> bool:
        """Evaluate True/False answer"""
        user_clean = user_answer.strip().lower()
        correct_clean = correct_answer.strip().lower()
        
        # Handle various formats
        true_values = {'true', 't', 'yes', '1'}
        false_values = {'false', 'f', 'no', '0'}
        
        user_bool = user_clean in true_values
        correct_bool = correct_clean in true_values
        
        if user_clean in true_values or user_clean in false_values:
            if correct_clean in true_values or correct_clean in false_values:
                return user_bool == correct_bool
        
        return user_clean == correct_clean
    
    def _evaluate_short_answer(self, user_answer: str, correct_answer: str,
                               keywords: List[str] = None) -> Tuple[bool, float]:
        """
        Evaluate short answer using multiple methods.
        
        Returns:
            Tuple of (is_correct, similarity_score)
        """
        user_clean = user_answer.strip().lower()
        correct_clean = correct_answer.strip().lower()
        
        # Method 1: Exact match
        if user_clean == correct_clean:
            return True, 1.0
        
        # Method 2: Keyword matching
        if keywords:
            keywords_found = sum(1 for kw in keywords if kw.lower() in user_clean)
            keyword_ratio = keywords_found / len(keywords)
            
            if keyword_ratio >= 0.6:
                return True, keyword_ratio
        
        # Method 3: String similarity
        string_sim = SequenceMatcher(None, user_clean, correct_clean).ratio()
        
        if string_sim > 0.8:
            return True, string_sim
        
        # Method 4: Semantic Similarity Grading
        # This is where we understand what the student actually meant!
        # Step 1: If exact words and string ratios fail, we read their answer.
        # Step 2: Convert both the student's answer and the correct answer into vectors (lists of numbers).
        # Step 3: Check how much of the "meaning" overlaps, giving credit to paraphrasing without giving away marks for unrelated guesses.
        self._load_sentence_model()
        
        if self._sentence_model:
            try:
                import numpy as np
                
                # Turn sentences into mathematical meanings
                embeddings = self._sentence_model.encode([user_clean, correct_clean])
                
                # Check how big these meaning vectors are (norm)
                norm1 = np.linalg.norm(embeddings[0])
                norm2 = np.linalg.norm(embeddings[1])
                
                if norm1 > 0 and norm2 > 0:
                    # Compare the two vectors: dot product over normalized product.
                    # This tells us how closely related the actual concepts are.
                    semantic_sim = float(np.dot(embeddings[0], embeddings[1]) / (norm1 * norm2))
                    
                    # Fix any weird maths resulting from empty strings
                    if not np.isfinite(semantic_sim):
                        semantic_sim = 0.0
                    
                    # Step 4: Grading. The threshold here is 0.7.
                    # If it's mostly the same idea (e.g. "car" vs "automobile" semantics), reward the student!
                    if semantic_sim > 0.7:
                        return True, semantic_sim
                
            except Exception as e:
                print(f"[SEMANTIC] Error in semantic similarity: {str(e)}")
                pass
        
        # Not correct
        return False, max(string_sim, 0)
    
    def get_weak_concepts(self, result: Dict, threshold: float = 0.5) -> List[Dict]:
        """
        Identify weak concepts from quiz results.
        
        Args:
            result: Quiz result dictionary
            threshold: Score below which a concept is considered weak
            
        Returns:
            List of weak concept dictionaries
        """
        concept_performance = result.get('concept_performance', {})
        
        weak_concepts = []
        for concept, score in concept_performance.items():
            if score < threshold:
                weak_concepts.append({
                    'name': concept,
                    'score': score,
                    'priority': 1 - score  # Higher priority for lower scores
                })
        
        # Sort by priority (highest first)
        weak_concepts.sort(key=lambda x: x['priority'], reverse=True)
        
        return weak_concepts
    
    def get_study_recommendations(self, weak_concepts: List[Dict],
                                  quiz_id: str) -> List[Dict]:
        """
        Generate study recommendations based on weak concepts.
        
        Args:
            weak_concepts: List of weak concept dictionaries
            quiz_id: Quiz identifier for context
            
        Returns:
            List of recommendation dictionaries
        """
        from services.firebase_service import FirebaseService
        firebase = FirebaseService()
        
        quiz = firebase.get_quiz(quiz_id)
        doc_id = quiz.get('document_id') if quiz else None
        
        recommendations = []
        
        for concept in weak_concepts:
            rec = {
                'concept': concept['name'],
                'priority': concept['priority'],
                'actions': [
                    f"Review the section on {concept['name']}",
                    f"Practice more questions about {concept['name']}",
                    f"Create flashcards for {concept['name']} key points"
                ]
            }
            
            # Add related concepts if document is available
            if doc_id:
                document = firebase.get_document(doc_id)
                if document and 'knowledge_graph' in document:
                    from services.concept_service import ConceptService
                    concept_service = ConceptService()
                    
                    related = concept_service.get_related_concepts(
                        concept['name'], document['knowledge_graph']
                    )
                    
                    if related:
                        rec['related_concepts'] = related[:3]
                        rec['actions'].append(
                            f"Also review related concepts: {', '.join(related[:3])}"
                        )
            
            recommendations.append(rec)
        
        return recommendations
    
    def calculate_learning_gain(self, pre_test_result: Dict,
                                post_test_result: Dict) -> Dict:
        """
        Calculate learning gain between pre and post test.
        
        Args:
            pre_test_result: Pre-test quiz result
            post_test_result: Post-test quiz result
            
        Returns:
            Learning gain metrics
        """
        pre_score = pre_test_result.get('score', 0)
        post_score = post_test_result.get('score', 0)
        
        # Raw gain
        raw_gain = post_score - pre_score
        
        # Normalized gain: (post - pre) / (100 - pre)
        # This accounts for ceiling effects
        if pre_score < 100:
            normalized_gain = (post_score - pre_score) / (100 - pre_score)
        else:
            normalized_gain = 0
        
        # Concept-level gains
        pre_concepts = pre_test_result.get('concept_performance', {})
        post_concepts = post_test_result.get('concept_performance', {})
        
        concept_gains = {}
        for concept in set(pre_concepts.keys()) | set(post_concepts.keys()):
            pre = pre_concepts.get(concept, 0)
            post = post_concepts.get(concept, 0)
            concept_gains[concept] = post - pre
        
        return {
            'raw_gain': raw_gain,
            'normalized_gain': normalized_gain,
            'pre_score': pre_score,
            'post_score': post_score,
            'concept_gains': concept_gains,
            'improved_concepts': [c for c, g in concept_gains.items() if g > 0],
            'declined_concepts': [c for c, g in concept_gains.items() if g < 0]
        }
    
    def generate_performance_report(self, user_id: str) -> Dict:
        """
        Generate comprehensive performance report for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Performance report dictionary
        """
        from services.firebase_service import FirebaseService
        firebase = FirebaseService()
        
        user_data = firebase.get_user_data(user_id)
        quiz_history = user_data.get('quiz_history', [])
        concept_mastery = user_data.get('concept_mastery', {})
        
        # Overall statistics
        if quiz_history:
            scores = [q.get('score', 0) for q in quiz_history]
            avg_score = sum(scores) / len(scores)
            trend = self._calculate_trend(scores)
        else:
            avg_score = 0
            trend = 'no_data'
        
        # Concept breakdown
        strong_concepts = [c for c, m in concept_mastery.items() if m >= 0.7]
        weak_concepts = [c for c, m in concept_mastery.items() if m < 0.5]
        improving_concepts = []  # Would need historical data
        
        return {
            'total_quizzes': len(quiz_history),
            'average_score': avg_score,
            'score_trend': trend,
            'concepts_mastered': len(strong_concepts),
            'concepts_need_work': len(weak_concepts),
            'strong_concepts': strong_concepts,
            'weak_concepts': weak_concepts,
            'overall_mastery': sum(concept_mastery.values()) / len(concept_mastery) 
                              if concept_mastery else 0
        }
    
    def _calculate_trend(self, scores: List[float]) -> str:
        """Calculate trend from scores"""
        if len(scores) < 3:
            return 'insufficient_data'
        
        recent = scores[-3:]
        early = scores[:3]
        
        recent_avg = sum(recent) / len(recent)
        early_avg = sum(early) / len(early)
        
        diff = recent_avg - early_avg
        
        if diff > 5:
            return 'improving'
        elif diff < -5:
            return 'declining'
        else:
            return 'stable'
