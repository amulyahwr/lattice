# Auto-start on Login (macOS)

Use launchd to have the Lattice daemon start automatically when you log in to your Mac. This means Lattice is always running — you don't need to start it manually.

## Step 1: Copy the plist template

The repo includes a plist template in `extras/dev.lattice.daemon.plist`. Copy it to `~/Library/LaunchAgents/`:

```bash
cp extras/dev.lattice.daemon.plist ~/Library/LaunchAgents/dev.lattice.daemon.plist
```

## Step 2: Edit the plist

Open `~/Library/LaunchAgents/dev.lattice.daemon.plist` in a text editor and replace the placeholder values:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.lattice.daemon</string>

    <key>ProgramArguments</key>
    <array>
        <string>/path/to/lattice-repo/.venv/bin/lattice-daemon</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>LLM_PROVIDER</key><string>ollama</string>
        <key>LLM_MODEL</key><string>gemma4</string>
        <key>LLM_API_KEY</key><string><!-- leave empty for Ollama --></string>
        <key>LLM_BASE_URL</key><string><!-- leave empty for Ollama --></string>
        <key>LATTICE_DIR</key><string>/Users/yourname/.lattice</string>
        <key>LATTICE_DENSE_SEEDS</key><string>1</string>
    </dict>

    <key>ProcessType</key>
    <string>Background</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/yourname/.lattice/launchd.stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/yourname/.lattice/launchd.stderr.log</string>
</dict>
</plist>
```

Replace:
- `/path/to/lattice-repo/.venv/bin/lattice-daemon` → actual path
- `/Users/yourname/.lattice` → your actual `LATTICE_DIR`

## Step 3: Load it

```bash
launchctl load ~/Library/LaunchAgents/dev.lattice.daemon.plist
```

## Step 4: Verify

```bash
launchctl list | grep lattice
# Should print: PID  0  dev.lattice.daemon

uv run lattice-daemon status
# Should return: {"ok": true, ...}
```

## Managing the daemon

```bash
# stop
launchctl unload ~/Library/LaunchAgents/dev.lattice.daemon.plist

# restart
launchctl unload ~/Library/LaunchAgents/dev.lattice.daemon.plist
launchctl load ~/Library/LaunchAgents/dev.lattice.daemon.plist

# view logs
tail -f ~/.lattice/launchd.stderr.log
tail -f ~/.lattice/daemon.log
```

## Power Nap

The plist sets `ProcessType=Background`, which tells macOS to keep the daemon alive during Power Nap. This means Telegram messages queued while your laptop is sleeping are processed within seconds of the next Power Nap wake cycle.

## Troubleshooting

**Daemon doesn't start**

```bash
cat ~/.lattice/launchd.stderr.log
```

Common causes:
- Path to `lattice-daemon` binary is wrong (check `.venv/bin/`)
- `LATTICE_DIR` doesn't exist (create it: `mkdir -p ~/.lattice`)
- `LLM_MODEL` not set

**Daemon starts but immediately crashes**

```bash
tail -20 ~/.lattice/daemon.log
```

Usually an env var issue (missing `LLM_MODEL`, invalid `LLM_BASE_URL`).
