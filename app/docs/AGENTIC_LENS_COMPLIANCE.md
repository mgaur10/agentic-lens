# Agentic-Prism — Compliance & Constraints (Non-Negotiable)

This document defines the **strict requirements** for the Agentic-Prism cloud-native Agent Architecture. All generated code must adhere; violations (e.g., use of Service Account JSON keys) must be corrected immediately.

---

## 1. Technology Stack

| Layer | Requirement |
|-------|-------------|
| **Runtime** | Vertex AI Agent Engine (Fully Managed) |
| **Framework** | Google Cloud ADK v1.18+ |
| **Language** | Python 3.12+ |
| **Infrastructure** | Terraform (Security & IAM only) |

---

## 2. Security Mandates (The Fortress)

### Identity: AGENT_IDENTITY Only

- **FORBIDDEN:** Creating or downloading Service Account JSON keys. No `GOOGLE_APPLICATION_CREDENTIALS` pointing to a key file in project code.
- **REQUIRED:** IAM roles bound to Agent Identity principals:  
  `principal://agents.global.org-{ORG_ID}.system.id.goog/.../agents/{name}`  
  (See `security/iam/agent_permissions.tf`.)

### Encryption

- **CMEK** (Customer-Managed Encryption Keys) for all Session and Memory storage.  
  See `security/kms.tf` and `engine/session_config.yaml` (kms_key_id).

### Gatekeeper

- **Model Armor** must scan every prompt **before** the Supervisor processes it.  
  Supervisor flow: Security Gate (Model Armor) → Routing (Gemini 2.5) → Dispatch.

---

## 3. Architecture (The Prism)

- **Supervisor (The Brain):** Gemini 2.5 Pro (Thinking Model); routes intents.
- **Agents (Departments):**
  - **Engineering:** Builder (Scout → Coder → Sentinel loop).
  - **X-Ray:** Auditor (Dual-Level IAM Analysis).
  - **Events:** Researcher (Vertex Search RAG).
  - **Chat:** Fallback (Gemini 1.5 Pro).
- **UI (Control Center):** 3-Column: Sidebar (Controls) | Chat (Main) | Glass Box (Live Logs).  
  Memory: Managed by Agent Engine Session ID (no local key storage).

---

## 4. Current Status

- [x] ADK structure (`adk.yaml`, `identity_mode: AGENT_IDENTITY`).
- [x] Security foundation (`security/`: Model Armor, IAM, CMEK).
- [ ] Agent logic (`agents/`) — in progress.
- [ ] Frontend (`client/`) — in progress.

---

**If any generated code violates these rules (e.g., uses a JSON key or a service account key file), stop and correct it immediately.**
