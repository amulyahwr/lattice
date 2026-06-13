# Set Up Browser Extension

The Lattice Chrome extension lets you save any selected text on a web page directly to your atom store with one keyboard shortcut.

!!! note "Status"
    The browser extension is shipped. This guide is a stub — full setup instructions coming soon.

## Quick start

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** → select the `extras/chrome-extension/` directory from the Lattice repo
4. The Lattice icon appears in the toolbar

## Usage

- Select any text on a web page
- Press **⌥⇧S** (Option+Shift+S) — or right-click → **Save to Lattice**
- The extension POSTs to `localhost:7337/api/ingest`

## Requirements

- Lattice daemon must be running
- Chrome (Chromium-based browsers may work but are untested)
