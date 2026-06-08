# Research: Comments Pagination

## R1: Google Drive Comments API Pagination

**Decision**: Use `pageToken`/`nextPageToken` cursor-based pagination with `pageSize=100` per request.

**Rationale**: The Google Drive API v3 `comments.list` endpoint supports cursor-based pagination via `pageToken` and returns `nextPageToken` when more results exist. The maximum `pageSize` is 100. Using 100 minimizes the number of API round-trips.

**Alternatives considered**:
- Smaller `pageSize` (e.g., 20): More API calls, no benefit. Rejected.
- Offset-based pagination: Not supported by the Drive Comments API. N/A.

## R2: Environment Variable Pattern

**Decision**: Use `os.getenv("WORKSPACE_MCP_COMMENTS_MAX", "100")` in `core/comments.py`, following the existing pattern in `core/config.py`.

**Rationale**: The project uses `os.getenv` with `WORKSPACE_MCP_*` prefixed names (e.g., `WORKSPACE_MCP_PORT`, `WORKSPACE_MCP_BASE_URI`). The same pattern keeps configuration consistent.

**Alternatives considered**:
- Centralize in `core/config.py`: Adds an import dependency for a single value. The env var is only used in `core/comments.py`. Rejected for simplicity.
- Use a config file: Overengineered for a single setting. Rejected.

## R3: Parameter Threading Through Factory

**Decision**: Add `max_comments: int | None = None` parameter to each `list_comments` function variant inside `create_comment_tools`, and pass it through to `_read_comments_impl`.

**Rationale**: The factory creates three variants of `list_comments` (one per `file_id_param` branch). Each variant needs the parameter in its signature so MCP clients can pass it. The shared `_read_comments_impl` does the actual pagination work.

**Alternatives considered**:
- Single generic function with `**kwargs`: Loses explicit parameter documentation for MCP tool schema. Rejected.
- Refactor factory to eliminate branching: Scope creep, changes too much of the existing structure. Rejected.

## R4: Test Strategy

**Decision**: Unit tests using `unittest.mock.AsyncMock` to mock the Google Drive service. Test class in `tests/core/test_comments.py`.

**Rationale**: The project uses pytest with plain `assert` statements and class-based test organization (see `tests/core/test_attachment_storage.py`). No existing comment tests exist. Mocking the Drive service is necessary since integration tests require Google API credentials.

**Alternatives considered**:
- Integration tests with real API: Requires credentials, flaky, slow. Not appropriate for a pagination fix. Rejected.
- No tests: Upstream has a testing checklist in PR template. Tests demonstrate correctness. Rejected.
