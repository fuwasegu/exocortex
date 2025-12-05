"""Configuration settings for Exocortex."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Exocortex configuration."""

    # Data storage
    data_dir: Path = field(default_factory=lambda: Path.home() / ".exocortex")
    db_name: str = "exocortex_db"

    # Embedding model
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Knowledge autonomy thresholds
    link_suggestion_threshold: float = 0.65
    duplicate_detection_threshold: float = 0.90
    contradiction_check_threshold: float = 0.70

    # Limits
    max_summary_length: int = 200
    max_tags_per_memory: int = 20
    stale_memory_days: int = 90

    @property
    def db_path(self) -> Path:
        """Get the full database path."""
        return self.data_dir / self.db_name

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        data_dir_str = os.environ.get("EXOCORTEX_DATA_DIR")
        data_dir = Path(data_dir_str) if data_dir_str else Path.home() / ".exocortex"

        return cls(
            data_dir=data_dir,
            db_name=os.environ.get("EXOCORTEX_DB_NAME", "exocortex_db"),
            embedding_model=os.environ.get(
                "EXOCORTEX_EMBEDDING_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            ),
            link_suggestion_threshold=float(
                os.environ.get("EXOCORTEX_LINK_THRESHOLD", "0.65")
            ),
            duplicate_detection_threshold=float(
                os.environ.get("EXOCORTEX_DUPLICATE_THRESHOLD", "0.90")
            ),
            contradiction_check_threshold=float(
                os.environ.get("EXOCORTEX_CONTRADICTION_THRESHOLD", "0.70")
            ),
            max_summary_length=int(
                os.environ.get("EXOCORTEX_MAX_SUMMARY_LENGTH", "200")
            ),
            max_tags_per_memory=int(os.environ.get("EXOCORTEX_MAX_TAGS", "20")),
            stale_memory_days=int(os.environ.get("EXOCORTEX_STALE_DAYS", "90")),
        )


# Module-level config instance (for backwards compatibility during migration)
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Reset the config (for testing)."""
    global _config
    _config = None
