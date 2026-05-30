"""
Recommendation Service - Generate AI-powered personalized learning recommendations
"""
import re
from typing import List, Dict, Optional


class RecommendationService:
    """
    Service for generating personalized learning recommendations based on quiz performance.
    """
    
    def __init__(self):
        self._llm = None
        self._model_name = None
    
    def get_learning_recommendations(self, weak_concepts: List[Dict], 
                                     concept_performance: Dict,
                                     quiz_results: List[Dict],
                                     max_recommendations: int = 5) -> List[Dict]:
        """
        Generate AI-powered learning recommendations for weak concepts.
        
        Args:
            weak_concepts: List of concepts with low performance
            concept_performance: Dict of all concept scores
            quiz_results: List of detailed quiz results for each question
            max_recommendations: Max number of recommendations to generate
            
        Returns:
            List of recommendation dicts with 'concept', 'score', 'priority', 'actions', and 'explanation'
        """
        recommendations = []
        
        if not weak_concepts:
            # All concepts strong - provide consolidation recommendations
            return [{
                'concept': '✅ Excellent Performance',
                'score': 1.0,
                'priority': 'positive',
                'actions': [
                    'Review the advanced topics related to your strong areas',
                    'Consider helping other students with these concepts',
                    'Take a harder quiz to challenge yourself',
                    'Try real-world applications of what you learned'
                ],
                'explanation': 'You performed very well! Keep building on your excellent foundation.'
            }]
        
        try:
            # Sort weak concepts by severity (lowest score first)
            sorted_weak = sorted(weak_concepts, key=lambda x: x['score'])
            
            for weak_concept in sorted_weak[:max_recommendations]:
                concept_name = weak_concept.get('name', 'Unknown')
                score = weak_concept.get('score', 0)
                score_pct = score * 100
                
                # Find related questions
                related_questions = [
                    q for q in quiz_results 
                    if q.get('concept', '').lower() == concept_name.lower() and not q.get('is_correct')
                ]
                
                # Determine priority and generate context-specific actions
                if score_pct < 20:
                    priority = 'critical'
                    icon = '🔴'
                    intro = f"This is a critical area where you scored {score_pct:.0f}%."
                    actions = self._generate_critical_actions(concept_name, related_questions)
                elif score_pct < 50:
                    priority = 'high'
                    icon = '🟠'
                    intro = f"This needs focused practice - you scored {score_pct:.0f}%."
                    actions = self._generate_high_priority_actions(concept_name, related_questions)
                else:
                    priority = 'medium'
                    icon = '🟡'
                    intro = f"Some improvement needed - you scored {score_pct:.0f}%."
                    actions = self._generate_medium_priority_actions(concept_name, related_questions)
                
                recommendation = {
                    'concept': f"{icon} {concept_name}",
                    'concept_clean': concept_name,
                    'score': score,
                    'score_pct': score_pct,
                    'priority': priority,
                    'actions': actions,
                    'explanation': intro,
                    'related_errors': len(related_questions)
                }
                
                recommendations.append(recommendation)
            
        except Exception as e:
            print(f"[ERROR] Error generating recommendations: {str(e)}")
            # Fallback basic recommendations
            for weak_concept in sorted(weak_concepts, key=lambda x: x['score'])[:3]:
                recommendations.append({
                    'concept': f"📚 {weak_concept.get('name', 'Unknown Topic')}",
                    'concept_clean': weak_concept.get('name', 'Unknown'),
                    'score': weak_concept.get('score', 0),
                    'score_pct': weak_concept.get('score', 0) * 100,
                    'priority': 'high',
                    'actions': ['Review course materials', 'Practice more problems', 'Watch tutorial videos'],
                    'explanation': 'This concept needs more practice and review.'
                })
        
        return recommendations
    
    def _generate_critical_actions(self, concept: str, failed_questions: List[Dict]) -> List[str]:
        """Generate actions for critically weak concepts (< 20%)"""
        actions = [
            f"📖 Start from basics: Review foundational concepts of '{concept}' from your textbook or course notes",
            f"🎥 Watch tutorial videos: Find video explanations specifically for '{concept}'",
            f"✏️  Solved examples: Study solved examples and worked problems for this concept",
            f"🔄 Retake this quiz: After review, take the quiz again to test your understanding",
            f"💬 Ask for help: Post questions in forums or ask your instructor for clarification"
        ]
        
        # Add specific action based on types of mistakes
        if failed_questions:
            question_types = set(q.get('question_type', 'mcq') for q in failed_questions)
            if 'mcq' in question_types:
                actions.insert(2, "🎯 MCQ strategy: Eliminate obviously wrong options first, then reason through remaining choices")
            if 'short_answer' in question_types:
                actions.insert(3, "📝 Writing practice: Practice expressing your understanding in your own words")
        
        return actions[:5]  # Return top 5
    
    def _generate_high_priority_actions(self, concept: str, failed_questions: List[Dict]) -> List[str]:
        """Generate actions for weak concepts (20-50%)"""
        actions = [
            f"🎯 Focused practice: Dedicate 30 mins to solve problems on '{concept}' specifically",
            f"📊 Concept mapping: Create a mind map showing relationships between topics in '{concept}'",
            f"🔍 Error analysis: Review your wrong answers to understand where your thinking went wrong",
            f"💡 Real-world example: Find practical applications of '{concept}' in your field",
            f"📚 Alternative resources: Try different explanations - Khan Academy, YouTube, or other textbooks"
        ]
        return actions[:4]
    
    def _generate_medium_priority_actions(self, concept: str, failed_questions: List[Dict]) -> List[str]:
        """Generate actions for medium priority concepts (50-70%)"""
        actions = [
            f"🚀 Build mastery: Practice advanced problems on '{concept}' to strengthen understanding",
            f"🔗 Connect concepts: Link '{concept}' with related topics you already know well",
            f"📝 Teach someone: Explain '{concept}' to someone else to solidify your knowledge",
            f"🎯 Targeted practice: Focus on the types of questions you found challenging"
        ]
        return actions[:3]
    
    def get_strong_areas(self, strong_concepts: List[Dict]) -> List[Dict]:
        """
        Get positive reinforcement and advancement recommendations for strong areas.
        
        Args:
            strong_concepts: List of concepts with high performance (>= 80%)
            
        Returns:
            List of positive recommendations
        """
        strong_areas = []
        
        for strong_concept in strong_concepts[:3]:
            concept_name = strong_concept.get('name', 'Unknown')
            score = strong_concept.get('score', 0)
            score_pct = score * 100
            
            strong_areas.append({
                'concept': f"✅ {concept_name}",
                'concept_clean': concept_name,
                'score': score,
                'score_pct': score_pct,
                'priority': 'strong',
                'actions': [
                    f"🏆 Consolidate: You've mastered {concept_name}! Review key points to keep them fresh",
                    f"🚀 Advance: Explore advanced topics or real-world applications",
                    f"👥 Share knowledge: Help other students with {concept_name}"
                ],
                'explanation': f'Strong performance at {score_pct:.0f}%! Keep it up!'
            })
        
        return strong_areas
    
    def get_study_plan(self, weak_concepts: List[Dict], strong_concepts: List[Dict],
                       overall_score: float) -> Dict:
        """
        Generate a personalized study plan based on performance.
        
        Args:
            weak_concepts: List of weak concepts
            strong_concepts: List of strong concepts
            overall_score: Overall quiz score percentage
            
        Returns:
            Study plan dictionary
        """
        plan = {
            'priority_level': 'High',
            'estimated_study_hours': 2,
            'focus_areas': [],
            'next_steps': []
        }
        
        # Determine priority level and study hours
        if overall_score >= 80:
            plan['priority_level'] = 'Low'
            plan['estimated_study_hours'] = 1
            plan['next_steps'] = [
                'Excellent work! Consider attempting advanced problems.',
                'Review concepts periodically to maintain mastery.',
                'Help other students understand these concepts.'
            ]
        elif overall_score >= 60:
            plan['priority_level'] = 'Medium'
            plan['estimated_study_hours'] = 1.5
            plan['next_steps'] = [
                'Focus on consolidating weaker areas.',
                'Practice similar problems to strengthen understanding.',
                'Review before taking the next quiz.'
            ]
        else:
            plan['priority_level'] = 'High'
            plan['estimated_study_hours'] = 3
            plan['next_steps'] = [
                'Urgent: Review fundamental concepts thoroughly.',
                'Work through worked examples step-by-step.',
                'Consider seeking help from instructor or tutoring.',
                'Plan to retake this quiz after intensive study.'
            ]
        
        # Add focus areas
        if weak_concepts:
            for wc in weak_concepts[:3]:
                plan['focus_areas'].append({
                    'area': wc.get('name', 'Unknown'),
                    'current_score': wc.get('score', 0) * 100,
                    'target_score': 80,
                    'time_allocation': '40%' if wc.get('score', 0) < 0.3 else '30%'
                })
        
        return plan
    
    def format_recommendations_for_display(self, recommendations: List[Dict]) -> List[Dict]:
        """
        Format recommendations for template display with all fields.
        
        Args:
            recommendations: Raw recommendation dictionaries
            
        Returns:
            Formatted recommendations ready for template
        """
        formatted = []
        
        for rec in recommendations:
            formatted.append({
                'concept': rec.get('concept', 'Unknown'),
                'concept_clean': rec.get('concept_clean', 'Unknown'),
                'score': rec.get('score', 0),
                'score_pct': rec.get('score_pct', 0),
                'priority': rec.get('priority', 'medium'),
                'explanation': rec.get('explanation', ''),
                'actions': rec.get('actions', []),
                'related_errors': rec.get('related_errors', 0)
            })
        
        return formatted
