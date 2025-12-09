"""Curiosity Engine - AI that questions and wonders.

This module implements the "Curiosity Engine" that actively looks for:
- Contradictions between memories
- Outdated knowledge that may need revision
- Knowledge gaps that could be filled

Inspired by the human ability to notice inconsistencies and ask questions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exocortex.infra.repositories import MemoryRepository

logger = logging.getLogger(__name__)


@dataclass
class Contradiction:
    """A potential contradiction between two memories."""

    memory_a_id: str
    memory_a_summary: str
    memory_b_id: str
    memory_b_summary: str
    similarity: float
    reason: str
    confidence: float  # How confident we are this is a real contradiction


@dataclass
class OutdatedKnowledge:
    """Knowledge that may be outdated."""

    memory_id: str
    summary: str
    superseded_by_id: str | None
    superseded_by_summary: str | None
    reason: str


@dataclass
class KnowledgeGap:
    """A potential gap in knowledge."""

    topic: str
    related_tags: list[str]
    suggestion: str


@dataclass
class CuriosityReport:
    """Report from the Curiosity Engine's scan."""

    contradictions: list[Contradiction] = field(default_factory=list)
    outdated_knowledge: list[OutdatedKnowledge] = field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    scan_summary: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for MCP response."""
        return {
            "contradictions": [
                {
                    "memory_a_id": c.memory_a_id,
                    "memory_a_summary": c.memory_a_summary,
                    "memory_b_id": c.memory_b_id,
                    "memory_b_summary": c.memory_b_summary,
                    "similarity": c.similarity,
                    "reason": c.reason,
                    "confidence": c.confidence,
                }
                for c in self.contradictions
            ],
            "outdated_knowledge": [
                {
                    "memory_id": o.memory_id,
                    "summary": o.summary,
                    "superseded_by_id": o.superseded_by_id,
                    "superseded_by_summary": o.superseded_by_summary,
                    "reason": o.reason,
                }
                for o in self.outdated_knowledge
            ],
            "knowledge_gaps": [
                {
                    "topic": g.topic,
                    "related_tags": g.related_tags,
                    "suggestion": g.suggestion,
                }
                for g in self.knowledge_gaps
            ],
            "questions": self.questions,
            "scan_summary": self.scan_summary,
        }


# Keywords that indicate contradictory statements
CONTRADICTION_KEYWORDS = {
    "positive": [
        "works",
        "success",
        "solved",
        "fixed",
        "correct",
        "should",
        "always",
        "best",
        "recommended",
    ],
    "negative": [
        "doesn't work",
        "failed",
        "broken",
        "wrong",
        "never",
        "avoid",
        "worst",
        "don't",
        "incorrect",
    ],
}


class CuriosityEngine:
    """Engine that actively questions and wonders about the knowledge base.

    Like a curious human, it looks for:
    - "Wait, these two memories seem to contradict each other..."
    - "This knowledge seems outdated, is it still valid?"
    - "I notice we don't have much knowledge about X..."
    """

    def __init__(
        self,
        repository: MemoryRepository,
        contradiction_threshold: float = 0.65,
        min_confidence: float = 0.5,
    ) -> None:
        """Initialize the Curiosity Engine.

        Args:
            repository: Memory repository for data access.
            contradiction_threshold: Minimum similarity for contradiction check.
            min_confidence: Minimum confidence to report a finding.
        """
        self._repo = repository
        self._contradiction_threshold = contradiction_threshold
        self._min_confidence = min_confidence

    def scan(
        self,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        max_findings: int = 10,
    ) -> CuriosityReport:
        """Scan the knowledge base for interesting findings.

        Args:
            context_filter: Optional context to focus on.
            tag_filter: Optional tags to focus on.
            max_findings: Maximum findings per category.

        Returns:
            CuriosityReport with findings and questions.
        """
        report = CuriosityReport()

        # Find contradictions
        contradictions = self._find_contradictions(
            context_filter, tag_filter, max_findings
        )
        report.contradictions = contradictions

        # Find outdated knowledge
        outdated = self._find_outdated_knowledge(context_filter, max_findings)
        report.outdated_knowledge = outdated

        # Generate questions based on findings
        report.questions = self._generate_questions(report)

        # Create summary
        report.scan_summary = self._create_summary(report)

        return report

    def _find_contradictions(
        self,
        context_filter: str | None,
        tag_filter: list[str] | None,
        max_findings: int,
    ) -> list[Contradiction]:
        """Find potential contradictions between memories.

        Looks for memories that are semantically similar but have
        contradictory content (e.g., one says "X works" and another says "X doesn't work").
        """
        contradictions: list[Contradiction] = []

        # Get memories to analyze
        memories, _, _ = self._repo.list_memories(
            limit=100,  # Analyze recent memories
            context_filter=context_filter,
            tag_filter=tag_filter,
        )

        if len(memories) < 2:
            return contradictions

        # Compare pairs for contradictions
        for i, mem_a in enumerate(memories):
            if len(contradictions) >= max_findings:
                break

            for mem_b in memories[i + 1 :]:
                if len(contradictions) >= max_findings:
                    break

                # Check for contradiction signals
                contradiction = self._check_contradiction(mem_a, mem_b)
                if contradiction and contradiction.confidence >= self._min_confidence:
                    contradictions.append(contradiction)

        return contradictions

    def _check_contradiction(self, mem_a, mem_b) -> Contradiction | None:
        """Check if two memories contradict each other."""
        # Get content for analysis
        content_a = (mem_a.content or mem_a.summary or "").lower()
        content_b = (mem_b.content or mem_b.summary or "").lower()

        # Check type-based contradictions (success vs failure on similar topic)
        type_contradiction = self._check_type_contradiction(mem_a, mem_b)

        # Check keyword-based contradictions
        keyword_contradiction = self._check_keyword_contradiction(content_a, content_b)

        # Calculate confidence
        confidence = 0.0
        reasons = []

        if type_contradiction:
            confidence += 0.4
            reasons.append(type_contradiction)

        if keyword_contradiction:
            confidence += 0.4
            reasons.append(keyword_contradiction)

        # Check if they share tags (more likely to be about same topic)
        shared_tags = set(mem_a.tags or []) & set(mem_b.tags or [])
        if shared_tags:
            confidence += 0.2
            reasons.append(f"shared tags: {', '.join(list(shared_tags)[:3])}")

        if confidence >= self._min_confidence and reasons:
            return Contradiction(
                memory_a_id=mem_a.id,
                memory_a_summary=mem_a.summary[:100] if mem_a.summary else "",
                memory_b_id=mem_b.id,
                memory_b_summary=mem_b.summary[:100] if mem_b.summary else "",
                similarity=len(shared_tags) / max(len(mem_a.tags or [1]), 1),
                reason=" | ".join(reasons),
                confidence=min(confidence, 1.0),
            )

        return None

    def _check_type_contradiction(self, mem_a, mem_b) -> str | None:
        """Check for contradiction based on memory types."""
        type_a = mem_a.memory_type
        type_b = mem_b.memory_type

        # Success vs Failure on overlapping tags is suspicious
        if (type_a == "success" and type_b == "failure") or (
            type_a == "failure" and type_b == "success"
        ):
            shared_tags = set(mem_a.tags or []) & set(mem_b.tags or [])
            if shared_tags:
                return f"success vs failure on same topic ({', '.join(list(shared_tags)[:2])})"

        return None

    def _check_keyword_contradiction(
        self, content_a: str, content_b: str
    ) -> str | None:
        """Check for contradictory keywords in content."""
        # Check if one has positive keywords and other has negative
        a_positive = any(kw in content_a for kw in CONTRADICTION_KEYWORDS["positive"])
        a_negative = any(kw in content_a for kw in CONTRADICTION_KEYWORDS["negative"])
        b_positive = any(kw in content_b for kw in CONTRADICTION_KEYWORDS["positive"])
        b_negative = any(kw in content_b for kw in CONTRADICTION_KEYWORDS["negative"])

        if (a_positive and b_negative) or (a_negative and b_positive):
            return "contradictory sentiment detected"

        return None

    def _find_outdated_knowledge(
        self,
        context_filter: str | None,
        max_findings: int,
    ) -> list[OutdatedKnowledge]:
        """Find knowledge that may be outdated.

        Looks for:
        - Memories that have been superseded but are still frequently accessed
        - Old decisions that haven't been reviewed
        """
        outdated: list[OutdatedKnowledge] = []

        # Find memories with supersedes relationships
        # These are candidates for "outdated" knowledge
        memories, _, _ = self._repo.list_memories(
            limit=50,
            context_filter=context_filter,
            type_filter=None,
        )

        for mem in memories:
            if len(outdated) >= max_findings:
                break

            # Check if this memory has been superseded
            links = self._repo.get_links(mem.id)
            for link in links:
                if link.relation_type == "supersedes":
                    # This memory supersedes something - the target might be outdated
                    target = self._repo.get_by_id(link.target_id)
                    if target:
                        outdated.append(
                            OutdatedKnowledge(
                                memory_id=target.id,
                                summary=target.summary[:100] if target.summary else "",
                                superseded_by_id=mem.id,
                                superseded_by_summary=(
                                    mem.summary[:100] if mem.summary else ""
                                ),
                                reason="This knowledge has been superseded by newer information",
                            )
                        )

        return outdated

    def _generate_questions(self, report: CuriosityReport) -> list[str]:
        """Generate human-like questions based on findings."""
        questions: list[str] = []

        if report.contradictions:
            questions.append(
                "🤔 I noticed some memories that might contradict each other. "
                "Are both still valid, or has your understanding changed?"
            )

        if report.outdated_knowledge:
            questions.append(
                "📅 Some knowledge has been superseded. "
                "Should the old information be archived or is it still relevant in some contexts?"
            )

        if not report.contradictions and not report.outdated_knowledge:
            questions.append(
                "✨ Your knowledge base looks consistent! "
                "Keep recording insights to build stronger patterns."
            )

        return questions

    def _create_summary(self, report: CuriosityReport) -> str:
        """Create a human-readable summary of findings."""
        parts = []

        if report.contradictions:
            parts.append(
                f"Found {len(report.contradictions)} potential contradiction(s)"
            )

        if report.outdated_knowledge:
            parts.append(
                f"Found {len(report.outdated_knowledge)} potentially outdated item(s)"
            )

        if not parts:
            return "No notable findings. Your knowledge base appears consistent."

        return ". ".join(parts) + "."
