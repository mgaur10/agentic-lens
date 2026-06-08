# Reasoning Engine roster (12 agents)

Deploy via repo `./deploy.sh` or `migration/scripts/phase2-agents.sh`.

| Agent | Department | Notes |
|-------|------------|-------|
| supervisor | Routing | Entry for Glass UI; Model Armor in flow |
| chat | Chat | Fallback, competitor pivot |
| eng_lead | Engineering | Orchestrates squad |
| eng_scout | Engineering | Planning / grounding |
| eng_coder | Engineering | Code / Terraform output |
| eng_quality_and_security_reviewer | Engineering | Security review loop |
| events | Events | Vertex AI Search |
| xray_manager | X-Ray | Orchestrator |
| xray_librarian | X-Ray | GitHub / Secret Manager |
| xray_architect | X-Ray | Cloud Asset / state |
| xray_specialist | X-Ray | Firestore `iam_knowledge_base` |
| xray_auditor | X-Ray | QA |

**Identity principal pattern:**

```text
principal://agents.global.org-{ORG_ID}.system.id.goog/resources/aiplatform/projects/{PROJECT_ID}/locations/{REGION}/agents/agentic_lens_{agent_name}
```

Agent folder `eng_lead` → principal `agentic_lens_eng_lead` (see `agentic-lens/security/iam/`).
