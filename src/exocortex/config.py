"""Configuration management for Exocortex."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Exocortex configuration.

    Configuration can be set via environment variables:
    - EXOCORTEX_DATA_DIR: Database storage directory (default: ./data)
    - EXOCORTEX_LOG_LEVEL: Logging level (default: INFO)
    - EXOCORTEX_EMBEDDING_MODEL: Embedding model name (default: BAAI/bge-small-en-v1.5)
    """

    data_dir: Path = field(default_factory=lambda: Path("./data"))
    log_level: str = "INFO"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        data_dir = os.environ.get("EXOCORTEX_DATA_DIR", "./data")
        log_level = os.environ.get("EXOCORTEX_LOG_LEVEL", "INFO")
        embedding_model = os.environ.get(
            "EXOCORTEX_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"
        )

        return cls(
            data_dir=Path(data_dir),
            log_level=log_level.upper(),
            embedding_model=embedding_model,
        )

    def ensure_data_dir(self) -> None:
        """Create data directory if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)


# Global configuration instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None

