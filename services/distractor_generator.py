"""Distractor Generator – produce plausible, conceptually-related wrong answers.

Contributor note
───────────────
Krish Thakkar contributed to the embedding-based distractor selection and the
semantic de-duplication pass that keeps options distinct (so learners see
plausible *alternatives*, not near-duplicates).

Design goals
────────────
1. Distractors come from the SAME topic cluster (never random noise).
2. Each distractor is semantically distinct from the correct answer AND from
   the other distractors (checked via embeddings when available).
3. Multiple strategies are layered: knowledge-graph neighbours → embedding
   similarity → context-derived phrases → rule-based fallbacks.  Each layer
   only fires when the previous one didn't produce enough candidates.
4. "Obviously wrong" options (e.g. "None of the above") are only used as a
   last resort.
"""

from __future__ import annotations
import random
import re
from typing import Dict, List, Optional

# Similarity ceiling – any candidate above this is treated as a near-duplicate.
# We keep this fairly strict so the final options don't feel like the same
# answer rephrased.
_SIM_THRESHOLD = 0.82


class DistractorGenerator:
    """Generate exactly 3 high-quality distractors for a given MCQ."""

    def __init__(self):
        self._sentence_model = None
        self._model_attempted = False

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def generate(
        self,
        correct_answer: str,
        concept: str,
        all_concepts: List[Dict],
        knowledge_graph: Dict,
        context: str,
        count: int = 3,
    ) -> List[str]:
        """
        Think of this as trying different idea buckets until we have enough good wrong answers:
        Step 1: Look at the Knowledge Graph (things directly related to the concept). Let's see if any of its neighbors make good wrong answers.
        Step 2: Look at Embeddings (things that mean something similar). If step 1 didn't give us enough, we find ideas that are mathematically close.
        Step 3: Look at the Context (the text around the concept). If we're still short, grab plausible phrases from the text itself.
        Step 4: Semantic Deduplication. Make sure none of the answers mean the exact same thing or are too similar to the correct answer.
        Step 5: Rule-Based Fallback. If all else fails, use templates to fake a wrong answer (like swapping 'increases' with 'decreases').
        """
        if not correct_answer or not correct_answer.strip():
            return self._last_resort_distractors(concept, count)

        candidates: List[str] = []

        # Step 1: Knowledge Graph. Look at what concepts connect to our main concept.
        # This is great because it gives us distractors from the *same topic family* without doing heavy maths.
        candidates += self._from_knowledge_graph(
            concept, all_concepts, knowledge_graph, correct_answer
        )

        # Step 2: Embeddings. If we don't have enough options, use AI to find mathematically similar concepts.
        # This finds things that are close enough to be tricky, but mostly separate ideas.
        if len(candidates) < count * 2:
            candidates += self._from_embeddings(
                concept, all_concepts, correct_answer
            )

        # Step 3: Context phrases. Still not enough? Let's read the text around the concept itself
        # and grab sentences that sound plausible but aren't the correct answer.
        if len(candidates) < count * 2:
            candidates += self._from_context(context, concept, correct_answer)

        # Step 4: Quality Gate. We have lots of messy candidates now.
        # Let's filter out candidates that mean the same thing (e.g. "it gets bigger" and "it increases").
        unique = self._filter_unique(candidates, correct_answer, count)

        # Step 5: The Fallback. If we STILL don't have enough (maybe a tiny article?),
        # let's just manipulate the correct answer to make up a fake wrong one.
        if len(unique) < count:
            fallbacks = self._rule_based_fallback(
                correct_answer, concept, count - len(unique)
            )
            unique += fallbacks

        return unique[:count]

    # ──────────────────────────────────────────────────────────
    # Strategy 1 – Knowledge Graph neighbours
    # ──────────────────────────────────────────────────────────

    def _from_knowledge_graph(
        self,
        concept: str,
        all_concepts: List[Dict],
        knowledge_graph: Dict,
        correct_answer: str,
    ) -> List[str]:
        candidates: List[str] = []
        nodes = knowledge_graph.get("nodes", [])
        edges = knowledge_graph.get("edges", [])

        # Find the concept's node id
        concept_node_id = None
        for n in nodes:
            if n["label"].lower() == concept.lower():
                concept_node_id = n["id"]
                break

        if not concept_node_id:
            return candidates

        # Collect 1-hop neighbour labels
        neighbour_ids: set = set()
        for e in edges:
            if e["from"] == concept_node_id:
                neighbour_ids.add(e["to"])
            elif e["to"] == concept_node_id:
                neighbour_ids.add(e["from"])

        neighbour_labels = []
        for n in nodes:
            if n["id"] in neighbour_ids and n["label"].lower() != concept.lower():
                neighbour_labels.append(n["label"])

        # For each neighbour, try to find a short descriptive phrase from concepts list
        concept_lookup = {c["name"].lower(): c for c in all_concepts}
        for label in neighbour_labels:
            desc = concept_lookup.get(label.lower(), {}).get("context", "")
            if desc and len(desc) > 10:
                # Extract a sentence-length chunk
                sentence = self._first_sentence(desc)
                if sentence and sentence.lower() != correct_answer.lower():
                    candidates.append(sentence)
            else:
                # Use the label itself as distractor text
                if label.lower() != correct_answer.lower():
                    candidates.append(label)

        random.shuffle(candidates)
        return candidates[:6]

    # ──────────────────────────────────────────────────────────
    # Strategy 2 – Embedding similarity
    # ──────────────────────────────────────────────────────────

    def _from_embeddings(
        self,
        concept: str,
        all_concepts: List[Dict],
        correct_answer: str,
    ) -> List[str]:
        self._load_sentence_model()
        if self._sentence_model is None:
            return []

        try:
            import numpy as np

            other_concepts = [
                c for c in all_concepts if c["name"].lower() != concept.lower()
            ]
            if not other_concepts:
                return []

            names = [c["name"] for c in other_concepts]
            embeddings = self._sentence_model.encode([concept] + names)
            concept_emb = embeddings[0]

            scored = []
            for i, name in enumerate(names):
                sim = float(
                    np.dot(concept_emb, embeddings[i + 1])
                    / (np.linalg.norm(concept_emb) * np.linalg.norm(embeddings[i + 1]) + 1e-9)
                )
                scored.append((name, sim))

            # Pick moderately similar (0.25-0.80) — close enough to be plausible,
            # far enough to be wrong
            scored.sort(key=lambda x: x[1], reverse=True)
            candidates = [
                name
                for name, sim in scored
                if 0.20 < sim < 0.85
                and name.lower() != correct_answer.lower()
            ]
            return candidates[:6]
        except Exception:
            return []

    # ──────────────────────────────────────────────────────────
    # Strategy 3 – Context-derived phrases
    # ──────────────────────────────────────────────────────────

    def _from_context(
        self,
        context: str,
        concept: str,
        correct_answer: str,
    ) -> List[str]:
        """Extract plausible-sounding phrases from surrounding text."""
        if not context:
            return []

        sentences = [
            s.strip()
            for s in re.split(r"[.!?]", context)
            if len(s.strip()) > 15
        ]
        # Exclude sentences that are too similar to the correct answer
        candidates = []
        for s in sentences:
            s_clean = s.strip()
            if (
                s_clean.lower() != correct_answer.lower()
                and concept.lower() not in s_clean.lower()
                and len(s_clean) < 250
            ):
                candidates.append(s_clean)

        random.shuffle(candidates)
        return candidates[:6]

    # ──────────────────────────────────────────────────────────
    # Strategy 4 – Rule-based fallback
    # ──────────────────────────────────────────────────────────

    def _rule_based_fallback(
        self,
        correct_answer: str,
        concept: str,
        count: int,
    ) -> List[str]:
        """Generate plausible wrong answers via text manipulation.

        This is the last resort, so we try to produce answers that
        look structurally similar to the correct answer but contain
        a factual error.
        """
        results: List[str] = []
        words = correct_answer.split()

        # ── Strategy A: Flip key verbs/relationships ──
        if len(words) >= 3:
            flip_pairs = [
                ("involves", "does not involve"),
                ("is", "is not"),
                ("increases", "decreases"),
                ("decreases", "increases"),
                ("enables", "prevents"),
                ("prevents", "enables"),
                ("before", "after"),
                ("after", "before"),
                ("improves", "degrades"),
                ("supports", "conflicts with"),
                ("requires", "does not require"),
                ("allows", "restricts"),
                ("input", "output"),
                ("output", "input"),
                ("primary", "secondary"),
                ("first", "last"),
            ]
            for pos_word, neg_word in flip_pairs:
                if pos_word in correct_answer.lower() and len(results) < count:
                    variant = re.sub(
                        re.escape(pos_word), neg_word, correct_answer,
                        count=1, flags=re.IGNORECASE,
                    )
                    if variant.lower() != correct_answer.lower():
                        results.append(variant)

        # ── Strategy B: Shuffle key noun phrases ──
        if len(results) < count and len(words) >= 5:
            # Swap two content-word positions for a structurally similar but wrong answer
            content_indices = [
                i for i, w in enumerate(words)
                if len(w) > 3 and w.lower() not in {
                    "the", "and", "for", "with", "that", "this", "from",
                    "which", "where", "when", "what", "does", "have",
                }
            ]
            if len(content_indices) >= 2:
                shuffled = list(words)
                i, j = random.sample(content_indices, 2)
                shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
                variant = " ".join(shuffled)
                if variant.lower() != correct_answer.lower():
                    results.append(variant)

        # ── Strategy C: Truncate / partial truth ──
        if len(results) < count and len(words) >= 6:
            # Take first half — a partial truth that is incomplete
            mid = len(words) // 2
            partial = " ".join(words[:mid])
            if not partial.endswith("."):
                partial = partial.rstrip(",;:") + " only"
            if partial.lower() != correct_answer.lower():
                results.append(partial)

        # ── Strategy D: Concept-aware plausible alternatives ──
        # These are more specific than generic "unrelated to X" fillers
        if len(results) < count:
            specific_patterns = [
                f"{concept} combined with an unrelated process",
                f"An indirect effect of {concept} on external factors",
                f"{concept} applied in reverse order",
                f"A simplified version of {concept} without key constraints",
                f"The preprocessing step before {concept} begins",
                f"{concept} operating without any dependencies",
            ]
            random.shuffle(specific_patterns)
            for pat in specific_patterns:
                if len(results) >= count:
                    break
                results.append(pat)

        return results[:count]

    # ──────────────────────────────────────────────────────────
    # Semantic deduplication
    # ──────────────────────────────────────────────────────────

    def _filter_unique(
        self,
        candidates: List[str],
        correct_answer: str,
        count: int,
    ) -> List[str]:
        """
        Step 4 Details: Semantic Deduplication.
        This picks ONLY unique, distinct options so the user doesn't get 
        three answers that basically mean "It gets bigger."
        """
        if not candidates:
            return []

        self._load_sentence_model()

        if self._sentence_model is None:
            # Fallback: Just make sure the words aren't identical.
            seen_lower: set = {correct_answer.lower()}
            unique: List[str] = []
            for c in candidates:
                if c.lower() not in seen_lower:
                    seen_lower.add(c.lower())
                    unique.append(c)
                if len(unique) >= count:
                    break
            return unique

        try:
            import numpy as np

            # Step 4a: Let's turn all the possible answers into meaning vectors.
            all_texts = [correct_answer] + candidates
            embeddings = self._sentence_model.encode(all_texts)
            correct_emb = embeddings[0] # Meaning of the correct answer

            accepted: List[str] = []
            accepted_embs = []

            for i, cand in enumerate(candidates):
                cand_emb = embeddings[i + 1]

                # Step 4b: Wait, is this basically the correct answer?
                # Don't accidentally give them the correct answer disguised as a wrong one!
                sim_correct = float(
                    np.dot(correct_emb, cand_emb)
                    / (np.linalg.norm(correct_emb) * np.linalg.norm(cand_emb) + 1e-9)
                )
                if sim_correct > _SIM_THRESHOLD:
                    continue

                # Step 4c: Wait, is this basically the SAME exact wrong answer we already used?
                # We want 3 DIFFERENT wrong answers.
                too_similar = False
                for acc_emb in accepted_embs:
                    sim = float(
                        np.dot(cand_emb, acc_emb)
                        / (np.linalg.norm(cand_emb) * np.linalg.norm(acc_emb) + 1e-9)
                    )
                    if sim > _SIM_THRESHOLD:
                        too_similar = True
                        break

                if not too_similar:
                    accepted.append(cand)
                    accepted_embs.append(cand_emb)

                # Step 4d: Do we have enough yet? Let's stop looking.
                if len(accepted) >= count:
                    break

            return accepted
        except Exception:
            # Fallback
            seen_lower = {correct_answer.lower()}
            unique = []
            for c in candidates:
                if c.lower() not in seen_lower:
                    seen_lower.add(c.lower())
                    unique.append(c)
                if len(unique) >= count:
                    break
            return unique

    # ──────────────────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────────────────

    def _load_sentence_model(self):
        if self._sentence_model is not None or self._model_attempted:
            return
        self._model_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            self._sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            self._sentence_model = None

    @staticmethod
    def _first_sentence(text: str) -> str:
        """Return the first sentence (up to 200 chars)."""
        for sep in (".", "!", "?"):
            idx = text.find(sep)
            if 10 < idx < 200:
                return text[: idx + 1].strip()
        return text[:200].strip()

    @staticmethod
    def _last_resort_distractors(concept: str, count: int) -> List[str]:
        pool = [
            f"An indirect effect of {concept} on external factors",
            f"{concept} applied in reverse order",
            f"A simplified version of {concept} without key constraints",
            f"The preprocessing step before {concept} begins",
        ]
        random.shuffle(pool)
        return pool[:count]
