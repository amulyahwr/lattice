# Ingest Files

Lattice can extract atoms from documents — PDFs, Word docs, spreadsheets, markdown, and plain text.

## Supported file types

| Extension | Notes |
|-----------|-------|
| `.pdf` | Text extracted via `pypdf` — requires `uv sync --group pdf` |
| `.docx` | Requires `python-docx` |
| `.pptx` | Text from slides |
| `.xlsx`, `.xls` | Cell content as text |
| `.md` | Segmented by headings |
| `.txt` | Plain text |

## Method 1: `lc` CLI

```bash
uv run lc path/to/meeting-notes.md
uv run lc ~/Downloads/report.pdf
```

Prints atom count on completion.

## Method 2: Web UI drag-and-drop

Open [localhost:7337](http://localhost:7337) and drag a file onto the chat area. The web UI uploads it to `/api/ingest-file` and shows the result.

## Method 3: Inbox file drop

Copy any `.md` or `.txt` file into `LATTICE_DIR/inbox/`:

```bash
cp ~/notes/book-summary.md ~/.lattice/inbox/
```

The daemon picks it up within seconds and moves it to `processed/`. This is the best path for automation or bulk ingestion.

!!! note
    Only `.md` and `.txt` files are supported by the inbox watcher. For PDF/docx, use `lc` or the web UI.

## Install PDF support

```bash
uv sync --group pdf
```

Without this, `.pdf` files will fail with a missing dependency error.

## Source ID

For file ingests, the `source_id` field on each atom is set to the filename (e.g., `meeting-notes.md`). This makes it easy to filter atoms by source in the graph.
