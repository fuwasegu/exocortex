"""Brain-inspired cognitive modules for Exocortex.

This package organizes cognitive functions using neuroscience-inspired naming:

## Module Structure

### amygdala/ - Emotional Processing (Phase 2.0)
- Frustration Indexing (Somatic Marker Hypothesis)
- Sentiment Analysis
- Emotional memory prioritization

### hippocampus/ - Memory Formation & Retrieval
- Memory encoding and storage
- Similarity-based recall
- Memory dynamics (recency, frequency)

### neocortex/ - Pattern Recognition & Abstraction
- Pattern extraction from memory clusters
- Abstract rule generation
- Confidence scoring

### prefrontal/ - Planning & Decision Making (Future: Phase 2.2)
- Curiosity Engine (Active Learning)
- Question generation
- Knowledge gap detection

### temporal_lobe/ - Temporal Processing (Future: Phase 2.3)
- Temporal Reasoning
- Decision lineage tracking
- Causal relationship inference

## Design Philosophy

Each module encapsulates a specific cognitive function, inspired by
how the human brain organizes different types of processing:

- **Amygdala**: Emotional tagging and prioritization
- **Hippocampus**: Memory consolidation and retrieval
- **Neocortex**: Higher-order pattern recognition
- **Prefrontal**: Executive functions and planning
- **Temporal Lobe**: Sequential and temporal processing
"""

from .amygdala import FrustrationIndexer, SentimentAnalyzer

__all__ = [
    "FrustrationIndexer",
    "SentimentAnalyzer",
]
