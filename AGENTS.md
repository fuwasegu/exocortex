# AI Agent Instructions for Exocortex

## Version Management

### Always Bump Version When Creating PRs

When creating a PR for feature additions or bug fixes, always increment `__version__` in `exocortex/__init__.py`.

```python
# exocortex/__init__.py
__version__ = "X.Y.Z"  # ← Update this
```

**Reason:** In proxy mode, the SSE server runs in the background for extended periods. If the version doesn't change, the old server won't restart and new features won't take effect.

### Versioning Rules

- **Patch (0.0.X)**: Bug fixes, test fixes, documentation updates
- **Minor (0.X.0)**: New features, non-breaking API changes
- **Major (X.0.0)**: Breaking changes

## Testing

### Dashboard Test Considerations

In `tests/unit/test_dashboard.py` API tests, mock `get_container()` and create the app within each test. Creating the app in a fixture will cause it to hang trying to connect to the DB.

```python
# ✅ Good
def test_api_something(self, mock_container):
    mock_container_obj, mock_repo = mock_container
    # Setup mocks...
    with patch("exocortex.dashboard.app.get_container", return_value=mock_container_obj):
        app = create_dashboard_app()
        client = TestClient(app)
        response = client.get("/api/something")

# ❌ Bad - Causes DB hang
@pytest.fixture
def dashboard_client():
    app = create_dashboard_app()  # Tries to connect to DB here
    return TestClient(app)
```

## Proxy Mode Constraints

### Incompatibility with exo_sleep

Do not use `exo_sleep` in proxy mode (`--mode proxy`). The SSE server holds the KùzuDB connection, preventing the Dream Worker from accessing it (causes timeout).

## Mocking Guidelines

When mocking in tests, patch functions at the **location where they are used**, not where they are defined:

```python
# ✅ Good - Patch at usage location
@patch("exocortex.server.sleep.spawn_detached_dreamer")

# ❌ Bad - Patch at definition location
@patch("exocortex.worker.process.spawn_detached_dreamer")
```
