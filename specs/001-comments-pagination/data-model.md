# Data Model: Comments Pagination

## Entities

### Comment (unchanged)

The comment entity is defined by the Google Drive API and is not modified by this feature. Comments are retrieved via `service.comments().list()` and contain:

- `id`: Unique identifier
- `content`: Comment text
- `author`: Author object with `displayName`
- `createdTime`: ISO timestamp
- `modifiedTime`: ISO timestamp
- `resolved`: Boolean
- `quotedFileContent`: Optional quoted text from the document
- `replies`: List of reply objects

### Configuration (new)

The maximum comments limit follows a resolution chain:

1. Per-call `max_comments` parameter (highest priority)
2. `WORKSPACE_MCP_COMMENTS_MAX` environment variable
3. Hardcoded fallback: 100

No new persistent entities or state are introduced.

## State Transitions

N/A. Comments are read-only in this feature. No lifecycle changes.

## Data Volume

- API returns up to 100 comments per page
- Default limit: 100 comments total (1 API call for most documents)
- Maximum practical limit: bounded by caller-specified `max_comments`
- Each API page request is an independent HTTP round-trip
