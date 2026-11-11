"""Independent observations from real responses, never saved fixtures or mocks."""

import json
import subprocess
from html.parser import HTMLParser
from urllib.parse import urljoin

from base_api import update_url_query
from base_api.modules.errors import HTTPStatusError


class ListingObserver(HTMLParser):
    """Track list container nesting independently of the production CSS parser."""

    def __init__(self, content):
        super().__init__()
        self.depth = 0
        self.region = None
        self.ids = []
        self.slots = 0
        self.ads = 0
        self.next = None
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        a = dict(attributes)
        classes = set(a.get("class", "").split())
        if tag == "div":
            self.depth += 1
            if "list-videos" in classes:
                assert self.region is None, "Unexpected nested listing"
                self.region = self.depth
            elif (
                self.region is not None
                and self.depth == self.region + 1
                and "list-global__item" in classes
            ):
                self.slots += 1
                if a.get("data-itemid"):
                    self.ids.append(a["data-itemid"])
                else:
                    self.ads += 1
        if tag == "a" and {"pagination__number", "next"} <= classes:
            href = a.get("href", "")
            if not href.startswith(("javascript:", "#")):
                self.next = href

    def handle_endtag(self, tag):
        if tag == "div":
            if self.depth == self.region:
                self.region = None
            self.depth -= 1


async def observe_pages(core, url):
    pages = []
    seen = set()
    while url:
        assert url not in seen, "Live pagination loop"
        seen.add(url)
        try:
            content = await core.fetch_text(url)
        except HTTPStatusError as error:
            if error.status_code == 404 and pages:
                break
            raise
        observer = ListingObserver(content)
        if not observer.ids:
            break
        pages.append(observer)
        # Check the numeric page beyond disabled Next links independently too.
        url = (
            urljoin(content.url, observer.next)
            if observer.next
            else update_url_query(content.url, pg=len(pages) + 1)
        )
    return pages


def probe(path, width=None, height=None, duration=None):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    data = json.loads(result.stdout)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = [s for s in data["streams"] if s["codec_type"] == "audio"]
    assert audio, "Source supplies audio; completed output must retain it"
    assert path.stat().st_size > 100_000
    if width is not None:
        assert video["width"] == width
    if height is not None:
        assert video["height"] == height
    if duration is not None:
        assert abs(float(data["format"]["duration"]) - duration) < 2
    return {
        "width": video["width"],
        "height": video["height"],
        "duration": float(data["format"]["duration"]),
        "bytes": path.stat().st_size,
        "audio": audio[0]["codec_name"],
        "tags": data["format"].get("tags", {}),
    }
