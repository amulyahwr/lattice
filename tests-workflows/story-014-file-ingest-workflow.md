# STORY-014 Test Workflow — File Ingest (PDF, Office, Code, Text)

Verifies that any file type can be ingested across all Lattice channels.

---

## Pre-flight

```bash
uv sync --group pdf --group office   # install optional parsers
lattice-start
open http://localhost:7337
```

Check optional deps are installed:

```bash
python3 -c "import pypdf; print('pdf ok')"
python3 -c "import pptx; print('pptx ok')"
python3 -c "import openpyxl; print('xlsx ok')"
python3 -c "import xlrd; print('xls ok')"
```

---

## Phase 1 — Inbox drop (all types)

Drop files directly into `~/.lattice/inbox/`. The daemon picks them up within seconds and moves them to `processed/`.

```bash
# PDF
cp ~/Downloads/report.pdf ~/.lattice/inbox/

# Word document
cp ~/Documents/notes.docx ~/.lattice/inbox/

# PowerPoint
cp ~/Documents/deck.pptx ~/.lattice/inbox/

# Excel
cp ~/Documents/budget.xlsx ~/.lattice/inbox/

# Code file
cp ~/projects/main.py ~/.lattice/inbox/

# Plain text
echo "I prefer dark roast coffee" > ~/.lattice/inbox/coffee.txt
```

**Verify each file was processed:**

```bash
ls ~/.lattice/processed/
lc status
```

Count should increase after each file. Files should appear in `processed/` not `inbox/`.

**Image-only PDF (edge case):**

```bash
# A scanned PDF with no text layer
cp ~/Downloads/scanned_receipt.pdf ~/.lattice/inbox/
```

Expected: moved to `processed/` with a warning in the daemon log, no atoms created:

```bash
grep "image-only\|no text" ~/.lattice/daemon.log | tail -3
```

**Binary file (rejected):**

```bash
cp ~/Downloads/photo.jpg ~/.lattice/inbox/
```

Expected: moved to `processed/` with a warning — no atoms, no crash.

---

## Phase 2 — `lc` CLI

```bash
# PDF
lc ~/Downloads/report.pdf

# Word doc
lc ~/Documents/notes.docx

# PowerPoint
lc ~/Documents/deck.pptx

# Excel spreadsheet
lc ~/Documents/budget.xlsx

# Any code file
lc ~/projects/main.py

# CSV
lc ~/Downloads/data.csv
```

**Expected output for a successful ingest (new content):**
```
Saved. 3 new ideas added to your memory.
```

**Re-upload same file (all duplicates):**
```
Already knew all of this — nothing new.
```

**Re-upload updated file (mix of new + refreshed):**
```
Saved. 2 new ideas picked up, 1 refreshed with newer info.
```

**Image-only PDF:**
```
No text found — PDF may be image-only.
```
Exit code 1 — no atoms created.

**Binary file (photo.jpg):**
```
File appears to be binary (not text-readable): photo.jpg
```
Exit code 1.

**Unsupported format (.ppt old binary):**
```
.ppt (old PowerPoint binary) is not supported. Save as .pptx and try again.
```
Exit code 1.

**Missing optional dep:**
```
python-pptx is required for .pptx files. Install with: uv sync --group office
```
Exit code 1.

---

## Phase 3 — Web UI file upload

Open `http://localhost:7337`. Click the **↑** upload button to the right of the Ask input. Supports single or multiple files (selected together — uploaded in parallel).

**Upload a PDF:**
- Select a `.pdf` file → toast: `"report.pdf — 3 new ideas saved to your memory ✓"`

**Upload a .pptx:**
- Select a `.pptx` file → toast: `"deck.pptx — 5 new ideas saved to your memory ✓"`

**Upload a .xlsx:**
- Select a `.xlsx` file → toast: `"budget.xlsx — 2 new ideas saved to your memory ✓"`

**Upload a .py file:**
- Select any Python file → toast: `"main.py — 2 new ideas saved to your memory ✓"`

**Re-upload same file:**
- Toast: `"report.pdf — already knew all of this. Nothing new."`

**Re-upload with new content:**
- Toast: `"report.pdf — 2 new ideas picked up, 1 refreshed. Your memory grew ✓"`

**Upload multiple files at once:**
- Select several files → one toast per file, uploads run in parallel.

**Upload a binary file (photo.jpg):**
- Toast in red: `"File appears to be binary (not text-readable): photo.jpg"`
- No atoms created.

**Upload an image-only PDF:**
- Toast in red: `"No text found — PDF may be image-only"`

**Daemon offline:**
- Toast in red: `"Upload failed — daemon may be offline."`

---

## Phase 4 — Telegram: Send file as attachment

In Telegram, tap the attachment icon and send a file.

**PDF attachment (new content):**
```
Got it — reading the file now…
report.pdf absorbed ✓ — 3 new ideas picked up.
```

**Re-send same PDF:**
```
Got it — reading the file now…
Already knew all of this — report.pdf is fully up to date. Nothing new.
```

**PDF with mix of new + updated:**
```
Got it — reading the file now…
report.pdf absorbed ✓ — 2 new ideas picked up, 1 refreshed with newer info.
```

**PPTX attachment:**
```
Got it — reading the file now…
deck.pptx absorbed ✓ — 5 new ideas picked up.
```

**XLSX attachment:**
```
Got it — reading the file now…
budget.xlsx absorbed ✓ — 2 new ideas picked up.
```

**Binary attachment (photo.jpg):**
```
Got it — reading the file now…
File appears to be binary (not text-readable): photo.jpg
```

**Image-only PDF:**
```
Got it — reading the file now…
No text found — PDF may be image-only
```

---

## Phase 5 — MCP (`lattice_ingest` with `file_path`)

In a Claude Code session:

```
lattice_ingest:
  file_path: "/Users/you/Downloads/report.pdf"
  metadata:
    source_id: "claude-code"
    observed_at: <now>
```

Expected: `{"atom_ids": ["abc123", ...]}`

**Word doc:**
```
lattice_ingest:
  file_path: "/Users/you/Documents/notes.docx"
```

**File not found:**
```json
{"error": "file not found: /path/to/missing.pdf"}
```

**Missing dep:**
```json
{"error": "python-pptx is required for .pptx files. Install with: uv sync --group office"}
```

---

## Phase 6 — Recall what was ingested

After ingesting a file with known content, recall it:

```bash
# Web UI or Telegram
"What did the report say about Q3 results?"
"What decisions were in the meeting notes?"
"What are the budget figures for next quarter?"
```

Answer should cite the ingested file as the source.

---

## Pass criteria

| Check | Pass if |
|---|---|
| PDF ingested via inbox drop | ✅ atoms created, file in processed/ |
| PPTX ingested with slide numbers in context | ✅ "Slide 1" in source |
| XLSX ingested with sheet names in context | ✅ sheet name visible |
| `.py` / `.csv` / `.md` ingested as text | ✅ atoms created |
| Image-only PDF → warning, no atoms, moved to processed | ✅ graceful skip |
| Binary file → rejected with clear message | ✅ error shown, not stuck in inbox |
| `.ppt` → clear "save as .pptx" message | ✅ helpful error |
| Missing optional dep → install instruction shown | ✅ not a crash |
| `lc path/to/file.pdf` works | ✅ "Saved. N things" |
| Web UI upload button accepts any file | ✅ toast with result |
| Telegram file attachment ingested | ✅ confirmation reply |
| MCP `file_path` ingests local file | ✅ atom_ids returned |
| Recall retrieves content from ingested file | ✅ answer cites file source |

---

## Supported formats quick reference

| Extension | Library needed | Install |
|---|---|---|
| `.pdf` | pypdf | `uv sync --group pdf` |
| `.docx` | python-docx | `uv sync --group docx` |
| `.pptx` | python-pptx | `uv sync --group office` |
| `.xlsx` | openpyxl | `uv sync --group office` |
| `.xls` | xlrd | `uv sync --group office` |
| `.txt`, `.md`, `.py`, `.js`, `.csv`, `.json`, `.yaml`, `.html`, `.rst`, `.go`, … | none | always works |
| `.ppt` (old binary) | ❌ not supported | save as .pptx |
| `.jpg`, `.png`, `.mp4`, … | ❌ binary | rejected gracefully |
