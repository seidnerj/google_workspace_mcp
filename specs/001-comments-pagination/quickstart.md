# Quickstart: Comments Pagination

## Setup

```bash
# Clone and install
git clone https://github.com/taylorwilsdon/google_workspace_mcp.git
cd google_workspace_mcp
git checkout 001-comments-pagination
pip install -e ".[dev]"
```

## Run Tests

```bash
pytest tests/core/test_comments.py -v
```

## Key Files

| File | Purpose |
|------|---------|
| `core/comments.py` | Pagination logic in `_read_comments_impl`, factory updates in `create_comment_tools` |
| `tests/core/test_comments.py` | Unit tests for pagination behavior |

## Configuration

Set the server-wide default comment limit (optional):

```bash
export WORKSPACE_MCP_COMMENTS_MAX=200
```

Default is 100 if not set. Per-call `max_comments` parameter overrides the env var.
