"""
Supervisor Agent (The Prism) - Central Routing Logic
Routes user queries to appropriate agent departments.
"""

import re
import time


class SupervisorAgent:
    """
    The Supervisor (Prism) - Central orchestrator that routes queries
    to the appropriate agent department based on content analysis.
    
    Departments:
    - Engineering: Cloud Architecture and Best Practices, Infrastructure as Code (Terraform), CLI commands (gcloud, kubectl), Debugging and Error resolution, Comparison of Google Cloud services (e.g., Spanner vs SQL)
    - Events: Handles questions about registration, agenda, tickets, pricing, location, and sponsorship/partners
    - X-Ray: Security & IAM Audit (audit, scan, permission, IAM, policy, role, least privilege, code review, security, vulnerability)
    - Chat: General conversation fallback

    Log Color: 🟡 Yellow (Google Yellow #FBBC04)
    """

    # X-Ray (Granting access, IAM, Secrets, Auditing, CMEK, Org Policy, access troubleshooting)
    XRAY_KEYWORDS = [
        'x-ray', 'xray', 'audit', 'scan',
        'permission', 'iam', 'policy', 'role', 'least privilege',
        'github', 'repo', 'git', 'code review',
        'secure', 'security', 'vulnerability',
        'grant', 'access', 'custom role', 'custom iam role',
        'rotate', 'secret manager', 'personal access token', 'token',
        'service accounts', 'owner', 'editor',
        'organization policy', 'public access prevention',
        'cmek', 'customer managed encryption', 'key ring', 'kms',
        '403', 'forbidden',  # access troubleshooting / IAM debugging
    ]

    # Routing keywords for each department
    # PRIORITY 1: Engineering Action Verbs (The "Builder")
    # These action verbs ALWAYS route to Engineering, regardless of topic
    ENGINEERING_ACTION_VERBS = [
        'create', 'deploy', 'build', 'design', 'write code', 'generate', 'configure', 'setup',
        'set up', 'make', 'add', 'remove', 'delete', 'update', 'modify', 'change',
        'implement', 'provision', 'install', 'initialize', 'construct'
    ]
    
    # PRIORITY 2: Events Action Verbs (The "Concierge")
    # These action verbs route to Events when asking about conferences/schedules
    EVENTS_ACTION_VERBS = [
        'who', 'when', 'where', 'what', 'how', 'tell me about', 'find', 'search',
        'are there', 'is there', 'is the'  # "Are there Kubernetes labs?" → Events
    ]
    
    # Noun keywords (checked AFTER action verbs)
    EVENTS_KEYWORDS = [
        'event', 'events', 'schedule', 'schedules', 'agenda', 'agendas',
        'speaker', 'speakers', 'keynote', 'keynotes', 'vegas', 'next', 'next \'26', 'next 26',
        'conference', 'conferences', 'session', 'sessions', 'time', 'where', 'when',
        'ticket', 'tickets', 'party', 'venue', 'venues', 'track', 'tracks',
        'faq', 'faqs', 'registration', 'register', 'attend', 'attendance',
        'workshop', 'workshops', 'expo', 'exhibition', 'booth', 'booths',
        'date', 'dates', 'google next', 'google cloud next', 'gcp next',
        'sponsorship', 'sponsor', 'sponsors', 'sponsoring', 'email', 'contact', 'who',
        'partner opportunities', 'partner opportunity', 'partners', 'partner',
        'exhibitor info', 'exhibitor', 'exhibitors', 'exhibiting',
        'pricing', 'price', 'cost', 'deadline', 'deadlines', 'early bird', 'early-bird',
        'late registration', 'late-registration', 'discount', 'discounts', 'promo', 'promotion',
        # Venue & location (from Events QA learning)
        'mandalay bay', 'convention center', 'las vegas',
        # Pass tiers & event features
        'innovators', 'cloud hero', 'expo hall',
        'keynote', 'lunch', 'panel', 'attendees', 'day 2',
        'badge', 'day 1', 'bio', 'ride-share', 'pick up', 'uber', 'lyft',
        # Concierge stress-test: direct retrieval, logistics, guardrails
        'opening keynote', 'registration desk', 'opening hours', 'room', 'hall',
        'zero trust', 'shuttle', 'airport', 'weather', 'titled',
    ]
    
    ENGINEERING_KEYWORDS = [
        # Infrastructure as Code
        'terraform', 'deployment', 'code', 'vm', 'virtual machine',
        'bucket', 'storage bucket', 'network', 'networks', 'firewall', 'firewalls',
        'policy', 'policies', 'infrastructure', 'secure', 'security', 'iam', 
        'service account', 'compute instance', 'cloud run', 'cloud function', 
        'kubernetes', 'gke', 'vpc', 'subnet', 'load balancer', 'ssl certificate', 
        'domain', 'dns', 'monitoring', 'logging', 'alerting', 'backup', 
        'disaster recovery', 'worker', 'processing',
        # Cloud Architecture and Best Practices
        'architect', 'architecture', 'architectural', 'best practice', 'best practices',
        'design pattern', 'design patterns', 'cloud architecture', 'system design',
        'scalability', 'reliability', 'availability', 'performance', 'optimization',
        # CLI Commands
        'gcloud', 'kubectl', 'gsutil', 'bq', 'gcloud command', 'kubectl command',
        'cli', 'command line', 'terminal', 'shell script',
        # Debugging and Error Resolution
        'debug', 'debugging', 'error', 'errors', 'troubleshoot', 'troubleshooting',
        'fix', 'issue', 'issues', 'problem', 'problems', 'resolve', 'resolution',
        'log', 'logs', 'trace', 'stack trace', 'exception', 'exception',
        # Google Cloud Services (for comparisons and architectural questions)
        'spanner', 'cloud sql', 'bigquery', 'bigtable', 'firestore', 'datastore',
        'cloud storage', 'cloud functions', 'cloud run', 'app engine', 'compute engine',
        'cloud build', 'cloud deploy', 'artifact registry', 'container registry',
        'cloud memorystore', 'memorystore', 'redis',
        'cloudbuild', 'cloud build', 'docker', 'eventarc',
        'cloud pub/sub', 'cloud tasks', 'cloud scheduler', 'cloud endpoints',
        'api gateway', 'cloud iam', 'cloud identity', 'cloud kms', 'secret manager',
        'cloud monitoring', 'cloud logging', 'error reporting', 'trace',
        'cloud armor', 'cloud cdn', 'cloud load balancing', 'cloud dns',
        'cloud vpc', 'cloud interconnect', 'cloud vpn', 'cloud nat',
        # Service Comparison Keywords
        'vs', 'versus', 'compare', 'comparison', 'difference', 'differences',
        'when should', 'when to use', 'when to choose', 'should i use', 'should i choose',
        'which is better', 'which one', 'pros and cons', 'advantages', 'disadvantages',
        'trade-off', 'trade-offs', 'tradeoff', 'tradeoffs', 'recommend', 'recommendation',
        'explain', 'why use', 'why choose', 'what is the difference', 'what\'s the difference'
    ]
    
    def __init__(self):
        """Initialize the Supervisor Agent."""
        self.thinking_delay = 0.5  # Brief pause for routing
    
    def route(self, input_text: str, chat_history: list = None) -> str:
        """
        Route user input to the appropriate agent department.
        Uses conversation history to maintain context and improve routing decisions.
        
        **Routing Priority (STRICT HIERARCHY):**
        1. **Priority 1: Engineering Intent (The "Builder" & "Architect")**
           - Action verbs: Create, Deploy, Build, Write Code, Generate, Configure, Setup
           - Architectural questions: "When should I choose...", "Compare...", "What's the difference...", "Why use...", "Should I use..."
           - Cloud Architecture: Best practices, design patterns, service comparisons
           - CLI commands: gcloud, kubectl, debugging, error resolution
           - Rule: A request to 'Create' or 'Deploy' is ALWAYS Engineering, regardless of topic.
           - Rule: Architectural questions (e.g., "When should I choose Spanner?") are ALWAYS Engineering.
        2. **Priority 2: Events Intent (The "Concierge")**
           - Action verbs: Who, When, Where, What, How (regarding conferences/schedules)
           - Handles questions about registration, agenda, tickets, pricing, location, and sponsorship/partners.
           - Note: Cost/pricing questions about events (e.g., "How much is a ticket?") route to Events.
        3. **Fallback: Noun Keywords**
           - Check noun keywords if no action verbs match
        
        Args:
            input_text: The validated user input
            chat_history: Previous conversation messages for context-aware routing
            
        Returns:
            Department name: "Engineering", "Events", "X-Ray", or "Chat"
        """
        if not input_text:
            return "Chat"
        
        input_lower = input_text.lower()
        
        # Simulate supervisor "thinking" time
        time.sleep(self.thinking_delay)

        # PRIORITY 0: The "Repo Rule" - Explicit Repo Inspection vs Deployment logic
        # Matches cloud router.py guardrails. MUST RUN BEFORE TRAINER/AI.
        
        # 1. Repo Inspection (Read/Analyze) -> X-Ray
        inspection_keywords = ["check file structure", "read this repo", "analyze this repo", "audit this repo", "what is in this repo", "check the file structure"]
        if any(k in input_lower for k in inspection_keywords):
            return "X-Ray"

        # 2. Repo Deployment (Write/Build) -> Engineering
        deployment_keywords = ["deploy this repo", "build this repo", "deploy the repo"]
        if any(k in input_lower for k in deployment_keywords):
            return "Engineering"

        
        # Use learned routing from approved feedback when confidence is high enough
        try:
            from backend.supervisor_trainer import SupervisorTrainer
            trainer = SupervisorTrainer()
            suggested, confidence, _ = trainer.suggest_routing(input_text)
            if confidence >= 0.25 and suggested:
                return suggested
        except Exception:
            pass  # Fall through to keyword-based routing
        
        # PRIORITY 0: Chat-first — greetings, general knowledge (non-infra), creative, writing assistance
        chat_first_phrases = [
            'who are you', 'what can this platform', 'what can you do',
            'list and tuple', 'list vs tuple', 'python list and a tuple',
            'haiku', 'write a haiku',
            'good morning', 'good afternoon', 'good evening', 'ready to start',
            'tcp and udp', 'difference between tcp',
            'draft a quick email', 'draft a quick', 'email to my manager',
        ]
        if any(phrase in input_lower for phrase in chat_first_phrases):
            return "Chat"
        
        # PRIORITY 0.3: Events intent — "who is speaking at ... panel/session" (conference) before X-Ray
        events_speaker_phrases = ['who is speaking', 'speaking at', 'who speaks', 'speakers at']
        events_context_words = ['panel', 'session', 'keynote', 'session about']
        if any(p in input_lower for p in events_speaker_phrases) and any(c in input_lower for c in events_context_words):
            return "Events"
        
        # PRIORITY 0.35: Events content discovery — workshops/labs/sessions (schedule) before X-Ray "security"
        if any(w in input_lower for w in ['workshops', 'labs', 'hands-on']) and any(c in input_lower for c in ['related to', 'about', 'sessions', 'schedule']):
            return "Events"
        
        # PRIORITY 0.4: Events — "list sessions related to X" / "sessions related to IAM/security" (conference content, not IAM ops)
        if any(p in input_lower for p in ['sessions related to', 'list all sessions', 'list sessions', 'sessions about']) and any(c in input_lower for c in ['session', 'schedule', 'track', 'tracks']):
            return "Events"
        
        # PRIORITY 0.5: X-Ray intent (granting access, IAM, audit, rotate, org policy, CMEK, 403) — before Engineering "create"
        xray_intent_phrases = [
            'grant ', 'grant read', 'grant write', 'custom iam role', 'custom role',
            'audit my project', 'rotate ', 'secret manager', 'personal access token',
            'service account', 'minimal permissions', 'organization policy',
            'public access prevention', 'cmek', 'customer managed encryption', 'key ring',
            '403', 'forbidden', 'list objects',
        ]
        if any(phrase in input_lower for phrase in xray_intent_phrases):
            # "Dedicated service account" inside a Terraform / IaC request is builder work (Engineering),
            # not an IAM audit handoff to X-Ray.
            builder_iac_markers = (
                "terraform",
                "write the",
                "write modular",
                "modular terraform",
                "infrastructure as code",
                "iac",
                "hcl",
            )
            if any(m in input_lower for m in builder_iac_markers):
                pass
            elif any(kw in input_lower for kw in self.XRAY_KEYWORDS):
                return "X-Ray"

        # PRIORITY 1: Check Engineering Action Verbs
        # Rule: A request to 'Create' or 'Deploy' is ALWAYS Engineering, regardless of topic.
        # Even if the user mentions "events" (e.g., "Deploy a website for the event"),
        # the *action* is deployment -> Engineering.
        # Use word boundaries to avoid "add" matching inside "address" (Events venue queries)
        for verb in self.ENGINEERING_ACTION_VERBS:
            pattern = r'\b' + re.escape(verb) + r'\b'
            if re.search(pattern, input_lower):
                return "Engineering"
        
        # PRIORITY 1.2: Strong infrastructure/Engineering indicators (from QA learning)
        # Route to Engineering when query clearly mentions GCP infra - avoids "time" in "timeout",
        # "expo" in "exposing", "cost" in infrastructure context routing to Events.
        # Exclude "Google Cloud Next" (event name) and conference content ("labs", "workshops").
        if 'google cloud next' not in input_lower and 'google next' not in input_lower:
            infrastructure_indicators = [
                'cloud run', 'compute engine', 'gke', 'terraform', 'storage bucket',
                'bigquery', 'cloud function', 'cloud storage', 'gcp ', ' gcp'
            ]
            # "Kubernetes" alone can mean conference sessions - only route to Eng if technical intent
            kubernetes_technical = 'kubernetes' in input_lower and any(
                t in input_lower for t in ['write', 'deploy', 'create', 'terraform', 'yaml', 'config']
            )
            if kubernetes_technical or any(indicator in input_lower for indicator in infrastructure_indicators):
                return "Engineering"

        # PRIORITY 1.43: Repository blueprint / topology (read-only, Git-backed) -> X-Ray
        # "Deployment architecture" of a repo must not be classified as Engineering design work.
        repo_markers = (
            "github.com/",
            "this repository",
            "this repo",
            "the repository",
        )
        blueprint_markers = (
            "topology",
            "blueprint",
            "component topology",
            "map out",
            "deployment architecture",
            "architectural blueprint",
            "component",
        )
        if any(m in input_lower for m in repo_markers) and any(
            b in input_lower for b in blueprint_markers
        ):
            return "X-Ray"

        # PRIORITY 1.44: Billing & discount models (SUD / CUD) — Chat (Ambassador), not Engineering
        billing_topics = (
            "sustained use discount",
            "committed use discount",
            " sustained use ",
            " committed use ",
            " spend-based discount",
            " sud ",
            " suds ",
            " cud ",
            " cuds ",
        )
        billing_questions = (
            "difference between",
            "what is the difference",
            "what's the difference",
            "when should",
            "when to use",
            "compare",
            "comparison",
            "versus",
            " vs ",
            " vs.",
            "explain",
        )
        if any(t in input_lower for t in billing_topics) and any(
            q in input_lower for q in billing_questions
        ):
            return "Chat"

        # PRIORITY 1.5: Check for Architectural Questions
        # Rule: Architectural questions (e.g., "When should I choose Spanner?", "Compare X vs Y")
        # are ALWAYS Engineering, not Events or Chat.
        architectural_keywords = [
            'when should', 'when to use', 'when to choose', 'should i use', 'should i choose',
            'which is better', 'which one', 'compare', 'comparison', 'vs ', 'versus',
            'what\'s the difference', 'what is the difference', 'difference between',
            'pros and cons', 'advantages', 'disadvantages', 'trade-off', 'trade-offs',
            'recommend', 'recommendation', 'explain', 'why use', 'why choose',
            'best practice', 'best practices', 'architecture', 'architectural', 'design pattern'
        ]
        if any(keyword in input_lower for keyword in architectural_keywords):
            # Additional check: Make sure it's not about Events (e.g., "When should I register?")
            # Only exclude if it's clearly about Events AND contains Events-specific keywords
            events_specific_keywords = ['register', 'registration', 'ticket', 'conference', 'event', 'schedule', 'agenda', 'speaker', 'venue', 'sponsorship', 'partner', 'convention center', 'mandalay bay', 'address']
            # If it contains Cloud/Engineering keywords, prioritize Engineering even if Events keywords are present
            has_engineering_keywords = any(keyword in input_lower for keyword in ['cloud', 'gcp', 'google cloud', 'vm', 'instance', 'bucket', 'function', 'run', 'terraform', 'kubernetes', 'gke'])
            if not any(events_keyword in input_lower for events_keyword in events_specific_keywords) or has_engineering_keywords:
                return "Engineering"

        # PRIORITY 1.7: X-Ray (Security & IAM Audit)
        # Route to X-Ray for audit, IAM, permissions, code review, security scan
        if any(keyword in input_lower for keyword in self.XRAY_KEYWORDS):
            return "X-Ray"

        # PRIORITY 2: Check Events Action Verbs
        # Only route to Events if asking Who/When/Where/What/How about conferences/schedules
        # AND the query contains Events-related nouns
        events_action_match = any(verb in input_lower for verb in self.EVENTS_ACTION_VERBS)
        events_noun_match = any(keyword in input_lower for keyword in self.EVENTS_KEYWORDS)
        
        if events_action_match and events_noun_match:
            return "Events"
        
        # Cost/pricing queries: Route to Events if about event tickets/pricing
        # Otherwise, if about infrastructure costs, let it fall through to Engineering or Chat
        cost_keywords = ['cost', 'price', 'bill', 'estimate', 'how much', 'pricing', 'expense']
        if any(keyword in input_lower for keyword in cost_keywords):
            # If asking about event pricing/tickets, route to Events
            if any(events_keyword in input_lower for events_keyword in ['ticket', 'tickets', 'event', 'events', 'conference', 'registration']):
                return "Events"
            # For infrastructure cost questions without action verbs, route to Chat
            # (Engineering handles cost questions when creating/deploying resources)
            if not any(verb in input_lower for verb in self.ENGINEERING_ACTION_VERBS):
                return "Chat"
        
        # Smart Routing: Use history to maintain context
        # If we were just talking about a department, ambiguous follow-up questions should stay in that department
        if chat_history:
            # Check last few messages to see what department was active
            recent_messages = chat_history[-5:]  # Last 5 messages for better context
            events_context = False
            engineering_context = False
            
            for msg in reversed(recent_messages):
                content = msg.get("content", "").lower()
                # Check if recent messages mention events/engineering keywords
                if any(keyword in content for keyword in self.EVENTS_KEYWORDS):
                    events_context = True
                if any(keyword in content for keyword in self.ENGINEERING_KEYWORDS):
                    engineering_context = True
            
            # If current query is ambiguous but recent context exists, route to that department
            # BUT only if no action verbs were matched above
            if events_context and not any(verb in input_lower for verb in self.ENGINEERING_ACTION_VERBS):
                # If user asks "Where is it?" or "What about lunch?" after Events conversation
                if any(keyword in input_lower for keyword in ["it", "that", "this", "the", "where", "when", "what about", "how about"]):
                    return "Events"
            
            if engineering_context and not any(verb in input_lower for verb in self.EVENTS_ACTION_VERBS):
                # If user asks "Change the region" or "Make it bigger" after Engineering conversation
                if any(keyword in input_lower for keyword in ["it", "that", "this", "the", "change", "update", "modify", "region", "zone", "bucket", "vm", "instance", "make", "add", "remove"]):
                    return "Engineering"
        
        # FALLBACK: Check noun keywords (only if no action verbs matched)
        # Check Events keywords
        if any(keyword in input_lower for keyword in self.EVENTS_KEYWORDS):
            return "Events"
        
        # Check for Engineering keywords
        if any(keyword in input_lower for keyword in self.ENGINEERING_KEYWORDS):
            return "Engineering"
        
        # Default to Chat department
        return "Chat"
