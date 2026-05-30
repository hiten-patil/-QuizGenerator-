"""
Progress Service - Track user quiz performance and provide analytics
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from services.mongodb_service import MongoDBService


class ProgressService:
    """Service for tracking user progress and generating performance analytics"""
    
    def __init__(self, db_service=None):
        # Use injected db_service or create new one for backward compatibility
        self.db_service = db_service or MongoDBService()
    
    def get_user_progress(self, user_id: str) -> Dict:
        """Get comprehensive user progress including stats and trends"""
        try:
            attempts = self.db_service.get_quiz_history(user_id)
            
            if not attempts:
                return {
                    'total_quizzes': 0,
                    'average_score': 0,
                    'best_score': 0,
                    'worst_score': 0,
                    'total_marks_earned': 0,
                    'total_marks_possible': 0,
                    'weak_concepts': [],
                    'strong_concepts': [],
                    'daily_progress': [],
                    'weekly_progress': [],
                    'monthly_progress': []
                }
            
            # Calculate statistics
            scores = []
            total_earned = 0
            total_possible = 0
            concept_performance = {}
            
            for attempt in attempts:
                if isinstance(attempt, dict):
                    # Score as percentage
                    score_val = float(attempt.get('score_percentage', attempt.get('score', 0)) or 0)
                    scores.append(score_val)
                    
                    # Track marks
                    marks_earned = int(attempt.get('marks_obtained', 0) or 0)
                    marks_total = int(attempt.get('total_marks', 0) or 0)
                    total_earned += marks_earned
                    total_possible += marks_total
                    
                    # Track concept performance
                    for concept, performance in (attempt.get('concept_performance', {}) or {}).items():
                        if concept not in concept_performance:
                            concept_performance[concept] = {'scores': [], 'attempts': 0}
                        if isinstance(performance, dict):
                            concept_performance[concept]['scores'].append(float(performance.get('correct', 0)))
                        else:
                            concept_performance[concept]['scores'].append(float(performance or 0))
                        concept_performance[concept]['attempts'] += 1
            
            # Calculate concept averages
            weak_concepts = []
            strong_concepts = []
            for concept, perf in concept_performance.items():
                avg = sum(perf['scores']) / len(perf['scores']) if perf['scores'] else 0
                if avg < 0.5:
                    weak_concepts.append({'name': concept, 'score': avg, 'attempts': perf['attempts']})
                elif avg >= 0.8:
                    strong_concepts.append({'name': concept, 'score': avg, 'attempts': perf['attempts']})
            
            weak_concepts.sort(key=lambda x: x['score'])
            strong_concepts.sort(key=lambda x: x['score'], reverse=True)
            
            # Daily/Weekly/Monthly progress aggregation
            daily_progress = self._aggregate_progress_by_period(attempts, 'day')
            weekly_progress = self._aggregate_progress_by_period(attempts, 'week')
            monthly_progress = self._aggregate_progress_by_period(attempts, 'month')
            
            return {
                'total_quizzes': len(scores),
                'average_score': sum(scores) / len(scores) if scores else 0,
                'best_score': max(scores) if scores else 0,
                'worst_score': min(scores) if scores else 0,
                'total_marks_earned': total_earned,
                'total_marks_possible': total_possible,
                'weak_concepts': weak_concepts,
                'strong_concepts': strong_concepts,
                'daily_progress': daily_progress,
                'weekly_progress': weekly_progress,
                'monthly_progress': monthly_progress,
                'recent_attempts': attempts[-10:] if len(attempts) > 10 else attempts
            }
        except Exception as e:
            print(f"[ProgressService] Error getting user progress: {str(e)}")
            return {
                'total_quizzes': 0,
                'average_score': 0,
                'best_score': 0,
                'worst_score': 0,
                'total_marks_earned': 0,
                'total_marks_possible': 0,
                'weak_concepts': [],
                'strong_concepts': [],
                'daily_progress': [],
                'weekly_progress': [],
                'monthly_progress': []
            }
    
    def _aggregate_progress_by_period(self, attempts: List[Dict], period: str) -> List[Dict]:
        """Aggregate quiz performance by time period (day, week, month)"""
        progress = {}
        
        for attempt in attempts:
            try:
                # Get timestamp
                timestamp_str = attempt.get('timestamp', '')
                if isinstance(timestamp_str, str) and len(timestamp_str) >= 10:
                    # Parse date from timestamp
                    date_str = timestamp_str[:10]
                    
                    if period == 'day':
                        key = date_str
                    elif period == 'week':
                        # Get week number
                        dt = datetime.strptime(date_str, '%Y-%m-%d')
                        key = dt.strftime('%Y-W%U')
                    elif period == 'month':
                        key = date_str[:7]  # YYYY-MM
                    else:
                        continue
                    
                    if key not in progress:
                        progress[key] = {'total_score': 0, 'count': 0, 'dates': []}
                    
                    score_val = float(attempt.get('score_percentage', attempt.get('score', 0)) or 0)
                    progress[key]['total_score'] += score_val
                    progress[key]['count'] += 1
                    progress[key]['dates'].append(date_str)
            except Exception as e:
                print(f"[ProgressService] Error aggregating period data: {str(e)}")
                continue
        
        # Convert to list with averages
        result = []
        for period_key in sorted(progress.keys()):
            data = progress[period_key]
            result.append({
                'period': period_key,
                'average_score': data['total_score'] / data['count'] if data['count'] > 0 else 0,
                'quizzes_attempted': data['count'],
                'total_score': data['total_score']
            })
        
        return result
    
    def get_concept_weak_areas(self, user_id: str, top_n: int = 5) -> List[Dict]:
        """Get user's weakest concept areas for targeted learning"""
        progress = self.get_user_progress(user_id)
        weak = progress.get('weak_concepts', [])
        return weak[:top_n]
    
    def get_improvement_suggestions(self, user_id: str, weak_concepts: List[Dict]) -> List[str]:
        """Generate personalized learning suggestions based on weak areas"""
        suggestions = []
        
        if not weak_concepts:
            suggestions.append("Great! You're doing well on all topics. Try more advanced quizzes!")
        else:
            for i, concept in enumerate(weak_concepts[:3], 1):
                name = concept.get('name', 'Unknown')
                score = concept.get('score', 0)
                
                if score < 0.3:
                    suggestions.append(f"Focus on '{name}' - You scored {score*100:.0f}%. Try reviewing the material.")
                elif score < 0.5:
                    suggestions.append(f"Practice '{name}' more - Your score of {score*100:.0f}% shows room for improvement.")
                elif score < 0.7:
                    suggestions.append(f"Strengthen '{name}' - Working on this will boost your overall performance.")
        
        return suggestions
    
    def get_quiz_feedback(self, attempt_id: str, user_id: str) -> Dict:
        """Get detailed feedback for a specific quiz attempt"""
        try:
            from services.firebase_service import FirebaseService
            firebase = FirebaseService()
            
            # This would need to be implemented in your firebase/mongodb service
            # For now, return a template
            return {
                'attempt_id': attempt_id,
                'feedback': 'Quiz feedback loaded',
                'strengths': [],
                'areas_for_improvement': []
            }
        except Exception as e:
            print(f"[ProgressService] Error getting quiz feedback: {str(e)}")
            return {}
