"""Hippocampus module - Memory Formation & Retrieval.

The hippocampus is crucial for:
- Encoding new memories
- Consolidating short-term to long-term memory
- Spatial and contextual memory

In Exocortex, this module handles:
- Memory creation and storage
- Similarity-based retrieval
- Memory dynamics (recency, frequency tracking)
- Hybrid scoring for recall
"""

from .dynamics import MemoryDynamics

__all__ = ["MemoryDynamics"]

