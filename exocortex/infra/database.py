"""Database connection management for KùzuDB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import kuzu

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manages KùzuDB database connection and schema initialization."""

    def __init__(self, db_path: Path, embedding_dimension: int) -> None:
        """Initialize the database connection.

        Args:
            db_path: Path to the database directory.
            embedding_dimension: Dimension of embedding vectors.
        """
        self._db_path = db_path
        self._embedding_dimension = embedding_dimension
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None
        self._initialized = False

    @property
    def db(self) -> kuzu.Database:
        """Get the database instance, creating if needed."""
        if self._db is None:
            import kuzu

            logger.info(f"Initializing database at: {self._db_path}")
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = kuzu.Database(str(self._db_path))
        return self._db

    @property
    def conn(self) -> kuzu.Connection:
        """Get a database connection, initializing schema if needed."""
        if self._conn is None:
            import kuzu

            self._conn = kuzu.Connection(self.db)
            if not self._initialized:
                self._init_schema()
                self._initialized = True
        return self._conn

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        logger.info("Initializing database schema...")
        dim = self._embedding_dimension

        # Create Memory node table
        self.conn.execute(f"""
            CREATE NODE TABLE IF NOT EXISTS Memory (
                id STRING,
                content STRING,
                summary STRING,
                embedding FLOAT[{dim}],
                memory_type STRING,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                PRIMARY KEY (id)
            )
        """)

        # Create Context node table
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Context (
                name STRING,
                created_at TIMESTAMP,
                PRIMARY KEY (name)
            )
        """)

        # Create Tag node table
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Tag (
                name STRING,
                created_at TIMESTAMP,
                PRIMARY KEY (name)
            )
        """)

        # Create relationship tables
        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS ORIGINATED_IN (
                FROM Memory TO Context
            )
        """)

        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS TAGGED_WITH (
                FROM Memory TO Tag
            )
        """)

        # Create RELATED_TO relationship table for memory-to-memory links
        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS RELATED_TO (
                FROM Memory TO Memory,
                relation_type STRING,
                reason STRING,
                created_at TIMESTAMP
            )
        """)

        # Create vector index
        self._create_vector_index()

        logger.info("Database schema initialized successfully")

    def _create_vector_index(self) -> None:
        """Create vector index for memory embeddings."""
        try:
            self.conn.execute("""
                CALL CREATE_VECTOR_INDEX(
                    'Memory',
                    'memory_embedding_idx',
                    'embedding',
                    metric := 'cosine'
                )
            """)
            logger.info("Vector index created successfully")
        except Exception as e:
            # Index might already exist
            logger.debug(f"Vector index creation skipped: {e}")

    def execute(self, query: str, parameters: dict | None = None) -> kuzu.QueryResult:
        """Execute a query on the database.

        Args:
            query: Cypher query string.
            parameters: Optional query parameters.

        Returns:
            Query result.
        """
        if parameters:
            return self.conn.execute(query, parameters=parameters)
        return self.conn.execute(query)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn = None
        if self._db is not None:
            self._db = None
        logger.info("Database connection closed")
