"""
Concept Mapper – links every generated question to a concept node in the
Knowledge Graph and provides concept-level utilities.

Responsibilities
────────────────
1. Map a question → concept → difficulty   (the required triple).
2. Cache concept embeddings so repeated lookups are O(1).
3. Find the best context window for a concept from the full document.
4. Provide a related-concept lookup used by the distractor generator and
   the difficulty controller.
5. Detect duplicate / near-duplicate questions via embedding similarity.
"""

from __future__ import annotations
import re
import random
from typing import Dict, List, Optional, Tuple


class ConceptMapper:
    """Maps questions to Knowledge-Graph concepts with cached embeddings."""

    def __init__(self):
        self._sentence_model = None
        self._model_attempted = False
        # Cache: concept_name (lower) → embedding vector
        self._embedding_cache: Dict[str, object] = {}
        # Cache: concept_name (lower) → best context string
        self._context_cache: Dict[str, str] = {}

    # ──────────────────────────────────────────────────────────
    # Public helpers
    # ──────────────────────────────────────────────────────────

    def build_concept_index(self, concepts: List[Dict], text: str) -> None:
        """
        Pre-compute and cache:
        • The best context window for every concept.
        • Sentence-transformer embeddings for every concept name (if available).

        Call this ONCE before generating questions to keep generation fast.
        """
        # Context cache
        for c in concepts:
            name = c["name"]
            key = name.lower()
            if key not in self._context_cache:
                ctx = c.get("context") or self._find_context(text, name)
                self._context_cache[key] = ctx

        # Embedding cache
        self._load_sentence_model()
        if self._sentence_model is not None:
            try:
                names = [c["name"] for c in concepts]
                embeddings = self._sentence_model.encode(names)
                for name, emb in zip(names, embeddings):
                    self._embedding_cache[name.lower()] = emb
            except Exception:
                pass  # embeddings are optional

    def get_context(self, text: str, concept_name: str, size: int = 1500) -> str:
        """Return cached context or compute it on the fly."""
        key = concept_name.lower()
        if key in self._context_cache:
            return self._context_cache[key]
        ctx = self._find_context(text, concept_name, size)
        self._context_cache[key] = ctx
        return ctx

    def get_related_concepts(
        self,
        concept_name: str,
        all_concepts: List[Dict],
        knowledge_graph: Dict,
        top_k: int = 5,
    ) -> List[str]:
        """
        Return names of related concepts via:
        1. Knowledge-graph 1-hop neighbours (preferred).
        2. Embedding similarity fallback.
        """
        related: List[str] = []

        # ── 1. KG neighbours ──
        nodes = knowledge_graph.get("nodes", [])
        edges = knowledge_graph.get("edges", [])

        node_id = None
        id_to_label: Dict[str, str] = {}
        for n in nodes:
            id_to_label[n["id"]] = n["label"]
            if n["label"].lower() == concept_name.lower():
                node_id = n["id"]

        if node_id:
            neighbours: set = set()
            for e in edges:
                if e["from"] == node_id:
                    neighbours.add(e["to"])
                elif e["to"] == node_id:
                    neighbours.add(e["from"])
            for nid in neighbours:
                label = id_to_label.get(nid, "")
                if label and label.lower() != concept_name.lower():
                    related.append(label)

        if len(related) >= top_k:
            return related[:top_k]

        # ── 2. Embedding similarity fallback ──
        self._load_sentence_model()
        if self._sentence_model is not None:
            try:
                import numpy as np

                target_emb = self._embedding_cache.get(concept_name.lower())
                if target_emb is None:
                    target_emb = self._sentence_model.encode([concept_name])[0]

                scored = []
                for c in all_concepts:
                    name = c["name"]
                    if name.lower() == concept_name.lower() or name in related:
                        continue
                    emb = self._embedding_cache.get(name.lower())
                    if emb is None:
                        emb = self._sentence_model.encode([name])[0]
                    sim = float(
                        np.dot(target_emb, emb)
                        / (np.linalg.norm(target_emb) * np.linalg.norm(emb) + 1e-9)
                    )
                    scored.append((name, sim))
                scored.sort(key=lambda x: x[1], reverse=True)
                for name, _ in scored[: top_k - len(related)]:
                    related.append(name)
            except Exception:
                pass

        return related[:top_k]

    # ──────────────────────────────────────────────────────────
    # Duplicate / similarity detection
    # ──────────────────────────────────────────────────────────

    def is_duplicate_question(
        self,
        new_question: str,
        existing_questions: List[str],
        threshold: float = 0.88,
    ) -> bool:
        """Return True if *new_question* is semantically too close to any existing one."""
        if not existing_questions:
            return False

        self._load_sentence_model()
        if self._sentence_model is None:
            # Fallback: exact-string check
            new_lower = new_question.lower().strip()
            return any(new_lower == q.lower().strip() for q in existing_questions)

        try:
            import numpy as np

            all_texts = [new_question] + existing_questions
            embeddings = self._sentence_model.encode(all_texts)
            new_emb = embeddings[0]

            for i in range(1, len(embeddings)):
                sim = float(
                    np.dot(new_emb, embeddings[i])
                    / (np.linalg.norm(new_emb) * np.linalg.norm(embeddings[i]) + 1e-9)
                )
                if sim > threshold:
                    return True
            return False
        except Exception:
            return False

    def build_question_concept_map(
        self,
        questions: List[Dict],
    ) -> Dict[str, Dict]:
        """
        Return a mapping:  question_id → { concept, difficulty }
        fulfilling the required   question → concept → difficulty   triple.
        """
        return {
            q.get("id", f"q_{i}"): {
                "concept": q.get("concept", "General"),
                "difficulty": q.get("difficulty", "medium"),
            }
            for i, q in enumerate(questions)
        }

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    def _find_context(self, text: str, concept_name: str, size: int = 1500) -> str:
        """Find the most informative context window for *concept_name* in *text*."""
        if not text:
            return ""

        contexts: List[str] = []

        # Direct mentions
        pattern = re.compile(re.escape(concept_name), re.IGNORECASE)
        for m in list(pattern.finditer(text))[:3]:
            start = max(0, m.start() - size // 2)
            end = min(len(text), m.end() + size // 2)
            contexts.append(text[start:end].strip())

        # Word-level fallback
        if not contexts:
            for word in concept_name.split():
                if len(word) <= 3:
                    continue
                pat = re.compile(re.escape(word), re.IGNORECASE)
                m = pat.search(text)
                if m:
                    start = max(0, m.start() - size // 3)
                    end = min(len(text), m.end() + size // 3)
                    contexts.append(text[start:end].strip())
                    break

        if contexts:
            return max(contexts, key=len)

        # Absolute fallback: beginning of the text
        return text[:size]

    def _load_sentence_model(self):
        if self._sentence_model is not None or self._model_attempted:
            return
        self._model_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            self._sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            self._sentence_model = None
