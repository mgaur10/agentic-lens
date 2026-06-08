# Pre-push checklist — migration repo

**This folder is the git repository root.** Do not init git in the parent `agentic-prism-v3/` directory.

## 1. Secrets scan

```bash
cd /path/to/migration   # repo root

git grep -E 'AGENTIC_LENS_SUPERVISOR_ENGINE=projects/' -- ':!*.template' ':!LEDGER.md' ':!IMPLEMENTATION.md' ':!PRE_PUSH.md' || true
test ! -f app/.env && test ! -f config/migration.env && echo "OK: no local secrets in tree"
```

Only templates (`config/*.template`, `app/env.template`, etc.) — no live engine IDs or PATs.

## 2. Bundle size (no venvs)

```bash
du -sh app/agentic-lens/.venv app/.venv 2>/dev/null   # should be absent or untracked
```

Expected repo size: **~2–5 MB** tracked. If `git count-objects` shows hundreds of MB, a `.venv/` slipped in.

Maintainers refreshing `app/` from the full monorepo: run `sync-app-bundle.sh` from a checkout that has the parent tree (optional; not required at deploy destinations).

## 3. What to commit

| Include | Exclude |
|---------|---------|
| `scripts/`, docs, `config/*.template`, `artifacts/` | `output/*` logs |
| `app/` source (agents, Glass UI, infra scripts) | `app/.env`, `app/versions.env` |
| `sync-app-bundle.sh` | `**/.venv/`, `**/.terraform/`, `*.tfstate` |
| | `config/migration.env` |

## 4. Push

```bash
cd /path/to/migration
git init    # once
git add -A
git status  # verify no .env / .venv / tfstate
git commit -m "Agentic Prism greenfield migration pack (agentic-lens)."
git remote add origin <your-remote-url>
git push -u origin main
```

## 5. At destination (after clone)

```bash
cp config/versions.env.template app/versions.env
cp config/env.template app/.env
cp config/migration.env.example config/migration.env
# edit the three files, then:
./scripts/phase0-preflight.sh
```

See [IMPLEMENTATION.md](./IMPLEMENTATION.md) and [LEDGER.md](./LEDGER.md).
