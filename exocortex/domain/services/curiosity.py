"""Curiosity Engine - AI that questions and wonders.

This module implements the "Curiosity Engine" that actively looks for:
- Contradictions between memories
- Outdated knowledge that may need revision
- Knowledge gaps that could be filled

Inspired by the human ability to notice inconsistencies and ask questions.

Sentiment Analysis:
    When available (pip install exocortex[sentiment]), uses a local BERT model
    for more accurate positive/negative detection. Falls back to keyword-based
    detection when the model is not installed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .sentiment import SentimentAnalyzer, get_sentiment_analyzer

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
    days_since_update: int | None = None


@dataclass
class KnowledgeGap:
    """A potential gap in knowledge."""

    topic: str
    related_tags: list[str]
    suggestion: str


@dataclass
class SuggestedLink:
    """A suggested link between two memories."""

    source_id: str
    source_summary: str
    target_id: str
    target_summary: str
    reason: str
    link_type: str  # "tag_shared", "context_shared", "semantic_similar"
    confidence: float
    suggested_relation: str = "related"  # Default relation type to use


@dataclass
class CuriosityReport:
    """Report from the Curiosity Engine's scan."""

    contradictions: list[Contradiction] = field(default_factory=list)
    outdated_knowledge: list[OutdatedKnowledge] = field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = field(default_factory=list)
    suggested_links: list[SuggestedLink] = field(default_factory=list)
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
                    "days_since_update": o.days_since_update,
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
            "suggested_links": [
                {
                    "source_id": s.source_id,
                    "source_summary": s.source_summary,
                    "target_id": s.target_id,
                    "target_summary": s.target_summary,
                    "reason": s.reason,
                    "link_type": s.link_type,
                    "confidence": s.confidence,
                    "suggested_relation": s.suggested_relation,
                }
                for s in self.suggested_links
            ],
            "questions": self.questions,
            "scan_summary": self.scan_summary,
        }


# Keywords that indicate contradictory statements (English + Japanese)
CONTRADICTION_KEYWORDS = {
    "positive": [
        # English
        "works",
        "success",
        "solved",
        "fixed",
        "correct",
        "should",
        "always",
        "best",
        "recommended",
        "good",
        "great",
        "perfect",
        # Japanese
        "成功",
        "解決",
        "修正",
        "正しい",
        "推奨",
        "良い",
        "動く",
        "機能する",
        "完了",
        "うまくいった",
        "できた",
        "正解",
        "ベスト",
    ],
    "negative": [
        # English
        "doesn't work",
        "failed",
        "broken",
        "wrong",
        "never",
        "avoid",
        "worst",
        "don't",
        "incorrect",
        "bad",
        "error",
        "bug",
        # Japanese
        "失敗",
        "バグ",
        "間違い",
        "悪い",
        "動かない",
        "エラー",
        "避ける",
        "非推奨",
        "未解決",
        "ダメ",
        "できない",
        "不正解",
        "ハマった",
        "問題",
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
        stale_days: int = 90,
        sentiment_analyzer: SentimentAnalyzer | None = None,
        use_sentiment_model: bool = True,
    ) -> None:
        """Initialize the Curiosity Engine.

        Args:
            repository: Memory repository for data access.
            contradiction_threshold: Minimum similarity for contradiction check.
            min_confidence: Minimum confidence to report a finding.
            stale_days: Days after which a memory is considered potentially stale.
            sentiment_analyzer: Optional custom sentiment analyzer instance.
            use_sentiment_model: Whether to use BERT model for sentiment (if available).
        """
        self._repo = repository
        self._contradiction_threshold = contradiction_threshold
        self._min_confidence = min_confidence
        self._stale_days = stale_days
        self._use_sentiment_model = use_sentiment_model

        # Initialize sentiment analyzer (lazy-loaded)
        if sentiment_analyzer is not None:
            self._sentiment_analyzer = sentiment_analyzer
        elif use_sentiment_model:
            self._sentiment_analyzer = get_sentiment_analyzer()
        else:
            self._sentiment_analyzer = None

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

        # Find contradictions using semantic similarity
        contradictions = self._find_contradictions(
            context_filter, tag_filter, max_findings
        )
        report.contradictions = contradictions

        # Find outdated knowledge (stale, not superseded)
        outdated = self._find_outdated_knowledge(context_filter, max_findings)
        report.outdated_knowledge = outdated

        # Find suggested links (unlinked but related memories)
        suggested_links = self._find_suggested_links(
            context_filter, tag_filter, max_findings
        )
        report.suggested_links = suggested_links

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

        Uses semantic similarity (vector search) to find related memories,
        then checks for contradictory signals (type, keywords).

        This approach:
        1. Gets recent memories as "seed" memories
        2. For each seed, searches for semantically similar memories across DB
        3. Checks if any similar pairs have contradictory signals
        """
        contradictions: list[Contradiction] = []
        checked_pairs: set[tuple[str, str]] = set()

        # Get recent memories as seeds (smaller set to iterate)
        seed_memories, _, _ = self._repo.list_memories(
            limit=30,  # Recent memories as seeds
            context_filter=context_filter,
            tag_filter=tag_filter,
        )

        if len(seed_memories) < 1:
            return contradictions

        # For each seed, find semantically similar memories
        for seed in seed_memories:
            if len(contradictions) >= max_findings:
                break

            # Use semantic search to find similar memories across entire DB
            similar_memories, _ = self._repo.search_by_similarity(
                query=seed.content or seed.summary or "",
                limit=10,
                context_filter=context_filter,
            )

            for similar in similar_memories:
                if len(contradictions) >= max_findings:
                    break

                # Skip self-comparison
                if similar.id == seed.id:
                    continue

                # Skip already checked pairs
                pair = tuple(sorted([seed.id, similar.id]))
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)

                # Check for contradiction signals
                contradiction = self._check_contradiction(
                    seed, similar, similarity=similar.similarity or 0.0
                )
                if contradiction and contradiction.confidence >= self._min_confidence:
                    contradictions.append(contradiction)

        return contradictions

    def _check_contradiction(
        self, mem_a, mem_b, similarity: float = 0.0
    ) -> Contradiction | None:
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

        # High semantic similarity increases confidence
        if similarity >= self._contradiction_threshold:
            confidence += 0.3
            reasons.append(f"high semantic similarity ({similarity:.2f})")

        # Check if they share tags (more likely to be about same topic)
        shared_tags = set(mem_a.tags or []) & set(mem_b.tags or [])
        if shared_tags:
            confidence += 0.1
            reasons.append(f"shared tags: {', '.join(list(shared_tags)[:3])}")

        if confidence >= self._min_confidence and reasons:
            return Contradiction(
                memory_a_id=mem_a.id,
                memory_a_summary=mem_a.summary[:100] if mem_a.summary else "",
                memory_b_id=mem_b.id,
                memory_b_summary=mem_b.summary[:100] if mem_b.summary else "",
                similarity=similarity,
                reason=" | ".join(reasons),
                confidence=min(confidence, 1.0),
            )

        return None

    def _check_type_contradiction(self, mem_a, mem_b) -> str | None:
        """Check for contradiction based on memory types."""
        type_a = mem_a.memory_type
        type_b = mem_b.memory_type

        # Normalize types (might be string or enum)
        type_a_str = str(type_a).lower() if type_a else ""
        type_b_str = str(type_b).lower() if type_b else ""

        # Success vs Failure on overlapping tags is suspicious
        if ("success" in type_a_str and "failure" in type_b_str) or (
            "failure" in type_a_str and "success" in type_b_str
        ):
            shared_tags = set(mem_a.tags or []) & set(mem_b.tags or [])
            if shared_tags:
                return f"success vs failure on same topic ({', '.join(list(shared_tags)[:2])})"

        return None

    def _check_keyword_contradiction(
        self, content_a: str, content_b: str
    ) -> str | None:
        """Check for contradictory sentiment in content.

        Uses BERT-based sentiment analysis if available, falls back to
        keyword-based detection otherwise.
        """
        # Try BERT-based sentiment analysis first
        if self._sentiment_analyzer and self._sentiment_analyzer.is_available():
            is_contradictory, reason = self._sentiment_analyzer.is_contradictory(
                content_a, content_b, min_confidence=0.7
            )
            if is_contradictory:
                return f"🤖 {reason}"

        # Fallback to keyword-based detection
        a_positive = any(kw in content_a for kw in CONTRADICTION_KEYWORDS["positive"])
        a_negative = any(kw in content_a for kw in CONTRADICTION_KEYWORDS["negative"])
        b_positive = any(kw in content_b for kw in CONTRADICTION_KEYWORDS["positive"])
        b_negative = any(kw in content_b for kw in CONTRADICTION_KEYWORDS["negative"])

        if (a_positive and b_negative) or (a_negative and b_positive):
            return "contradictory sentiment detected (keyword-based)"

        return None

    def _find_outdated_knowledge(
        self,
        context_filter: str | None,
        max_findings: int,
    ) -> list[OutdatedKnowledge]:
        """Find knowledge that may be outdated (stale and not superseded).

        Looks for memories that:
        1. Haven't been updated/accessed for a long time (stale_days)
        2. Are NOT already marked as superseded (important decisions left unreviewed)
        3. Are of type INSIGHT or DECISION (not just notes/logs)
        """
        outdated: list[OutdatedKnowledge] = []
        now = datetime.now(timezone.utc)
        stale_threshold = now - timedelta(days=self._stale_days)

        # Get memories to analyze (focus on important types)
        memories, _, _ = self._repo.list_memories(
            limit=100,
            context_filter=context_filter,
            type_filter=None,
        )

        for mem in memories:
            if len(outdated) >= max_findings:
                break

            # Skip recent memories
            last_updated = mem.updated_at or mem.created_at
            if last_updated:
                # Ensure timezone-aware comparison
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=timezone.utc)
                if last_updated > stale_threshold:
                    continue

            # Focus on important memory types that should be reviewed
            mem_type_str = str(mem.memory_type).lower() if mem.memory_type else ""
            if mem_type_str not in ["insight", "decision"]:
                continue

            # Check if this memory has been superseded (incoming supersedes link)
            # If it's already superseded, it's "resolved" outdated, not "neglected"
            is_superseded = self._check_if_superseded(mem.id)
            if is_superseded:
                continue

            # This is a stale, important memory that hasn't been reviewed/superseded
            if last_updated:
                # Ensure timezone-aware for calculation
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=timezone.utc)
                days_old = (now - last_updated).days
            else:
                days_old = None
            outdated.append(
                OutdatedKnowledge(
                    memory_id=mem.id,
                    summary=mem.summary[:100] if mem.summary else "",
                    superseded_by_id=None,
                    superseded_by_summary=None,
                    reason=f"This {mem_type_str} is {days_old} days old and hasn't been reviewed or superseded",
                    days_since_update=days_old,
                )
            )

        return outdated

    def _find_suggested_links(
        self,
        context_filter: str | None,
        tag_filter: list[str] | None,
        max_findings: int,
    ) -> list[SuggestedLink]:
        """Find unlinked memories that should be connected.

        Uses three strategies:
        1. Tag sharing - memories with same tags
        2. Context sharing - memories in same project/context
        3. Semantic similarity - high similarity (>0.7) memories

        Only suggests links for memories that aren't already linked.
        """
        suggested: list[SuggestedLink] = []
        checked_pairs: set[tuple[str, str]] = set()
        existing_links = self._get_existing_link_pairs()

        # Get memories to analyze
        memories, _, _ = self._repo.list_memories(
            limit=100,
            context_filter=context_filter,
            tag_filter=tag_filter,
        )

        if len(memories) < 2:
            return suggested

        # Strategy 1: Tag sharing (high confidence)
        tag_suggestions = self._find_tag_shared_links(
            memories, existing_links, checked_pairs, max_findings
        )
        suggested.extend(tag_suggestions)

        # Strategy 2: Context sharing (medium confidence)
        context_suggestions = self._find_context_shared_links(
            memories, existing_links, checked_pairs, max_findings - len(suggested)
        )
        suggested.extend(context_suggestions)

        # Strategy 3: Semantic similarity (high confidence for >0.7)
        semantic_suggestions = self._find_semantic_links(
            memories, existing_links, checked_pairs, max_findings - len(suggested)
        )
        suggested.extend(semantic_suggestions)

        return suggested[:max_findings]

    def _get_existing_link_pairs(self) -> set[tuple[str, str]]:
        """Get all existing link pairs to avoid duplicate suggestions."""
        pairs: set[tuple[str, str]] = set()
        try:
            # Get all memories with links
            memories, _, _ = self._repo.list_memories(limit=500)
            for mem in memories:
                links = self._repo.get_links(mem.id)
                for link in links:
                    pair = tuple(sorted([mem.id, link.target_id]))
                    pairs.add(pair)
        except Exception as e:
            logger.warning(f"Error getting existing links: {e}")
        return pairs

    def _find_tag_shared_links(
        self,
        memories: list,
        existing_links: set[tuple[str, str]],
        checked_pairs: set[tuple[str, str]],
        max_findings: int,
    ) -> list[SuggestedLink]:
        """Find memories that share multiple tags but aren't linked."""
        suggested: list[SuggestedLink] = []

        # Group memories by tags
        tag_to_memories: dict[str, list] = {}
        for mem in memories:
            for tag in mem.tags or []:
                if tag not in tag_to_memories:
                    tag_to_memories[tag] = []
                tag_to_memories[tag].append(mem)

        # Find pairs with multiple shared tags
        for i, mem_a in enumerate(memories):
            if len(suggested) >= max_findings:
                break

            for mem_b in memories[i + 1 :]:
                if len(suggested) >= max_findings:
                    break

                pair = tuple(sorted([mem_a.id, mem_b.id]))
                if pair in checked_pairs or pair in existing_links:
                    continue

                shared_tags = set(mem_a.tags or []) & set(mem_b.tags or [])
                if len(shared_tags) >= 2:  # At least 2 shared tags
                    checked_pairs.add(pair)
                    confidence = min(0.5 + len(shared_tags) * 0.1, 0.9)
                    suggested.append(
                        SuggestedLink(
                            source_id=mem_a.id,
                            source_summary=mem_a.summary[:80] if mem_a.summary else "",
                            target_id=mem_b.id,
                            target_summary=mem_b.summary[:80] if mem_b.summary else "",
                            reason=f"Share {len(shared_tags)} tags: {', '.join(list(shared_tags)[:3])}",
                            link_type="tag_shared",
                            confidence=confidence,
                            suggested_relation="related",
                        )
                    )

        return suggested

    def _find_context_shared_links(
        self,
        memories: list,
        existing_links: set[tuple[str, str]],
        checked_pairs: set[tuple[str, str]],
        max_findings: int,
    ) -> list[SuggestedLink]:
        """Find memories in same context with same type but aren't linked."""
        suggested: list[SuggestedLink] = []

        # Group by context
        context_to_memories: dict[str, list] = {}
        for mem in memories:
            ctx = mem.context_name or "unknown"
            if ctx not in context_to_memories:
                context_to_memories[ctx] = []
            context_to_memories[ctx].append(mem)

        # Find pairs in same context with same type
        for ctx, ctx_memories in context_to_memories.items():
            if len(suggested) >= max_findings:
                break

            for i, mem_a in enumerate(ctx_memories):
                if len(suggested) >= max_findings:
                    break

                for mem_b in ctx_memories[i + 1 :]:
                    if len(suggested) >= max_findings:
                        break

                    pair = tuple(sorted([mem_a.id, mem_b.id]))
                    if pair in checked_pairs or pair in existing_links:
                        continue

                    # Same context + same type = likely related
                    type_a = str(mem_a.memory_type).lower() if mem_a.memory_type else ""
                    type_b = str(mem_b.memory_type).lower() if mem_b.memory_type else ""

                    if type_a == type_b and type_a in [
                        "insight",
                        "decision",
                        "success",
                    ]:
                        checked_pairs.add(pair)
                        suggested.append(
                            SuggestedLink(
                                source_id=mem_a.id,
                                source_summary=mem_a.summary[:80]
                                if mem_a.summary
                                else "",
                                target_id=mem_b.id,
                                target_summary=mem_b.summary[:80]
                                if mem_b.summary
                                else "",
                                reason=f"Same context '{ctx}' and type '{type_a}'",
                                link_type="context_shared",
                                confidence=0.6,
                                suggested_relation="related",
                            )
                        )

        return suggested

    def _find_semantic_links(
        self,
        memories: list,
        existing_links: set[tuple[str, str]],
        checked_pairs: set[tuple[str, str]],
        max_findings: int,
    ) -> list[SuggestedLink]:
        """Find memories with high semantic similarity that aren't linked."""
        suggested: list[SuggestedLink] = []
        similarity_threshold = 0.70  # High similarity threshold

        # Sample memories for semantic search (avoid too many queries)
        sample_size = min(20, len(memories))
        sample_memories = memories[:sample_size]

        for mem in sample_memories:
            if len(suggested) >= max_findings:
                break

            # Search for similar memories
            try:
                similar_memories, _ = self._repo.search_by_similarity(
                    query=mem.content or mem.summary or "",
                    limit=5,
                )
            except Exception as e:
                logger.warning(f"Error in semantic search: {e}")
                continue

            for similar in similar_memories:
                if len(suggested) >= max_findings:
                    break

                # Skip self
                if similar.id == mem.id:
                    continue

                pair = tuple(sorted([mem.id, similar.id]))
                if pair in checked_pairs or pair in existing_links:
                    continue

                similarity = similar.similarity or 0.0
                if similarity >= similarity_threshold:
                    checked_pairs.add(pair)
                    suggested.append(
                        SuggestedLink(
                            source_id=mem.id,
                            source_summary=mem.summary[:80] if mem.summary else "",
                            target_id=similar.id,
                            target_summary=similar.summary[:80]
                            if similar.summary
                            else "",
                            reason=f"High semantic similarity ({similarity:.0%})",
                            link_type="semantic_similar",
                            confidence=similarity,
                            suggested_relation="related",
                        )
                    )

        return suggested

    def _check_if_superseded(self, memory_id: str) -> bool:
        """Check if a memory has been superseded by another memory.

        Uses get_incoming_links to efficiently find all memories that
        link TO this memory with 'supersedes' relation.
        """
        try:
            # Get incoming links with 'supersedes' relation type
            from ...domain.models import RelationType

            incoming_links = self._repo.get_incoming_links(
                memory_id, relation_type=RelationType.SUPERSEDES
            )
            return len(incoming_links) > 0
        except Exception as e:
            logger.warning(f"Error checking supersedes for {memory_id}: {e}")
            return False

    def _generate_questions(self, report: CuriosityReport) -> list[str]:
        """Generate human-like questions based on findings."""
        questions: list[str] = []

        if report.contradictions:
            questions.append(
                "🤔 いくつかの記憶が矛盾しているようです。"
                "両方とも有効ですか？それとも理解が変わりましたか？"
            )

        if report.outdated_knowledge:
            questions.append(
                "📅 古くなった知識が見つかりました。"
                "まだ有効ですか？新しい情報で更新が必要では？"
            )

        if report.suggested_links:
            questions.append(
                "🔗 リンクされていない関連メモリが見つかりました。"
                "これらをリンクして知識グラフを強化しませんか？"
            )

        if (
            not report.contradictions
            and not report.outdated_knowledge
            and not report.suggested_links
        ):
            questions.append(
                "✨ 知識ベースは一貫しています！"
                "引き続き知見を記録して、より強いパターンを構築しましょう。"
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
                f"Found {len(report.outdated_knowledge)} potentially stale item(s) needing review"
            )

        if report.suggested_links:
            parts.append(
                f"Found {len(report.suggested_links)} suggested link(s) to strengthen the knowledge graph"
            )

        if not parts:
            return "No notable findings. Your knowledge base appears consistent."

        return ". ".join(parts) + "."
