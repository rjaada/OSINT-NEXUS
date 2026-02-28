import urllib.request
import feedparser

urls = [
    "https://news.un.org/feed/subscribe/ar/news/all/rss.xml",
    "https://www.france24.com/ar/rss",
]

for url in urls:
    print(f"\n--- Fetching {url} ---")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml = response.read()
            parsed = feedparser.parse(xml)
            print(f"Found {len(parsed.entries)} entries.")
            for e in parsed.entries[:3]:
                title = getattr(e, "title", "No Title")
                print(f"TITLE: {title}")
    except Exception as ex:
        print("Error:", ex)
