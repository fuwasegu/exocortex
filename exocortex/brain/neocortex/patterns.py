"""Pattern Extraction - Abstract rule generation from memories.

Implements pattern recognition that:
- Clusters similar memories
- Extracts common themes and rules
- Generates abstract patterns with confidence scores
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass
class ClusterAnalysis:
    """Result of analyzing a memory cluster."""

    common_tags: list[str]
    dominant_type: str | None
    memory_count: int
    avg_similarity: float


class PatternExtractor:
    """Extracts patterns from memory clusters.

    This class implements the pattern abstraction logic that
    identifies common themes across groups of similar memories.
    """

    def __init__(
        self,
        min_cluster_size: int = 3,
        similarity_threshold: float = 0.7,
        confidence_per_instance: float = 0.1,
        max_confidence: float = 0.95,
    ) -> None:
        """Initialize pattern extractor.

        Args:
            min_cluster_size: Minimum memories to form a pattern
            similarity_threshold: Minimum similarity to cluster together
            confidence_per_instance: Confidence boost per matching instance
            max_confidence: Maximum confidence cap
        """
        self.min_cluster_size = min_cluster_size
        self.similarity_threshold = similarity_threshold
        self.confidence_per_instance = confidence_per_instance
        self.max_confidence = max_confidence

    def analyze_cluster(
        self,
        tags_list: list[list[str]],
        types_list: list[str],
        similarities: list[float] | None = None,
    ) -> ClusterAnalysis:
        """Analyze a cluster of memories to extract common traits.

        Args:
            tags_list: List of tag lists from each memory
            types_list: List of memory types
            similarities: Optional list of similarity scores

        Returns:
            ClusterAnalysis with common traits
        """
        # Find common tags (appearing in >50% of memories)
        all_tags = [tag for tags in tags_list for tag in tags]
        tag_counts = Counter(all_tags)
        threshold = len(tags_list) / 2
        common_tags = [tag for tag, count in tag_counts.items() if count >= threshold]

        # Find dominant type
        type_counts = Counter(types_list)
        dominant_type = type_counts.most_common(1)[0][0] if type_counts else None

        # Calculate average similarity
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0

        return ClusterAnalysis(
            common_tags=common_tags,
            dominant_type=dominant_type,
            memory_count=len(tags_list),
            avg_similarity=avg_similarity,
        )

    def calculate_confidence(
        self, instance_count: int, base_confidence: float = 0.5
    ) -> float:
        """Calculate pattern confidence based on instance count.

        Args:
            instance_count: Number of memories exemplifying this pattern
            base_confidence: Starting confidence level

        Returns:
            Confidence score capped at max_confidence
        """
        confidence = (
            base_confidence + (instance_count - 1) * self.confidence_per_instance
        )
        return min(confidence, self.max_confidence)

    def should_create_pattern(self, cluster_size: int) -> bool:
        """Check if a cluster is large enough to form a pattern.

        Args:
            cluster_size: Number of memories in the cluster

        Returns:
            True if pattern should be created
        """
        return cluster_size >= self.min_cluster_size
