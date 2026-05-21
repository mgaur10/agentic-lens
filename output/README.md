# Migration deploy outputs (local only)

This directory is **gitignored**. Phase scripts write logs and IDs here during deploy.

| File pattern | Created by |
|--------------|------------|
| `phase*-*.log` | `scripts/phase*.sh` |
| `engine-ids.env` | `write-engine-ids-to-env.sh` |
| `glass-ui-url.txt` | `verify-health.sh` |
| `sign-off.md` | copy from `CHECKLIST.md` when done |
| `project-info-*.txt` | `phase0-preflight.sh` |

Do not commit this folder; archive locally if needed for audit.
