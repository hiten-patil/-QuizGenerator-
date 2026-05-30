"""
Adaptive Quiz Engine - Production-Grade Quiz Generation System
================================================================

This is the main orchestration module for generating adaptive, intelligent quizzes
from lecture content. It integrates multiple AI components:

1. Concept Extraction (KeyBERT, spaCy, TF-IDF, RAKE)
2. Question Generation (OpenAI GPT, Google Gemini, or local FLAN-T5)
3. Adaptive Selection (Thompson Sampling, Epsilon-Greedy, UCB1)
4. Difficulty Management (Zone of Proximal Development)
5. Knowledge Graph Construction

QUIZ MODES:
-----------
1. RANDOM: Random selection from generated question bank
2. CONCEPT_BALANCED: Ensures equal representation across concepts
3. ADAPTIVE: Uses multi-armed bandit algorithms to prioritize weak concepts

SUPPORTED QUESTION TYPES:
-------------------------
- MCQ (Multiple Choice with 4 options)
- TRUE_FALSE (Statement verification)
- SHORT_ANSWER (Open-ended questions with keyword matching)

USAGE EXAMPLE:
--------------
    engine = AdaptiveQuizEngine()
    
    # Generate quiz from lecture content
    quiz = engine.generate_quiz(
        lecture_text=lecture_content,
        num_questions=20,
        quiz_type='adaptive',
        difficulty='mixed',
        question_types=['mcq', 'true_false'],
        concept_mastery={'reinforcement learning': 0.3, 'neural networks': 0.7}
    )
    
    # Quiz contains structured questions ready for deployment
    for q in quiz['questions']:
        print(q['question'], q['options'], q['correct_answer'])

ADAPTIVE BEHAVIOR:
------------------
When quiz_type='adaptive', the engine uses Thompson Sampling to:
- Prioritize concepts with LOW mastery scores (more practice needed)
- Match question difficulty to student's Zone of Proximal Development
- Balance exploration (testing new concepts) vs exploitation (reinforcing weaknesses)

The bandit algorithm models each concept as an "arm":
- Alpha parameter ∝ (1 - mastery) → high for weak concepts
- Beta parameter ∝ mastery → high for strong concepts
- Questions sampled from Beta(alpha, beta) distribution

Author: Senior AI Engineer
Date: March 2026
"""

from __future__ import annotations

import json
import random
import time
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from services.concept_service import ConceptService
from services.question_generator import QuestionGenerator
from services.bandit_service import BanditService
from services.difficulty_controller import DifficultyController


class AdaptiveQuizEngine:
    """
    Production quiz generation engine with adaptive learning capabilities.
    
    This class orchestrates the entire quiz generation pipeline:
    1. Extract concepts from lecture text
    2. Build knowledge graph showing concept relationships
    3. Generate large question bank (50-200 questions)
    4. Select optimal questions based on quiz type and student mastery
    """
    
    def __init__(self, use_gpu: bool = False):
        """
        Initialize the adaptive quiz engine.
        
        Args:
            use_gpu: Whether to use GPU acceleration for NLP models
        """
        self.concept_service = ConceptService(use_gpu=use_gpu)
        self.question_generator = QuestionGenerator()
        self.bandit_service = BanditService()
        self.difficulty_controller = DifficultyController()
        
        print("[AdaptiveQuizEngine] Initialized with adaptive learning capabilities")
    
    # ================================================================
    # Main Public API
    # ================================================================
    
    def generate_quiz(
        self,
        lecture_text: str,
        num_questions: int = 20,
        quiz_type: str = 'random',
        difficulty: str = 'mixed',
        question_types: Optional[List[str]] = None,
        concept_mastery: Optional[Dict[str, float]] = None,
        bandit_algorithm: str = 'thompson_sampling'
    ) -> Dict:
        """
        Generate a complete quiz from lecture content.
        
        Args:
            lecture_text: Raw text extracted from lecture notes or PDF
            num_questions: Number of questions to include in final quiz (10-50 recommended)
            quiz_type: 'random', 'concept_balanced', or 'adaptive'
            difficulty: 'easy', 'medium', 'hard', or 'mixed'
            question_types: List of types to include: ['mcq', 'true_false', 'short_answer']
                          If None, includes all types in balanced distribution
            concept_mastery: Dict mapping concept names to mastery scores (0.0-1.0)
                           Only used when quiz_type='adaptive'
                           Lower scores = more practice needed
            bandit_algorithm: 'thompson_sampling', 'epsilon_greedy', or 'ucb1'
                            Only used when quiz_type='adaptive'
        
        Returns:
            Dictionary containing:
            {
                'questions': List[Dict],  # Structured question objects
                'metadata': Dict,         # Generation metadata
                'concepts': List[Dict],   # Extracted concepts
                'knowledge_graph': Dict   # Concept relationships
            }
        
        Raises:
            ValueError: If lecture_text is empty or quiz_type is invalid
        """
        if not lecture_text or len(lecture_text.strip()) < 100:
            raise ValueError("Lecture text must be at least 100 characters")
        
        valid_quiz_types = {'random', 'concept_balanced', 'adaptive'}
        if quiz_type not in valid_quiz_types:
            raise ValueError(f"quiz_type must be one of {valid_quiz_types}")
        
        if quiz_type == 'adaptive' and not concept_mastery:
            print("[AdaptiveQuizEngine] WARNING: adaptive mode requires concept_mastery. "
                  "Defaulting to concept_balanced.")
            quiz_type = 'concept_balanced'
        
        start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"GENERATING {quiz_type.upper()} QUIZ")
        print(f"{'='*70}")
        print(f"Lecture length: {len(lecture_text)} characters")
        print(f"Target questions: {num_questions}")
        print(f"Difficulty: {difficulty}")
        print(f"Question types: {question_types or 'balanced mix'}")
        if quiz_type == 'adaptive':
            print(f"Bandit algorithm: {bandit_algorithm}")
            print(f"Concept mastery scores provided: {len(concept_mastery or {})}")
        print(f"{'='*70}\n")
        
        # STEP 1: Extract concepts from lecture
        print("[1/5] Extracting concepts from lecture content...")
        concepts = self.extract_concepts(lecture_text, max_concepts=50)
        print(f"      ✓ Extracted {len(concepts)} key concepts")
        
        # STEP 2: Build knowledge graph
        print("[2/5] Building knowledge graph...")
        knowledge_graph = self.build_knowledge_graph(lecture_text, concepts)
        print(f"      ✓ Constructed graph with {len(knowledge_graph.get('nodes', []))} nodes "
              f"and {len(knowledge_graph.get('edges', []))} relationships")
        
        # STEP 3: Generate comprehensive question bank
        print("[3/5] Generating question bank...")
        # Generate 3-5x more questions than needed for better selection
        bank_size = min(200, max(50, num_questions * 4))
        question_bank = self.generate_question_bank(
            lecture_text,
            concepts,
            knowledge_graph,
            num_questions=bank_size,
            question_types=question_types,
            difficulty=difficulty
        )
        print(f"      ✓ Generated {len(question_bank)} questions across "
              f"{len(set(q.get('concept') for q in question_bank))} concepts")
        
        # STEP 4: Select questions based on quiz type
        print(f"[4/5] Selecting questions using {quiz_type} strategy...")
        if quiz_type == 'random':
            selected_questions = self.select_questions_random(
                question_bank, num_questions
            )
        elif quiz_type == 'concept_balanced':
            selected_questions = self.select_questions_balanced(
                question_bank, concepts, num_questions
            )
        else:  # adaptive
            selected_questions = self.select_questions_adaptive(
                question_bank,
                concept_mastery,
                num_questions,
                bandit_algorithm
            )
        print(f"      ✓ Selected {len(selected_questions)} optimal questions")
        
        # STEP 5: Package results
        print("[5/5] Packaging quiz...")
        elapsed = time.time() - start_time
        
        quiz = {
            'questions': selected_questions,
            'metadata': {
                'num_questions': len(selected_questions),
                'quiz_type': quiz_type,
                'difficulty': difficulty,
                'question_types': question_types or ['mcq', 'true_false', 'short_answer'],
                'bandit_algorithm': bandit_algorithm if quiz_type == 'adaptive' else None,
                'generation_time_seconds': round(elapsed, 2),
                'lecture_length_chars': len(lecture_text),
                'num_concepts': len(concepts),
                'question_bank_size': len(question_bank),
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            },
            'concepts': concepts,
            'knowledge_graph': knowledge_graph
        }
        
        print(f"\n{'='*70}")
        print(f"✓ QUIZ GENERATED SUCCESSFULLY in {elapsed:.2f}s")
        print(f"{'='*70}\n")
        
        return quiz
    
    # ================================================================
    # Concept Extraction
    # ================================================================
    
    def extract_concepts(self, text: str, max_concepts: int = 50) -> List[Dict]:
        """
        Extract key concepts from lecture text using multiple NLP techniques.
        
        Uses a layered approach:
        1. TF-IDF for statistically important terms
        2. RAKE for keyphrase extraction
        3. KeyBERT for semantic keyphrases
        4. spaCy NER for named entities
        5. Sentence transformers for semantic clustering
        
        Args:
            text: Lecture content
            max_concepts: Maximum number of concepts to extract
        
        Returns:
            List of concept dictionaries with keys:
                - name: Concept name
                - score: Importance score (0.0-1.0)
                - type: Concept type (keyword, phrase, entity, etc.)
                - context: Surrounding text snippet
                - source: Extraction method used
        """
        return self.concept_service.extract_concepts(text, max_concepts)
    
    def build_knowledge_graph(self, text: str, concepts: List[Dict]) -> Dict:
        """
        Build a knowledge graph showing relationships between concepts.
        
        Uses semantic similarity to identify related concepts and creates
        edges between them. This helps generate questions that test
        conceptual relationships rather than isolated facts.
        
        Args:
            text: Lecture content
            concepts: Extracted concepts
        
        Returns:
            Knowledge graph dictionary with:
                - nodes: List of concept nodes
                - edges: List of (source, target, weight) tuples
                - clusters: Concept clusters (related topics)
        """
        return self.concept_service.build_knowledge_graph(text, concepts)
    
    # ================================================================
    # Question Bank Generation
    # ================================================================
    
    def generate_question_bank(
        self,
        text: str,
        concepts: List[Dict],
        knowledge_graph: Dict,
        num_questions: int = 100,
        question_types: Optional[List[str]] = None,
        difficulty: str = 'mixed'
    ) -> List[Dict]:
        """
        Generate a large bank of questions from lecture content.
        
        This creates 50-200 high-quality questions tagged with:
        - Concept (which topic is tested)
        - Difficulty (easy/medium/hard)
        - Type (MCQ/True-False/Short Answer)
        - Explanation (detailed rationale)
        
        The question generator uses the full document context to ensure
        questions are logically consistent and test actual understanding.
        
        Args:
            text: Lecture content
            concepts: Extracted concepts
            knowledge_graph: Concept relationships
            num_questions: Target number of questions (50-200 recommended)
            question_types: Types to generate
            difficulty: Difficulty distribution
        
        Returns:
            List of question dictionaries, each containing:
            {
                'question': str,
                'type': 'MCQ' | 'TRUE_FALSE' | 'SHORT_ANSWER',
                'options': List[str],  # For MCQ: ['A', 'B', 'C', 'D']
                'correct_answer': str,
                'concept': str,
                'difficulty': 'easy' | 'medium' | 'hard',
                'explanation': str,
                'keywords': List[str]  # For SHORT_ANSWER only
            }
        """
        questions = self.question_generator.generate_questions(
            text=text,
            concepts=concepts,
            knowledge_graph=knowledge_graph,
            num_questions=num_questions,
            question_types=question_types,
            difficulty=difficulty
        )
        
        return questions
    
    # ================================================================
    # Question Selection Strategies
    # ================================================================
    
    def select_questions_random(
        self,
        question_bank: List[Dict],
        num_questions: int
    ) -> List[Dict]:
        """
        Random selection from question bank.
        
        Simple random sampling - useful for baseline quizzes or when
        no student performance data is available.
        
        Args:
            question_bank: Available questions
            num_questions: Number to select
        
        Returns:
            Randomly selected questions
        """
        if len(question_bank) <= num_questions:
            return question_bank
        
        selected = random.sample(question_bank, num_questions)
        
        print(f"      Random selection: {num_questions} questions")
        return selected
    
    def select_questions_balanced(
        self,
        question_bank: List[Dict],
        concepts: List[Dict],
        num_questions: int
    ) -> List[Dict]:
        """
        Concept-balanced selection ensuring diverse topic coverage.
        
        This strategy:
        1. Identifies all unique concepts in question bank
        2. Calculates target questions per concept (proportional to importance)
        3. Samples evenly across concepts
        4. Ensures students are tested on all major topics
        
        Args:
            question_bank: Available questions
            concepts: Extracted concepts (for importance scoring)
            num_questions: Number to select
        
        Returns:
            Concept-balanced question set
        """
        # Group questions by concept
        concept_groups = defaultdict(list)
        for q in question_bank:
            concept = q.get('concept', 'unknown')
            concept_groups[concept].append(q)
        
        if not concept_groups:
            return self.select_questions_random(question_bank, num_questions)
        
        # Calculate importance weight for each concept
        concept_weights = {}
        concept_map = {c['name']: c.get('score', 0.5) for c in concepts}
        
        for concept in concept_groups.keys():
            # Use concept importance score, with fallback for unknown concepts
            weight = concept_map.get(concept, 0.3)
            concept_weights[concept] = weight
        
        # Normalize weights
        total_weight = sum(concept_weights.values())
        if total_weight > 0:
            for concept in concept_weights:
                concept_weights[concept] /= total_weight
        
        # Allocate questions per concept
        selected = []
        remaining = num_questions
        
        # Sort concepts by weight (descending)
        sorted_concepts = sorted(
            concept_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        for concept, weight in sorted_concepts:
            if remaining <= 0:
                break
            
            available = concept_groups[concept]
            # Calculate target for this concept
            target = max(1, round(num_questions * weight))
            # Don't take more than available or remaining
            take = min(target, len(available), remaining)
            
            # Randomly sample from this concept
            selected.extend(random.sample(available, take))
            remaining -= take
        
        # If we still need more, randomly sample from remaining questions
        if remaining > 0:
            used_ids = {id(q) for q in selected}
            remaining_questions = [q for q in question_bank if id(q) not in used_ids]
            if remaining_questions:
                additional = random.sample(
                    remaining_questions,
                    min(remaining, len(remaining_questions))
                )
                selected.extend(additional)
        
        # Shuffle to avoid concept clustering
        random.shuffle(selected)
        
        concept_dist = defaultdict(int)
        for q in selected:
            concept_dist[q.get('concept')] += 1
        
        print(f"      Concept-balanced selection:")
        for concept, count in sorted(concept_dist.items(), key=lambda x: -x[1])[:5]:
            print(f"        - {concept}: {count} questions")
        
        return selected[:num_questions]
    
    def select_questions_adaptive(
        self,
        question_bank: List[Dict],
        concept_mastery: Dict[str, float],
        num_questions: int,
        algorithm: str = 'thompson_sampling'
    ) -> List[Dict]:
        """
        Adaptive selection using multi-armed bandit algorithms.
        
        This is the most sophisticated selection strategy, implementing
        reinforcement learning to optimize learning outcomes:
        
        THOMPSON SAMPLING (default):
        ---------------------------
        For each concept, we model mastery as a Beta distribution:
        - Alpha ∝ (1 - mastery) → high for concepts needing practice
        - Beta ∝ mastery → high for well-understood concepts
        
        We sample from Beta(alpha, beta) and select questions from
        concepts with highest samples. This naturally balances:
        - Exploration: testing unfamiliar concepts
        - Exploitation: reinforcing weak areas
        
        DIFFICULTY MATCHING:
        -------------------
        Questions are matched to student's Zone of Proximal Development:
        - If mastery = 0.3, prefer medium difficulty (0.45-0.55 range)
        - Avoid questions that are too hard (frustrating) or too easy (boring)
        - Optimal difficulty ≈ current_mastery + 0.15
        
        EPSILON-GREEDY:
        --------------
        With probability ε (0.1), explore randomly.
        Otherwise, exploit by selecting from weakest concepts.
        
        UCB1 (Upper Confidence Bound):
        ------------------------------
        Balance mean reward with exploration bonus:
        UCB = (1 - mastery) + c * sqrt(log(total_pulls) / arm_pulls)
        
        Args:
            question_bank: Available questions
            concept_mastery: Dict mapping concepts to mastery scores (0.0-1.0)
                           Example: {'neural networks': 0.7, 'backprop': 0.3}
                           Lower scores indicate concepts needing more practice
            num_questions: Number to select
            algorithm: 'thompson_sampling', 'epsilon_greedy', or 'ucb1'
        
        Returns:
            Adaptively selected questions prioritizing weak concepts
        """
        if not concept_mastery:
            print("      WARNING: No mastery data provided, falling back to balanced selection")
            return self.select_questions_balanced(question_bank, [], num_questions)
        
        print(f"      Adaptive selection using {algorithm}:")
        print(f"        Mastery scores:")
        
        # Show weakest concepts (these will be prioritized)
        sorted_mastery = sorted(concept_mastery.items(), key=lambda x: x[1])
        for concept, score in sorted_mastery[:5]:
            status = "⚠️  WEAK" if score < 0.4 else "⚡ LEARNING" if score < 0.7 else "✓ STRONG"
            print(f"          {status} {concept}: {score:.2f}")
        
        # Use bandit service for adaptive selection
        selected = self.bandit_service.select_questions(
            questions=question_bank,
            concept_mastery=concept_mastery,
            num_questions=num_questions,
            algorithm=algorithm
        )
        
        # Analyze selection
        concept_distribution = defaultdict(int)
        difficulty_distribution = defaultdict(int)
        
        for q in selected:
            concept = q.get('concept', 'unknown')
            difficulty = q.get('difficulty', 'medium')
            concept_distribution[concept] += 1
            difficulty_distribution[difficulty] += 1
        
        print(f"\n      Selected {len(selected)} questions:")
        print(f"        Top concepts tested:")
        for concept, count in sorted(concept_distribution.items(), key=lambda x: -x[1])[:5]:
            mastery = concept_mastery.get(concept, 0.5)
            print(f"          - {concept} ({count} q's, mastery: {mastery:.2f})")
        
        print(f"        Difficulty distribution:")
        for diff, count in sorted(difficulty_distribution.items()):
            print(f"          - {diff}: {count}")
        
        return selected
    
    # ================================================================
    # Helper: Generate MCQ (legacy support for manual generation)
    # ================================================================
    
    def generate_mcq(
        self,
        concept: str,
        context: str,
        difficulty: str = 'medium'
    ) -> Dict:
        """
        Generate a single MCQ question for a specific concept.
        
        This is a convenience method for manual question generation.
        For bulk generation, use generate_question_bank() instead.
        
        Args:
            concept: Target concept to test
            context: Relevant text snippet
            difficulty: 'easy', 'medium', or 'hard'
        
        Returns:
            Single MCQ question dictionary
        """
        # Create minimal concept structure
        concepts = [{'name': concept, 'score': 1.0, 'context': context}]
        
        questions = self.question_generator.generate_questions(
            text=context,
            concepts=concepts,
            knowledge_graph={'nodes': [], 'edges': []},
            num_questions=1,
            question_types=['mcq'],
            difficulty=difficulty
        )
        
        return questions[0] if questions else None
    
    def generate_true_false(
        self,
        concept: str,
        context: str,
        difficulty: str = 'medium'
    ) -> Dict:
        """
        Generate a single True/False question.
        
        Args:
            concept: Target concept
            context: Relevant text
            difficulty: Question difficulty
        
        Returns:
            True/False question dictionary
        """
        concepts = [{'name': concept, 'score': 1.0, 'context': context}]
        
        questions = self.question_generator.generate_questions(
            text=context,
            concepts=concepts,
            knowledge_graph={'nodes': [], 'edges': []},
            num_questions=1,
            question_types=['true_false'],
            difficulty=difficulty
        )
        
        return questions[0] if questions else None
    
    def generate_short_answer(
        self,
        concept: str,
        context: str,
        difficulty: str = 'medium'
    ) -> Dict:
        """
        Generate a single short answer question.
        
        Args:
            concept: Target concept
            context: Relevant text
            difficulty: Question difficulty
        
        Returns:
            Short answer question dictionary with keywords
        """
        concepts = [{'name': concept, 'score': 1.0, 'context': context}]
        
        questions = self.question_generator.generate_questions(
            text=context,
            concepts=concepts,
            knowledge_graph={'nodes': [], 'edges': []},
            num_questions=1,
            question_types=['short_answer'],
            difficulty=difficulty
        )
        
        return questions[0] if questions else None


# ================================================================
# Example Usage & Testing
# ================================================================

def example_lecture_content() -> str:
    """
    Example lecture content for demonstration.
    
    This represents typical AI/ML lecture notes that might be
    extracted from a PDF or document.
    """
    return """
    LECTURE 5: REINFORCEMENT LEARNING AND SEARCH ALGORITHMS
    
    Introduction to Reinforcement Learning
    =======================================
    Reinforcement learning (RL) is a machine learning paradigm where an agent
    learns to make decisions by interacting with an environment. Unlike supervised
    learning, there are no labeled examples. Instead, the agent receives rewards
    or penalties for its actions and must learn to maximize cumulative reward.
    
    The key components of RL are:
    - Agent: The decision-maker
    - Environment: The world the agent interacts with
    - State: Current situation of the agent
    - Action: Choices available to the agent
    - Reward: Feedback signal from environment
    - Policy: Strategy mapping states to actions
    
    The Markov Decision Process (MDP) provides the mathematical framework for RL.
    An MDP is defined by a tuple (S, A, P, R, γ) where S is the state space,
    A is the action space, P is the transition probability function, R is the
    reward function, and γ is the discount factor (0 ≤ γ < 1).
    
    The Bellman equation is fundamental to RL:
    V(s) = max_a [R(s,a) + γ Σ P(s'|s,a) V(s')]
    
    This equation states that the value of a state is the maximum expected sum
    of immediate reward plus the discounted value of the next state.
    
    Q-Learning Algorithm
    ====================
    Q-learning is a model-free RL algorithm that learns the quality (Q-value)
    of state-action pairs. The Q-value Q(s,a) represents the expected cumulative
    reward of taking action a in state s and following the optimal policy thereafter.
    
    The Q-learning update rule is:
    Q(s,a) ← Q(s,a) + α[r + γ max_a' Q(s',a') - Q(s,a)]
    
    where α is the learning rate, r is the immediate reward, and s' is the next state.
    
    Q-learning is guaranteed to converge to the optimal policy given sufficient
    exploration and appropriate learning rate decay. The ε-greedy strategy is
    commonly used for exploration: with probability ε, choose a random action;
    otherwise, choose the action with highest Q-value.
    
    Deep Q-Networks (DQN)
    =====================
    Deep Q-Networks extend Q-learning to high-dimensional state spaces by using
    neural networks to approximate the Q-function. The DQN algorithm introduced
    two key innovations:
    
    1. Experience Replay: Store transitions (s,a,r,s') in a replay buffer and
       sample random minibatches for training. This breaks correlation between
       consecutive samples and improves data efficiency.
    
    2. Target Network: Use a separate target network for computing Q-value targets
       that is updated periodically. This stabilizes training by reducing the
       moving target problem.
    
    DQN achieved human-level performance on many Atari games, demonstrating that
    deep RL can learn complex control policies from raw pixel inputs.
    
    Search Algorithms
    =================
    Search algorithms are fundamental to AI for finding solutions in problem spaces.
    They are used in planning, game playing, and optimization.
    
    Uninformed Search
    -----------------
    Uninformed search algorithms explore the search space without domain knowledge:
    
    - Breadth-First Search (BFS): Explores neighbors before children. Guaranteed
      to find the shortest path but requires O(b^d) space where b is branching
      factor and d is depth.
    
    - Depth-First Search (DFS): Explores deepest nodes first. Memory efficient
      O(bd) but not guaranteed to find shortest path.
    
    - Uniform Cost Search (UCS): Expands the node with lowest path cost. Optimal
      if costs are non-negative.
    
    Informed Search (Heuristic Search)
    ----------------------------------
    Heuristic search algorithms use domain knowledge to guide exploration:
    
    - Greedy Best-First Search: Expands nodes that appear closest to goal based
      on heuristic h(n). Fast but not optimal.
    
    - A* Search: Combines path cost g(n) and heuristic h(n) using evaluation
      function f(n) = g(n) + h(n). A* is optimal if h(n) is admissible
      (never overestimates true cost) and consistent (triangle inequality).
    
    The effectiveness of A* depends critically on the heuristic. Good heuristics
    balance accuracy and computational cost. For example, in pathfinding, the
    Euclidean distance is admissible but may underestimate; the Manhattan distance
    is more accurate for grid-based movement.
    
    Adversarial Search (Game Playing)
    ----------------------------------
    In competitive multi-agent environments, we use adversarial search:
    
    - Minimax Algorithm: Assumes opponent plays optimally. Computes minimax value
      by alternating between maximizing and minimizing layers. Depth-limited
      search with evaluation functions needed for complex games.
    
    - Alpha-Beta Pruning: Optimization that eliminates branches that cannot
      influence the final decision. Can reduce effective branching factor from
      b to sqrt(b), enabling deeper search.
    
    - Monte Carlo Tree Search (MCTS): Uses random simulations to estimate node
      values. Particularly effective in games with high branching factors like Go.
      AlphaGo combined MCTS with deep neural networks to achieve superhuman performance.
    
    Policy Gradient Methods
    =======================
    Policy gradient methods directly optimize the policy π(a|s) rather than learning
    a value function. The key insight is to use gradient ascent to maximize expected
    reward J(θ) where θ are policy parameters:
    
    ∇J(θ) = E[∇log π(a|s;θ) Q(s,a)]
    
    The REINFORCE algorithm uses Monte Carlo sampling to estimate this gradient.
    Actor-Critic methods combine policy gradients (actor) with value function
    approximation (critic) for reduced variance.
    
    Modern policy gradient algorithms like Proximal Policy Optimization (PPO) and
    Trust Region Policy Optimization (TRPO) use sophisticated techniques to ensure
    stable learning with large neural network policies.
    
    Applications of RL and Search
    =============================
    Reinforcement learning and search algorithms have diverse applications:
    
    - Robotics: Learning locomotion, manipulation, and navigation
    - Game AI: Chess, Go, poker, video games
    - Autonomous vehicles: Path planning and decision making
    - Resource management: Data center cooling, traffic control
    - Finance: Portfolio optimization, trading strategies
    - Healthcare: Treatment planning, drug discovery
    
    The combination of deep learning with RL has enabled breakthrough results
    in complex domains, though challenges remain in sample efficiency, safety,
    and interpretability.
    """


def run_example():
    """
    Comprehensive example demonstrating all quiz generation modes.
    """
    print("\n" + "="*80)
    print("ADAPTIVE QUIZ ENGINE - COMPREHENSIVE DEMONSTRATION")
    print("="*80 + "\n")
    
    # Initialize engine
    engine = AdaptiveQuizEngine(use_gpu=False)
    
    # Get example lecture content
    lecture = example_lecture_content()
    
    # ================================================================
    # Example 1: Random Quiz
    # ================================================================
    print("\n" + "─"*80)
    print("EXAMPLE 1: RANDOM QUIZ")
    print("─"*80 + "\n")
    
    quiz_random = engine.generate_quiz(
        lecture_text=lecture,
        num_questions=10,
        quiz_type='random',
        difficulty='mixed',
        question_types=['mcq', 'true_false']
    )
    
    print("\nSample Questions (Random Mode):")
    print("─"*80)
    for i, q in enumerate(quiz_random['questions'][:3], 1):
        print(f"\nQ{i}. [{q['type']}] {q['question']}")
        if q['type'] == 'MCQ':
            for opt in q['options']:
                print(f"    {opt}")
        print(f"    ✓ Answer: {q['correct_answer']}")
        print(f"    📚 Concept: {q['concept']}")
        print(f"    ⚡ Difficulty: {q['difficulty']}")
    
    # ================================================================
    # Example 2: Concept-Balanced Quiz
    # ================================================================
    print("\n\n" + "─"*80)
    print("EXAMPLE 2: CONCEPT-BALANCED QUIZ")
    print("─"*80 + "\n")
    
    quiz_balanced = engine.generate_quiz(
        lecture_text=lecture,
        num_questions=15,
        quiz_type='concept_balanced',
        difficulty='medium',
        question_types=['mcq', 'true_false', 'short_answer']
    )
    
    print("\nConcept Distribution (Balanced Mode):")
    print("─"*80)
    concept_dist = defaultdict(int)
    for q in quiz_balanced['questions']:
        concept_dist[q['concept']] += 1
    
    for concept, count in sorted(concept_dist.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"{concept:30s} | {bar} ({count})")
    
    # ================================================================
    # Example 3: Adaptive Quiz with Student Mastery
    # ================================================================
    print("\n\n" + "─"*80)
    print("EXAMPLE 3: ADAPTIVE QUIZ (THOMPSON SAMPLING)")
    print("─"*80 + "\n")
    
    # Simulate student with varying concept mastery
    student_mastery = {
        'reinforcement learning': 0.3,      # Weak - needs practice
        'q-learning': 0.25,                 # Very weak
        'deep q-networks': 0.4,             # Below average
        'search algorithms': 0.75,          # Strong
        'a* search': 0.8,                   # Very strong
        'breadth-first search': 0.7,        # Above average
        'minimax algorithm': 0.5,           # Average
        'policy gradient methods': 0.2,     # Very weak
        'bellman equation': 0.35,           # Weak
        'monte carlo tree search': 0.6      # Moderate
    }
    
    print("Student Mastery Profile:")
    print("─"*80)
    for concept, mastery in sorted(student_mastery.items(), key=lambda x: x[1]):
        bar_length = int(mastery * 30)
        bar = "█" * bar_length + "░" * (30 - bar_length)
        status = "🔴" if mastery < 0.4 else "🟡" if mastery < 0.7 else "🟢"
        print(f"{status} {concept:30s} | {bar} {mastery:.2f}")
    
    quiz_adaptive = engine.generate_quiz(
        lecture_text=lecture,
        num_questions=20,
        quiz_type='adaptive',
        difficulty='mixed',
        question_types=['mcq', 'true_false', 'short_answer'],
        concept_mastery=student_mastery,
        bandit_algorithm='thompson_sampling'
    )
    
    print("\n\nAdaptive Selection Analysis:")
    print("─"*80)
    
    # Analyze which concepts were selected
    adaptive_dist = defaultdict(int)
    for q in quiz_adaptive['questions']:
        adaptive_dist[q['concept']] += 1
    
    print("\nConcepts Selected (should favor weak areas):")
    for concept, count in sorted(adaptive_dist.items(), key=lambda x: -x[1]):
        mastery = student_mastery.get(concept, 0.5)
        status = "⚠️  TARGETED" if mastery < 0.4 else "✓ reviewed"
        bar = "█" * count
        print(f"{status:15s} {concept:30s} | {bar} ({count} q's, mastery: {mastery:.2f})")
    
    # Show sample adaptive questions
    print("\n\nSample Questions (Adaptive Mode):")
    print("─"*80)
    for i, q in enumerate(quiz_adaptive['questions'][:3], 1):
        concept = q['concept']
        mastery = student_mastery.get(concept, 0.5)
        print(f"\nQ{i}. 📍 {concept} (mastery: {mastery:.2f})")
        print(f"    [{q['type']}] {q['question']}")
        if q['type'] == 'MCQ':
            for opt in q['options']:
                marker = "✓" if opt.startswith(q['correct_answer']) else " "
                print(f"    {marker} {opt}")
        else:
            print(f"    ✓ Answer: {q['correct_answer']}")
        print(f"    ⚡ Difficulty: {q['difficulty']}")
    
    # ================================================================
    # Comparison: Adaptive vs Random
    # ================================================================
    print("\n\n" + "─"*80)
    print("COMPARISON: ADAPTIVE vs RANDOM SELECTION")
    print("─"*80 + "\n")
    
    # Calculate average mastery of selected concepts
    adaptive_avg = sum(
        student_mastery.get(q['concept'], 0.5)
        for q in quiz_adaptive['questions']
    ) / len(quiz_adaptive['questions'])
    
    random_avg = sum(
        student_mastery.get(q['concept'], 0.5)
        for q in quiz_random['questions']
    ) / len(quiz_random['questions'])
    
    print(f"Average concept mastery in selected questions:")
    print(f"  Random mode:   {random_avg:.3f}")
    print(f"  Adaptive mode: {adaptive_avg:.3f}")
    print(f"\n  Δ Difference:  {random_avg - adaptive_avg:+.3f}")
    print(f"\n  {'✓ Adaptive successfully targets weaker concepts!' if adaptive_avg < random_avg else '  ⚠️  Random happened to select weaker concepts'}")
    
    # ================================================================
    # Export Quiz as JSON
    # ================================================================
    print("\n\n" + "─"*80)
    print("QUIZ EXPORT")
    print("─"*80 + "\n")
    
    output_file = "adaptive_quiz_example.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(quiz_adaptive, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Adaptive quiz exported to: {output_file}")
    print(f"  Questions: {len(quiz_adaptive['questions'])}")
    print(f"  Concepts: {len(quiz_adaptive['concepts'])}")
    print(f"  Generation time: {quiz_adaptive['metadata']['generation_time_seconds']}s")
    
    print("\n" + "="*80)
    print("DEMONSTRATION COMPLETE")
    print("="*80 + "\n")
    
    return quiz_adaptive


if __name__ == "__main__":
    """
    Run comprehensive examples demonstrating all features.
    
    Execute this file directly to see:
    1. Random quiz generation
    2. Concept-balanced quiz generation
    3. Adaptive quiz with Thompson Sampling
    4. Comparison and analysis
    5. JSON export
    """
    quiz = run_example()
    
    print("\n📚 USAGE IN YOUR APPLICATION:")
    print("─"*80)
    print("""
from services.adaptive_quiz_engine import AdaptiveQuizEngine

# Initialize
engine = AdaptiveQuizEngine()

# Generate adaptive quiz
quiz = engine.generate_quiz(
    lecture_text=your_lecture_content,
    num_questions=20,
    quiz_type='adaptive',
    concept_mastery=student_mastery_scores,
    bandit_algorithm='thompson_sampling'
)

# Access questions
for q in quiz['questions']:
    print(q['question'])
    print(q['correct_answer'])
    """)
