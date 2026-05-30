"""
Bandit Service - Multi-Armed Bandit algorithms for adaptive question selection.

This is a core AI component implementing:
1. Epsilon-Greedy
2. UCB1 (Upper Confidence Bound)
3. Thompson Sampling

The bandit treats each concept (or concept-difficulty pair) as an "arm" and
balances exploration (testing weak areas) with exploitation (reinforcing learning).
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import random
import math


class BanditService:
    """
    Multi-Armed Bandit service for adaptive question selection.
    
    The key insight: We model question selection as a bandit problem where:
    - Each arm = a concept (or concept-difficulty pair)
    - Reward = 1 if student answers incorrectly (we want to practice weak concepts)
    - We balance exploring new concepts vs exploiting known weak areas
    """
    
    def __init__(self):
        # Store arm statistics per user
        # Structure: {user_id: {concept: {'pulls': n, 'rewards': sum, 'alpha': a, 'beta': b}}}
        self._arm_stats = defaultdict(lambda: defaultdict(
            lambda: {'pulls': 0, 'rewards': 0, 'alpha': 1, 'beta': 1}
        ))
        
        # Configuration
        self.epsilon = 0.1  # For epsilon-greedy
        self.ucb_c = 2.0    # Confidence parameter for UCB1
    
    def select_questions(self, questions: List[Dict], concept_mastery: Dict,
                        num_questions: int, algorithm: str = 'thompson_sampling') -> List[Dict]:
        """
        Select questions adaptively using bandit algorithm.
        
        Args:
            questions: Available question pool
            concept_mastery: User's mastery scores per concept
            num_questions: Number of questions to select
            algorithm: 'epsilon_greedy', 'ucb1', or 'thompson_sampling'
            
        Returns:
            List of selected questions
        """
        if not questions:
            return []
        
        selected = []
        available = questions.copy()
        
        for _ in range(min(num_questions, len(questions))):
            if not available:
                break
            
            # Select next question using bandit algorithm
            if algorithm == 'epsilon_greedy':
                next_q = self._epsilon_greedy_select(available, concept_mastery)
            elif algorithm == 'ucb1':
                next_q = self._ucb1_select(available, concept_mastery)
            else:  # thompson_sampling (default)
                next_q = self._thompson_sampling_select(available, concept_mastery)
            
            selected.append(next_q)
            available.remove(next_q)
        
        return selected
    
    def select_next_question(self, remaining_questions: List[Dict],
                            concept_mastery: Dict,
                            algorithm: str = 'thompson_sampling') -> Dict:
        """
        Select the next single question during a quiz.
        
        Args:
            remaining_questions: Questions not yet answered
            concept_mastery: User's concept mastery scores
            algorithm: Bandit algorithm to use
            
        Returns:
            Selected question dictionary
        """
        if not remaining_questions:
            return None
        
        if algorithm == 'epsilon_greedy':
            return self._epsilon_greedy_select(remaining_questions, concept_mastery)
        elif algorithm == 'ucb1':
            return self._ucb1_select(remaining_questions, concept_mastery)
        else:
            return self._thompson_sampling_select(remaining_questions, concept_mastery)
    
    def _epsilon_greedy_select(self, questions: List[Dict],
                               concept_mastery: Dict) -> Dict:
        """
        Epsilon-Greedy selection: with probability epsilon, explore randomly;
        otherwise exploit the concept with lowest mastery.
        
        Args:
            questions: Available questions
            concept_mastery: User's mastery scores
            
        Returns:
            Selected question
        """
        if random.random() < self.epsilon:
            # Explore: random selection
            return random.choice(questions)
        else:
            # Exploit: select from weakest concept
            return self._select_weakest_concept_question(questions, concept_mastery)
    
    def _ucb1_select(self, questions: List[Dict], concept_mastery: Dict) -> Dict:
        """
        UCB1 (Upper Confidence Bound) selection.
        
        UCB score = mean_reward + c * sqrt(log(total_pulls) / arm_pulls)
        
        We invert mastery so lower mastery = higher "reward" for learning.
        """
        if not questions:
            return None
        
        # Calculate total pulls (across all concepts)
        total_pulls = sum(
            max(1, 10 - int(m * 10))  # Approximate pulls from mastery
            for m in concept_mastery.values()
        ) or 1
        
        best_question = None
        best_ucb = -float('inf')
        
        for q in questions:
            concept = q.get('concept', 'unknown')
            mastery = concept_mastery.get(concept, 0.5)
            
            # Invert mastery: we want to prioritize low-mastery concepts
            # Mean "reward" = 1 - mastery (higher reward for weaker concepts)
            mean_reward = 1 - mastery
            
            # Estimate number of pulls for this concept
            pulls = max(1, 10 - int(mastery * 10))
            
            # UCB1 formula
            exploration_bonus = self.ucb_c * math.sqrt(math.log(total_pulls + 1) / pulls)
            ucb_score = mean_reward + exploration_bonus
            
            # Add difficulty weighting
            difficulty = q.get('difficulty', 'medium')
            if difficulty == 'hard' and mastery < 0.3:
                ucb_score *= 0.8  # Reduce priority if too hard
            elif difficulty == 'easy' and mastery > 0.7:
                ucb_score *= 0.5  # Reduce priority if too easy
            
            if ucb_score > best_ucb:
                best_ucb = ucb_score
                best_question = q
        
        return best_question or random.choice(questions)
    
    def _thompson_sampling_select(self, questions: List[Dict],
                                  concept_mastery: Dict) -> Dict:
        """
        Thompson Sampling: Sample from Beta distribution for each arm.

        For each concept:
        - alpha proportional to (1 - mastery) → higher for weak concepts
        - beta proportional to mastery → higher for strong concepts

        Difficulty matching ensures the selected question is appropriately
        challenging given the student's current skill level.
        """
        if not questions:
            return None

        best_question = None
        best_sample = -float('inf')

        for q in questions:
            concept = q.get('concept', 'unknown')
            mastery = concept_mastery.get(concept, 0.5)

            # Convert mastery to Beta distribution parameters
            alpha = max(1, int((1 - mastery) * 10) + 1)
            beta_param = max(1, int(mastery * 10) + 1)

            # Sample from Beta distribution
            sample = np.random.beta(alpha, beta_param)

            # ── Difficulty-skill matching ──
            # Match question difficulty to the student's zone of proximal
            # development: slightly above current mastery for optimal learning.
            difficulty = q.get('difficulty', 'medium').lower()
            diff_map = {'easy': 0.3, 'medium': 0.55, 'hard': 0.8}
            q_difficulty_level = diff_map.get(difficulty, 0.55)

            # Ideal difficulty is slightly above mastery (Vygotsky ZPD)
            ideal_difficulty = min(0.9, mastery + 0.15)
            difficulty_gap = abs(q_difficulty_level - ideal_difficulty)

            # Scale: perfect match = 1.0, worst mismatch ≈ 0.5
            difficulty_multiplier = max(0.5, 1.0 - difficulty_gap)

            # Penalize extremes more aggressively
            if difficulty == 'hard' and mastery < 0.25:
                difficulty_multiplier *= 0.6  # Way too hard → frustrating
            elif difficulty == 'easy' and mastery > 0.75:
                difficulty_multiplier *= 0.5  # Way too easy → boring
            elif difficulty == 'medium':
                difficulty_multiplier *= 1.05  # Slight boost for medium

            sample *= difficulty_multiplier

            if sample > best_sample:
                best_sample = sample
                best_question = q

        return best_question or random.choice(questions)
    
    def _select_weakest_concept_question(self, questions: List[Dict],
                                         concept_mastery: Dict) -> Dict:
        """Select a question from the weakest concept"""
        # Find question with lowest mastery concept
        min_mastery = float('inf')
        weakest_question = None
        
        for q in questions:
            concept = q.get('concept', 'unknown')
            mastery = concept_mastery.get(concept, 0.5)
            
            if mastery < min_mastery:
                min_mastery = mastery
                weakest_question = q
        
        return weakest_question or random.choice(questions)
    
    def update_arm(self, user_id: str, concept: str, reward: float):
        """
        Update arm statistics after receiving reward.
        
        Args:
            user_id: User identifier
            concept: Concept/arm that was pulled
            reward: Reward signal (0 for correct, 1 for incorrect in our case)
        """
        stats = self._arm_stats[user_id][concept]
        stats['pulls'] += 1
        stats['rewards'] += reward
        
        # Update Beta distribution parameters for Thompson Sampling
        if reward > 0.5:
            stats['alpha'] += 1  # Incorrect answer
        else:
            stats['beta'] += 1   # Correct answer
    
    def update_mastery(self, user_id: str, concept_performance: Dict):
        """
        Update mastery based on quiz performance.
        
        Args:
            user_id: User identifier
            concept_performance: Dict mapping concept to performance score (0-1)
        """
        try:
            for concept, performance in (concept_performance or {}).items():
                try:
                    # Ensure performance is a valid float
                    perf_val = float(performance)
                    # Clamp to [0, 1]
                    if perf_val < 0:
                        perf_val = 0
                    elif perf_val > 1:
                        perf_val = 1
                    # Update arm with inverse of performance (we want to target weak areas)
                    self.update_arm(user_id, concept, 1 - perf_val)
                except (ValueError, TypeError) as e:
                    print(f"[WARNING] Invalid performance value for {concept}: {performance}")
                    pass
        except Exception as e:
            print(f"[ERROR] Error in update_mastery: {str(e)}")
    
    def get_arm_statistics(self, user_id: str) -> Dict:
        """Get arm statistics for a user"""
        return dict(self._arm_stats[user_id])
    
    def reset_user_stats(self, user_id: str):
        """Reset statistics for a user"""
        if user_id in self._arm_stats:
            del self._arm_stats[user_id]
    
    def get_exploration_rate(self, user_id: str, concept: str) -> float:
        """
        Calculate how much we should explore this concept.
        Higher value = more exploration needed.
        """
        stats = self._arm_stats[user_id][concept]
        pulls = stats['pulls']
        
        if pulls == 0:
            return 1.0  # Maximum exploration for unseen concepts
        
        # Decrease exploration as we get more data
        return min(1.0, math.sqrt(1.0 / pulls))
    
    def recommend_concepts_to_practice(self, user_id: str, 
                                       concept_mastery: Dict,
                                       top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Recommend concepts that need the most practice.
        
        Args:
            user_id: User identifier
            concept_mastery: User's mastery scores
            top_k: Number of concepts to recommend
            
        Returns:
            List of (concept, priority_score) tuples
        """
        recommendations = []
        
        for concept, mastery in concept_mastery.items():
            # Priority combines low mastery with exploration needs
            exploration_rate = self.get_exploration_rate(user_id, concept)
            
            # Priority score: higher for low mastery and high exploration need
            priority = (1 - mastery) * 0.7 + exploration_rate * 0.3
            
            recommendations.append((concept, priority))
        
        # Sort by priority (descending)
        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        return recommendations[:top_k]
    
    def calculate_learning_efficiency(self, user_id: str, 
                                     initial_mastery: Dict,
                                     final_mastery: Dict) -> Dict:
        """
        Calculate learning efficiency metrics.
        
        Args:
            user_id: User identifier
            initial_mastery: Mastery before quiz
            final_mastery: Mastery after quiz
            
        Returns:
            Dictionary with efficiency metrics
        """
        improvements = []
        
        for concept in initial_mastery:
            if concept in final_mastery:
                improvement = final_mastery[concept] - initial_mastery[concept]
                improvements.append(improvement)
        
        if not improvements:
            return {'average_improvement': 0, 'concepts_improved': 0}
        
        return {
            'average_improvement': np.mean(improvements),
            'max_improvement': max(improvements),
            'concepts_improved': sum(1 for i in improvements if i > 0),
            'total_concepts': len(improvements)
        }


class ContextualBandit(BanditService):
    """
    Extended bandit that considers additional context features
    like time of day, recent performance trend, etc.
    """
    
    def __init__(self):
        super().__init__()
        self._context_weights = {
            'mastery': 0.4,
            'recency': 0.2,
            'difficulty_match': 0.2,
            'exploration': 0.2
        }
    
    def select_with_context(self, questions: List[Dict],
                           concept_mastery: Dict,
                           recent_answers: List[bool],
                           time_of_day: str = 'day') -> Dict:
        """
        Select question considering additional context.
        
        Args:
            questions: Available questions
            concept_mastery: User's mastery scores
            recent_answers: Last N answer correctness (True=correct)
            time_of_day: 'morning', 'day', 'evening', 'night'
            
        Returns:
            Selected question
        """
        if not questions:
            return None
        
        # Calculate recent performance trend
        if recent_answers:
            recent_accuracy = sum(recent_answers) / len(recent_answers)
        else:
            recent_accuracy = 0.5
        
        best_score = -float('inf')
        best_question = None
        
        for q in questions:
            concept = q.get('concept', 'unknown')
            mastery = concept_mastery.get(concept, 0.5)
            difficulty = q.get('difficulty', 'medium')
            
            # Calculate component scores
            mastery_score = 1 - mastery  # Higher for weak concepts
            
            # Difficulty matching based on recent performance
            if recent_accuracy > 0.7:
                difficulty_score = {'easy': 0.3, 'medium': 0.8, 'hard': 1.0}
            elif recent_accuracy < 0.4:
                difficulty_score = {'easy': 1.0, 'medium': 0.7, 'hard': 0.3}
            else:
                difficulty_score = {'easy': 0.5, 'medium': 1.0, 'hard': 0.5}
            
            diff_match = difficulty_score.get(difficulty, 0.5)
            
            # Exploration score (Thompson sampling-based)
            alpha = max(1, int((1 - mastery) * 10) + 1)
            beta = max(1, int(mastery * 10) + 1)
            exploration_score = np.random.beta(alpha, beta)
            
            # Recency score (prefer less recently practiced concepts)
            recency_score = 0.5  # Placeholder - would use actual recency data
            
            # Combine scores
            total_score = (
                self._context_weights['mastery'] * mastery_score +
                self._context_weights['difficulty_match'] * diff_match +
                self._context_weights['exploration'] * exploration_score +
                self._context_weights['recency'] * recency_score
            )
            
            if total_score > best_score:
                best_score = total_score
                best_question = q
        
        return best_question or random.choice(questions)
