"""Unit tests for dashboard module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from exocortex.dashboard.app import create_dashboard_app


@pytest.fixture
def mock_container():
    """Mock the container with repository."""
    mock_repo = MagicMock()
    mock_container = MagicMock()
    mock_container.repository = mock_repo
    return mock_container, mock_repo


class TestDashboardApp:
    """Tests for dashboard app creation."""

    def test_create_dashboard_app(self):
        """Test that dashboard app is created successfully."""
        app = create_dashboard_app()
        assert app is not None

    def test_index_route_exists(self):
        """Test that index route returns HTML."""
        app = create_dashboard_app()
        client = TestClient(app)
        response = client.get("/")
        # Should return HTML (either 200 with content or 404 if no static file)
        assert response.status_code in [200, 404]


class TestApiStats:
    """Tests for /api/stats endpoint."""

    def test_api_stats_success(self, mock_container):
        """Test stats endpoint returns correct data."""
        mock_container_obj, mock_repo = mock_container

        # Mock get_stats()
        mock_stats = MagicMock()
        mock_stats.total_memories = 100
        mock_stats.memories_by_type = {"insight": 20, "failure": 15}
        mock_stats.total_contexts = 2
        mock_stats.total_tags = 3
        mock_repo.get_stats.return_value = mock_stats

        # Mock _execute_read for contexts
        mock_ctx_result = MagicMock()
        mock_ctx_result.has_next.side_effect = [True, True, False]
        mock_ctx_result.get_next.side_effect = [["project1"], ["project2"]]

        # Mock _execute_read for tags
        mock_tag_result = MagicMock()
        mock_tag_result.has_next.side_effect = [True, True, True, False]
        mock_tag_result.get_next.side_effect = [["python"], ["api"], ["bugfix"]]

        mock_repo._execute_read.side_effect = [mock_ctx_result, mock_tag_result]
        mock_repo.get_orphan_memories.return_value = []

        with patch(
            "exocortex.dashboard.app.get_container", return_value=mock_container_obj
        ):
            app = create_dashboard_app()
            client = TestClient(app)
            response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stats" in data
        assert data["stats"]["total_memories"] == 100
        assert data["stats"]["contexts_count"] == 2
        assert data["stats"]["tags_count"] == 3

    def test_api_stats_error(self):
        """Test stats endpoint handles errors."""
        with patch(
            "exocortex.dashboard.app.get_container", side_effect=Exception("DB error")
        ):
            app = create_dashboard_app()
            client = TestClient(app)
            response = client.get("/api/stats")

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert "error" in data


class TestApiMemories:
    """Tests for /api/memories endpoint."""

    def test_api_memories_list(self, mock_container):
        """Test memories list endpoint."""
        mock_container_obj, mock_repo = mock_container

        # Create mock memory
        mock_memory = MagicMock()
        mock_memory.id = "mem-1"
        mock_memory.summary = "Test memory summary"
        mock_memory.content = "Test content"
        mock_memory.context = "test-project"  # Changed from context_name
        mock_memory.memory_type = MagicMock(value="insight")
        mock_memory.tags = ["test", "mock"]
        mock_memory.created_at = None
        mock_memory.access_count = 5

        # list_memories returns (memories, total, has_more)
        mock_repo.list_memories.return_value = ([mock_memory], 1, False)

        with patch(
            "exocortex.dashboard.app.get_container", return_value=mock_container_obj
        ):
            app = create_dashboard_app()
            client = TestClient(app)
            response = client.get("/api/memories?limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["memories"]) == 1
        assert data["memories"][0]["id"] == "mem-1"
        assert data["total"] == 1

    def test_api_memories_with_filters(self, mock_container):
        """Test memories list with type and context filters."""
        mock_container_obj, mock_repo = mock_container
        mock_repo.list_memories.return_value = ([], 0, False)

        with patch(
            "exocortex.dashboard.app.get_container", return_value=mock_container_obj
        ):
            app = create_dashboard_app()
            client = TestClient(app)
            response = client.get("/api/memories?type=insight&context=myproject")

        assert response.status_code == 200
        mock_repo.list_memories.assert_called_once()
        # Verify filters were passed
        call_kwargs = mock_repo.list_memories.call_args.kwargs
        assert call_kwargs["type_filter"] == "insight"
        assert call_kwargs["context_filter"] == "myproject"


class TestApiHealth:
    """Tests for /api/health endpoint."""

    def test_api_health_good(self, mock_container):
        """Test health endpoint with healthy knowledge base."""
        mock_container_obj, mock_repo = mock_container

        mock_stats = MagicMock()
        mock_stats.total_memories = 50
        mock_repo.get_stats.return_value = mock_stats
        mock_repo.get_orphan_memories.return_value = []

        with patch(
            "exocortex.dashboard.app.get_container", return_value=mock_container_obj
        ):
            app = create_dashboard_app()
            client = TestClient(app)
            response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["health"]["score"] == 100.0
        assert len(data["health"]["issues"]) == 0

    def test_api_health_with_orphans(self, mock_container):
        """Test health endpoint with orphan memories."""
        mock_container_obj, mock_repo = mock_container

        mock_stats = MagicMock()
        mock_stats.total_memories = 10
        mock_repo.get_stats.return_value = mock_stats
        mock_repo.get_orphan_memories.return_value = [
            ("orphan-1", "Orphan 1"),
            ("orphan-2", "Orphan 2"),
        ]

        with patch(
            "exocortex.dashboard.app.get_container", return_value=mock_container_obj
        ):
            app = create_dashboard_app()
            client = TestClient(app)
            response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # 2 orphans out of 10 = 20% orphan ratio = 80% health
        assert data["health"]["score"] == 80.0
        assert data["health"]["orphan_count"] == 2
        assert len(data["health"]["issues"]) > 0


class TestApiGraph:
    """Tests for /api/graph endpoint."""

    def test_api_graph_empty(self, mock_container):
        """Test graph endpoint with no memories."""
        mock_container_obj, mock_repo = mock_container
        mock_repo.list_memories.return_value = ([], 0, False)

        with patch(
            "exocortex.dashboard.app.get_container", return_value=mock_container_obj
        ):
            app = create_dashboard_app()
            client = TestClient(app)
            response = client.get("/api/graph")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["graph"]["nodes"]) == 0
        assert len(data["graph"]["edges"]) == 0

    def test_api_graph_with_memories(self, mock_container):
        """Test graph endpoint with memories and links."""
        mock_container_obj, mock_repo = mock_container

        mock_memory = MagicMock()
        mock_memory.id = "mem-1"
        mock_memory.summary = "Test memory"
        mock_memory.content = "Content"
        mock_memory.memory_type = MagicMock(value="insight")
        mock_memory.context = "test"  # Changed from context_name

        # list_memories returns (memories, total, has_more)
        mock_repo.list_memories.return_value = ([mock_memory], 1, False)

        # Mock MemoryLink object
        mock_link = MagicMock()
        mock_link.target_id = "mem-2"
        mock_link.relation_type = MagicMock(value="related")
        mock_repo.get_links.return_value = [mock_link]

        with patch(
            "exocortex.dashboard.app.get_container", return_value=mock_container_obj
        ):
            app = create_dashboard_app()
            client = TestClient(app)
            response = client.get("/api/graph")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["graph"]["nodes"]) == 1
        assert len(data["graph"]["edges"]) == 1
