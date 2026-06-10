import requests
import urllib3
from html.parser import HTMLParser

# Suppress SSL warnings for clean logs when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_data(self):
        return ''.join(self.text)

import re
import trafilatura

class MLStripper(HTMLParser):
    """Fallback HTML stripper used when trafilatura cannot extract content."""
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_data(self):
        return ''.join(self.text)

def strip_tags(html):
    """Fallback: strip all HTML tags. Used only when trafilatura fails."""
    html = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', html, flags=re.IGNORECASE)
    s = MLStripper()
    s.feed(html)
    return s.get_data().strip()

def _extract_content(html: str) -> str:
    """Extract main article content from HTML using trafilatura.
    Falls back to strip_tags if trafilatura returns nothing.
    """
    try:
        extracted = trafilatura.extract(
            html,
            include_links=False,
            include_tables=True,
            include_comments=False,
            no_fallback=False,
        )
        if extracted and len(extracted.strip()) > 100:
            return extracted.strip()
    except Exception:
        pass
    return strip_tags(html)

def get_current_time():
    """Returns the current date for the conference."""
    return "2026-05-21" # Google I/O dummy date

def fetch_url(url: str) -> str:
    """Fetches the content of a given URL, extracts the main article text, and returns it.
    Once you receive the content, you MUST summarize it or answer the user's question based on it.
    NEVER output the raw content directly to the user — always respond with a clean, structured summary.
    """
    print(f"Attempting to fetch URL: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # Use verify=False to ensure robust E2E connections bypassing corporate gateway SSL intercepts if any
        response = requests.get(url, headers=headers, timeout=15.0, verify=False)
        response.raise_for_status()

        body = response.text
        if "<html" in body.lower():
            body = _extract_content(body)  # smart extraction: nav/sidebar/footer removed

        # 8k chars of clean article text is ample for summarization (~4-5 pages)
        if len(body) > 8000:
            body = body[:8000] + "\n... [Content truncated — ask about specific sections if needed] ..."

        return f"FETCH_OK ({response.status_code}): {url}\n\n{body}"
    except Exception as e:
        return f"FETCH_FAILED: {str(e)}"
