"""
Difficulty Controller - Bloom's Taxonomy-based difficulty management.

Maps difficulty levels to cognitive complexity using Bloom's Taxonomy:
  Easy   → Remember / Understand  (definitions, fact recall)
  Medium → Apply / Analyze        (relationships, cause-effect)
  Hard   → Evaluate / Create      (scenarios, reasoning, application)

Provides question templates, prompt strategies, and scoring that genuinely
change cognitive complexity rather than just surface wording.
"""

from __future__ import annotations
import random
import re
from typing import Dict, List, Optional, Tuple


# ────────────────────────────────────────────────────────────────
# Bloom's Taxonomy mapping
# ────────────────────────────────────────────────────────────────

BLOOMS_LEVELS = {
    "easy": {
        "taxonomy": ["Remember", "Understand"],
        "verbs": [
            "define", "identify", "list", "state", "describe",
            "explain", "summarize", "classify", "recognize",
        ],
        "question_stems": [
            "What is the definition of {concept}?",
            "Which of the following best defines {concept}?",
            "What does {concept} refer to?",
            "{concept} is best described as:",
            "Which statement correctly identifies {concept}?",
            "Which of the following is true about {concept}?",
            "How is {concept} defined in the context of the material?",
            "What is {concept}?",
            "What is the primary purpose of {concept}?",
            "Which of the following accurately describes the role of {concept}?",
            "What key characteristic distinguishes {concept}?",
            "In the given material, {concept} is used to:",
        ],
    },
    "medium": {
        "taxonomy": ["Apply", "Analyze"],
        "verbs": [
            "apply", "compare", "contrast", "differentiate",
            "relate", "organize", "examine", "distinguish",
        ],
        "question_stems": [
            "How does {concept} relate to {related}?",
            "What is the relationship between {concept} and {related}?",
            "Which of the following explains the effect of {concept}?",
            "What happens when {concept} is applied in practice?",
            "How can {concept} be distinguished from {related}?",
            "What is the cause-and-effect relationship involving {concept}?",
            "Which scenario demonstrates the use of {concept}?",
            "Compare and contrast {concept} with {related}. Which statement is correct?",
            "Why is {concept} necessary when working with {related}?",
            "What problem does {concept} solve that {related} does not?",
            "If {concept} were removed from the process, what would change?",
            "Which of the following is a consequence of applying {concept}?",
        ],
    },
    "hard": {
        "taxonomy": ["Evaluate", "Create"],
        "verbs": [
            "evaluate", "justify", "critique", "predict",
            "design", "construct", "hypothesize", "assess",
        ],
        "question_stems": [
            "Given a scenario where {scenario}, what would be the outcome of applying {concept}?",
            "A student claims that {claim}. Evaluate this claim regarding {concept}.",
            "If {condition}, how would {concept} behave differently?",
            "Which of the following best evaluates the impact of {concept} in {scenario}?",
            "Design an approach using {concept} to solve {scenario}. Which step is correct?",
            "Predict what would happen if {concept} were removed from {scenario}.",
            "Critically assess: Why is {concept} considered important in {related}?",
            "Which argument best justifies the use of {concept} over {related}?",
            "In a situation where {scenario}, which limitation of {concept} would be most significant?",
            "A team decides to replace {concept} with {related}. What trade-off should they expect?",
            "Which evidence from the material best supports the importance of {concept} in {scenario}?",
            "Evaluate: Under what conditions would {concept} fail to produce the desired outcome?",
        ],
    },
}


class DifficultyController:
    """
    Controls question difficulty using Bloom's Taxonomy levels.
    Ensures Easy/Medium/Hard genuinely differ in cognitive demand.
    """

    # ────────────────────────────────────────────────────────────
    # Template selection
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def get_question_stem(
        difficulty: str,
        concept: str,
        related_concept: Optional[str] = None,
        context: str = "",
    ) -> str:
        """
        Return a difficulty-appropriate question stem populated with concept
        names and, for harder levels, scenario/claim fragments derived from
        the lecture context.
        """
        difficulty = difficulty.lower()
        if difficulty not in BLOOMS_LEVELS:
            difficulty = "medium"

        level = BLOOMS_LEVELS[difficulty]
        templates = level["question_stems"]
        related = related_concept or "other concepts"

        # For hard questions we need scenario fragments
        scenario = DifficultyController._extract_scenario(context, concept)
        claim = DifficultyController._extract_claim(context, concept)
        condition = DifficultyController._extract_condition(context, concept)

        stem = random.choice(templates)
        stem = stem.format(
            concept=concept,
            related=related,
            scenario=scenario,
            claim=claim,
            condition=condition,
        )
        return stem

    @staticmethod
    def get_blooms_verbs(difficulty: str) -> List[str]:
        """Return Bloom's action verbs for the given difficulty."""
        difficulty = difficulty.lower()
        return BLOOMS_LEVELS.get(difficulty, BLOOMS_LEVELS["medium"])["verbs"]

    @staticmethod
    def get_bloom_info(difficulty: str) -> Dict:
        """Return Bloom's taxonomy label and verbs for the given difficulty."""
        difficulty = difficulty.lower()
        level = BLOOMS_LEVELS.get(difficulty, BLOOMS_LEVELS["medium"])
        return {
            "taxonomy": " / ".join(level["taxonomy"]),
            "verbs": level["verbs"],
        }

    @staticmethod
    def get_model_prompt(
        difficulty: str,
        concept: str,
        context: str,
        related_concept: Optional[str] = None,
    ) -> str:
        """
        Build a prompt for the transformer model that encodes difficulty
        via Bloom's Taxonomy instructions.
        """
        difficulty = difficulty.lower()
        if difficulty not in BLOOMS_LEVELS:
            difficulty = "medium"

        level = BLOOMS_LEVELS[difficulty]
        taxonomy_label = " / ".join(level["taxonomy"])
        verb_sample = ", ".join(random.sample(level["verbs"], min(3, len(level["verbs"]))))

        if difficulty == "easy":
            instruction = (
                f"Generate a simple factual MCQ about '{concept}' that tests "
                f"recall or basic understanding ({taxonomy_label}). "
                f"The question should ask the student to {verb_sample}."
            )
        elif difficulty == "medium":
            related = related_concept or "related topics"
            instruction = (
                f"Generate an MCQ about '{concept}' that tests conceptual "
                f"understanding or analysis ({taxonomy_label}). "
                f"Consider relating it to '{related}'. "
                f"The question should require the student to {verb_sample}."
            )
        else:
            instruction = (
                f"Generate a challenging scenario-based MCQ about '{concept}' "
                f"that tests evaluation or reasoning ({taxonomy_label}). "
                f"Use a realistic scenario from the context. "
                f"The question should require the student to {verb_sample}."
            )

        prompt = (
            f"{instruction}\n\n"
            f"Context:\n{context[:1500]}\n\n"
            f"Return ONLY the question text ending with '?'."
        )
        return prompt

    # ────────────────────────────────────────────────────────────
    # Concept selection helpers
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def select_concepts_for_difficulty(
        concepts: List[Dict],
        difficulty: str,
        count: int,
    ) -> List[Dict]:
        """
        Select concepts appropriate for the requested difficulty.

        Easy  → high-score (common / well-defined) concepts
        Hard  → low-score (rare / complex) concepts
        Medium→ mid-range
        Mixed → random sample
        """
        difficulty = difficulty.lower()
        if difficulty == "mixed" or len(concepts) <= count:
            pool = concepts
        elif difficulty == "easy":
            pool = sorted(concepts, key=lambda c: c.get("score", 0.5), reverse=True)
        elif difficulty == "hard":
            pool = sorted(concepts, key=lambda c: c.get("score", 0.5))
        else:
            pool = concepts

        # Take more than needed so the generator can skip bad candidates
        pool = pool[: count * 3] if len(pool) > count * 3 else pool
        selected = random.sample(pool, min(count, len(pool)))
        return selected

    @staticmethod
    def assign_difficulty_label(concept: Dict, target: str) -> str:
        """Return difficulty label for a question given target mode."""
        if target != "mixed":
            return target
        score = concept.get("score", 0.5)
        if score > 0.65:
            return "easy"
        elif score > 0.35:
            return "medium"
        return "hard"

    # ────────────────────────────────────────────────────────────
    # Internal helpers for scenario extraction
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_scenario(context: str, concept: str) -> str:
        """Pull a short scenario fragment from context for hard questions."""
        sentences = [s.strip() for s in re.split(r"[.!?]", context) if len(s.strip()) > 30]
        # Prefer sentences containing the concept
        relevant = [s for s in sentences if concept.lower() in s.lower()]
        if relevant:
            chosen = relevant[0]
        elif sentences:
            chosen = sentences[0]
        else:
            return f"a practical use of {concept}"
        # Truncate for readability
        return chosen[:120] if len(chosen) > 120 else chosen

    @staticmethod
    def _extract_claim(context: str, concept: str) -> str:
        """Generate a debatable claim from context for evaluation questions."""
        sentences = [s.strip() for s in re.split(r"[.!?]", context) if concept.lower() in s.lower() and len(s.strip()) > 20]
        if sentences:
            return sentences[0][:100]
        return f"{concept} is essential to understanding this topic"

    @staticmethod
    def _extract_condition(context: str, concept: str) -> str:
        """Extract a conditional situation from context."""
        patterns = [
            rf"if\s+.*?{re.escape(concept)}.*?(?=[.!?])",
            rf"when\s+.*?{re.escape(concept)}.*?(?=[.!?])",
        ]
        for pat in patterns:
            m = re.search(pat, context, re.IGNORECASE)
            if m:
                return m.group(0)[:100]
        return f"{concept} is applied under different conditions"
