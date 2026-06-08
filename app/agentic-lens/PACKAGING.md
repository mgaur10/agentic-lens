# Packaging — zip only `migration/`

The migration pack is **self-contained**. Zip the `migration` folder and transfer it; unzip anywhere and deploy from inside it.

## Create the zip (from parent repo)

```bash
cd /path/to/agentic-prism-v3

# Ensure app/ bundle is current
./migration/sync-app-bundle.sh

cd ..
zip -r agentic-prism-migration.zip agentic-prism-v3/migration \
  -x "agentic-prism-v3/migration/output/*" \
  -x "agentic-prism-v3/migration/config/migration.env" \
  -x "agentic-prism-v3/migration/app/.env" \
  -x "agentic-prism-v3/migration/app/versions.env" \
  -x "agentic-prism-v3/migration/app/.venv/*" \
  -x "agentic-prism-v3/migration/app/agentic-lens/.venv/*" \
  -x "agentic-prism-v3/migration/app/**/*.db"
```

Or from inside the repo:

```bash
./migration/sync-app-bundle.sh
zip -r agentic-prism-migration.zip migration \
  -x "migration/output/*" \
  -x "migration/config/migration.env" \
  -x "migration/app/.env" \
  -x "migration/app/versions.env" \
  -x "migration/app/.venv/*" \
  -x "migration/app/agentic-lens/.venv/*" \
  -x "migration/app/**/.terraform/*" \
  -x "migration/app/**/*.tfstate*" \
  -x "migration/app/**/.agent_engine_config.json" \
  -x "migration/app/**/__pycache__/*" \
  -x "migration/app/**/node_modules/*"
```

**Git push:** init git in `migration/` only; see [PRE_PUSH.md](./PRE_PUSH.md). Same exclusions as the zip.

**Expected size:** ~2–5 MB (without venvs). If the zip is hundreds of MB, you accidentally included `.venv/` or `node_modules/`.

## At destination

```bash
unzip agentic-prism-migration.zip -d /opt/deploy
cd /opt/deploy/migration   # or agentic-prism-v3/migration depending on zip layout

chmod +x scripts/*.sh
# Follow IMPLEMENTATION.md
```

## What must be in the zip

- [ ] `migration/app/deploy.sh`
- [ ] `migration/app/agentic-lens/agents/` (12 agents)
- [ ] `migration/app/agentic-lens/glass_ui/`
- [ ] `migration/app/infra/apply.sh`
- [ ] `migration/IMPLEMENTATION.md`
- [ ] `migration/scripts/run-phased.sh`

Verify:

```bash
test -f migration/app/deploy.sh && test -d migration/app/agentic-lens/agents/supervisor && echo OK
```
