"""Verified routes and pure HTML extraction; no site JavaScript is executed."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser

from .errors import ParseError

HOST = "https://www.porn.com"
# Only populated with hosts whose scene identity and locale were checked live.
HOSTS = frozenset(
    {
        "porn.com",
        "www.porn.com",
        "de.porn.com",
        "es.porn.com",
        "fr.porn.com",
        "it.porn.com",
        "jp.porn.com",
        "ru.porn.com",
        "nl.porn.com",
        "pt.porn.com",
        "pl.porn.com",
        "se.porn.com",
    }
)
SCENE = re.compile(r"^/scene/(\d+)(?:/[^/]+)?/?$")


def normalize_url(url: str) -> str:
    p = urlsplit(url)
    if (
        p.scheme not in {"https", "http"}
        or p.hostname not in HOSTS
        or p.username is not None
        or p.password is not None
        or p.port not in {None, 80, 443}
    ):
        raise ValueError("Expected a verified porn.com URL")
    return urlunsplit(("https", p.hostname, p.path or "/", p.query, ""))


def video_identity(url: str) -> tuple[str, str]:
    url = normalize_url(url)
    match = SCENE.fullmatch(urlsplit(url).path)
    if not match:
        raise ValueError("Expected /scene/<numeric-id>[/<slug>]")
    return url, match[1]


def text(node) -> str | None:
    return node.text(separator=" ", strip=True).strip() or None if node else None


def integer(value: str | None) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else None


def page_parser(content: str) -> LexborHTMLParser:
    p = LexborHTMLParser(content)
    if not p.css_first("main h1"):
        raise ParseError(
            "Missing target page heading; refusing an empty/challenge response"
        )
    return p


def extract_videos(content: str, base_url: str) -> list[dict]:
    p = page_parser(content)
    if not p.css_first("main .list-videos"):
        # Real empty search pages retain a heading but can omit the list wrapper.
        body = p.css_first("body")
        if (
            body
            and "page-template-page-search-results"
            in body.attributes.get("class", "").split()
            and p.css_first("main .heading-primary__sub-title")
        ):
            return []
        raise ParseError("Expected video listing region")
    items = []
    for card in p.css("main .list-videos > .list-global__item[data-itemid]"):
        anchor = card.css_first(".list-global__title a")
        if not anchor:
            raise ParseError("Video card is missing its target link")
        identity = card.attributes["data-itemid"]
        if not identity.isdigit():
            raise ParseError("Invalid scene identity")
        link_url = urljoin(base_url, anchor.attributes["href"])
        scene_url = (
            link_url
            if SCENE.fullmatch(urlsplit(link_url).path)
            else urljoin(base_url, f"/scene/{identity}")
        )
        image = card.css_first("picture img")
        preview = card.css_first("video[data-preview]")
        source = card.css_first(".list-global__details span a")
        items.append(
            dict(
                url=scene_url,
                video_id=identity,
                title=text(anchor),
                thumbnail_url=image.attributes.get(
                    "data-src", image.attributes.get("src")
                )
                if image
                else None,
                length=text(card.css_first(".list-global__duration")),
                rating=integer(text(card.css_first(".list-global__rating"))),
                preview_video_url=preview.attributes.get("data-preview")
                if preview
                else None,
                source_name=text(source),
                source_url=urljoin(base_url, source.attributes["href"])
                if source
                else None,
                link_url=link_url,
            )
        )
    return items


def extract_directory(content: str, base_url: str) -> list[dict]:
    p = page_parser(content)
    result = []
    for anchor in p.css(
        "main .list-global__title a, main .category-list__group a[data-catid]"
    ):
        result.append(
            {
                "url": normalize_url(urljoin(base_url, anchor.attributes["href"])),
                "name": text(anchor),
            }
        )
    body = p.css_first("body")
    empty_directory = (
        body
        and "page-template-page-list-content"
        in body.attributes.get("class", "").split()
    )
    if not result and not p.css_first("main .list-global") and not empty_directory:
        raise ParseError("Directory has no recognized entries")
    return result


def next_page(content: str, base_url: str) -> str | None:
    p = page_parser(content)
    n = p.css_first("main .pagination a.next[href]")
    if not n or n.attributes["href"].startswith(("javascript:", "#")):
        return None
    return normalize_url(urljoin(base_url, n.attributes["href"]))
