"""
Question Generator – Multi-Type Quiz Engine (MCQ + True/False + Short Answer)
==============================================================================
Multi-provider architecture for high-quality educational question generation.

Provider priority (auto-detected from environment variables):
  1. OpenAI GPT     — set OPENAI_API_KEY
  2. Google Gemini  — set GEMINI_API_KEY
  3. Local FLAN-T5  — always available (offline fallback)

Supported question types:
  • MCQ          — 4-option multiple choice with misconception-based distractors
  • True/False   — statement verification with explanation of why true/false
  • Short Answer — open-ended questions requiring concise written responses

API providers generate COMPLETE questions in a single prompt.
Local FLAN-T5 uses a multi-step approach with sub-modules for quality.
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Dict, List, Optional

from services.difficulty_controller import DifficultyController
from services.distractor_generator import DistractorGenerator
from services.concept_mapper import ConceptMapper

_LETTERS = ["A", "B", "C", "D"]

# Default distribution of question types when "mixed" types are requested
_DEFAULT_TYPE_MIX = {"mcq": 0.60, "true_false": 0.20, "short_answer": 0.20}


class QuestionGenerator:
    """
    Production quiz engine with automatic provider selection.

    Generates three question types:
      • MCQ (multiple-choice with 4 options)
      • True/False (statement verification)
      • Short Answer (open-ended, keyword-graded)

    Public entry point: ``generate_questions(...)``
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.getenv(
            "QUESTION_GEN_MODEL", "google/flan-t5-base"
        )
        self._provider: Optional[str] = None  # openai | gemini | local
        self._openai_client = None
        self._gemini_model = None
        self._t5_model = None
        self._t5_tokenizer = None
        self._device = "cpu"

        # Sub-modules
        self._difficulty = DifficultyController()
        self._distractors = DistractorGenerator()
        self._mapper = ConceptMapper()

    # ================================================================
    # Provider detection & lazy initialization
    # ================================================================

    def _init_provider(self):
        """Detect and initialize the best available LLM provider."""
        if self._provider is not None:
            return

        # 1. OpenAI
        key = os.getenv("OPENAI_API_KEY", "")
        if key and key != "your-openai-api-key":
            try:
                import openai

                self._openai_client = openai.OpenAI(api_key=key)
                self._provider = "openai"
                print("[QuestionGen] Provider: OpenAI GPT")
                return
            except ImportError:
                print("[QuestionGen] `openai` package not installed, skipping.")
            except Exception as exc:
                print(f"[QuestionGen] OpenAI init error: {exc}")

        # 2. Google Gemini
        key = os.getenv("GEMINI_API_KEY", "")
        if key and key != "your-gemini-api-key":
            try:
                import google.generativeai as genai

                genai.configure(api_key=key)
                model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
                self._gemini_model = genai.GenerativeModel(model_name)
                self._provider = "gemini"
                print(f"[QuestionGen] Provider: Google Gemini ({model_name})")
                return
            except ImportError:
                print(
                    "[QuestionGen] `google-generativeai` package not installed, skipping."
                )
            except Exception as exc:
                print(f"[QuestionGen] Gemini init error: {exc}")

        # 3. Local FLAN-T5 (always available)
        self._load_local_model()
        self._provider = "local"

    def _load_local_model(self):
        if self._t5_model is not None:
            return
        try:
            from transformers import T5ForConditionalGeneration, T5Tokenizer
            import torch

            print(f"[QuestionGen] Loading local model: {self.model_name}")
            self._t5_tokenizer = T5Tokenizer.from_pretrained(self.model_name)
            self._t5_model = T5ForConditionalGeneration.from_pretrained(
                self.model_name
            )
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            self._t5_model.to(self._device)
            print(f"[QuestionGen] Local model ready on {self._device}")
        except Exception as exc:
            print(f"[QuestionGen] Local model unavailable: {exc}")
            self._t5_model = None

    # ================================================================
    # Document understanding helpers
    # ================================================================

    def _build_document_summary(self, text: str, concepts: List[Dict]) -> str:
        """Build a concise overview of the full document for holistic question generation.

        This ensures the model understands the WHOLE document — not just a small
        snippet — so questions are logically grounded in the complete material.
        """
        concept_names = [c["name"] for c in concepts[:20]]

        # Extract the most informative sentences from the document
        sentences = [s.strip() for s in re.split(r'[.!?]\s+', text) if len(s.strip()) > 25]

        # Pick sentences that mention key concepts (up to ~1200 chars)
        key_sentences = []
        used_concepts = set()
        for s in sentences:
            s_lower = s.lower()
            for cn in concept_names:
                if cn.lower() in s_lower and cn not in used_concepts:
                    key_sentences.append(s.strip())
                    used_concepts.add(cn)
                    break
            if len(". ".join(key_sentences)) > 1200:
                break

        # If we have few concept-sentences, add the first few document sentences
        if len(key_sentences) < 5:
            for s in sentences[:10]:
                if s not in key_sentences:
                    key_sentences.append(s)
                if len(key_sentences) >= 8:
                    break

        overview = ". ".join(key_sentences)
        if not overview.endswith("."):
            overview += "."

        topic_list = ", ".join(concept_names[:15])
        return (
            f"DOCUMENT OVERVIEW: This material covers the following key topics: "
            f"{topic_list}.\n\n"
            f"KEY CONTENT: {overview[:1500]}"
        )

    # ================================================================
    # Question type distribution helper
    # ================================================================

    @staticmethod
    def _plan_question_types(
        num_questions: int,
        question_types: Optional[List[str]],
    ) -> List[str]:
        """Return an ordered list of question types to generate.

        If user explicitly selects specific types, ONLY those types are generated.
        If question_types is not provided or empty, uses balanced mix.
        """
        # Normalise requested types
        valid = {"mcq", "true_false", "short_answer"}
        
        # If user explicitly selected types, respect them 100%
        if question_types and isinstance(question_types, list):
            requested = [t for t in question_types if t in valid]
            if requested:  # User selected specific types
                # Generate ONLY the selected types  
                counts: Dict[str, int] = {}
                assigned = 0
                
                # Distribute questions evenly among selected types
                questions_per_type = num_questions // len(requested)
                remainder = num_questions % len(requested)
                
                for i, t in enumerate(requested):
                    c = questions_per_type + (1 if i < remainder else 0)
                    counts[t] = c
                    assigned += c
                
                # Build flat list and shuffle for variety
                plan: List[str] = []
                for t, c in counts.items():
                    plan.extend([t] * c)
                random.shuffle(plan)
                return plan
        
        # Default: balanced mix (user didn't select types)
        requested = list(valid)
        
        # Calculate counts per type using default mix
        mix: Dict[str, float] = {}
        for t in requested:
            mix[t] = _DEFAULT_TYPE_MIX.get(t, 1.0 / len(requested))

        # Normalise weights
        total_w = sum(mix.values())
        counts: Dict[str, int] = {}
        assigned = 0
        for t in mix:
            c = max(1, round(num_questions * mix[t] / total_w))
            counts[t] = c
            assigned += c

        # Adjust to match requested total
        while assigned > num_questions:
            for t in sorted(counts, key=lambda x: counts[x], reverse=True):
                if counts[t] > 1 and assigned > num_questions:
                    counts[t] -= 1
                    assigned -= 1
        while assigned < num_questions:
            for t in sorted(counts, key=lambda x: counts[x]):
                if assigned < num_questions:
                    counts[t] += 1
                    assigned += 1

        # Build flat list and shuffle for variety
        plan: List[str] = []
        for t, c in counts.items():
            plan.extend([t] * c)
        random.shuffle(plan)
        return plan

    # ================================================================
    # PUBLIC → generate_questions
    # ================================================================

    def generate_questions(
        self,
        text: str,
        concepts: List[Dict],
        knowledge_graph: Dict,
        num_questions: int = 10,
        question_types: List[str] = None,
        difficulty: str = "mixed",
    ) -> List[Dict]:
        """
        Generate *num_questions* questions from the document text + concepts.

        Supports MCQ, True/False, and Short Answer question types.
        The generator builds a document-level summary so every question
        is grounded in overall document understanding.

        Returns list of question dicts with keys:
            question, correct_answer, concept, difficulty, explanation, type
            + options (for MCQ), keywords (for short_answer)
        Plus backward-compat keys: text, id
        """
        if not concepts:
            raise ValueError("No concepts provided for question generation.")
        if not text:
            raise ValueError("No text provided for question generation.")

        # Plan which question types to generate
        type_plan = self._plan_question_types(num_questions, question_types)
        type_counts = {}
        for t in type_plan:
            type_counts[t] = type_counts.get(t, 0) + 1

        print(
            f"[QuestionGen] Generating {num_questions} questions "
            f"({len(concepts)} concepts, difficulty={difficulty}, "
            f"types={type_counts})"
        )
        
        # Show which question types were selected
        if question_types and len(question_types) > 0:
            print(f"[QuestionGen] User selected types: {', '.join(question_types)}")
        else:
            print("[QuestionGen] No specific types selected - using balanced mix")

        self._init_provider()
        self._mapper.build_concept_index(concepts, text)

        # Build a condensed document overview for holistic understanding
        self._doc_summary = self._build_document_summary(text, concepts)

        selected = DifficultyController.select_concepts_for_difficulty(
            concepts, difficulty, num_questions * 3
        )

        questions: List[Dict] = []
        used: List[str] = []
        concept_idx = 0

        for q_type in type_plan:
            if len(questions) >= num_questions:
                break
            # Cycle through concepts, wrapping around if needed
            if concept_idx >= len(selected):
                concept_idx = 0
            concept = selected[concept_idx]
            concept_idx += 1

            q = self._generate_single_question(
                q_type, concept, text, concepts, knowledge_graph,
                difficulty, used
            )
            if q is not None:
                questions.append(q)
                used.append(q["question"])

        # If we fell short, fill remaining with MCQs (most reliable)
        extra_attempts = 0
        while len(questions) < num_questions and extra_attempts < num_questions * 2:
            extra_attempts += 1
            if concept_idx >= len(selected):
                concept_idx = 0
            concept = selected[concept_idx]
            concept_idx += 1
            q = self._generate_single_question(
                "mcq", concept, text, concepts, knowledge_graph,
                difficulty, used
            )
            if q is not None:
                questions.append(q)
                used.append(q["question"])

        # Finalize — assign IDs and backward-compat fields
        random.shuffle(questions)
        for i, q in enumerate(questions):
            q["id"] = f"q_{i}"
            q["text"] = q["question"]  # backward compat

        mcq_c = sum(1 for q in questions if q["type"] == "mcq")
        tf_c = sum(1 for q in questions if q["type"] == "true_false")
        sa_c = sum(1 for q in questions if q["type"] == "short_answer")
        print(
            f"[QuestionGen] Generated {len(questions)} questions via {self._provider} "
            f"(MCQ={mcq_c}, T/F={tf_c}, Short={sa_c})"
        )
        return questions

    # ================================================================
    # Unified single-question dispatcher
    # ================================================================

    def _generate_single_question(
        self, q_type, concept, text, all_concepts, kg,
        target_difficulty, existing
    ) -> Optional[Dict]:
        """Route to the appropriate generator based on question type."""
        name = concept["name"]
        diff = DifficultyController.assign_difficulty_label(concept, target_difficulty)
        ctx = self._mapper.get_context(text, name)
        if not ctx or len(ctx.strip()) < 30:
            return None

        related_names = self._mapper.get_related_concepts(
            name, all_concepts, kg, top_k=3
        )
        related = related_names[0] if related_names else None

        result = None
        if q_type == "true_false":
            result = self._generate_true_false(diff, name, related, ctx, text, all_concepts, kg)
        elif q_type == "short_answer":
            result = self._generate_short_answer(diff, name, related, ctx, text, all_concepts, kg)
        else:
            result = self._generate_mcq_question(diff, name, related, ctx, text, all_concepts, kg)

        if result is None:
            return None

        # Duplicate check
        if self._mapper.is_duplicate_question(result["question"], existing):
            return None

        result["concept"] = name
        result["difficulty"] = diff.capitalize()
        return result

    # ================================================================
    # MCQ Generation
    # ================================================================

    def _generate_mcq_question(
        self, difficulty, concept, related, context, text, all_concepts, kg
    ) -> Optional[Dict]:
        """Generate a single MCQ via provider or fallback."""
        mcq = None
        if self._provider in ("openai", "gemini"):
            mcq = self._api_generate_mcq(difficulty, concept, related, context)
        else:
            mcq = self._local_generate_mcq(
                difficulty, concept, related, context, text, all_concepts, kg
            )

        if mcq is None:
            mcq = self._rule_based_mcq(
                difficulty, concept, related, context, text, all_concepts, kg
            )

        if mcq:
            mcq["type"] = "mcq"
        return mcq

    def _api_generate_mcq(
        self, difficulty, concept, related, context
    ) -> Optional[Dict]:
        prompt = self._build_mcq_api_prompt(difficulty, concept, related, context)
        raw = self._call_api(prompt)
        parsed = self._parse_mcq_response(raw)
        if parsed and len(parsed.get("options", [])) == 4:
            return parsed
        return None

    def _build_mcq_api_prompt(self, difficulty, concept, related, context):
        bloom = DifficultyController.get_bloom_info(difficulty)
        taxonomy = bloom["taxonomy"]
        verbs = ", ".join(random.sample(bloom["verbs"], min(3, len(bloom["verbs"]))))

        if difficulty.lower() == "easy":
            diff_instruction = (
                f"Create a RECALL / UNDERSTANDING level question.\n"
                f"The student should need to {verbs}.\n"
                f"Focus on definitions, facts, or key terms.\n"
                f"The question should test whether the student truly understands "
                f"the concept — NOT just recognize a keyword."
            )
        elif difficulty.lower() == "medium":
            rel = f" Relate it to '{related}'." if related else ""
            diff_instruction = (
                f"Create an APPLICATION / ANALYSIS level question.\n"
                f"The student should need to {verbs}.{rel}\n"
                f"Focus on relationships, cause-and-effect, or comparisons.\n"
                f"The student should need to REASON about the concept — "
                f"not just recall a definition. Present a concrete situation "
                f"where the student must APPLY their knowledge."
            )
        else:
            rel = f" You may contrast with '{related}'." if related else ""
            diff_instruction = (
                f"Create an EVALUATION / SYNTHESIS level question.\n"
                f"The student should need to {verbs}.{rel}\n"
                f"Use a realistic scenario requiring critical thinking.\n"
                f"The question MUST present a specific scenario, case study, "
                f"or hypothetical situation. The student should EVALUATE "
                f"trade-offs or PREDICT outcomes based on deep understanding."
            )

        doc_ctx = getattr(self, "_doc_summary", "")
        doc_block = f"\n{doc_ctx}\n\n" if doc_ctx else ""

        prompt = (
            "You are an expert educational assessment designer who creates "
            "exam-quality questions that test deep understanding.\n\n"
            "Generate ONE high-quality multiple-choice question "
            "from the lecture content below.\n\n"
            f"{doc_block}"
            f"SPECIFIC SECTION ON '{concept}':\n{context[:2000]}\n\n"
            f"TOPIC: {concept}\n"
            f"DIFFICULTY: {difficulty.upper()} (Bloom's Taxonomy: {taxonomy})\n\n"
            f"INSTRUCTIONS:\n{diff_instruction}\n\n"
            "QUALITY RULES (MANDATORY):\n"
            "- The question must require THINKING, not just pattern matching\n"
            "- Write a clear, unambiguous question ending with ?\n"
            "- Provide EXACTLY 4 options labelled A), B), C), D)\n"
            "- Only ONE option must be unambiguously correct\n"
            "- WRONG options must reflect common MISCONCEPTIONS or plausible "
            "errors students actually make (e.g. confusing similar concepts, "
            "partial truths, reversed cause-effect, over-generalizations)\n"
            "- All options must be similar in length, specificity, and tone\n"
            "- Do NOT include 'All of the above' or 'None of the above'\n"
            "- Do NOT make the correct answer obviously different from others\n"
            "- The explanation must justify WHY the answer is correct AND "
            "briefly explain why each wrong option fails\n\n"
            "FORMAT (follow exactly):\n"
            "QUESTION: <question text?>\n"
            "A) <option>\n"
            "B) <option>\n"
            "C) <option>\n"
            "D) <option>\n"
            "ANSWER: <A, B, C, or D>\n"
            "EXPLANATION: <explanation>"
        )
        return prompt

    # ================================================================
    # True/False Generation
    # ================================================================

    def _generate_true_false(
        self, difficulty, concept, related, context, text, all_concepts, kg
    ) -> Optional[Dict]:
        """Generate a True/False question via API or local fallback."""
        if self._provider in ("openai", "gemini"):
            result = self._api_generate_tf(difficulty, concept, related, context)
            if result:
                result["type"] = "true_false"
                return result

        # Local / rule-based fallback
        result = self._local_generate_tf(difficulty, concept, related, context, text)
        if result:
            result["type"] = "true_false"
        return result

    def _api_generate_tf(self, difficulty, concept, related, context) -> Optional[Dict]:
        """Use API to generate a True/False question."""
        bloom = DifficultyController.get_bloom_info(difficulty)
        taxonomy = bloom["taxonomy"]

        doc_ctx = getattr(self, "_doc_summary", "")
        doc_block = f"\n{doc_ctx}\n\n" if doc_ctx else ""

        # Decide whether to generate a True or False statement
        make_false = random.random() < 0.5

        if make_false:
            truth_instruction = (
                "Create a statement that is PLAUSIBLY WRONG — it should sound "
                "believable but contain a subtle factual error, reversed "
                "cause-effect, or common misconception. The correct answer is FALSE."
            )
        else:
            truth_instruction = (
                "Create a statement that is FACTUALLY CORRECT based on the "
                "lecture content. It should be specific and testable. "
                "The correct answer is TRUE."
            )

        if difficulty.lower() == "easy":
            diff_detail = "The statement should test basic recall of a definition or fact."
        elif difficulty.lower() == "medium":
            rel_part = f" Consider relating it to '{related}'." if related else ""
            diff_detail = (
                f"The statement should involve a relationship or comparison "
                f"between concepts.{rel_part}"
            )
        else:
            diff_detail = (
                "The statement should involve a subtle edge case, a "
                "conditional truth, or an evaluative claim that requires "
                "deep understanding to verify."
            )

        prompt = (
            "You are an expert educational assessment designer.\n\n"
            "Generate ONE True/False question from the lecture content below.\n\n"
            f"{doc_block}"
            f"SPECIFIC SECTION ON '{concept}':\n{context[:2000]}\n\n"
            f"TOPIC: {concept}\n"
            f"DIFFICULTY: {difficulty.upper()} (Bloom's Taxonomy: {taxonomy})\n\n"
            f"INSTRUCTIONS:\n{truth_instruction}\n{diff_detail}\n\n"
            "QUALITY RULES:\n"
            "- The statement must be SPECIFIC and derived from the lecture content\n"
            "- Avoid vague or unfalsifiable claims\n"
            "- If FALSE, the error must be SUBTLE (not obviously ridiculous)\n"
            "- The explanation must clearly state WHY the statement is true or false\n\n"
            "FORMAT (follow exactly):\n"
            "STATEMENT: <declarative statement>\n"
            "ANSWER: <True or False>\n"
            "EXPLANATION: <why it is true/false, referencing the lecture content>"
        )

        raw = self._call_api(prompt)
        return self._parse_tf_response(raw)

    def _local_generate_tf(
        self, difficulty, concept, related, context, text
    ) -> Optional[Dict]:
        """Generate True/False via local model or rule-based extraction."""
        # Try T5 first
        if self._t5_model is not None:
            make_false = random.random() < 0.5
            if make_false:
                t5_prompt = (
                    f"Create a false but plausible statement about \"{concept}\" "
                    f"based on: {context[:400]}\n\n"
                    f"False statement:"
                )
            else:
                t5_prompt = (
                    f"Create a true factual statement about \"{concept}\" "
                    f"based on: {context[:400]}\n\n"
                    f"True statement:"
                )
            raw = self._t5_generate(t5_prompt, max_length=120)
            if raw and len(raw.strip()) > 15:
                stmt = raw.strip()
                if stmt.endswith("?"):
                    stmt = stmt[:-1] + "."
                if not stmt.endswith("."):
                    stmt += "."
                return {
                    "question": stmt,
                    "correct_answer": "False" if make_false else "True",
                    "options": [],
                    "explanation": self._build_tf_explanation(
                        context, concept, "False" if make_false else "True", stmt
                    ),
                }

        # Rule-based fallback: extract a factual sentence and optionally corrupt it
        return self._rule_based_tf(difficulty, concept, related, context)

    def _rule_based_tf(self, difficulty, concept, related, context) -> Optional[Dict]:
        """Generate a True/False question by extracting/corrupting a factual sentence."""
        sentences = [
            s.strip() for s in re.split(r"[.!?]", context)
            if len(s.strip()) > 25 and concept.lower() in s.lower()
        ]
        if not sentences:
            sentences = [
                s.strip() for s in re.split(r"[.!?]", context) if len(s.strip()) > 25
            ]
        if not sentences:
            return None

        base_sentence = random.choice(sentences[:5]).strip()
        if not base_sentence.endswith("."):
            base_sentence += "."

        make_false = random.random() < 0.5
        if make_false:
            corrupted = self._corrupt_statement(base_sentence, concept, related)
            if corrupted and corrupted != base_sentence:
                return {
                    "question": corrupted,
                    "correct_answer": "False",
                    "options": [],
                    "explanation": self._build_tf_explanation(
                        context, concept, "False", corrupted
                    ),
                }
            # If corruption failed, use the true statement instead
            make_false = False

        return {
            "question": base_sentence,
            "correct_answer": "True",
            "options": [],
            "explanation": self._build_tf_explanation(
                context, concept, "True", base_sentence
            ),
        }

    def _corrupt_statement(self, statement: str, concept: str, related: Optional[str]) -> str:
        """Introduce a subtle factual error into a true statement.

        Corruption strategies (applied in priority order):
        1. Swap a key term with a related but incorrect concept
        2. Negate a key verb or relationship
        3. Swap numerical/quantitative terms
        4. Replace a qualifier (always↔never, all↔some)
        """
        result = statement

        # Strategy 1: Swap concept with related concept
        if related and related.lower() != concept.lower():
            if concept.lower() in result.lower():
                result = re.sub(
                    re.escape(concept), related, result, count=1, flags=re.IGNORECASE
                )
                if result != statement:
                    return result

        # Strategy 2: Negate key verbs/relationships
        negation_swaps = [
            (r"\bis\b", "is not"), (r"\bare\b", "are not"),
            (r"\bcan\b", "cannot"), (r"\bdoes\b", "does not"),
            (r"\bincreases\b", "decreases"), (r"\bdecreases\b", "increases"),
            (r"\benables\b", "prevents"), (r"\bprevents\b", "enables"),
            (r"\brequires\b", "does not require"),
            (r"\bsupports\b", "does not support"),
            (r"\bimproves\b", "degrades"), (r"\bdegrades\b", "improves"),
        ]
        s_lower = statement.lower()
        for pattern, replacement in negation_swaps:
            if re.search(pattern, s_lower):
                result = re.sub(pattern, replacement, statement, count=1, flags=re.IGNORECASE)
                if result != statement:
                    return result

        # Strategy 3: Swap qualifiers
        qualifier_swaps = [
            ("always", "never"), ("never", "always"),
            ("all", "none"), ("none", "all"),
            ("most", "few"), ("few", "most"),
            ("before", "after"), ("after", "before"),
            ("first", "last"), ("last", "first"),
        ]
        for orig, swap in qualifier_swaps:
            if f" {orig} " in statement.lower():
                result = re.sub(
                    rf"\b{orig}\b", swap, statement, count=1, flags=re.IGNORECASE
                )
                if result != statement:
                    return result

        return statement  # No corruption applied

    def _build_tf_explanation(
        self, context: str, concept: str, answer: str, statement: str
    ) -> str:
        """Build an explanation for a True/False question."""
        sentences = re.split(r"[.!?]", context)
        relevant = [
            s.strip() for s in sentences
            if concept.lower() in s.lower() and len(s.strip()) > 20
        ]
        if relevant:
            evidence = ". ".join(relevant[:2]).strip()
            if not evidence.endswith("."):
                evidence += "."
        else:
            evidence = context[:300].strip()
            if not evidence.endswith("."):
                evidence += "."

        if answer == "True":
            return (
                f"This statement is TRUE.\n\n"
                f"According to the lecture material: {evidence}\n\n"
                f"Concept: {concept}"
            )
        else:
            return (
                f"This statement is FALSE.\n\n"
                f"The lecture material actually states: {evidence}\n\n"
                f"The statement contains an error that contradicts "
                f"the source material.\n\n"
                f"Concept: {concept}"
            )

    # ================================================================
    # Short Answer Generation
    # ================================================================

    def _generate_short_answer(
        self, difficulty, concept, related, context, text, all_concepts, kg
    ) -> Optional[Dict]:
        """Generate a short-answer question via API or local fallback."""
        if self._provider in ("openai", "gemini"):
            result = self._api_generate_sa(difficulty, concept, related, context)
            if result:
                result["type"] = "short_answer"
                return result

        result = self._local_generate_sa(difficulty, concept, related, context, text)
        if result:
            result["type"] = "short_answer"
        return result

    def _api_generate_sa(self, difficulty, concept, related, context) -> Optional[Dict]:
        """Use API to generate a short-answer question."""
        bloom = DifficultyController.get_bloom_info(difficulty)
        taxonomy = bloom["taxonomy"]
        verbs = ", ".join(random.sample(bloom["verbs"], min(3, len(bloom["verbs"]))))

        doc_ctx = getattr(self, "_doc_summary", "")
        doc_block = f"\n{doc_ctx}\n\n" if doc_ctx else ""

        if difficulty.lower() == "easy":
            diff_detail = (
                f"Ask a straightforward question that requires the student to "
                f"{verbs} — recalling a definition, fact, or key characteristic."
            )
        elif difficulty.lower() == "medium":
            rel_part = f" You may reference '{related}'." if related else ""
            diff_detail = (
                f"Ask a question that requires the student to {verbs} — "
                f"explaining a relationship, process, or comparison.{rel_part}"
            )
        else:
            diff_detail = (
                f"Ask a question that requires the student to {verbs} — "
                f"analyzing a scenario, evaluating trade-offs, or predicting outcomes."
            )

        prompt = (
            "You are an expert educational assessment designer.\n\n"
            "Generate ONE short-answer question from the lecture content below.\n"
            "The answer should be 1-3 sentences long.\n\n"
            f"{doc_block}"
            f"SPECIFIC SECTION ON '{concept}':\n{context[:2000]}\n\n"
            f"TOPIC: {concept}\n"
            f"DIFFICULTY: {difficulty.upper()} (Bloom's Taxonomy: {taxonomy})\n\n"
            f"INSTRUCTIONS:\n{diff_detail}\n\n"
            "QUALITY RULES:\n"
            "- The question must be clear and have a definite correct answer\n"
            "- The answer should require understanding, not just copying text\n"
            "- Provide keywords that MUST appear in a correct answer\n\n"
            "FORMAT (follow exactly):\n"
            "QUESTION: <question text?>\n"
            "ANSWER: <expected answer, 1-3 sentences>\n"
            "KEYWORDS: <comma-separated key terms that should appear in answer>\n"
            "EXPLANATION: <why this is the correct answer>"
        )

        raw = self._call_api(prompt)
        return self._parse_sa_response(raw, context, concept)

    def _local_generate_sa(
        self, difficulty, concept, related, context, text
    ) -> Optional[Dict]:
        """Generate short-answer via local model or rule-based extraction."""
        bloom = DifficultyController.get_bloom_info(difficulty)
        verb = random.choice(bloom["verbs"])

        # Try T5
        if self._t5_model is not None:
            q_prompt = (
                f"Generate a short-answer question about \"{concept}\" that "
                f"requires the student to {verb}.\n\n"
                f"Context: {context[:400]}\n\nQuestion:"
            )
            question = self._t5_generate(q_prompt, max_length=100)
            if question and len(question.strip()) > 10:
                question = question.strip()
                if not question.endswith("?"):
                    question += "?"

                # Get answer
                a_prompt = (
                    f"Answer the question based on the context.\n\n"
                    f"Context: {context[:400]}\n\n"
                    f"Question: {question}\n\nAnswer:"
                )
                answer = self._t5_generate(a_prompt, max_length=120)
                if answer and len(answer.strip()) > 5:
                    keywords = self._extract_keywords_from_answer(answer, concept)
                    return {
                        "question": question,
                        "correct_answer": answer.strip(),
                        "keywords": keywords,
                        "options": [],
                        "explanation": self._build_sa_explanation(
                            context, concept, answer.strip()
                        ),
                    }

        # Rule-based fallback
        return self._rule_based_sa(difficulty, concept, related, context)

    def _rule_based_sa(self, difficulty, concept, related, context) -> Optional[Dict]:
        """Generate a short-answer question using Bloom's templates."""
        if difficulty.lower() == "easy":
            templates = [
                f"Define {concept} in your own words.",
                f"What is {concept} and why is it important?",
                f"Briefly explain the concept of {concept}.",
                f"What is the primary purpose of {concept}?",
                f"List the key characteristics of {concept}.",
            ]
        elif difficulty.lower() == "medium":
            rel_part = related or "related concepts"
            templates = [
                f"Explain how {concept} relates to {rel_part}.",
                f"What is the difference between {concept} and {rel_part}?",
                f"Describe a scenario where {concept} would be applied.",
                f"Why is {concept} important in the context of {rel_part}?",
                f"Explain the cause-and-effect relationship involving {concept}.",
            ]
        else:
            templates = [
                f"Evaluate the importance of {concept} and justify your reasoning.",
                f"What would happen if {concept} were removed from this system?",
                f"Critically assess: Under what conditions might {concept} fail?",
                f"Design an approach that leverages {concept} to solve a real problem.",
                f"Compare and contrast different approaches to {concept}.",
            ]

        question = random.choice(templates)
        answer = self._extract_answer_from_context(context, concept, question)
        if not answer or len(answer.strip()) < 5:
            return None

        keywords = self._extract_keywords_from_answer(answer, concept)
        return {
            "question": question,
            "correct_answer": answer.strip(),
            "keywords": keywords,
            "options": [],
            "explanation": self._build_sa_explanation(context, concept, answer.strip()),
        }

    def _extract_keywords_from_answer(self, answer: str, concept: str) -> List[str]:
        """Extract key terms from the correct answer for grading short answers."""
        # Always include the concept itself
        keywords = [concept.lower()]

        # Extract significant words (> 3 chars, not stopwords)
        stopwords = {
            "the", "and", "for", "with", "that", "this", "from", "into",
            "which", "where", "when", "what", "does", "have", "been", "were",
            "they", "their", "them", "about", "also", "more", "most", "some",
            "other", "than", "then", "very", "just", "only",
        }
        words = re.findall(r"\b[a-zA-Z]{4,}\b", answer.lower())
        for w in words:
            if w not in stopwords and w not in keywords:
                keywords.append(w)
            if len(keywords) >= 6:
                break

        return keywords

    def _build_sa_explanation(self, context: str, concept: str, answer: str) -> str:
        """Build an explanation for a short-answer question."""
        sentences = re.split(r"[.!?]", context)
        relevant = [
            s.strip() for s in sentences
            if concept.lower() in s.lower() and len(s.strip()) > 20
        ]
        if relevant:
            evidence = ". ".join(relevant[:2]).strip()
            if not evidence.endswith("."):
                evidence += "."
        else:
            evidence = context[:300].strip()
            if not evidence.endswith("."):
                evidence += "."

        display = (answer[:200] + "...") if len(answer) > 200 else answer
        return (
            f"Expected answer: {display}\n\n"
            f"Key information from the material: {evidence}\n\n"
            f"Concept: {concept}"
        )

    def _parse_sa_response(self, raw: Optional[str], context: str, concept: str) -> Optional[Dict]:
        """Parse API response for short-answer format."""
        if not raw or len(raw) < 20:
            return None

        q_m = re.search(r"QUESTION:\s*(.+?)(?=\n\s*ANSWER:)", raw, re.DOTALL | re.IGNORECASE)
        if not q_m:
            return None
        question = q_m.group(1).strip()

        a_m = re.search(r"ANSWER:\s*(.+?)(?=\n\s*(?:KEYWORDS|EXPLANATION):)", raw, re.DOTALL | re.IGNORECASE)
        if not a_m:
            a_m = re.search(r"ANSWER:\s*(.+?)$", raw, re.DOTALL | re.IGNORECASE)
        if not a_m:
            return None
        answer = a_m.group(1).strip()

        # Extract keywords
        keywords = [concept.lower()]
        k_m = re.search(r"KEYWORDS:\s*(.+?)(?=\n\s*EXPLANATION:)", raw, re.DOTALL | re.IGNORECASE)
        if k_m:
            kw_text = k_m.group(1).strip()
            for kw in re.split(r"[,;]", kw_text):
                kw = kw.strip().lower()
                if kw and len(kw) > 2 and kw not in keywords:
                    keywords.append(kw)

        # Explanation
        explanation = ""
        e_m = re.search(r"EXPLANATION:\s*(.+)", raw, re.DOTALL | re.IGNORECASE)
        if e_m:
            explanation = e_m.group(1).strip().split("\n")[0]

        return {
            "question": question,
            "correct_answer": answer,
            "keywords": keywords,
            "options": [],
            "explanation": explanation or self._build_sa_explanation(context, concept, answer),
        }

    def _parse_tf_response(self, raw: Optional[str]) -> Optional[Dict]:
        """Parse API response for True/False format."""
        if not raw or len(raw) < 15:
            return None

        s_m = re.search(r"STATEMENT:\s*(.+?)(?=\n\s*ANSWER:)", raw, re.DOTALL | re.IGNORECASE)
        if not s_m:
            return None
        statement = s_m.group(1).strip()

        a_m = re.search(r"ANSWER:\s*(True|False)", raw, re.IGNORECASE)
        if not a_m:
            return None
        answer = a_m.group(1).capitalize()

        explanation = ""
        e_m = re.search(r"EXPLANATION:\s*(.+)", raw, re.DOTALL | re.IGNORECASE)
        if e_m:
            explanation = e_m.group(1).strip().split("\n")[0]

        return {
            "question": statement,
            "correct_answer": answer,
            "options": [],
            "explanation": explanation or f"The statement is {answer}.",
        }

    # ================================================================
    # API helpers
    # ================================================================

    def _call_api(self, prompt: str) -> Optional[str]:
        if self._provider == "openai":
            return self._call_openai(prompt)
        if self._provider == "gemini":
            return self._call_gemini(prompt)
        return None

    def _call_openai(self, prompt: str) -> Optional[str]:
        try:
            model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
            resp = self._openai_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a university-level exam question designer. "
                            "You write questions that test genuine understanding "
                            "and logical reasoning — never trivia or pattern matching. "
                            "Your wrong options always target common student "
                            "misconceptions. Follow the requested format exactly."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.75,
                max_tokens=600,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[QuestionGen] OpenAI error: {exc}")
            return None

    def _call_gemini(self, prompt: str) -> Optional[str]:
        try:
            resp = self._gemini_model.generate_content(
                prompt,
                generation_config={"temperature": 0.7, "max_output_tokens": 500},
            )
            return resp.text.strip()
        except Exception as exc:
            print(f"[QuestionGen] Gemini error: {exc}")
            return None

    # ================================================================
    # Local (FLAN-T5) Generation — multi-step approach
    # ================================================================

    def _local_generate_mcq(
        self, difficulty, concept, related, context, text, all_concepts, kg
    ) -> Optional[Dict]:
        """
        Multi-step local generation:
          1. Try complete MCQ prompt (sometimes works with larger models)
          2. Generate question → answer → distractors separately
        """
        mcq = self._local_try_complete(difficulty, concept, related, context)
        if mcq:
            return mcq

        mcq = self._local_try_multistep(
            difficulty, concept, related, context, all_concepts, kg
        )
        return mcq

    def _local_try_complete(
        self, difficulty, concept, related, context
    ) -> Optional[Dict]:
        """Attempt complete MCQ generation with FLAN-T5."""
        bloom = DifficultyController.get_bloom_info(difficulty)
        verb = random.choice(bloom["verbs"])
        doc_hint = ""
        raw_summary = getattr(self, "_doc_summary", "")
        if raw_summary:
            topic_line = raw_summary.split("\n")[0][:200]
            doc_hint = f"{topic_line}\n\n"
        prompt = (
            f"{doc_hint}"
            f"You are an exam question writer. Create a {difficulty} difficulty "
            f"multiple choice question about \"{concept}\" that requires the "
            f"student to {verb}. Provide 4 options (A, B, C, D) where only one "
            f"is correct and the wrong options represent common misconceptions. "
            f"Include the correct answer letter and a brief explanation.\n\n"
            f"Context: {context[:500]}\n\n"
            f"QUESTION:"
        )
        raw = self._t5_generate(prompt, max_length=300)
        if not raw:
            return None
        return self._parse_mcq_response("QUESTION: " + raw)

    def _local_try_multistep(
        self, difficulty, concept, related, context, all_concepts, kg
    ) -> Optional[Dict]:
        """Generate question, answer, and distractors in separate model calls."""
        bloom = DifficultyController.get_bloom_info(difficulty)
        verb = random.choice(bloom["verbs"])

        # ── Step A: Generate question text ──
        if difficulty.lower() == "easy":
            q_prompt = (
                f"Based on the following passage, generate a clear educational "
                f"question that tests whether a student can {verb} the concept "
                f'of "{concept}". The question should require understanding, '
                f"not just keyword recognition.\n\n"
                f"Passage: {context[:500]}\n\n"
                f"Question:"
            )
        elif difficulty.lower() == "medium":
            rel_part = f' and relate it to "{related}"' if related else ""
            q_prompt = (
                f"Based on the following passage, generate an analytical question "
                f"that requires a student to {verb} the concept of "
                f'"{concept}"{rel_part}. The question should test reasoning '
                f"about cause-effect or comparison, not just recall.\n\n"
                f"Passage: {context[:500]}\n\n"
                f"Question:"
            )
        else:
            q_prompt = (
                f"Based on the following passage, generate a challenging question "
                f"that presents a realistic scenario and requires a student to "
                f'{verb} and think critically about "{concept}". The student '
                f"must evaluate or predict an outcome.\n\n"
                f"Passage: {context[:500]}\n\n"
                f"Question:"
            )

        question = self._t5_generate(q_prompt, max_length=128)
        if not question or len(question) < 10:
            return None
        question = question.strip()
        if not question.endswith("?"):
            question += "?"

        # ── Step B: Extract correct answer via QA prompt ──
        a_prompt = (
            f"Answer the question based on the context.\n\n"
            f"Context: {context[:500]}\n\n"
            f"Question: {question}\n\nAnswer:"
        )
        answer = self._t5_generate(a_prompt, max_length=100)
        if not answer or len(answer.strip()) < 3:
            answer = self._extract_answer_from_context(context, concept, question)
        if not answer or len(answer.strip()) < 3:
            return None
        answer = answer.strip()

        # Truncate overly long answers
        if len(answer) > 200:
            cut = answer[:200].rfind(".")
            answer = answer[: cut + 1] if cut > 50 else answer[:200]

        # ── Step C: Generate distractors ──
        distractors = self._generate_local_distractors(
            question, answer, concept, context, all_concepts, kg
        )
        if len(distractors) < 3:
            return None

        return self._assemble_mcq(question, answer, distractors, context, concept)

    def _generate_local_distractors(
        self, question, answer, concept, context, all_concepts, kg
    ) -> List[str]:
        """
        Try to generate distractors with the model first,
        then fall back to the distractor sub-module.
        """
        model_distractors: List[str] = []

        if self._t5_model is not None:
            d_prompt = (
                f"A student is answering: {question}\n"
                f"The correct answer is: {answer}\n\n"
                f"Generate 3 wrong answers that represent common student "
                f"misconceptions. Each wrong answer should be plausible "
                f"and from the same domain but clearly incorrect.\n\n"
                f"Context: {context[:300]}\n\n"
                f"Wrong answers:"
            )
            raw = self._t5_generate(d_prompt, max_length=150)
            if raw:
                parts = re.split(r"[,\n;]|\d+[.)]\s*", raw)
                for p in parts:
                    p = p.strip().strip("-").strip()
                    if (
                        p
                        and len(p) > 3
                        and p.lower() != answer.lower()
                        and p.lower() != concept.lower()
                    ):
                        model_distractors.append(p)

        if len(model_distractors) >= 3:
            return model_distractors[:3]

        sub_distractors = self._distractors.generate(
            correct_answer=answer,
            concept=concept,
            all_concepts=all_concepts,
            knowledge_graph=kg,
            context=context,
            count=3 - len(model_distractors),
        )
        return (model_distractors + sub_distractors)[:3]

    def _t5_generate(self, prompt: str, max_length: int = 200) -> Optional[str]:
        """Low-level FLAN-T5 generation."""
        if self._t5_model is None:
            self._load_local_model()
        if self._t5_model is None:
            return None
        try:
            import torch

            inputs = self._t5_tokenizer(
                prompt, return_tensors="pt", max_length=512, truncation=True
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = self._t5_model.generate(
                    **inputs,
                    max_length=max_length,
                    num_beams=5,
                    no_repeat_ngram_size=3,
                    early_stopping=True,
                )
            return (
                self._t5_tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
            )
        except Exception as exc:
            print(f"[QuestionGen] T5 generation error: {exc}")
            return None

    # ================================================================
    # Rule-based MCQ fallback (last resort)
    # ================================================================

    def _rule_based_mcq(
        self, difficulty, concept, related, context, text, all_concepts, kg
    ) -> Optional[Dict]:
        """Generate MCQ using Bloom's templates + distractor sub-module."""
        question = DifficultyController.get_question_stem(
            difficulty, concept, related, context
        )
        if not question:
            return None

        answer = self._extract_answer_from_context(context, concept, question)
        if not answer or len(answer.strip()) < 3:
            return None

        distractors = self._distractors.generate(
            correct_answer=answer,
            concept=concept,
            all_concepts=all_concepts,
            knowledge_graph=kg,
            context=context,
            count=3,
        )
        if len(distractors) < 3:
            return None

        return self._assemble_mcq(question, answer, distractors, context, concept)

    # ================================================================
    # Shared helpers
    # ================================================================

    @staticmethod
    def _strip_option_label(text: str) -> str:
        """Remove leading letter labels like 'A. ', 'A) ', 'a. ' from option text."""
        return re.sub(r'^[A-Da-d][.):]\s*', '', text.strip())

    def _assemble_mcq(
        self,
        question: str,
        correct: str,
        distractors: List[str],
        context: str,
        concept: str,
    ) -> Dict:
        """Shuffle options, assign letters, build final MCQ dict.

        Options are stored as PLAIN TEXT without letter prefixes.
        The UI templates add their own A/B/C/D labels.
        """
        correct_clean = self._strip_option_label(correct)
        dist_clean = [self._strip_option_label(d) for d in distractors[:3]]

        raw = [correct_clean] + dist_clean
        random.shuffle(raw)
        idx = raw.index(correct_clean)
        letter = _LETTERS[idx]
        explanation = self._build_explanation(context, concept, correct_clean)
        return {
            "question": question,
            "options": raw,
            "correct_answer": letter,
            "explanation": explanation,
        }

    def _extract_answer_from_context(
        self, context: str, concept: str, question: str
    ) -> Optional[str]:
        """Extract a correct answer from context using heuristics + similarity."""
        q_lower = question.lower()
        sentences = [
            s.strip() for s in re.split(r"[.!?]", context) if len(s.strip()) > 15
        ]

        # ── Definition questions ──
        if any(
            kw in q_lower
            for kw in ("what is", "define", "definition", "describes", "refers to")
        ):
            for s in sentences:
                if concept.lower() in s.lower():
                    m = re.search(
                        rf"{re.escape(concept)}\s+(?:is|refers to|means|defined as)\s+(.+)",
                        s,
                        re.IGNORECASE,
                    )
                    if m:
                        return m.group(1).strip()[:200]

        # ── Purpose questions ──
        if any(kw in q_lower for kw in ("why", "purpose", "used for")):
            for s in sentences:
                if concept.lower() in s.lower() and any(
                    w in s.lower()
                    for w in ("used for", "purpose", "helps", "enables", "allows")
                ):
                    return s[:200]

        # ── Process / how questions ──
        if any(kw in q_lower for kw in ("how", "process", "method", "work")):
            for s in sentences:
                if concept.lower() in s.lower() and any(
                    w in s.lower() for w in ("process", "step", "method", "by")
                ):
                    return s[:200]

        # ── Sentence-similarity fallback ──
        self._mapper._load_sentence_model()
        if self._mapper._sentence_model is not None:
            try:
                import numpy as np

                relevant = [s for s in sentences if len(s) > 20]
                if relevant:
                    embs = self._mapper._sentence_model.encode(
                        [question] + relevant
                    )
                    q_emb = embs[0]
                    best, best_sim = relevant[0], -1.0
                    for i, s in enumerate(relevant):
                        sim = float(
                            np.dot(q_emb, embs[i + 1])
                            / (
                                np.linalg.norm(q_emb)
                                * np.linalg.norm(embs[i + 1])
                                + 1e-9
                            )
                        )
                        if sim > best_sim:
                            best_sim = sim
                            best = s
                    return best[:250]
            except Exception:
                pass

        # ── Last resort ──
        relevant = [s for s in sentences if concept.lower() in s.lower()]
        if relevant:
            return max(relevant, key=len)[:250]
        return context[:150].strip() if context else None

    def _build_explanation(
        self, context: str, concept: str, answer: str
    ) -> str:
        """Build a pedagogically useful explanation for the correct answer."""
        sentences = re.split(r"[.!?]", context)
        relevant = [
            s.strip()
            for s in sentences
            if concept.lower() in s.lower() and len(s.strip()) > 20
        ]
        if relevant:
            info = ". ".join(relevant[:2]).strip()
            if not info.endswith("."):
                info += "."
        else:
            info = context[:300].strip()
            if not info.endswith("."):
                info += "."

        display = (answer[:180] + "...") if len(answer) > 180 else answer
        return (
            f"The correct answer is: {display}\n\n"
            f"Key reasoning: {info}\n\n"
            f"Concept: {concept}"
        )

    # ================================================================
    # MCQ Response parsers (multi-strategy)
    # ================================================================

    def _parse_mcq_response(self, raw: Optional[str]) -> Optional[Dict]:
        """Try multiple parsing strategies to extract structured MCQ."""
        if not raw or len(raw) < 20:
            return None

        result = self._parse_structured(raw)
        if result:
            return result

        result = self._parse_json(raw)
        if result:
            return result

        result = self._parse_loose(raw)
        return result

    def _parse_structured(self, raw: str) -> Optional[Dict]:
        """Parse QUESTION: / A) B) C) D) / ANSWER: / EXPLANATION: format."""
        q_m = re.search(
            r"QUESTION:\s*(.+?)(?=\n\s*[A-D]\))",
            raw,
            re.DOTALL | re.IGNORECASE,
        )
        if not q_m:
            q_m = re.search(
                r"^(.+?\?)\s*\n\s*[A-D]\)", raw, re.DOTALL | re.MULTILINE
            )
        if not q_m:
            return None
        question = q_m.group(1).strip()

        opts: Dict[str, str] = {}
        for letter in _LETTERS:
            pat = (
                rf"{letter}\)\s*(.+?)"
                rf"(?=\n\s*[A-D]\)|\n\s*(?:ANSWER|CORRECT|EXPLANATION):|$)"
            )
            m = re.search(pat, raw, re.DOTALL | re.IGNORECASE)
            if m:
                opts[letter] = m.group(1).strip()
        if len(opts) != 4:
            return None

        a_m = re.search(r"(?:ANSWER|CORRECT):\s*([A-Da-d])", raw, re.IGNORECASE)
        if not a_m:
            return None
        letter = a_m.group(1).upper()
        if letter not in opts:
            return None

        e_m = re.search(r"EXPLANATION:\s*(.+)", raw, re.DOTALL | re.IGNORECASE)
        explanation = ""
        if e_m:
            explanation = e_m.group(1).strip().split("\n")[0]

        clean_opts = [self._strip_option_label(opts[l]) for l in _LETTERS]
        return {
            "question": question,
            "options": clean_opts,
            "correct_answer": letter,
            "explanation": explanation
            or f"The correct answer is {letter}. {opts.get(letter, '')}",
        }

    def _parse_json(self, raw: str) -> Optional[Dict]:
        """Parse JSON-formatted response."""
        try:
            m = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
            if not m:
                return None
            data = json.loads(m.group())

            q = data.get("question", "")
            options = data.get("options", [])
            correct = data.get("correct_answer", data.get("answer", ""))
            explanation = data.get("explanation", "")

            if not q or len(options) != 4 or not correct:
                return None

            clean_opts = [self._strip_option_label(str(opt)) for opt in options]

            c = correct.strip().upper()
            if len(c) > 1:
                c = c[0]
            if c not in _LETTERS:
                return None

            return {
                "question": q,
                "options": clean_opts,
                "correct_answer": c,
                "explanation": explanation,
            }
        except (json.JSONDecodeError, KeyError):
            return None

    def _parse_loose(self, raw: str) -> Optional[Dict]:
        """Last-resort loose parsing for varied formats."""
        lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
        if len(lines) < 5:
            return None

        question = None
        opt_start = 0
        for i, line in enumerate(lines):
            clean = re.sub(
                r"^(?:QUESTION|Q):\s*", "", line, flags=re.IGNORECASE
            ).strip()
            if clean.endswith("?"):
                question = clean
                opt_start = i + 1
                break
        if not question:
            question = lines[0].strip()
            if not question.endswith("?"):
                question += "?"
            opt_start = 1

        opts: Dict[str, str] = {}
        for line in lines[opt_start:]:
            m = re.match(r"^([A-Da-d])[.)]\s*(.+)", line)
            if m:
                opts[m.group(1).upper()] = m.group(2).strip()
        if len(opts) < 4:
            return None

        letter = None
        for line in lines:
            m = re.search(
                r"(?:answer|correct)[:\s]+([A-Da-d])", line, re.IGNORECASE
            )
            if m:
                letter = m.group(1).upper()
                break
        if not letter or letter not in opts:
            return None

        explanation = ""
        for line in lines:
            m = re.search(
                r"(?:explanation|reason)[:\s]+(.+)", line, re.IGNORECASE
            )
            if m:
                explanation = m.group(1).strip()
                break

        clean_opts = [self._strip_option_label(opts[l]) for l in _LETTERS if l in opts]
        return {
            "question": question,
            "options": clean_opts[:4],
            "correct_answer": letter,
            "explanation": explanation or f"The correct answer is {letter}.",
        }

