import pathlib
import re

import httpx

t = httpx.get(
    "https://mangakatana.com/manga/aishiteru-uso-dakedo.10797",
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=60,
).text
pathlib.Path(__file__).with_name("mk_detail_snip.html").write_text(
    t[t.find("single_book") : t.find("single_book") + 12000],
    encoding="utf-8",
)
ch = re.findall(
    r'<div class="chapter"><a href="https?://[^"]+/manga/([^"]+)"[^>]*>([^<]+)</a>',
    t,
)
series = "aishiteru-uso-dakedo.10797"
filtered = [(cid, title) for cid, title in ch if cid.startswith(series + "/")]
print("all", len(ch), "filtered", len(filtered))
print(filtered[:10])
