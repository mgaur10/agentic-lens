"""
High-quality training examples for calibrating the Supervisor Agent router.

Use these to:
- Test the router (backend supervisor or ADK router)
- Fine-tune the Supervisor's system prompt (e.g. Gemini routing prompt)

Nuance:
- eng_lead (Engineering): Building infrastructure, Terraform/Python code, architecture planning.
- xray_manager (X-Ray): Granting access, IAM, permissions, secrets, auditing, security policies.
- events: Conference schedule, speakers, logistics (RAG-backed).
- chat: General knowledge, coding concepts (non-infra), fallback, chitchat.
"""

from typing import List, Tuple

# Backend supervisor uses: "Engineering", "Events", "X-Ray", "Chat"
# ADK router uses underscore names: eng_lead, events, xray_manager, chat
BACKEND_TO_ADK = {
    "Engineering": "eng_lead",
    "Events": "events",
    "X-Ray": "xray_manager",
    "Chat": "chat",
}

# (user_query, expected_backend_department)
SUPERVISOR_TRAINING_EXAMPLES: List[Tuple[str, str]] = [
    # ----- Engineering Squad (eng_lead) -----
    (
        "Write Terraform code to deploy a private GKE Autopilot cluster in us-west1 with a VPC network.",
        "Engineering",
    ),
    (
        "I need a high-availability architecture for a 3-tier web application using Cloud Run and Cloud SQL.",
        "Engineering",
    ),
    (
        "Generate a Python script to upload a file to Google Cloud Storage using the official client library.",
        "Engineering",
    ),
    (
        "How do I set up a Cloud Function that triggers on a Pub/Sub message? Give me the main.tf.",
        "Engineering",
    ),
    # ----- X-Ray (xray_manager) -----
    (
        "Grant read-only access to the 'finance-data' bucket for the user 'alice@example.com'.",
        "X-Ray",
    ),
    (
        "Create a custom IAM role for a developer who needs to restart Cloud SQL instances but not delete them.",
        "X-Ray",
    ),
    (
        "Audit my project for any service accounts that have 'Owner' or 'Editor' permissions.",
        "X-Ray",
    ),
    (
        "I need to rotate the GitHub Personal Access Token stored in Secret Manager. How do I do that securely?",
        "X-Ray",
    ),
    # ----- Events -----
    (
        "When is the keynote speech by the Google Cloud CEO, and where is it located?",
        "Events",
    ),
    (
        "Are there any sessions about 'AI Agents' or 'Multi-Agent Systems' on Day 2?",
        "Events",
    ),
    (
        "Who is speaking at the 'Secure Supply Chain' panel?",
        "Events",
    ),
    (
        "Is lunch provided for attendees? If so, what time?",
        "Events",
    ),
    # ----- Chat -----
    (
        "Hi, who are you and what can this platform do?",
        "Chat",
    ),
    (
        "Explain the difference between a Python list and a tuple.",
        "Chat",
    ),
    (
        "Write a haiku about artificial intelligence.",
        "Chat",
    ),
    # ----- Second set: Edge cases, secondary responsibilities (Questions 16–30) -----
    # ----- Engineering: Resource provisioning, CI/CD, debugging, architecture -----
    (
        "I need a Cloud Memorystore Redis instance in the us-east4 region.",
        "Engineering",
    ),
    (
        "Write a cloudbuild.yaml file that builds a Docker image and pushes it to Artifact Registry.",
        "Engineering",
    ),
    (
        "My Python script is failing to connect to BigQuery. Can you check this code snippet?",
        "Engineering",
    ),
    (
        "Architect a serverless image processing pipeline using Cloud Run and Eventarc.",
        "Engineering",
    ),
    # ----- X-Ray: Identity, access control, encryption (CMEK), compliance, access troubleshooting -----
    (
        "Create a Service Account for my GitLab runner and give it minimal permissions to deploy to App Engine.",
        "X-Ray",
    ),
    (
        "Generate an Organization Policy to enforce public access prevention on all storage buckets.",
        "X-Ray",
    ),
    (
        "I need to encrypt my SQL database using a Customer Managed Encryption Key (CMEK). How do I set up the key ring?",
        "X-Ray",
    ),
    (
        "Why am I getting a '403 Forbidden' error when trying to list objects in the 'backup-prod' bucket?",
        "X-Ray",
    ),
    # ----- Events: Logistics, content discovery, speaker details -----
    (
        "What time does registration open on Day 1, and where do I pick up my badge?",
        "Events",
    ),
    (
        "Are there any hands-on workshops or labs related to Kubernetes security?",
        "Events",
    ),
    (
        "Can you summarize the bio for speaker 'Dr. Jane Smith'?",
        "Events",
    ),
    (
        "Is there a designated area for ride-share pickups (Uber/Lyft)?",
        "Events",
    ),
    # ----- Events: Concierge stress-test (RAG + guardrails) -----
    (
        "What time does the opening keynote start on Day 1, and which room is it in?",
        "Events",
    ),
    (
        "Who are the speakers for the session titled 'Future of AI Agents'?",
        "Events",
    ),
    (
        "Where is the registration desk located and what are the opening hours?",
        "Events",
    ),
    (
        "I am interested in security. List all sessions related to IAM or Zero Trust.",
        "Events",
    ),
    (
        "Are there any hands-on workshops or labs available for developers?",
        "Events",
    ),
    (
        "What tracks are available on Day 2?",
        "Events",
    ),
    (
        "I have a lunch meeting from 12:00 PM to 1:00 PM. What sessions will I miss?",
        "Events",
    ),
    (
        "Is there a shuttle bus from the airport to the venue?",
        "Events",
    ),
    (
        "Who is speaking about AWS Lambda?",
        "Events",
    ),
    (
        "What is the weather going to be like during the conference?",
        "Events",
    ),
    # ----- Chat: General tech, greetings, out-of-scope, writing assistance -----
    (
        "Good morning! I'm ready to start working on the project.",
        "Chat",
    ),
    (
        "What is the difference between TCP and UDP protocols?",
        "Chat",
    ),
    (
        "Draft a quick email to my manager explaining why I need budget for this tool.",
        "Chat",
    ),
]


def get_expected_adk_target(backend_department: str) -> str:
    """Return the ADK target agent name for a given backend department."""
    return BACKEND_TO_ADK.get(backend_department, "chat")


def get_all_examples_for_routing_tests():
    """Return list of (query, expected_backend, expected_adk) for tests."""
    return [
        (query, expected_backend, get_expected_adk_target(expected_backend))
        for query, expected_backend in SUPERVISOR_TRAINING_EXAMPLES
    ]
