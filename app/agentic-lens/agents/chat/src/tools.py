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

def strip_tags(html):
    # Remove script and style tags and their contents
    html = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', html, flags=re.IGNORECASE)
    s = MLStripper()
    s.feed(html)
    return s.get_data().strip()

def get_current_time():
    """Returns the current date for the conference."""
    return "2026-05-21" # Google I/O dummy date

def fetch_url(url: str) -> str:
    """Fetches the content of a given URL, extracts text from HTML, and returns it. Once you receive the content, you MUST summarize it or answer the user's question based on it. NEVER output the raw content directly to the user."""
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
            try:
                body = strip_tags(body)
            except Exception:
                pass
                
        if len(body) > 30000:
            body = body[:30000] + "\n... [Truncated due to length] ..."
            
        return f"SUCCESS: Fetch completed with HTTP code {response.status_code}. Extracted Text:\n{body}"
    except Exception as e:
        return f"FAILED: Exception occurred during fetch: {str(e)}"
