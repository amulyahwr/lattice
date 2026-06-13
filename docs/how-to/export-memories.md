# Export Your Memories

Your atoms are already in a portable format — plain `.md` files with YAML frontmatter. There's no special export step.

## Your atom store

```bash
ls ~/.lattice/
```

Every `.md` file is an atom. They're human-readable, git-trackable, and can be opened in any text editor.

## Backup

Since atoms are plain files, any file backup approach works:

```bash
# copy to an external drive
cp -r ~/.lattice ~/Backup/lattice-backup-$(date +%Y%m%d)

# or use rsync
rsync -av ~/.lattice/ ~/Backup/lattice/

# or git-track your atom store
cd ~/.lattice && git init && git add . && git commit -m "backup"
```

## Migrate to a new machine

Copy `LATTICE_DIR` to the new machine:

```bash
rsync -av ~/.lattice/ newmachine:~/.lattice/
```

Install Lattice on the new machine, set `LATTICE_DIR=~/.lattice`, and start the daemon. The graph will rebuild automatically on startup if the sidecars are out of sync.

## Filter and export

Use standard Unix tools to filter atoms:

```bash
# all preference atoms
grep -l "kind: preference" ~/.lattice/*.md

# atoms about coffee
grep -rl "coffee" ~/.lattice/*.md

# atoms from Telegram
grep -l "source_id: telegram" ~/.lattice/*.md
```

## Archival (coming soon)

STORY-044 (planned): `lattice archive` will move old or low-quality atoms to `LATTICE_DIR/archive/` without deleting them. Archived atoms are excluded from selection but remain on disk and can be restored.
