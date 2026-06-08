# Feature Specification: Comments Pagination

**Feature Branch**: `001-comments-pagination`  
**Created**: 2026-06-08  
**Status**: Draft  
**Input**: User description: "Add pagination support to comment reading tools so all comments are returned instead of only the first page"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retrieve All Comments from a Large Document (Priority: P1)

A user asks an AI assistant to read comments from a Google Doc that has 50+ comments. The assistant calls the `list_document_comments` tool. Today, only the first 20 comments are returned silently, giving the user an incomplete picture. With this fix, all comments are returned automatically, up to a configurable maximum.

**Why this priority**: This is the core bug fix. Users currently receive truncated results without any indication that comments are missing, leading to incorrect analysis and missed feedback.

**Independent Test**: Can be fully tested by creating a document with more than 20 comments and verifying that all comments are returned by the tool.

**Acceptance Scenarios**:

1. **Given** a Google Doc with 50 comments, **When** a user calls `list_document_comments` with no parameters, **Then** all 50 comments are returned in a single response.
2. **Given** a Google Doc with 150 comments, **When** a user calls `list_document_comments` with default settings, **Then** the first 100 comments are returned (server-wide default limit).
3. **Given** a Google Doc with 150 comments, **When** a user calls `list_document_comments` with `max_comments` set to 150, **Then** all 150 comments are returned.

---

### User Story 2 - Consistent Behavior Across All App Types (Priority: P1)

A user reads comments from Sheets and Slides documents, not just Docs. The pagination behavior must be identical across all three document types since they share the same underlying mechanism.

**Why this priority**: Equal to P1 because partial coverage would create inconsistent behavior across tools that users expect to work the same way.

**Independent Test**: Can be tested by verifying `list_spreadsheet_comments` and `list_presentation_comments` return the same paginated results as `list_document_comments` for documents with more than 20 comments.

**Acceptance Scenarios**:

1. **Given** a Google Sheet with 30 comments, **When** a user calls `list_spreadsheet_comments`, **Then** all 30 comments are returned.
2. **Given** a Google Slides presentation with 40 comments, **When** a user calls `list_presentation_comments`, **Then** all 40 comments are returned.

---

### User Story 3 - Server-Wide Default Configuration (Priority: P2)

A server administrator wants to set a default maximum comment limit for all tools to prevent excessive API usage. They configure an environment variable, and all comment-reading tools respect this limit unless overridden per-call.

**Why this priority**: Important for operational control but not required for the core fix to work. The hardcoded fallback of 100 provides a reasonable default without configuration.

**Independent Test**: Can be tested by setting the environment variable and verifying all three comment tools respect the configured limit.

**Acceptance Scenarios**:

1. **Given** the `WORKSPACE_MCP_COMMENTS_MAX` environment variable is set to 50, **When** a user calls any comment-reading tool without specifying `max_comments`, **Then** at most 50 comments are returned.
2. **Given** the environment variable is set to 50 and a user calls with `max_comments` set to 200, **When** the tool executes, **Then** 200 comments are returned (per-call override wins).
3. **Given** no environment variable is set and no `max_comments` parameter is provided, **When** a user calls any comment-reading tool, **Then** at most 100 comments are returned (hardcoded fallback).

---

### Edge Cases

- What happens when a document has zero comments? The tool should return an empty list, same as today.
- What happens when `max_comments` is set to 0? The tool should return an empty list (interpreted as "no comments requested").
- What happens when the API returns fewer comments than `max_comments`? The tool should return all available comments without error.
- What happens when the API returns an error mid-pagination? The tool should re-raise the API error to the caller, consistent with existing error handling patterns in the project. Partial results collected before the error are discarded.
- What happens when `max_comments` is negative? The tool should treat it as invalid input and use the default value.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All three comment-reading tools (Docs, Sheets, Slides) MUST return all available comments up to a configured maximum, not just the first page of results.
- **FR-002**: Each comment-reading tool MUST accept an optional `max_comments` parameter that limits the total number of comments returned.
- **FR-003**: The system MUST support a server-wide default maximum via the `WORKSPACE_MCP_COMMENTS_MAX` environment variable, with a hardcoded fallback of 100 when the variable is not set.
- **FR-004**: A per-call `max_comments` parameter MUST override the server-wide default when provided.
- **FR-005**: The system MUST handle pagination transparently, combining results from multiple pages into a single response for the caller.
- **FR-006**: The `max_comments` parameter MUST be optional with no change to existing tool signatures for callers who do not use it.

### Key Entities

- **Comment**: A comment on a Google Workspace document, including its content, author, and any replies. Retrieved via the Google Drive Comments API.
- **Comment Tool**: One of three MCP tools (`list_document_comments`, `list_spreadsheet_comments`, `list_presentation_comments`) that retrieve comments for a specific document type.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users receive all comments (up to the configured limit) from documents with more than 20 comments, eliminating silent truncation.
- **SC-002**: All three comment tools (Docs, Sheets, Slides) behave identically with respect to pagination and limits.
- **SC-003**: Existing callers that do not pass `max_comments` continue to work without modification, receiving up to 100 comments by default instead of 20.
- **SC-004**: Server administrators can configure the default comment limit via a single environment variable.

## Clarifications

### Session 2026-06-08

- Q: Should mid-pagination API errors return partial results or re-raise? → A: Re-raise the error; discard partial results. Consistent with standard error propagation patterns.

## Assumptions

- The Google Drive Comments API supports cursor-based pagination via `nextPageToken` and `pageToken` parameters, with a maximum of 100 results per page.
- The `WORKSPACE_MCP_*` naming convention for environment variables is an established pattern in this project.
- All three comment tools (Docs, Sheets, Slides) share a single implementation function, so fixing it once applies to all three.
- The existing error handling patterns in the project should be followed for any API errors during pagination.
- Tests should follow existing test patterns in the upstream repository if they exist.
