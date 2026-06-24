"""
Chat agent tools — web content fetching and general utilities.
"""
import requests
import urllib3
from html.parser import HTMLParser

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MLStripper(HTMLParser):
    """Strip HTML markup from text."""
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return " ".join(self.fed)


def strip_html(html: str) -> str:
    s = MLStripper()
    s.feed(html)
    return s.get_data()


def fetch_url(url: str) -> str:
    """Fetch URL content and return as plain text."""
    try:
        resp = requests.get(url, timeout=10, verify=False)
        resp.raise_for_status()
        return strip_html(resp.text)[:4000]
    except Exception as e:
        return f"Failed to fetch {url}: {e}"
