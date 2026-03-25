#!/usr/bin/env python3
"""
slow_italian_combined_feed.py
Builds a personal RSS feed for "Slow Italian, Fast Learning" that includes
both the audio enclosure and the full Italian/English transcript scraped from
the SBS episode webpage.

FOR PERSONAL USE ONLY. Do not redistribute.
"""

import time
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ── configuration ──────────────────────────────────────────────────────────────
SOURCE_FEED   = "https://sbs-ondemand.streamguys1.com/slow-italian-fast-learning/"
OUTPUT_FILE   = "SBS-Slow_Italian_Fast_Learning-feed/slow_italian_combined.xml"
DELAY_SECONDS = 2          # polite delay between SBS page requests
MAX_EPISODES  = 40         # set to None to process all episodes in the feed
USER_AGENT    = (
    "Mozilla/5.0 (compatible; PersonalRSSBuilder/1.0; "
    "+https://github.com/your-username/slow-italian-feed)"
)
# ──────────────────────────────────────────────────────────────────────────────


def fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return resp


def scrape_transcript(episode_url: str) -> str:
    """
    Fetch an SBS episode page and return the transcript as plain text.
    SBS renders the page via client-side JS, but the article body
    (including transcript) is present in the raw HTML inside
    <div data-component="ArticleBody"> or similar containers.
    Falls back to grabbing all <p> tags inside <article> if needed.
    """
    try:
        resp = fetch(episode_url)
    except Exception as e:
        return f"[Could not fetch transcript: {e}]"

    soup = BeautifulSoup(resp.text, "lxml")

    # Try the main article body first
    body = (
        soup.find("div", {"data-component": "ArticleBody"})
        or soup.find("div", class_=lambda c: c and "article-body" in c.lower())
        or soup.find("article")
    )

    if body:
        paragraphs = body.find_all("p")
    else:
        paragraphs = soup.find_all("p")

    text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    return text or "[Transcript not found – visit the episode page directly.]"


def build_feed(source_items: list[dict], channel_meta: dict) -> str:
    """Build a valid RSS 2.0 XML string from the processed episode list."""
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
        "xmlns:itunes":  "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:atom":    "http://www.w3.org/2005/Atom",
    })
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text       = channel_meta.get("title", "Slow Italian, Fast Learning – Combined")
    ET.SubElement(channel, "link").text        = channel_meta.get("link", "https://www.sbs.com.au/language/italian/en/podcast/slow-italian-fast-learning")
    ET.SubElement(channel, "description").text = channel_meta.get("description", "Audio + transcript combined feed (personal use)")
    ET.SubElement(channel, "language").text    = "it"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    for ep in source_items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text       = ep["title"]
        ET.SubElement(item, "link").text        = ep["link"]
        ET.SubElement(item, "pubDate").text     = ep["pubDate"]
        ET.SubElement(item, "description").text = ep["description"]

        # Full transcript in content:encoded (shown by RSS readers)
        content_encoded = ET.SubElement(item, "content:encoded")
        # Split transcript into <p> paragraphs instead of a <pre> block
        paragraphs_html = "".join(
            f"<p>{para}</p>"
            for para in ep["transcript"].split("\n\n")
            if para.strip()
        )
        content_encoded.text = (
            f"<![CDATA[<h2>{ep['title']}</h2>"
            f"<p><a href='{ep['link']}'>Open episode page on SBS</a></p>"
            f"<hr/>{paragraphs_html}]]>"
        )

        # Audio enclosure – essential for podcast apps
        if ep.get("enclosure_url"):
            ET.SubElement(item, "enclosure", {
                "url":    ep["enclosure_url"],
                "type":   ep.get("enclosure_type", "audio/mpeg"),
                "length": ep.get("enclosure_length", "0"),
            })

        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = ep.get("guid", ep["link"])
        if ep.get("duration"):
            ET.SubElement(item, "itunes:duration").text = ep["duration"]

    raw = ET.tostring(rss, encoding="unicode")
    # Pretty-print
    return minidom.parseString(raw).toprettyxml(indent="  ")


def parse_source_feed(xml_text: str) -> tuple[dict, list[dict]]:
    """Parse the original SBS RSS feed; return channel metadata + list of items."""
    root = ET.fromstring(xml_text)
    ns = {
        "itunes":  "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "content": "https://www.w3.org/TR/REC-xml/#syntax",
    }
    channel = root.find("channel")

    meta = {
        "title":       (channel.findtext("title")       or "").strip(),
        "link":        (channel.findtext("link")        or "").strip(),
        "description": (channel.findtext("description") or "").strip(),
    }

    items = []
    for item in channel.findall("item"):
        enc = item.find("enclosure")
        duration_el = item.find("itunes:duration", ns)
        items.append({
            "title":          (item.findtext("title")       or "").strip(),
            "link":           (item.findtext("link")        or "").strip(),
            "pubDate":        (item.findtext("pubDate")     or "").strip(),
            "description":    (item.findtext("description") or "").strip(),
            "guid":           (item.findtext("guid")        or "").strip(),
            "enclosure_url":  enc.get("url")    if enc is not None else "",
            "enclosure_type": enc.get("type")   if enc is not None else "audio/mpeg",
            "enclosure_length": enc.get("length") if enc is not None else "0",
            "duration":       duration_el.text.strip() if duration_el is not None else "",
        })
    return meta, items


def main():
    print(f"Fetching source feed: {SOURCE_FEED}")
    source_xml = fetch(SOURCE_FEED).text

    meta, all_items = parse_source_feed(source_xml)
    episodes = all_items[:MAX_EPISODES] if MAX_EPISODES else all_items
    print(f"Found {len(all_items)} episodes in feed; processing {len(episodes)}.")

    for i, ep in enumerate(episodes, 1):
        page_url = ep["link"]
        print(f"  [{i}/{len(episodes)}] Scraping transcript: {ep['title'][:60]}")
        ep["transcript"] = scrape_transcript(page_url)
        time.sleep(DELAY_SECONDS)

    xml_out = build_feed(episodes, meta)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_out)

    print(f"\nDone. Combined feed saved to: {OUTPUT_FILE}")
    print("Host this file somewhere accessible (NAS, GitHub Pages, VPS)")
    print("and subscribe to it in Inoreader, NetNewsWire, etc.")


if __name__ == "__main__":
    main()
