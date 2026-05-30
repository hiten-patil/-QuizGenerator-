"""
Concept Service - Extract concepts and build Knowledge Graph
This is a core AI component of the system.
"""
import re
from typing import List, Dict, Tuple, Set
from collections import defaultdict
import numpy as np


class ConceptService:
    """
    Service for extracting concepts from text and building a knowledge graph.
    
    Uses multiple NLP techniques:
    1. TF-IDF for important terms
    2. RAKE for keyphrase extraction
    3. KeyBERT for semantic keyphrases
    4. spaCy NER for named entities
    5. SBERT for semantic similarity between concepts
    """
    
    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        self._keybert = None
        self._sentence_model = None
        self._nlp = None
        self._rake = None
        
    def _load_models(self):
        """Lazy load NLP models"""
        if self._nlp is None:
            try:
                import spacy
                try:
                    self._nlp = spacy.load("en_core_web_sm")
                except OSError:
                    # Download if not available
                    import subprocess
                    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
                    self._nlp = spacy.load("en_core_web_sm")
            except ImportError:
                print("spaCy not installed. Some features will be limited.")
                self._nlp = None
    
    def _load_keybert(self):
        """Lazy load KeyBERT model"""
        if self._keybert is None:
            try:
                from keybert import KeyBERT
                self._keybert = KeyBERT()
            except ImportError:
                print("KeyBERT not installed. Using fallback extraction.")
                self._keybert = None
    
    def _load_sentence_model(self):
        """Lazy load sentence transformer model"""
        if self._sentence_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                model_name = "all-MiniLM-L6-v2"
                self._sentence_model = SentenceTransformer(model_name)
            except ImportError:
                print("sentence-transformers not installed.")
                self._sentence_model = None
    
    def extract_concepts(self, text: str, max_concepts: int = 50) -> List[Dict]:
        """
        Extract key concepts from text using multiple methods with aggressive fallbacks.
        Optimized for speed.
        
        Args:
            text: Input document text
            max_concepts: Maximum number of concepts to extract
            
        Returns:
            List of concept dictionaries with name, score, type, and context
        """
        if not text or len(text.strip()) < 20:
            return []

        concepts = []
        seen_concepts = set()
        
        # Limit text size for faster processing (use first 10000 chars + last 2000)
        if len(text) > 12000:
            text = text[:10000] + "\n...\n" + text[-2000:]
            print(f"[Concept Extraction] Text truncated to 12000 chars for faster processing")
        
        print(f"[Concept Extraction] Starting extraction from {len(text)} chars of text")
        
        # Method 1: TF-IDF extraction (FAST - run first)
        try:
            tfidf_concepts = self._extract_tfidf(text, top_n=max_concepts // 2)
            print(f"[Concept Extraction] TF-IDF found: {len(tfidf_concepts)} concepts")
            for concept, score in tfidf_concepts:
                if concept.lower() not in seen_concepts:
                    concepts.append({
                        'name': concept,
                        'score': score,
                        'type': 'keyword',
                        'source': 'tfidf'
                    })
                    seen_concepts.add(concept.lower())
        except Exception as e:
            print(f"[Concept Extraction] TF-IDF failed: {e}")
        
        # Method 2: RAKE extraction (FAST)
        try:
            rake_concepts = self._extract_rake(text, top_n=max_concepts // 3)
            print(f"[Concept Extraction] RAKE found: {len(rake_concepts)} concepts")
            for concept, score in rake_concepts:
                if concept.lower() not in seen_concepts:
                    concepts.append({
                        'name': concept,
                        'score': min(score / 10, 1.0),
                        'type': 'phrase',
                        'source': 'rake'
                    })
                    seen_concepts.add(concept.lower())
        except Exception as e:
            print(f"[Concept Extraction] RAKE failed: {e}")
        
        # Skip expensive methods if we already have enough good concepts
        if len(concepts) >= max_concepts * 0.7:
            print(f"[Concept Extraction] Skipping expensive methods, have {len(concepts)} concepts")
        else:
            # Method 3: KeyBERT extraction (SLOWER - only if needed)
            try:
                keybert_concepts = self._extract_keybert(text, top_n=max_concepts // 3)
                print(f"[Concept Extraction] KeyBERT found: {len(keybert_concepts)} concepts")
                for concept, score in keybert_concepts:
                    if concept.lower() not in seen_concepts:
                        concepts.append({
                            'name': concept,
                            'score': score,
                            'type': 'keyphrase',
                            'source': 'keybert'
                        })
                        seen_concepts.add(concept.lower())
            except Exception as e:
                print(f"[Concept Extraction] KeyBERT failed: {e}")
            
            # Method 4: Named Entity Recognition (SLOWER - only if needed)
            if len(concepts) < max_concepts * 0.8:
                try:
                    ner_concepts = self._extract_ner(text)
                    print(f"[Concept Extraction] NER found: {len(ner_concepts)} concepts")
                    for concept, entity_type in ner_concepts:
                        if concept.lower() not in seen_concepts:
                            concepts.append({
                                'name': concept,
                                'score': 0.7,
                                'type': entity_type,
                                'source': 'ner'
                            })
                            seen_concepts.add(concept.lower())
                except Exception as e:
                    print(f"[Concept Extraction] NER failed: {e}")
        
        # Sort by score and limit
        concepts.sort(key=lambda x: x['score'], reverse=True)
        concepts = concepts[:max_concepts]
        
        print(f"[Concept Extraction] After sorting: {len(concepts)} concepts")
        
        # Fallback 1: Noun phrase extraction
        if len(concepts) < max_concepts // 2:
            try:
                noun_phrases = self._extract_noun_phrases(text, top_n=max_concepts // 3)
                print(f"[Concept Extraction] Noun phrases found: {len(noun_phrases)}")
                for concept, score in noun_phrases:
                    if concept.lower() not in seen_concepts:
                        concepts.append({
                            'name': concept,
                            'score': score,
                            'type': 'noun_phrase',
                            'source': 'noun_extraction'
                        })
                        seen_concepts.add(concept.lower())
                        if len(concepts) >= max_concepts:
                            break
            except Exception as e:
                print(f"[Concept Extraction] Noun phrase failed: {e}")
        
        # Re-sort
        concepts.sort(key=lambda x: x['score'], reverse=True)
        concepts = concepts[:max_concepts]
        
        # Fallback 2: Basic keyword frequency
        if not concepts:
            print(f"[Concept Extraction] Using fallback keyword extraction")
            fallback = self._extract_fallback_keywords(text, top_n=max_concepts)
            for concept, score in fallback:
                if concept.lower() not in seen_concepts:
                    concepts.append({
                        'name': concept,
                        'score': score,
                        'type': 'keyword',
                        'source': 'fallback'
                    })
                    seen_concepts.add(concept.lower())
        
        # Fallback 3: Emergency extraction
        if not concepts:
            print(f"[Concept Extraction] Using emergency extraction")
            emergency = self._extract_emergency_keywords(text, top_n=max_concepts)
            for concept in emergency:
                if concept.lower() not in seen_concepts:
                    concepts.append({
                        'name': concept,
                        'score': 0.5,
                        'type': 'keyword',
                        'source': 'emergency'
                    })
                    seen_concepts.add(concept.lower())
        
        print(f"[Concept Extraction] Final: {len(concepts)} concepts")

        # Add context for each concept (lightweight - only find first occurrence)
        for concept in concepts:
            try:
                concept['context'] = self._get_concept_context(text, concept['name'], context_chars=150)
            except Exception as e:
                concept['context'] = ""
                print(f"[Concept Extraction] Context extraction failed for {concept['name']}: {e}")
        
        return concepts

    def _extract_fallback_keywords(self, text: str, top_n: int = 20) -> List[Tuple[str, float]]:
        """Fallback extraction using basic term frequency"""
        stopwords = {
            'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'your', 'you',
            'are', 'was', 'were', 'has', 'have', 'had', 'been', 'being', 'not', 'but',
            'can', 'could', 'should', 'would', 'may', 'might', 'will', 'shall', 'they',
            'their', 'them', 'its', 'it', 'our', 'ours', 'we', 'us', 'of', 'in', 'on',
            'to', 'as', 'by', 'an', 'a', 'is', 'at', 'or', 'if', 'then', 'than', 'so',
            'such', 'these', 'those', 'about', 'over', 'under', 'between', 'within',
            'without', 'also', 'more', 'most', 'some', 'any', 'each', 'other', 'which',
            'who', 'whom', 'what', 'when', 'where', 'why', 'how'
        }

        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
        freq = defaultdict(int)
        for word in words:
            if word in stopwords:
                continue
            freq[word] += 1

        if not freq:
            return []

        max_count = max(freq.values())
        scored = [(term, count / max_count) for term, count in freq.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]
    
    def _extract_keybert(self, text: str, top_n: int = 20) -> List[Tuple[str, float]]:
        """Extract keyphrases using KeyBERT - optimized for speed"""
        self._load_keybert()
        
        if self._keybert is None:
            return []
        
        try:
            # Limit text for KeyBERT (it's slow on long texts)
            if len(text) > 5000:
                text = text[:5000]
            
            keywords = self._keybert.extract_keywords(
                text,
                keyphrase_ngram_range=(1, 2),  # Reduced from (1,3) for speed
                stop_words='english',
                use_mmr=True,  # Maximal Marginal Relevance for diversity
                diversity=0.3,  # Reduced from 0.5 for speed
                top_n=top_n
            )
            return keywords
        except Exception as e:
            print(f"KeyBERT extraction failed: {e}")
            return []
    
    def _extract_tfidf(self, text: str, top_n: int = 15) -> List[Tuple[str, float]]:
        """Extract important terms using TF-IDF"""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # Split into sentences for document-level TF-IDF
            sentences = re.split(r'[.!?]\s+', text)
            if len(sentences) < 2:
                sentences = [text]
            
            vectorizer = TfidfVectorizer(
                ngram_range=(1, 2),
                stop_words='english',
                max_features=100
            )
            
            tfidf_matrix = vectorizer.fit_transform(sentences)
            feature_names = vectorizer.get_feature_names_out()
            
            # Get mean TF-IDF scores across documents
            mean_scores = np.asarray(tfidf_matrix.mean(axis=0)).flatten()
            
            # Create list of (term, score) tuples
            term_scores = [(feature_names[i], mean_scores[i]) 
                          for i in range(len(feature_names))]
            
            # Sort by score and return top terms
            term_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Filter out very short terms
            term_scores = [(t, s) for t, s in term_scores if len(t) > 2]
            
            return term_scores[:top_n]
            
        except ImportError:
            print("sklearn not installed. TF-IDF extraction skipped.")
            return []
    
    def _extract_ner(self, text: str) -> List[Tuple[str, str]]:
        """Extract named entities using spaCy"""
        self._load_models()
        
        if self._nlp is None:
            return []
        
        try:
            # Limit text length for spaCy
            max_length = 100000
            if len(text) > max_length:
                text = text[:max_length]
            
            # Process in smaller chunks to avoid memory issues
            doc = self._nlp(text)
            
            entities = []
            seen = set()
            
            # Filter for relevant entity types
            relevant_types = {'ORG', 'PRODUCT', 'EVENT', 'WORK_OF_ART', 
                            'LAW', 'LANGUAGE', 'FAC', 'GPE', 'PERSON'}
            
            for ent in doc.ents:
                if ent.label_ in relevant_types and ent.text.lower() not in seen:
                    entities.append((ent.text, ent.label_))
                    seen.add(ent.text.lower())
            
            return entities
            
        except Exception as e:
            print(f"NER extraction failed (spaCy error): {e}")
            print("Falling back to regex-based extraction...")
            return self._extract_ner_fallback(text)
    
    def _extract_ner_fallback(self, text: str) -> List[Tuple[str, str]]:
        """Fallback NER extraction using regex patterns"""
        entities = []
        
        # Simple capitalized phrase detection (often indicates proper nouns)
        capitalized_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        matches = re.findall(capitalized_pattern, text)
        
        seen = set()
        for match in matches:
            if len(match) > 2 and match.lower() not in seen and len(match.split()) <= 3:
                # Classify as generic organization/person
                if any(org_word in match for org_word in ['Inc', 'Ltd', 'Corp', 'Company', 'Lab', 'Center']):
                    entities.append((match, 'ORG'))
                else:
                    entities.append((match, 'PERSON'))
                seen.add(match.lower())
        
        return entities[:10]  # Return top 10
    
    def _extract_rake(self, text: str, top_n: int = 15) -> List[Tuple[str, float]]:
        """Extract keyphrases using RAKE algorithm"""
        try:
            from rake_nltk import Rake
            
            self._rake = Rake()
            self._rake.extract_keywords_from_text(text)
            
            # Get ranked phrases with scores
            ranked = self._rake.get_ranked_phrases_with_scores()
            
            # Filter out very long phrases
            filtered = [(phrase, score) for score, phrase in ranked 
                       if len(phrase.split()) <= 4 and len(phrase) > 3]
            
            return filtered[:top_n]
            
        except ImportError:
            print("rake-nltk not installed. RAKE extraction skipped.")
            return []
    
    def _get_concept_context(self, text: str, concept: str, 
                             context_chars: int = 200) -> str:
        """Get surrounding context for a concept"""
        pattern = re.compile(re.escape(concept), re.IGNORECASE)
        match = pattern.search(text)
        
        if not match:
            return ""
        
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        
        return text[start:end].strip()
    
    def build_knowledge_graph(self, concepts: List[Dict], text: str,
                               similarity_threshold: float = 0.4) -> Dict:
        """
        Build a knowledge graph from extracted concepts.
        
        Args:
            concepts: List of concept dictionaries
            text: Original document text
            similarity_threshold: Minimum similarity for creating edges
            
        Returns:
            Dictionary with 'nodes' and 'edges' for graph visualization
        """
        nodes = []
        edges = []
        
        concept_names = [c['name'] for c in concepts]
        
        # Create nodes
        for i, concept in enumerate(concepts):
            nodes.append({
                'id': f'node_{i}',
                'label': concept['name'],
                'score': concept.get('score', 0.5),
                'type': concept.get('type', 'concept')
            })
        
        # Create edges based on relationships
        
        # Method 1: Co-occurrence in same paragraph
        paragraphs = text.split('\n\n')
        cooccurrence = defaultdict(int)
        
        for para in paragraphs:
            para_lower = para.lower()
            present = [i for i, name in enumerate(concept_names) 
                      if name.lower() in para_lower]
            
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    key = (min(present[i], present[j]), max(present[i], present[j]))
                    cooccurrence[key] += 1
        
        # Add co-occurrence edges
        for (i, j), count in cooccurrence.items():
            if count >= 1:  # At least 1 co-occurrence
                edges.append({
                    'from': f'node_{i}',
                    'to': f'node_{j}',
                    'weight': min(count / 3, 1.0),
                    'type': 'cooccurrence'
                })
        
        # Method 2: Semantic similarity using embeddings
        self._load_sentence_model()
        
        if self._sentence_model is not None:
            try:
                embeddings = self._sentence_model.encode(concept_names)
                
                for i in range(len(concepts)):
                    for j in range(i + 1, len(concepts)):
                        # Cosine similarity
                        sim = np.dot(embeddings[i], embeddings[j]) / (
                            np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
                        )
                        
                        if sim > similarity_threshold:
                            # Check if edge already exists
                            edge_exists = any(
                                (e['from'] == f'node_{i}' and e['to'] == f'node_{j}') or
                                (e['from'] == f'node_{j}' and e['to'] == f'node_{i}')
                                for e in edges
                            )
                            
                            if not edge_exists:
                                edges.append({
                                    'from': f'node_{i}',
                                    'to': f'node_{j}',
                                    'weight': float(sim),
                                    'type': 'semantic'
                                })
                                
            except Exception as e:
                print(f"Semantic similarity calculation failed: {e}")
        
        # Method 3: Hierarchical relationships (heading structure)
        hierarchy_edges = self._extract_hierarchy_edges(concepts, text)
        edges.extend(hierarchy_edges)
        
        return {
            'nodes': nodes,
            'edges': edges,
            'concept_names': concept_names
        }
    
    def _extract_hierarchy_edges(self, concepts: List[Dict], text: str) -> List[Dict]:
        """Extract hierarchical relationships from document structure"""
        edges = []
        
        # Look for patterns like "X includes Y" or "types of X: A, B, C"
        concept_names = [c['name'] for c in concepts]
        
        for i, parent in enumerate(concept_names):
            parent_lower = parent.lower()
            
            for j, child in enumerate(concept_names):
                if i == j:
                    continue
                    
                child_lower = child.lower()
                
                # Check for explicit hierarchical patterns
                patterns = [
                    rf'{re.escape(parent_lower)}.*(?:includes?|contains?|has).*{re.escape(child_lower)}',
                    rf'types? of {re.escape(parent_lower)}.*{re.escape(child_lower)}',
                    rf'{re.escape(child_lower)}.*(?:is a|are).*{re.escape(parent_lower)}',
                ]
                
                for pattern in patterns:
                    if re.search(pattern, text.lower()):
                        edges.append({
                            'from': f'node_{i}',
                            'to': f'node_{j}',
                            'weight': 0.8,
                            'type': 'hierarchy'
                        })
                        break
        
        return edges
    
    def get_related_concepts(self, concept: str, knowledge_graph: Dict, 
                            depth: int = 1) -> List[str]:
        """
        Get concepts related to a given concept in the knowledge graph.
        
        Args:
            concept: Target concept name
            knowledge_graph: The knowledge graph dictionary
            depth: How many hops to follow
            
        Returns:
            List of related concept names
        """
        nodes = knowledge_graph.get('nodes', [])
        edges = knowledge_graph.get('edges', [])
        
        # Find node ID for the concept
        concept_node = None
        for node in nodes:
            if node['label'].lower() == concept.lower():
                concept_node = node['id']
                break
        
        if concept_node is None:
            return []
        
        # BFS to find related concepts
        related = set()
        current_level = {concept_node}
        
        for _ in range(depth):
            next_level = set()
            for node_id in current_level:
                for edge in edges:
                    if edge['from'] == node_id:
                        next_level.add(edge['to'])
                    elif edge['to'] == node_id:
                        next_level.add(edge['from'])
            
            related.update(next_level)
            current_level = next_level
        
        # Convert node IDs back to concept names
        related_names = []
        for node in nodes:
            if node['id'] in related and node['label'].lower() != concept.lower():
                related_names.append(node['label'])
        
        return related_names
    
    def calculate_concept_difficulty(self, concept: str, text: str, 
                                     knowledge_graph: Dict) -> str:
        """
        Estimate difficulty level of a concept based on various factors.
        
        Args:
            concept: Concept name
            text: Original text
            knowledge_graph: Knowledge graph
            
        Returns:
            'easy', 'medium', or 'hard'
        """
        score = 0
        
        # Factor 1: Frequency (less frequent = harder)
        frequency = text.lower().count(concept.lower())
        if frequency < 3:
            score += 2
        elif frequency < 10:
            score += 1
        
        # Factor 2: Number of related concepts (more related = harder)
        related = self.get_related_concepts(concept, knowledge_graph, depth=1)
        if len(related) > 5:
            score += 2
        elif len(related) > 2:
            score += 1
        
        # Factor 3: Concept name length (longer names often more specific/harder)
        if len(concept.split()) > 2:
            score += 1
        
        # Factor 4: Technical patterns (abbreviations, etc.)
        if re.match(r'^[A-Z]{2,}$', concept):  # Acronym
            score += 1
        
        if score >= 4:
            return 'hard'
        elif score >= 2:
            return 'medium'
        else:
            return 'easy'
    
    def export_graph_for_visualization(self, knowledge_graph: Dict) -> Dict:
        """
        Export knowledge graph in format suitable for vis.js / PyVis.
        
        Args:
            knowledge_graph: Internal knowledge graph format
            
        Returns:
            Dictionary formatted for visualization libraries
        """
        vis_nodes = []
        vis_edges = []
        
        # Color scheme based on concept type
        colors = {
            'keyphrase': '#4CAF50',
            'keyword': '#2196F3',
            'phrase': '#FF9800',
            'ORG': '#9C27B0',
            'PERSON': '#E91E63',
            'default': '#607D8B'
        }
        
        for node in knowledge_graph.get('nodes', []):
            color = colors.get(node.get('type'), colors['default'])
            vis_nodes.append({
                'id': node['id'],
                'label': node['label'],
                'color': color,
                'size': 10 + node.get('score', 0.5) * 20,
                'title': f"{node['label']}\nType: {node.get('type', 'concept')}"
            })
        
        for edge in knowledge_graph.get('edges', []):
            vis_edges.append({
                'from': edge['from'],
                'to': edge['to'],
                'width': edge.get('weight', 0.5) * 3,
                'color': {'opacity': 0.6}
            })
        
        return {
            'nodes': vis_nodes,
            'edges': vis_edges
        }    
    def _extract_noun_phrases(self, text: str, top_n: int = 15) -> List[Tuple[str, float]]:
        """Extract noun phrases using regex patterns"""
        phrases = []
        seen = set()
        
        # Pattern 1: Capitalized phrases
        pattern1 = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        matches1 = re.findall(pattern1, text)
        
        for phrase in matches1:
            if phrase.lower() not in seen and len(phrase) > 2:
                phrase_words = phrase.split()
                if len(phrase_words) <= 4:
                    phrases.append((phrase, 0.8))
                    seen.add(phrase.lower())
        
        # Pattern 2: Common academic terms
        academic_pattern = r'\b(algorithm|data|structure|system|model|theory|analysis|method|technique|process|concept|principle|function|variable|parameter|class|object|method|code|program|software|database|array|list|tree|graph)\b'
        matches2 = re.findall(academic_pattern, text, re.IGNORECASE)
        
        for term in matches2:
            if term.lower() not in seen:
                phrases.append((term, 0.75))
                seen.add(term.lower())
        
        return phrases[:top_n]
    
    def _extract_emergency_keywords(self, text: str, top_n: int = 20) -> List[str]:
        """Emergency extraction when all else fails"""
        words = text.lower().split()
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                    'of', 'is', 'are', 'was', 'were', 'be', 'been', 'by', 'with', 'from',
                    'it', 'its', 'this', 'that', 'these', 'those', 'as', 'if', 'so',
                    'have', 'has', 'had', 'do', 'does', 'did', 'can', 'could', 'will',
                    'would', 'should', 'may', 'might', 'which', 'what', 'where', 'when', 'who'}
        
        freq = defaultdict(int)
        for word in words:
            word = re.sub(r'[^a-z0-9]', '', word)
            if len(word) >= 3 and word not in stopwords:
                freq[word] += 1
        
        if not freq:
            words_clean = []
            for word in words:
                clean = re.sub(r'[^a-z0-9]', '', word.lower())
                if len(clean) >= 3:
                    words_clean.append(clean)
            return list(set(words_clean))[:top_n]
        
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:top_n]]