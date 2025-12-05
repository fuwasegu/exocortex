"""Dependency injection container for Exocortex."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config, get_config
from .domain.services import MemoryService
from .infra.database import SmartDatabaseManager
from .infra.embeddings import EmbeddingEngine
from .infra.repositories import MemoryRepository


@dataclass
class Container:
    """Dependency injection container.

    Manages the lifecycle of all application components with proper
    dependency injection.
    """

    config: Config
    _embedding_engine: EmbeddingEngine | None = None
    _database_manager: SmartDatabaseManager | None = None
    _repository: MemoryRepository | None = None
    _service: MemoryService | None = None

    @classmethod
    def create(cls, config: Config | None = None) -> Container:
        """Create a new container with the given config.

        Args:
            config: Optional config. Uses global config if not provided.

        Returns:
            A new Container instance.
        """
        return cls(config=config or get_config())

    @property
    def embedding_engine(self) -> EmbeddingEngine:
        """Get the embedding engine (lazy initialization)."""
        if self._embedding_engine is None:
            self._embedding_engine = EmbeddingEngine(
                model_name=self.config.embedding_model
            )
        return self._embedding_engine

    @property
    def database_manager(self) -> SmartDatabaseManager:
        """Get the smart database manager (lazy initialization)."""
        if self._database_manager is None:
            self._database_manager = SmartDatabaseManager(
                db_path=self.config.db_path,
                embedding_dimension=self.embedding_engine.dimension,
            )
        return self._database_manager

    @property
    def repository(self) -> MemoryRepository:
        """Get the memory repository (lazy initialization)."""
        if self._repository is None:
            self._repository = MemoryRepository(
                db_manager=self.database_manager,
                embedding_engine=self.embedding_engine,
                max_summary_length=self.config.max_summary_length,
            )
        return self._repository

    @property
    def memory_service(self) -> MemoryService:
        """Get the memory service (lazy initialization)."""
        if self._service is None:
            self._service = MemoryService(
                repository=self.repository,
                link_threshold=self.config.link_suggestion_threshold,
                duplicate_threshold=self.config.duplicate_detection_threshold,
                contradiction_threshold=self.config.contradiction_check_threshold,
                max_tags=self.config.max_tags_per_memory,
                stale_days=self.config.stale_memory_days,
            )
        return self._service

    def close(self) -> None:
        """Close all resources."""
        if self._database_manager is not None:
            self._database_manager.close()
            self._database_manager = None
        self._repository = None
        self._service = None


# Module-level container instance
_container: Container | None = None


def get_container() -> Container:
    """Get the global container instance."""
    global _container
    if _container is None:
        _container = Container.create()
    return _container


def reset_container() -> None:
    """Reset the container (for testing)."""
    global _container
    if _container is not None:
        _container.close()
    _container = None
