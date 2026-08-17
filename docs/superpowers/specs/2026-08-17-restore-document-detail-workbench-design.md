# Restore Document Detail Workbench

## Goal

Restore the document inspection capabilities removed during the authenticated workspace refactor while preserving the current sidebar, login flow, per-user document isolation, conversations, and authenticated API gateway.

## Scope

The document detail view will regain:

- A horizontal chunk rail built from the `chunks` returned by the existing document detail API.
- An original-source pane. PDF documents use the authenticated original-file proxy and follow the selected chunk's page. Text and Markdown documents show their source text.
- Three Markdown pane modes: rendered Markdown, raw Markdown, and the currently selected chunk.
- Chunk metadata including its display number, page or section, and character range when available.

The migration will not change authentication, document ownership, storage keys, chat behavior, upload behavior, or Python API contracts.

## Component Design

`Workspace` continues to own navigation and document loading. The detail workbench moves into a focused client component so the workspace does not absorb Markdown parsing and chunk-selection concerns.

The detail component owns two pieces of local state:

- The selected chunk's array position. Array position is used rather than `chunk.index` so sparse or non-zero-based backend indexes cannot select the wrong item.
- The active Markdown mode: `rendered`, `raw`, or `chunk`.

When the selected chunk has a page number, the PDF source URL receives `#page=<page>`. Changing chunks therefore updates the browser PDF viewer's page target. When a document changes, selection returns to the first chunk and rendered mode.

## Markdown Rendering

The restored renderer uses React elements and treats all document content as text. It does not inject document HTML. It supports the existing first-version feature set: headings, paragraphs, unordered and ordered lists, blockquotes, fenced code blocks, horizontal rules, inline code, bold text, and simple pipe tables.

The raw mode uses a code-style `pre` block. The chunk mode shows only the selected chunk and its available location metadata. Empty Markdown and empty chunk collections receive explicit empty states.

## Visual Direction

The page retains the current restrained zinc-and-blue workspace styling. The chunk rail is the signature element: a compact document ruler above the two-pane workbench. Selected chunks use the existing blue accent and visible keyboard focus. On wide screens, source and parsed views sit side by side; on smaller screens, they stack without hiding any mode.

## Data Flow and Errors

The existing `GET /api/documents/:id` request remains the sole detail data source and continues to return metadata, Markdown, and chunks after ownership checks. The existing `/api/documents/:id/original` proxy remains the source for PDF bytes. Existing workspace notices continue to report detail-loading failures.

## Testing

Frontend regression tests will verify:

- The chunk rail renders API chunks and changes the selected chunk.
- Selecting a paged chunk changes the PDF target page.
- Rendered, raw, and current-chunk modes expose their respective content.
- A sparse backend chunk index does not break selection.

The final verification will run the focused regression tests, the complete web test suite, type checking or production build, and a visual check of the document detail page when the local application can be started.
