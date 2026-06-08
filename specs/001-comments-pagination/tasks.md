# Tasks: Comments Pagination

**Input**: Design documents from `/specs/001-comments-pagination/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md

**Tests**: Included. The upstream project has a testing checklist in the PR template.

**Organization**: Tasks are grouped by user story. US1 and US2 (both P1) are coupled since they modify the same file and function chain, but each is independently verifiable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Core Pagination Logic)

**Purpose**: Add pagination capability to the shared implementation function that all three tools use.

- [x] T001 [US1] Add `max_comments` parameter and pagination loop to `_read_comments_impl` in core/comments.py. The function must: accept `max_comments: int | None = None`, resolve the effective limit to 100 when `None` (env var override added in T005), loop using `pageToken`/`nextPageToken`, set `pageSize=min(100, remaining)` per API call, accumulate comments until limit reached or no more pages, and handle `max_comments <= 0` by returning an empty list. Negative values should fall back to the default (100).

**Checkpoint**: `_read_comments_impl` now paginates, but callers don't yet pass `max_comments`.

---

## Phase 2: User Story 1+2 - Full Pagination Across All Tools (Priority: P1)

**Goal**: Thread `max_comments` through the factory so all three tool types (Docs, Sheets, Slides) expose it as an optional MCP tool parameter.

**Independent Test**: Call `list_document_comments`, `list_spreadsheet_comments`, and `list_presentation_comments` with `max_comments` set and verify the correct number of comments is returned.

### Implementation

- [x] T002 [US1] [US2] Add `max_comments: int | None = None` parameter to the `list_comments` function variant for `document_id` in `create_comment_tools` (core/comments.py, line ~89). Pass it to `_read_comments_impl`.
- [x] T003 [US1] [US2] Add `max_comments: int | None = None` parameter to the `list_comments` function variant for `spreadsheet_id` in `create_comment_tools` (core/comments.py, line ~123). Pass it to `_read_comments_impl`.
- [x] T004 [US1] [US2] Add `max_comments: int | None = None` parameter to the `list_comments` function variant for `presentation_id` in `create_comment_tools` (core/comments.py, line ~153). Pass it to `_read_comments_impl`.

**Checkpoint**: All three tools accept `max_comments` and paginate. Existing callers without `max_comments` get the default (100).

---

## Phase 3: User Story 3 - Server-Wide Default Configuration (Priority: P2)

**Goal**: Allow server administrators to configure the default comment limit via the `WORKSPACE_MCP_COMMENTS_MAX` environment variable.

**Independent Test**: Set the env var and verify all three tools respect it when `max_comments` is not provided per-call.

### Implementation

- [x] T005 [US3] Add env var resolution to `_read_comments_impl` in core/comments.py. When `max_comments` is `None` (not provided by caller), read `os.getenv("WORKSPACE_MCP_COMMENTS_MAX")`, parse as int, fall back to 100. Add `import os` at top of file if not already present.

**Checkpoint**: Full feature works end-to-end with env var, per-call override, and hardcoded fallback.

---

## Phase 4: Unit Tests

**Purpose**: Validate pagination behavior, parameter threading, env var resolution, and edge cases.

- [x] T006 [P] [US1] Add test class `TestReadCommentsImplPagination` to existing tests/core/test_comments.py. Tests: single page returns all comments, multi-page fetches all pages up to limit, `max_comments` stops pagination early when fewer than total available.
- [x] T007 [P] [US2] Add test class `TestCommentToolsFactory` to tests/core/test_comments.py. Tests: all three tool variants (document, spreadsheet, presentation) pass `max_comments` through to `_read_comments_impl`.
- [x] T008 [P] [US3] Add test class `TestCommentsEnvVar` to tests/core/test_comments.py. Tests: env var sets default when `max_comments` not provided, per-call `max_comments` overrides env var, missing env var falls back to 100.
- [x] T009 [P] Add test class `TestCommentsEdgeCases` to tests/core/test_comments.py. Tests: `max_comments=0` returns empty, negative `max_comments` uses default, zero comments returns empty message, mid-pagination API error re-raises.

**Checkpoint**: All tests pass. Run with `pytest tests/core/test_comments.py -v`.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [x] T010 Run `pytest tests/core/test_comments.py -v` and verify all tests pass
- [x] T011 Run existing test suite (`pytest tests/`) to verify no regressions
- [x] T012 Verify the MCP tool schema includes `max_comments` as optional parameter for all three tools

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies, start immediately
- **Phase 2 (US1+US2)**: Depends on T001 completion
- **Phase 3 (US3)**: Depends on T001 completion (can run in parallel with Phase 2)
- **Phase 4 (Tests)**: Depends on Phases 1-3 completion
- **Phase 5 (Polish)**: Depends on Phase 4 completion

### Parallel Opportunities

- T002, T003, T004 modify different code blocks in the same file but are sequential in practice (same file edits)
- T006, T007, T008, T009 add different test classes to the same file, can be written together
- Phase 2 and Phase 3 can run in parallel (T002-T004 and T005 touch different parts of `_read_comments_impl`)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001: Core pagination in `_read_comments_impl`
2. Complete T002-T004: Thread parameter through factory
3. **STOP and VALIDATE**: Test all three tools with large comment sets
4. Ship if ready (env var config is optional)

### Full Delivery

1. T001 → T002-T004 → T005 (all production code)
2. T006-T009 (all tests)
3. T010-T012 (validation)

---

## Notes

- All production changes are in a single file: `core/comments.py`
- All test changes are in a single new file: `tests/core/test_comments.py`
- Total estimated diff: ~80 lines (30 production + 50 test)
- Commit after each phase for clean git history
