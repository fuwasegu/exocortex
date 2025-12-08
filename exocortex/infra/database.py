"""Database connection management for KùzuDB."""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import kuzu

logger = logging.getLogger(__name__)

# Default retry settings for write operations
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 0.5  # seconds


class DatabaseLockError(Exception):
    """Raised when database is locked and cannot be accessed."""

    pass


class DatabaseConnection:
    """Manages KùzuDB database connection with read/write mode support.

    Supports both read-only mode (for concurrent access) and read-write mode
    (with exclusive lock). Multiple processes can read simultaneously, but
    only one process can write at a time.
    """

    def __init__(
        self,
        db_path: Path,
        embedding_dimension: int,
        read_only: bool = False,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
    ) -> None:
        """Initialize the database connection.

        Args:
            db_path: Path to the database directory.
            embedding_dimension: Dimension of embedding vectors.
            read_only: If True, open database in read-only mode (allows concurrent access).
            max_retries: Maximum retries for acquiring write lock.
            retry_delay: Delay between retries in seconds.
        """
        self._db_path = db_path
        self._embedding_dimension = embedding_dimension
        self._read_only = read_only
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None
        self._initialized = False

    @property
    def is_read_only(self) -> bool:
        """Check if connection is in read-only mode."""
        return self._read_only

    @property
    def db(self) -> kuzu.Database:
        """Get the database instance, creating if needed."""
        if self._db is None:
            import kuzu

            mode = "read-only" if self._read_only else "read-write"
            logger.info(f"Initializing database at: {self._db_path} ({mode})")
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = kuzu.Database(str(self._db_path), read_only=self._read_only)
        return self._db

    @property
    def conn(self) -> kuzu.Connection:
        """Get a database connection, initializing schema if needed."""
        if self._conn is None:
            import kuzu

            self._conn = kuzu.Connection(self.db)
            if not self._initialized and not self._read_only:
                self._init_schema()
                self._initialized = True
        return self._conn

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        logger.info("Initializing database schema...")
        dim = self._embedding_dimension

        # Create Memory node table with dynamics fields
        self.conn.execute(f"""
            CREATE NODE TABLE IF NOT EXISTS Memory (
                id STRING,
                content STRING,
                summary STRING,
                embedding FLOAT[{dim}],
                memory_type STRING,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                last_accessed_at TIMESTAMP,
                access_count INT64,
                decay_rate DOUBLE,
                frustration_score DOUBLE,
                time_cost_hours DOUBLE,
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

        # Create Pattern node table (Phase 2: Concept Abstraction)
        # Patterns represent abstract rules/insights extracted from concrete memories
        self.conn.execute(f"""
            CREATE NODE TABLE IF NOT EXISTS Pattern (
                id STRING,
                content STRING,
                summary STRING,
                embedding FLOAT[{dim}],
                confidence DOUBLE,
                instance_count INT64,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                PRIMARY KEY (id)
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

        # Create INSTANCE_OF relationship (Memory → Pattern)
        # Links concrete memories to abstract patterns they exemplify
        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS INSTANCE_OF (
                FROM Memory TO Pattern,
                confidence DOUBLE,
                created_at TIMESTAMP
            )
        """)

        # Run migrations for existing databases
        self._migrate_schema()

        # Create vector index
        self._create_vector_index()

        logger.info("Database schema initialized successfully")

    def _migrate_schema(self) -> None:
        """Run schema migrations for existing databases.

        Adds new columns to existing tables if they don't exist.
        KùzuDB supports ALTER TABLE ADD COLUMN since v0.4.0.
        """
        # Migration 1: Memory dynamics columns
        try:
            # Try to query a dynamics column - if it fails, we need to migrate
            result = self.conn.execute("""
                MATCH (m:Memory) RETURN m.access_count LIMIT 1
            """)
            # If we got here, column exists
            _ = result.get_next() if result.has_next() else None
            logger.debug("Memory dynamics columns already exist")
        except Exception:
            # Columns don't exist, add them
            logger.info("Migrating Memory table: adding dynamics columns...")

            try:
                self.conn.execute("""
                    ALTER TABLE Memory ADD last_accessed_at TIMESTAMP DEFAULT NULL
                """)
                logger.debug("Added last_accessed_at column")
            except Exception as e:
                logger.debug(f"last_accessed_at column might already exist: {e}")

            try:
                self.conn.execute("""
                    ALTER TABLE Memory ADD access_count INT64 DEFAULT 1
                """)
                logger.debug("Added access_count column")
            except Exception as e:
                logger.debug(f"access_count column might already exist: {e}")

            try:
                self.conn.execute("""
                    ALTER TABLE Memory ADD decay_rate DOUBLE DEFAULT 0.1
                """)
                logger.debug("Added decay_rate column")
            except Exception as e:
                logger.debug(f"decay_rate column might already exist: {e}")

            logger.info("Memory table migration completed")

        # Migration 2: Pattern table (Phase 2)
        # Check if Pattern table exists by trying to query it
        try:
            self.conn.execute("MATCH (p:Pattern) RETURN p.id LIMIT 1")
            logger.debug("Pattern table already exists")
        except Exception:
            logger.info("Pattern table not found - will be created by _init_schema")
            # Pattern table will be created by CREATE NODE TABLE IF NOT EXISTS

        # Migration 3: Frustration Indexing columns (Phase 2.0 - Somatic Marker)
        try:
            result = self.conn.execute("""
                MATCH (m:Memory) RETURN m.frustration_score LIMIT 1
            """)
            _ = result.get_next() if result.has_next() else None
            logger.debug("Frustration indexing columns already exist")
        except Exception:
            logger.info("Migrating Memory table: adding frustration columns...")

            try:
                self.conn.execute("""
                    ALTER TABLE Memory ADD frustration_score DOUBLE DEFAULT 0.0
                """)
                logger.debug("Added frustration_score column")
            except Exception as e:
                logger.debug(f"frustration_score column might already exist: {e}")

            try:
                self.conn.execute("""
                    ALTER TABLE Memory ADD time_cost_hours DOUBLE DEFAULT NULL
                """)
                logger.debug("Added time_cost_hours column")
            except Exception as e:
                logger.debug(f"time_cost_hours column might already exist: {e}")

            logger.info("Frustration indexing migration completed")

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
        mode = "read-only" if self._read_only else "read-write"
        logger.info(f"Database connection closed ({mode})")


class SmartDatabaseManager:
    """Manages read-only and read-write database connections.

    Provides automatic connection mode switching:
    - Read operations use read-only connection (allows concurrent access)
    - Write operations use read-write connection (exclusive lock with retry)
    """

    def __init__(
        self,
        db_path: Path,
        embedding_dimension: int,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
    ) -> None:
        """Initialize the smart database manager.

        Args:
            db_path: Path to the database directory.
            embedding_dimension: Dimension of embedding vectors.
            max_retries: Maximum retries for acquiring write lock.
            retry_delay: Delay between retries in seconds.
        """
        self._db_path = db_path
        self._embedding_dimension = embedding_dimension
        self._max_retries = max_retries
        self._retry_delay = retry_delay

        # Lazy-initialized connections
        self._read_conn: DatabaseConnection | None = None
        self._write_conn: DatabaseConnection | None = None

    def _ensure_database_initialized(self) -> None:
        """Ensure database is initialized (schema created) before read-only access."""
        if not self._db_path.exists():
            logger.info("Database doesn't exist, initializing with write connection...")
            # Create database and initialize schema
            init_conn = DatabaseConnection(
                db_path=self._db_path,
                embedding_dimension=self._embedding_dimension,
                read_only=False,
            )
            # Access conn to trigger schema initialization
            _ = init_conn.conn
            init_conn.close()
            logger.info("Database initialized successfully")

    @property
    def read_connection(self) -> DatabaseConnection:
        """Get read-only database connection (for concurrent access)."""
        if self._read_conn is None:
            # Ensure database exists before opening in read-only mode
            self._ensure_database_initialized()
            self._read_conn = DatabaseConnection(
                db_path=self._db_path,
                embedding_dimension=self._embedding_dimension,
                read_only=True,
            )
        return self._read_conn

    def get_write_connection(self) -> DatabaseConnection:
        """Get read-write database connection with retry logic.

        Note: This closes any existing read connection first to avoid
        conflicts within the same process.

        Returns:
            DatabaseConnection in read-write mode.

        Raises:
            DatabaseLockError: If unable to acquire write lock after retries.
        """
        # Close existing connections to avoid conflicts
        if self._read_conn is not None:
            self._read_conn.close()
            self._read_conn = None

        if self._write_conn is not None:
            self._write_conn.close()
            self._write_conn = None

        last_error: Exception | None = None
        retry_delay = self._retry_delay

        for attempt in range(self._max_retries):
            try:
                self._write_conn = DatabaseConnection(
                    db_path=self._db_path,
                    embedding_dimension=self._embedding_dimension,
                    read_only=False,
                )
                # Try to access the connection to verify it works
                _ = self._write_conn.conn
                logger.debug(f"Write connection acquired on attempt {attempt + 1}")
                return self._write_conn
            except Exception as e:
                last_error = e
                if self._write_conn is not None:
                    self._write_conn.close()
                    self._write_conn = None
                if attempt < self._max_retries - 1:
                    logger.warning(
                        f"Failed to acquire write lock (attempt {attempt + 1}/"
                        f"{self._max_retries}): {e}. Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    # Exponential backoff
                    retry_delay *= 1.5

        raise DatabaseLockError(
            f"Failed to acquire write lock after {self._max_retries} attempts. "
            f"Another process may be using the database. Last error: {last_error}"
        )

    @contextmanager
    def write_context(self) -> Generator[DatabaseConnection, None, None]:
        """Context manager for write operations with automatic cleanup.

        Usage:
            with manager.write_context() as conn:
                conn.execute("CREATE ...")

        Yields:
            DatabaseConnection in read-write mode.

        Raises:
            DatabaseLockError: If unable to acquire write lock.
        """
        conn = self.get_write_connection()
        try:
            yield conn
        finally:
            # Close write connection to release lock immediately
            self.release_write_lock()

    def release_write_lock(self) -> None:
        """Release the write lock by closing the write connection.

        This should be called after completing a batch of write operations
        to allow other processes to access the database.
        """
        if self._write_conn is not None:
            self._write_conn.close()
            self._write_conn = None
            logger.debug("Write lock released")

    def close(self) -> None:
        """Close all database connections."""
        if self._read_conn is not None:
            self._read_conn.close()
            self._read_conn = None
        if self._write_conn is not None:
            self._write_conn.close()
            self._write_conn = None
        logger.info("All database connections closed")
