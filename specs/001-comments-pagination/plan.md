# Implementation Plan: Comments Pagination

**Branch**: `001-comments-pagination` | **Date**: 2026-06-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-comments-pagination/spec.md`

## Summary

Add pagination support to the `_read_comments_impl` function in `core/comments.py` so all three comment-listing tools (Docs, Sheets, Slides) return all comments up to a configurable maximum instead of only the first API page (20 comments). Introduce an optional `max_comments` parameter threaded through the factory, with a server-wide default via the `WORKSPACE_MCP_COMMENTS_MAX` environment variable (fallback: 100).

## Technical Context

**Language/Version**: Python >=3.10
**Primary Dependencies**: fastmcp, google-api-python-client, mcp
**Storage**: N/A (read-only from Google Drive API)
**Testing**: pytest (plain assert, class-based tests, unittest.mock for async mocking)
**Target Platform**: Linux/macOS server (MCP server process)
**Project Type**: MCP server (Google Workspace integration)
**Performance Goals**: N/A (pagination adds minimal latency, bounded by API round-trips)
**Constraints**: Must not break existing tool signatures for callers that omit `max_comments`
**Scale/Scope**: Single file change (`core/comments.py`) plus additions to existing test file (`tests/core/test_comments.py`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution is template-only (not project-specific). No gates to evaluate.

## Project Structure

### Documentation (this feature)

```text
specs/001-comments-pagination/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
core/
├── comments.py          # Primary change: _read_comments_impl + factory updates
├── config.py            # Reference only (env var pattern)
└── ...

tests/
└── core/
    └── test_comments.py # Existing file: add pagination unit tests
```

**Structure Decision**: This is a single-module change within an existing flat project structure. No new directories needed. The test file follows the existing `tests/core/test_*.py` convention.

## Implementation Approach

### Change 1: Add pagination to `_read_comments_impl` (core/comments.py:204)

Current behavior: Single API call with no `pageSize`, returns only the default page (20 comments).

New behavior:
- Accept `max_comments: int | None = None` parameter
- When `max_comments` is `None` (not provided by caller), read `WORKSPACE_MCP_COMMENTS_MAX` env var, fall back to 100
- Validate resolved `max_comments` (negative values fall back to default of 100)
- Loop: call `service.comments().list()` with `pageSize=min(100, remaining)` and `pageToken`
- Accumulate comments until `max_comments` reached or no `nextPageToken`
- Return combined results

### Change 2: Thread `max_comments` through factory (core/comments.py:68)

Each of the three `list_comments` function variants (document, spreadsheet, presentation) needs:
- Add `max_comments: int | None = None` parameter to the function signature
- Pass it to `_read_comments_impl(service, app_name, file_id, max_comments=max_comments)`

This ensures the MCP tool schema exposes `max_comments` as an optional parameter for all three tools.

### Change 3: Unit tests (tests/core/test_comments.py)

New test classes added to existing file, covering:
- Single page (fewer comments than limit): no pagination needed
- Multi-page pagination: verify all pages fetched
- `max_comments` stops pagination early
- `max_comments=0` returns empty
- Negative `max_comments` falls back to default
- Environment variable override
- Mid-pagination API error re-raises
