"""
Events Department Agent
Uses Vertex AI Search with GCS data store to answer questions about Google Cloud Events.
"""

import os
import re
from typing import Callable, Optional, List
from dotenv import load_dotenv
import vertexai

load_dotenv()

from backend import feedback

# Import Discovery Engine
try:
    from google.cloud import discoveryengine_v1 as discoveryengine
    from google.api_core.client_options import ClientOptions
    DISCOVERY_ENGINE_AVAILABLE = True
except ImportError:
    DISCOVERY_ENGINE_AVAILABLE = False
    print("⚠️ google-cloud-discoveryengine not available.")

# --- CONFIGURATION (UPDATED) ---
# Cloud Run sets GOOGLE_CLOUD_PROJECT; local/Glass UI may use GCP_PROJECT_ID from .env
project_id = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
vertex_ai_location = (os.getenv("GCP_LOCATION") or "us-central1").strip()

# User provided IDs - required only when using local Events agent (not when using Agent Engine flow)
DATA_STORE_ID = (os.getenv("VERTEX_SEARCH_DATA_STORE_ID") or "").strip()

# Engine ID from Google Cloud Console - MUST be set via environment variables in production
# Note: The Engine ID is different from the Data Store ID for Enterprise Edition
ENGINE_ID = os.getenv("VERTEX_SEARCH_ENGINE_ID")
# ENGINE_ID is optional (only needed for Enterprise Edition)
COLLECTION_ID = "default_collection" # The API almost always uses 'default_collection' even if named otherwise in UI.

if project_id:
    try:
        vertexai.init(project=project_id, location=vertex_ai_location)
        VERTEX_AI_AVAILABLE = True
    except Exception as e:
        print(f"⚠️ Vertex AI initialization failed: {e}")
        VERTEX_AI_AVAILABLE = False
else:
    VERTEX_AI_AVAILABLE = False

class EventsAgent:
    def __init__(self, log_callback: Optional[Callable[[str, str, int, str], None]] = None):
        self.log_callback = log_callback
        self.conversation_turn = 0
        self.user_input = ""
        self.model = None
        
        if VERTEX_AI_AVAILABLE:
            # Lazy import with fallback for different package versions
            try:
                try:
                    # Try google.genai first (newer versions)
                    from google.genai import GenerativeModel
                except (ImportError, AttributeError):
                    try:
                        # Try the standard vertexai import
                        from vertexai.generative_models import GenerativeModel
                    except (ImportError, AttributeError):
                        try:
                            # Try preview import
                            from vertexai.preview.generative_models import GenerativeModel
                        except (ImportError, AttributeError):
                            try:
                                # Try google.generativeai (alternative SDK)
                                from google.generativeai import GenerativeModel
                            except (ImportError, AttributeError):
                                raise ImportError("Could not import GenerativeModel. Please ensure google-cloud-aiplatform>=1.40.0 is installed.")
                self.model = GenerativeModel("gemini-2.5-flash")
            except Exception as e:
                print(f"⚠️  Failed to import GenerativeModel: {e}")
                self.model = None
            self._log("Events Agent: Vertex AI initialized.", "events")
        else:
            self.model = None

    def _log(self, message: str, log_type: str = "events"):
        if self.log_callback:
            self.log_callback(message, log_type, self.conversation_turn, self.user_input)
        else:
            print(f"🔵 {message}")

    def _filter_sources_by_titles(self, search_data: str, relevant_titles: list) -> str:
        """
        Filter search_data to only include sources whose titles match the relevant_titles list.
        
        Args:
            search_data: The full search results string with sources (format: **Title**\nLink: ...\nContent...)
            relevant_titles: List of document titles that were actually used by the LLM
            
        Returns:
            Filtered search_data string containing only matching sources
        """
        if not relevant_titles or not search_data:
            # If no relevant titles specified, return empty to force LLM to provide relevant docs
            return ""
        
        # Normalize titles for matching (lowercase, remove extra whitespace, remove common suffixes)
        def normalize_title(title):
            normalized = title.lower().strip()
            # Remove common PDF/document suffixes that might differ
            normalized = re.sub(r'\.pdf$', '', normalized)
            normalized = re.sub(r'\s+', ' ', normalized)  # Normalize whitespace
            return normalized
        
        normalized_relevant = [normalize_title(title) for title in relevant_titles]
        
        # Split search_data by source blocks (each source starts with **Title**)
        # Pattern: **Title** followed by content until next **Title** or end
        # Format: **Title**\nLink: ...\nContent...
        source_pattern = r'\*\*(.+?)\*\*\n(.*?)(?=\n\*\*|$)'
        matches = list(re.finditer(source_pattern, search_data, re.DOTALL))
        
        filtered_parts = []
        for match in matches:
            source_title = match.group(1).strip()
            source_content = match.group(2).strip()
            
            # Normalize source title for comparison
            normalized_source_title = normalize_title(source_title)
            
            # Check if this source title matches any relevant title
            # Use flexible matching to handle variations
            is_relevant = False
            for relevant_title in normalized_relevant:
                # Check exact match or if one contains the other (with some tolerance)
                if (normalized_source_title == relevant_title or 
                    relevant_title in normalized_source_title or 
                    normalized_source_title in relevant_title):
                    is_relevant = True
                    break
                # Also check if key words match (for partial matches)
                relevant_words = set(relevant_title.split())
                source_words = set(normalized_source_title.split())
                # If most key words match, consider it relevant
                if len(relevant_words) > 0 and len(relevant_words.intersection(source_words)) >= min(2, len(relevant_words) // 2):
                    is_relevant = True
                    break
            
            if is_relevant:
                # Keep this source
                filtered_parts.append(f"**{source_title}**\n{source_content}")
        
        return "\n\n".join(filtered_parts) if filtered_parts else ""

    def _extract_search_terms(self, query: str) -> str:
        """
        Extract key search terms from conversational queries to improve search relevance.
        For example: "Tell me about session SPTL209. What is the title?" -> "SPTL209"
        Returns a simplified query with key terms.
        """
        # Extract session codes (e.g., SPTL209, ABC123) - highest priority
        session_code_pattern = r'\b[A-Z]{2,6}\d{2,4}\b'
        session_codes = re.findall(session_code_pattern, query.upper())
        if session_codes:
            return session_codes[0]
        
        # Extract quoted strings (often important terms)
        quoted = re.findall(r'"([^"]+)"', query)
        if quoted:
            return quoted[0]
        
        # For "Late Registration" pricing queries, check BEFORE capitalized phrase extraction
        # Try searching for "March 26" which is the start date for Late Registration
        if 'late registration' in query.lower() and ('cost' in query.lower() or 'price' in query.lower() or 'how much' in query.lower()):
            # Try to find price in query first
            price_in_query = re.search(r'\$[\d,]+', query)
            if price_in_query:
                return price_in_query.group(0)
            # Search for "March 26" which should find the Late Registration pricing section
            return "March 26"
        
        # Extract capitalized phrases (like "Late Registration", "Partner Summit", "Session Library", "CISO Connect")
        capitalized_phrases = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', query)
        if capitalized_phrases:
            # Return the longest capitalized phrase (usually most specific)
            return max(capitalized_phrases, key=len)
        
        # Extract specific numbers with context (like "21 years old", "20 years", "$999", "February 13, 2026")
        # Age patterns - check this BEFORE other number patterns
        # For age queries, if age < 21, search for "21" or "21 years" to find the requirement
        age_pattern = r'\b(\d+)\s*years?\s*old\b'
        age_match = re.search(age_pattern, query, re.IGNORECASE)
        if age_match:
            age_value = int(age_match.group(1))
            # If asking about age and the age is below 21, search for "21" to find the requirement
            if age_value < 21 and ('can i' in query.lower() or 'attend' in query.lower()):
                return "21 years"
            return f"{age_match.group(1)} years"
        
        # Date patterns (like "February 13, 2026" or "Feb 13" or "Feb 13, 2026")
        # First try full month names with year
        date_pattern_full = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'
        date_match = re.search(date_pattern_full, query, re.IGNORECASE)
        if date_match:
            # For pricing queries with dates, include pricing terms
            if 'price' in query.lower() or 'cost' in query.lower() or 'how much' in query.lower() or 'ticket' in query.lower():
                return f"{date_match.group(0)} price"
            return date_match.group(0)
        
        # Then try abbreviated month names (Jan, Feb, Mar, etc.) with optional year
        month_abbrev = {
            'jan': 'January', 'feb': 'February', 'mar': 'March', 'apr': 'April',
            'may': 'May', 'jun': 'June', 'jul': 'July', 'aug': 'August',
            'sep': 'September', 'oct': 'October', 'nov': 'November', 'dec': 'December'
        }
        date_pattern_abbrev = r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*(?:\d{4})?\b'
        date_match_abbrev = re.search(date_pattern_abbrev, query, re.IGNORECASE)
        if date_match_abbrev:
            month_abbrev_key = date_match_abbrev.group(1).lower()[:3]
            if month_abbrev_key in month_abbrev:
                # Return expanded month name for better search matching
                expanded_month = month_abbrev[month_abbrev_key]
                # Extract day number from the match
                day_match = re.search(r'\d{1,2}', date_match_abbrev.group(0))
                day = day_match.group(0) if day_match else ""
                # For pricing queries with dates, include both date and pricing terms
                if 'price' in query.lower() or 'cost' in query.lower() or 'how much' in query.lower() or 'ticket' in query.lower():
                    return f"{expanded_month} {day} price"
                return f"{expanded_month} {day}"
        
        # Price patterns (like "$2,299", "$999 USD")
        price_pattern = r'\$[\d,]+(?:\s*USD)?'
        price_match = re.search(price_pattern, query)
        if price_match:
            return price_match.group(0)
        
        # Extract email addresses
        email_pattern = r'\b[\w.-]+@[\w.-]+\.\w+\b'
        email_match = re.search(email_pattern, query)
        if email_match:
            return email_match.group(0)
        
        # For pricing/ticket queries without specific dates, search for pricing terms
        if ('price' in query.lower() or 'cost' in query.lower() or 'how much' in query.lower()) and 'ticket' in query.lower():
            # Check if there's a date reference (before, after, by, etc.)
            date_ref_pattern = r'\b(before|after|by|until|till)\s+([A-Za-z]+\s+\d{1,2})'
            date_ref_match = re.search(date_ref_pattern, query, re.IGNORECASE)
            if date_ref_match:
                date_part = date_ref_match.group(2)
                # Try to expand abbreviated month
                month_abbrev = {
                    'jan': 'January', 'feb': 'February', 'mar': 'March', 'apr': 'April',
                    'may': 'May', 'jun': 'June', 'jul': 'July', 'aug': 'August',
                    'sep': 'September', 'oct': 'October', 'nov': 'November', 'dec': 'December'
                }
                month_part = date_part.split()[0].lower()[:3]
                if month_part in month_abbrev:
                    expanded_month = month_abbrev[month_part]
                    day = date_part.split()[1]
                    return f"{expanded_month} {day} price"
                return f"{date_part} price"
            # No specific date, search for general pricing
            return "ticket price"
        
        # Extract specific phrases (Late Registration pricing already handled above)
        specific_phrases = [
            r'late\s+registration',  # Check this first before "registration"
            r'early\s+bird',
            r'partner\s+summit',
            r'session\s+library',
            r'ciso\s+connect',
            r'cpe\s+credits?',
            r'sponsorship',  # Add sponsorship as a key term
            r'ticket\s+price',  # Add ticket price as a key term
            r'registration\s+price'  # Add registration price as a key term
        ]
        for pattern in specific_phrases:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(0)
        
        # For "What is X" or "Tell me about X" patterns, extract key terms
        what_is_pattern = r'what is\s+(?:the\s+)?(.+?)(?:\?|$)'
        match = re.search(what_is_pattern, query.lower())
        if match:
            key_phrase = match.group(1).strip()
            # Remove common words but keep important ones
            key_phrase = re.sub(r'\b(the|a|an|to|for|of|in|on|at|by|with|if|i|am|can|do|need)\b', '', key_phrase, flags=re.IGNORECASE)
            key_phrase = key_phrase.strip()
            
            # Extract the most important 2-3 word phrases
            words = key_phrase.split()
            if len(words) >= 2:
                # For longer phrases, take the most specific part
                if len(words) > 3:
                    # Try to find capitalized words first
                    capitalized = [w for w in words if w[0].isupper()]
                    if capitalized:
                        return ' '.join(capitalized[:2])
                    # Otherwise take last 2-3 words
                    key_phrase = ' '.join(words[-3:])
                return key_phrase
        
        # For "How much", "When will", "Who should" patterns
        how_when_who_pattern = r'(?:how\s+much|when\s+will|who\s+should|how\s+do)\s+(.+?)(?:\?|$)'
        match = re.search(how_when_who_pattern, query.lower())
        if match:
            key_phrase = match.group(1).strip()
            # Remove common words
            key_phrase = re.sub(r'\b(the|a|an|to|for|of|in|on|at|by|with|if|i|am|can|do|need|be|is|are|specifically)\b', '', key_phrase, flags=re.IGNORECASE)
            key_phrase = key_phrase.strip()
            words = key_phrase.split()
            if words:
                # For "who should I email for sponsorship" -> extract "sponsorship"
                if 'sponsorship' in key_phrase.lower():
                    return 'sponsorship'
                # Take first 2-3 important words
                return ' '.join(words[:3])
        
        # For "Tell me about X" pattern
        tell_me_pattern = r'tell me about\s+(.+?)(?:\.|$|\?)'
        match = re.search(tell_me_pattern, query.lower())
        if match:
            key_phrase = match.group(1).strip()
            key_phrase = re.sub(r'\b(what|is|the|a|an|are|was|were|to|for|of|in|on|at|by|with)\b', '', key_phrase, flags=re.IGNORECASE)
            key_phrase = key_phrase.strip()
            if len(key_phrase) > 3:
                return key_phrase
        
        # For age-related queries (like "I am 20 years old") - catch any remaining age queries
        if ('years old' in query.lower() or 'age' in query.lower()) and ('can i' in query.lower() or 'attend' in query.lower()):
            age_num = re.search(r'\b(\d+)\s*years?\b', query, re.IGNORECASE)
            if age_num:
                age_value = int(age_num.group(1))
                # If age is below 21, search for "21" to find the requirement
                if age_value < 21:
                    return "21 years"
                return f"{age_num.group(1)} years"
            return "21 years"
        
        # If no pattern matches, try to extract key nouns/adjectives (2-3 word phrases)
        # Remove common stop words and return the most important terms
        words = query.lower().split()
        stop_words = {'what', 'is', 'the', 'a', 'an', 'are', 'was', 'were', 'to', 'for', 'of', 'in', 'on', 'at', 'by', 'with', 'about', 'tell', 'me', 'do', 'does', 'did', 'can', 'could', 'will', 'would', 'should', 'may', 'might', 'if', 'i', 'am', 'be', 'get', 'have', 'has', 'had'}
        important_words = [w for w in words if w not in stop_words and len(w) > 2]
        if important_words:
            # Return the last 2-3 important words (usually the most specific)
            return ' '.join(important_words[-2:])
        
        # Fallback: return original query
        return query

    def _search_events_knowledge(self, query: str) -> str:
        if not DISCOVERY_ENGINE_AVAILABLE:
            return ""

        try:
            # Preprocess query to extract key terms for better search relevance
            extracted_terms = self._extract_search_terms(query)
            
            # For pricing questions with dates, use original query for better context
            # The search engine can handle full context better than narrow extracted terms
            is_pricing_with_date = (
                ('price' in query.lower() or 'cost' in query.lower() or 'how much' in query.lower()) and
                ('ticket' in query.lower() or 'registration' in query.lower()) and
                (re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}', query, re.IGNORECASE) is not None)
            )
            
            # Use extracted terms if they're meaningful, otherwise use original query
            # If extracted terms are too short (< 3 chars) or same as original, use original
            # For pricing with dates, prefer original query for better context
            if is_pricing_with_date:
                search_query = query
                self._log(f"Events Agent: Using original query for pricing with date: '{query}'", "events")
            elif len(extracted_terms) < 3 or extracted_terms == query:
                search_query = query
            else:
                search_query = extracted_terms
                self._log(f"Events Agent: Extracted search terms: '{search_query}' from query: '{query}'", "events")
            # 1. Setup Client
            client_options = ClientOptions(api_endpoint="us-discoveryengine.googleapis.com")
            client = discoveryengine.SearchServiceClient(client_options=client_options)

            # 2. Construct Path - Try Engine first, fallback to Data Store
            # Path: projects/{project}/locations/{location}/collections/{collection}/engines/{engine}/servingConfigs/{config}
            # OR: projects/{project}/locations/{location}/collections/{collection}/dataStores/{dataStore}/servingConfigs/{config}
            project_number = os.getenv("GCP_PROJECT_NUMBER")
            if not project_number:
                raise ValueError("GCP_PROJECT_NUMBER environment variable is required for Discovery Engine API")
            
            # Require DATA_STORE_ID when using local Events agent (not needed when using Agent Engine flow)
            if not DATA_STORE_ID:
                raise ValueError(
                    "VERTEX_SEARCH_DATA_STORE_ID environment variable is required when using the Events agent locally. "
                    "Set it in .env or Cloud Run env vars, or use the Agent Engine flow (AGENTIC_LENS_SUPERVISOR_ENGINE) where Events runs in Vertex AI."
                )

            # Try Engine path first (for Enterprise Edition) - only if ENGINE_ID is set
            serving_config_engine = None
            if ENGINE_ID:
                serving_config_engine = f"projects/{project_number}/locations/us/collections/{COLLECTION_ID}/engines/{ENGINE_ID}/servingConfigs/default_search"
                self._log(f"Events Agent: Trying Engine path: {ENGINE_ID}", "events")
            
            # Fallback to Data Store path (for Standard Edition or if engine has no data stores)
            serving_config_datastore = f"projects/{project_number}/locations/us/collections/{COLLECTION_ID}/dataStores/{DATA_STORE_ID}/servingConfigs/default_search"

            # 3. The "Aggressive" Search Request
            # We ask for EVERYTHING: Extractive Answers, Segments, Snippets, and Summaries.
            # Try Engine path first (if available), fallback to Data Store if engine fails
            serving_config = serving_config_engine if serving_config_engine else serving_config_datastore
            try:
                # Only try Engine path if ENGINE_ID is configured
                if serving_config_engine:
                    # Standard Edition: Remove extractive_content_spec (Enterprise only)
                    request = discoveryengine.SearchRequest(
                        serving_config=serving_config_engine,
                        query=search_query,  # Use processed query
                        page_size=5,
                        content_search_spec={
                            "snippet_spec": {
                                "return_snippet": True, 
                                "max_snippet_count": 3  # Get multiple chunks per file
                            },
                            "summary_spec": {
                                "summary_result_count": 5,
                                "include_citations": True,
                                "ignore_adversarial_query": True
                            }
                        },
                        query_expansion_spec={"condition": "AUTO"}
                    )
                    response = client.search(request)
                    num_results = len(response.results) if hasattr(response, 'results') and response.results else 0
                    self._log(f"Events Agent: Engine search successful, found {num_results} results", "events")
                    
                    # If engine returns no results, fall back to data store
                    if num_results == 0:
                        self._log(f"Events Agent: Engine returned no results, falling back to Data Store path: {DATA_STORE_ID}", "events")
                        serving_config = serving_config_datastore
                        # Standard Edition: Remove extractive_content_spec (Enterprise only)
                        request = discoveryengine.SearchRequest(
                            serving_config=serving_config,
                            query=search_query,  # Use processed query
                            page_size=5,
                            content_search_spec={
                                "snippet_spec": {
                                    "return_snippet": True, 
                                    "max_snippet_count": 3
                                },
                                "summary_spec": {
                                    "summary_result_count": 5,
                                    "include_citations": True,
                                    "ignore_adversarial_query": True
                                }
                            },
                            query_expansion_spec={"condition": "AUTO"}
                        )
                        datastore_success = False
                        error_str = ""
                        try:
                            response = client.search(request)
                            num_results = len(response.results) if hasattr(response, 'results') and response.results else 0
                            self._log(f"Events Agent: Data Store search successful, found {num_results} results", "events")
                            datastore_success = True
                        except Exception as datastore_error:
                            error_str = str(datastore_error)
                            self._log(f"Events Agent: Data Store search failed: {error_str[:200]}", "events")
                            # If data store not found, try alternative names
                            if "not found" in error_str.lower() or "404" in error_str:
                                # Try alternative data store IDs
                                alternative_ids = ["event-web-knowledge_gcs_store", "events-web-knowledge"]
                                for alt_id in alternative_ids:
                                    if alt_id == DATA_STORE_ID:
                                        continue
                                    self._log(f"Events Agent: Trying alternative data store ID: {alt_id}", "events")
                                    alt_serving_config = f"projects/{project_number}/locations/us/collections/{COLLECTION_ID}/dataStores/{alt_id}/servingConfigs/default_search"
                                    request = discoveryengine.SearchRequest(
                                        serving_config=alt_serving_config,
                                        query=search_query,  # Use processed query
                                        page_size=5,
                                        content_search_spec={
                                            "snippet_spec": {"return_snippet": True, "max_snippet_count": 3},
                                            "summary_spec": {"summary_result_count": 5, "include_citations": True, "ignore_adversarial_query": True}
                                        },
                                        query_expansion_spec={"condition": "AUTO"}
                                    )
                                    try:
                                        response = client.search(request)
                                        num_results = len(response.results) if hasattr(response, 'results') and response.results else 0
                                        self._log(f"Events Agent: Alternative data store '{alt_id}' search successful, found {num_results} results", "events")
                                        datastore_success = True
                                        break
                                    except Exception as alt_error:
                                        self._log(f"Events Agent: Alternative data store '{alt_id}' also failed: {str(alt_error)[:100]}", "events")
                                        continue
                                if not datastore_success:
                                    raise datastore_error
                            else:
                                # Re-raise the original error if it wasn't a "not found" error
                                raise datastore_error
            except Exception as engine_error:
                error_str = str(engine_error)
                self._log(f"Events Agent: Search error: {error_str[:200]}", "events")
                # If engine has no data stores, ENGINE_ID not set, or permission denied, try data store path directly
                has_permission_error = "403" in error_str or "IAM_PERMISSION_DENIED" in error_str or "Permission" in error_str and "denied" in error_str
                if "ENGINE_HAS_NO_DATA_STORES" in error_str or "must have at least one data store" in error_str or not ENGINE_ID or has_permission_error:
                    self._log(f"Events Agent: Engine unavailable, using Data Store path: {DATA_STORE_ID}", "events")
                    serving_config = serving_config_datastore
                    # Standard Edition: Remove extractive_content_spec (Enterprise only)
                    request = discoveryengine.SearchRequest(
                        serving_config=serving_config,
                        query=search_query,  # Use processed query
                        page_size=5,
                        content_search_spec={
                            "snippet_spec": {
                                "return_snippet": True, 
                                "max_snippet_count": 3
                            },
                            "summary_spec": {
                                "summary_result_count": 5,
                                "include_citations": True,
                                "ignore_adversarial_query": True
                            }
                        },
                        query_expansion_spec={"condition": "AUTO"}
                    )
                    try:
                        response = client.search(request)
                        self._log(f"Events Agent: Data Store search successful, found {len(response.results) if hasattr(response, 'results') else 0} results", "events")
                    except Exception as datastore_error:
                        self._log(f"Events Agent: Data Store search also failed: {str(datastore_error)[:200]}", "events")
                        raise
                else:
                    # Re-raise if it's a different error
                    raise

            # 4. Parsing Logic (Prioritized)
            results = []
            
            # Check if we have results
            if not hasattr(response, 'results') or not response.results:
                self._log(f"Events Agent: No results in response - data store may be empty or documents not yet indexed", "events")
                return ""
            
            self._log(f"Events Agent: Processing {len(response.results)} search results", "events")
            
            # A. Summary (The "Text-in-Image" Solver)
            if hasattr(response, 'summary') and response.summary:
                if hasattr(response.summary, 'summary_text') and response.summary.summary_text:
                    self._log(f"Events Agent: Found summary: {response.summary.summary_text[:100]}...", "events")
                    results.append(f"**OFFICIAL SUMMARY**\n{response.summary.summary_text}\n---")

            # B. Document Content
            for idx, result in enumerate(response.results):
                if not hasattr(result, 'document'):
                    self._log(f"Events Agent: Result {idx} has no document attribute", "events")
                    continue
                
                if not hasattr(result.document, 'derived_struct_data'):
                    self._log(f"Events Agent: Result {idx} document has no derived_struct_data", "events")
                    continue
                
                data = result.document.derived_struct_data
                # Handle protobuf MapComposite type - convert to dict if needed
                if not isinstance(data, dict):
                    try:
                        # Convert protobuf MapComposite to dict
                        if hasattr(data, '_values'):
                            data = dict(data)
                        elif hasattr(data, 'get'):
                            # It might still support dict-like access
                            pass
                        else:
                            # Try to convert it
                            data = dict(data) if hasattr(data, '__iter__') else {}
                    except Exception as conv_error:
                        self._log(f"Events Agent: Could not convert derived_struct_data to dict: {conv_error}", "events")
                        continue
                
                # Now access as dict
                title = data.get("title", "Untitled") if hasattr(data, 'get') else getattr(data, 'title', 'Untitled')
                link = data.get("link", "") if hasattr(data, 'get') else getattr(data, 'link', '')
                
                self._log(f"Events Agent: Processing document {idx+1}: {title[:50]}...", "events")
                
                content_parts = []

                # Helper function to safely get from dict or protobuf map
                def safe_get(obj, key, default=None):
                    if hasattr(obj, 'get'):
                        return obj.get(key, default)
                    elif hasattr(obj, key):
                        return getattr(obj, key, default)
                    else:
                        return default
                
                # Check 1: Direct Extractive Answer
                answers = safe_get(data, "extractive_answers", [])
                if answers:
                    # Handle both list and protobuf repeated field
                    if not isinstance(answers, list):
                        try:
                            answers = list(answers)
                        except:
                            answers = []
                    if answers and len(answers) > 0:
                        first_answer = answers[0]
                        answer_content = safe_get(first_answer, 'content', '') or safe_get(first_answer, 'text', '') or str(first_answer)
                        if answer_content:
                            content_parts.append(f"Direct Answer: {answer_content}")
                            self._log(f"Events Agent: Found extractive answer for {title[:30]}", "events")

                # Check 2: Extractive Segments (Best for PDF paragraphs)
                segments = safe_get(data, "extractive_segments", [])
                if segments:
                    if not isinstance(segments, list):
                        try:
                            segments = list(segments)
                        except:
                            segments = []
                    if segments:
                        for seg in segments:
                            seg_content = safe_get(seg, 'content', '') or safe_get(seg, 'text', '') or str(seg)
                            if seg_content:
                                content_parts.append(f"Segment: {seg_content}")
                        self._log(f"Events Agent: Found {len(segments)} extractive segments for {title[:30]}", "events")

                # Check 3: Standard Snippets (Reliable Fallback)
                snippets = safe_get(data, "snippets", [])
                if snippets:
                    if not isinstance(snippets, list):
                        try:
                            snippets = list(snippets)
                        except:
                            snippets = []
                    if snippets:
                        for snip in snippets:
                            snip_content = safe_get(snip, 'snippet', '') or safe_get(snip, 'text', '') or str(snip)
                            if snip_content:
                                content_parts.append(f"Snippet: {snip_content}")
                        self._log(f"Events Agent: Found {len(snippets)} snippets for {title[:30]}", "events")

                # Combine what we found
                if content_parts:
                    full_text = "\n".join(content_parts)
                    results.append(f"**{title}**\nLink: {link}\n{full_text}")
                    self._log(f"Events Agent: Added content for {title[:30]} ({len(full_text)} chars)", "events")
                else:
                    self._log(f"Events Agent: Found doc '{title[:30]}' but no extractable content", "events")

            self._log(f"Events Agent: Total results after parsing: {len(results)}", "events")
            return "\n\n".join(results) if results else ""

        except Exception as e:
            self._log(f"Search Error: {e}", "events")
            return ""

    def answer(self, user_query: str, conversation_turn: int = 0, conversation_history: list = None) -> dict:
        self.conversation_turn = conversation_turn
        self.user_input = user_query
        
        # Initialize execution logs
        execution_logs = []
        
        # 1. Search
        execution_logs.append(f"🔵 Starting search for: {user_query[:100]}{'...' if len(user_query) > 100 else ''}")
        try:
            search_data = self._search_events_knowledge(user_query)
            execution_logs.append(f"🔵 Search completed. Data length: {len(search_data) if search_data else 0} characters")
        except Exception as e:
            execution_logs.append(f"🔴 Search error: {str(e)[:200]}")
            self._log(f"Events Agent search error: {e}", "events")
            search_data = ""
        
        # 2. Generate
        if not search_data:
            execution_logs.append("🔵 Engine returned 0 results.")
            execution_logs.append("🔵 Events Agent: No search results found.")
            return {"answer": "I couldn't find that information in the documents. Please check the official website.", "logs": execution_logs}
        
        num_results = len(search_data.split("**")) - 1 if "**" in search_data else 0
        execution_logs.append(f"🔵 Engine returned {num_results} results.")

        # 3. Load training examples (learned from Events QA)
        training_examples = feedback.get_training_examples(department="Events", active_only=True)
        training_examples_text = ""
        if training_examples:
            lines = []
            for ex in training_examples[:15]:
                lines.append(f"- \"{ex['example_query']}\" → {ex['expected_behavior']}")
            training_examples_text = "\n".join(lines)

        # 4. Process Conversation History
        execution_logs.append("🔵 Events Agent: Processing conversation history for context...")
        history_context = ""
        if conversation_history:
            # Get the last 3 items from conversation history
            recent_history = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
            
            # Format history into a string
            history_parts = []
            for msg in recent_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role and content:
                    # Format: "User: ..." or "Agent: ..."
                    role_label = "User" if role == "user" else "Agent"
                    history_parts.append(f"{role_label}: {content}")
            
            if history_parts:
                history_context = "\n".join(history_parts)
                execution_logs.append(f"🔵 Events Agent: Loaded {len(recent_history)} message(s) from conversation history.")

        # 5. Build prompt with history context
        if history_context:
            prompt = f"""
You are the Event Concierge. Answer the user's question based ONLY on the search results below.

EXAMPLE QUERIES AND EXPECTED ANSWER FORMAT (use to guide response style):
{training_examples_text if training_examples_text else "None"}

CONVERSATION HISTORY:
{history_context}

USER QUESTION: {user_query}

SEARCH RESULTS:
{search_data}

INSTRUCTIONS:
- Use the conversation history to understand context (e.g., if the user says "it" or "that", refer to the history).
- Look for pricing, dates, and names in the "Segments" and "Snippets".
- If the user asks about "Late Registration" pricing, carefully search for "$2,299" or pricing tiers mentioning "Late" or "March 26 - April 21".
- If the user asks about "Early Bird" pricing, look for "$999" or pricing tiers mentioning "Early Bird" or "February 13".
- If you see a price like "$999" or "$2,299" in a snippet, use it.
- For age questions, look for "21+" or "21 years old" in the results.
- Be helpful and polite.
- Extract the exact information requested (price, date, email, etc.) from the search results.
- If you find pricing information in the search results, provide it even if it's not explicitly labeled as "Late Registration".
- Citations: When you use search results, always list their exact Titles under '### RELEVANT_DOCS ###' so the user gets a source. No citation = hallucination risk.
- Guardrails: Do not invent sessions, speakers, or facts. If the question is about something not in the documents (e.g. weather, a competitor product, or a topic with no matching session), say clearly that you don't have that information and that you can only help with event schedule and logistics.

IMPORTANT: After your answer, verify which of the search results you specifically used to answer the question. At the very end of your response, output a list of their exact Titles under the header '### RELEVANT_DOCS ###'. List only the titles you actually used, one per line.
"""
        else:
            prompt = f"""
You are the Event Concierge. Answer the user's question based ONLY on the search results below.

EXAMPLE QUERIES AND EXPECTED ANSWER FORMAT (use to guide response style):
{training_examples_text if training_examples_text else "None"}

USER QUESTION: {user_query}

SEARCH RESULTS:
{search_data}

INSTRUCTIONS:
- Look for pricing, dates, and names in the "Segments" and "Snippets".
- If the user asks about "Late Registration" pricing, carefully search for "$2,299" or pricing tiers mentioning "Late" or "March 26 - April 21".
- If the user asks about "Early Bird" pricing, look for "$999" or pricing tiers mentioning "Early Bird" or "February 13".
- If you see a price like "$999" or "$2,299" in a snippet, use it.
- For age questions, look for "21+" or "21 years old" in the results.
- Be helpful and polite.
- Extract the exact information requested (price, date, email, etc.) from the search results.
- If you find pricing information in the search results, provide it even if it's not explicitly labeled as "Late Registration".
- Citations: When you use search results, always list their exact Titles under '### RELEVANT_DOCS ###' so the user gets a source. No citation = hallucination risk.
- Guardrails: Do not invent sessions, speakers, or facts. If the question is about something not in the documents (e.g. weather, a competitor product, or a topic with no matching session), say clearly that you don't have that information and that you can only help with event schedule and logistics.

IMPORTANT: After your answer, verify which of the search results you specifically used to answer the question. At the very end of your response, output a list of their exact Titles under the header '### RELEVANT_DOCS ###'. List only the titles you actually used, one per line.
"""
        
        try:
            # 6. Generate answer with LLM
            execution_logs.append("🔵 Events Agent: Generating answer with Gemini...")
            response = self.model.generate_content(prompt)
            ai_response = response.text
            execution_logs.append("🔵 Events Agent: Answer generated successfully.")
            
            # 7. Parse relevant documents from LLM response
            execution_logs.append("🔵 Events Agent: Parsing relevant documents from LLM response...")
            relevant_titles = []
            if "### RELEVANT_DOCS ###" in ai_response:
                # Split response to get the answer and relevant docs section
                parts = ai_response.split("### RELEVANT_DOCS ###", 1)
                answer_text = parts[0].strip()  # Answer without the relevant docs section
                relevant_docs_section = parts[1].strip() if len(parts) > 1 else ""
                
                # Extract titles from the relevant docs section
                for line in relevant_docs_section.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):  # Skip empty lines and markdown headers
                        # Remove any markdown formatting (**, -, etc.)
                        clean_title = line.lstrip('*- ').strip()
                        if clean_title:
                            relevant_titles.append(clean_title)
                
                # Remove the RELEVANT_DOCS section from the answer
                ai_response = answer_text
                execution_logs.append(f"🔵 Events Agent: Identified {len(relevant_titles)} relevant document(s).")
            else:
                # If LLM didn't provide relevant docs, use the full answer
                answer_text = ai_response
                execution_logs.append("🔵 Events Agent: No relevant docs section found, using all sources.")
            
            # 6. Filter search_data to only include sources with matching titles
            execution_logs.append("🔵 Filtering sources...")
            filtered_sources = self._filter_sources_by_titles(search_data, relevant_titles)
            num_filtered = len(filtered_sources.split("**")) - 1 if "**" in filtered_sources else 0
            execution_logs.append(f"🔵 Filtered to {num_filtered} source(s) for citation.")
            
            # 7. Append filtered sources to the response
            final_response = f"{ai_response}\n\n### SOURCES ###\n{filtered_sources}"
            execution_logs.append("🔵 Events Agent: Response complete with citations.")
            
            return {"answer": final_response, "logs": execution_logs}
        except Exception as e:
            execution_logs.append(f"🔵 Events Agent: Error generating answer - {str(e)}")
            return {"answer": f"I ran into an issue generating the answer: {e}", "logs": execution_logs}