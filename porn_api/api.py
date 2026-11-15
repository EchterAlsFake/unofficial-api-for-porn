"""Async porn.com scenes, directories, profiles, and shared-backend downloads."""

from __future__ import annotations

from base_api import paginated_stream, PageInfo, validate_pagination, ScrapeStream
from base_api.modules.pagination import linked_page

import argparse
import asyncio
import json
from contextlib import aclosing
from dataclasses import dataclass, replace
from typing import ClassVar, Literal
from urllib.parse import parse_qs, urljoin, urlsplit

import m3u8
from base_api import (
    BaseCore,
    BaseMedia,
    DownloadConfigHLS,
    ErrorMode,
    IteratorConfig,
    make_iterator_config,
    media_field,
    scrape_stream,
    update_url_query,
)
from base_api.modules.errors import HTTPStatusError, PageFetchError
from base_api.modules.logger import get_logger
from base_api.modules.provider import (
    download_errors,
    fetch_content,
    prepare_download_config,
)
from base_api.modules.static_functions import collect_variants

from .modules import errors
from .modules.consts import (
    HOST,
    extract_directory,
    extract_videos,
    integer,
    next_page,
    normalize_url,
    page_parser,
    text,
    video_identity,
)

logger = get_logger(__name__)


async def get_html_content(core: BaseCore, url: str, *, owner=None) -> str:
    return await fetch_content(
        core, url, logger=logger, owner=owner, error_types=errors
    )


@dataclass(frozen=True, slots=True)
class Rendition:
    width: int
    height: int
    bandwidth: int | None
    url: str


@dataclass(slots=True, kw_only=True, repr=False)
class Video(BaseMedia):
    url: str
    core: BaseCore
    video_id: str | None = None
    title: str | None = media_field("html")
    thumbnail_url: str | None = media_field("html")
    length: str | None = media_field("html")
    duration: int | None = media_field("html")
    language: str | None = media_field("html")
    tags: list[str] | None = media_field("html")
    categories_urls: list[str] | None = media_field("html")
    pornstars_names: list[str] | None = media_field("html")
    pornstars_urls: list[str] | None = media_field("html")
    author_name: str | None = media_field("html")
    author_link: str | None = media_field("html")
    m3u8_base_url: str | None = media_field("html")
    embed_url: str | None = media_field("html")
    is_playable: bool | None = media_field("html")
    unavailable_reason: str | None = media_field("html")
    thumbnail_template: str | None = media_field("html")
    thumbnail_count: int | None = media_field("html")
    # These values belong to the originating listing HTML, not scene statistics.
    rating: int | None = None
    preview_video_url: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    link_url: str | None = None

    loader_methods: ClassVar[dict[str, str]] = {"html": "_load_html"}

    def __post_init__(self):
        self.url, identity = video_identity(self.url)
        if self.video_id is not None and self.video_id != identity:
            raise ValueError("Scene URL and supplied ID disagree")
        self.video_id = identity

    async def _load_html(self) -> dict:
        content = await get_html_content(self.core, self.url, owner=self)
        resolved = getattr(content, "url", None) or self.url
        _, identity = video_identity(resolved)
        if identity != self.video_id:
            raise errors.ParseError("Response redirected to a different scene")
        p = page_parser(content)
        vote = p.css_first(".scene-vote[data-itemid]")
        if not vote or vote.attributes["data-itemid"] != self.video_id:
            raise errors.ParseError("Response scene ID does not match requested video")
        player = p.css_first("video.video-player__custom")
        attrs = player.attributes if player else {}
        stream = attrs.get("data-hls")
        no_embed = p.css_first(".video-player__no-embed")
        if not stream and not no_embed:
            raise errors.ParseError("Unrecognized scene player layout")
        duration = integer(attrs.get("data-duration"))
        actors = p.css(".video-player__details .video-player__actor")
        channel = p.css_first(".video-player__details .video-player__channel")
        categories = p.css(".video-player__details .video-player__tags a[href]")

        def seeded(name):
            return getattr(self, name) if self.is_field_loaded(name) else None

        return {
            "title": text(p.css_first("main h1")),
            "thumbnail_url": attrs.get("poster") or seeded("thumbnail_url"),
            "length": f"{duration // 60}:{duration % 60:02}"
            if duration is not None
            else seeded("length"),
            "duration": duration,
            "language": p.css_first("html").attributes.get("lang"),
            "tags": [text(n) for n in categories],
            "categories_urls": [
                normalize_url(urljoin(resolved, n.attributes["href"]))
                for n in categories
            ],
            "pornstars_names": [text(n) for n in actors],
            "pornstars_urls": [
                normalize_url(urljoin(resolved, n.attributes["href"]))
                for n in actors
                if n.attributes.get("href")
            ],
            "author_name": text(channel),
            "author_link": normalize_url(urljoin(resolved, channel.attributes["href"]))
            if channel and channel.attributes.get("href")
            else None,
            "m3u8_base_url": urljoin(resolved, stream) if stream else None,
            "embed_url": None,
            "is_playable": bool(stream),
            "unavailable_reason": text(no_embed),
            "thumbnail_template": attrs.get("data-thumb-tpl") or None,
            "thumbnail_count": integer(attrs.get("data-thumb-count")),
        }

    async def get_qualities(self) -> list[Rendition]:
        await self.load_fields("m3u8_base_url", "unavailable_reason")
        if not self.m3u8_base_url:
            raise errors.VideoUnavailable(
                self.unavailable_reason or "No public HLS player"
            )
        master = m3u8.loads(await get_html_content(self.core, self.m3u8_base_url))
        if not master.is_variant:
            raise errors.ParseError("Expected an HLS master playlist")
        result = []
        for variant in collect_variants(master):
            resolution = variant["raw"].stream_info.resolution
            if not resolution:
                raise errors.ParseError("Rendition lacks dimensions")
            result.append(
                Rendition(
                    width=resolution[0],
                    height=resolution[1],
                    bandwidth=variant.get("bandwidth"),
                    url=urljoin(self.m3u8_base_url, variant["uri"]),
                )
            )
        if not result:
            raise errors.ParseError("Master playlist has no video renditions")
        return sorted(result, key=lambda r: (r.height, r.bandwidth or 0))

    @download_errors(errors.DownloadFailed)
    async def download(self, configuration: DownloadConfigHLS, *, refresh: bool = True):
        """Download unencrypted public HLS; refresh signed sources per operation."""
        if not isinstance(configuration, DownloadConfigHLS):
            raise TypeError("Porn.com exposes HLS; use DownloadConfigHLS")
        media = self
        if refresh:
            # A new model refreshes sources without racing mutation of this model
            # or the caller's core/configuration in concurrent downloads.
            media = Video(url=self.url, core=self.core)
            from base_api import CachePolicy

            await self.core.fetch_text(self.url, cache_policy=CachePolicy.REFRESH)
        renditions = await media.get_qualities()
        # Respect encryption/DRM boundaries before passing URLs to the downloader.
        for rendition in renditions:
            playlist = m3u8.loads(await get_html_content(self.core, rendition.url))
            if any(key and key.method != "NONE" for key in playlist.keys):
                raise errors.VideoUnavailable("Encrypted HLS is unsupported")
        config = prepare_download_config(configuration, media.title or self.video_id)
        config.m3u8_base_url = media.m3u8_base_url
        return await self.core.download(configuration=config)

    async def get_pornstars(self, *, load_html: bool = True) -> list[Pornstar]:
        await self.load_fields("pornstars_urls")
        client = Client(self.core)
        return [
            await client.get_pornstar(url, load_html=load_html)
            for url in self.pornstars_urls or ()
        ]

    async def get_author(self, *, load_html: bool = True) -> Channel | None:
        await self.load_fields("author_link")
        return (
            await Client(self.core).get_channel(self.author_link, load_html=load_html)
            if self.author_link
            else None
        )

    async def get_source(self, *, load_html: bool = True) -> Source | None:
        return (
            await Client(self.core).get_source(self.source_url, load_html=load_html)
            if self.source_url
            else None
        )

    def related_videos(self, *, iterator_config: IteratorConfig | None = None):
        return _listing(
            self.core,
            self.url,
            Video,
            extract_videos,
            pages=1,
            iterator_config=iterator_config,
        )


@dataclass(slots=True, kw_only=True, repr=False)
class Collection(BaseMedia):
    url: str
    core: BaseCore
    name: str | None = media_field("html")
    description: str | None = media_field("html")
    language: str | None = media_field("html")
    video_count: int | None = media_field("html")
    profile_id: str | None = media_field("html")
    info: dict[str, str] | None = media_field("html")
    social_links: list[str] | None = media_field("html")
    loader_methods: ClassVar[dict[str, str]] = {"html": "_load_html"}
    page_type: ClassVar[str | None] = None

    def __post_init__(self):
        self.url = normalize_url(self.url)
        segments = urlsplit(self.url).path.strip("/").split("/")
        if not segments[0] or (
            len(segments) != 1
            and not (len(segments) == 2 and segments[0] in {"gay", "trans"})
        ):
            raise ValueError(
                "Expected a profile/category slug, optionally under /gay or /trans"
            )

    async def _load_html(self) -> dict:
        content = await get_html_content(self.core, self.url, owner=self)
        p = page_parser(content)
        body = p.css_first("body")
        classes = body.attributes.get("class", "").split()
        if self.page_type and f"single-{self.page_type}" not in classes:
            raise errors.ParseError(
                f"Requested {self.page_type} profile, received another page type"
            )
        if not self.page_type and not (
            "single-category" in classes
            or (
                urlsplit(self.url).path.rstrip("/") in {"/gay", "/trans"}
                and "home" in classes
            )
        ):
            raise errors.ParseError("Requested category, received another page type")
        info = {}
        for n in p.css(".profile__bio-item"):
            label = n.css_first("label")
            if label:
                key = text(label).rstrip(":")
                label.decompose()
                info[key] = text(n) or ""
        count = integer(text(p.css_first(".heading-primary__sub-title")))
        if count is None:
            count = integer(text(p.css_first(".pagination__label")))
        if count is None:
            count = integer(
                info.get("Total Videos") or info.get("Gesamtzahl der Videos")
            )
        return {
            "name": text(p.css_first("main h1")),
            "description": "\n\n".join(
                n.text(strip=True) for n in p.css(".body-text > .row:first-child p")
            )
            or None,
            "language": p.css_first("html").attributes.get("lang"),
            "video_count": count,
            "profile_id": body.attributes.get("data-pi")
            if body.attributes.get("data-pi") not in {None, "0"}
            else None,
            "info": info,
            "social_links": [
                n.attributes["href"] for n in p.css(".profile__bio a[href]")
            ],
        }

    def videos(
        self,
        *,
        pages: int | Literal["all"] = 1,
        start_page: int = 1,
        filters: Filters | None = None,
        iterator_config: IteratorConfig | None = None,
    ):
        validate_pagination(pages, start_page)
        url = filters.apply(self.url) if filters else self.url
        return _listing(
            self.core,
            url,
            Video,
            extract_videos,
            pages=pages,
            start_page=start_page,
            iterator_config=iterator_config,
        )


class Pornstar(Collection):
    page_type = "pornstar"


class Channel(Collection):
    page_type = "channel"


class Source(Collection):
    """The site's source index (for example XNXX), distinct from a studio."""

    page_type = "source"


class Category(Collection):
    """A named category listing, distinct from performer and channel profiles."""

    @property
    def is_directory(self) -> bool:
        return urlsplit(self.url).path.rstrip("/") in {"/gay", "/trans"}

    def videos(self, **kwargs):
        if self.is_directory:
            raise ValueError(
                "This is a category directory; use categories() to browse it"
            )
        return super().videos(**kwargs)

    def categories(self, *, iterator_config: IteratorConfig | None = None):
        if not self.is_directory:
            raise ValueError("Only /gay and /trans are category directories")
        return _listing(
            self.core,
            self.url.rstrip("/") + "/categories",
            Category,
            extract_directory,
            iterator_config=iterator_config,
        )


@dataclass(frozen=True, slots=True)
class Filters:
    """Observed site filters; duration limits are in minutes."""

    added_days: Literal[1, 7, 30, 90, 365] | None = None
    source: str | None = None
    hd: bool = False
    min_minutes: int | None = None
    max_minutes: int | None = None

    def apply(self, url: str) -> str:
        if self.added_days not in {None, 1, 7, 30, 90, 365}:
            raise ValueError("Unsupported added-days filter")
        for v in (self.min_minutes, self.max_minutes):
            if v is not None and (
                isinstance(v, bool) or not isinstance(v, int) or v < 0
            ):
                raise ValueError("Duration bounds must be nonnegative integer minutes")
        if (
            self.min_minutes is not None
            and self.max_minutes is not None
            and self.min_minutes > self.max_minutes
        ):
            raise ValueError("Minimum duration exceeds maximum")
        return update_url_query(
            url,
            ad=self.added_days,
            so=self.source,
            qu="hd" if self.hd else None,
            ll=self.min_minutes,
            lh=self.max_minutes,
        )


def _listing(
    core, url, constructor, extractor, *, pages=1, start_page=1, iterator_config=None
):
    validate_pagination(pages, start_page)
    url = normalize_url(url)
    if urlsplit(url).path.rstrip("/").endswith("/search"):

        async def resolve_search():
            content = await get_html_content(core, url)
            actual = getattr(content, "url", None) or url
            if urlsplit(actual).path.rstrip("/").endswith("/search"):
                raise errors.ParseError("Search did not resolve to its listing route")
            stream = _listing(
                core,
                actual,
                constructor,
                extractor,
                pages=pages,
                start_page=start_page,
                iterator_config=iterator_config,
            )
            async with stream:
                async for result in stream:
                    yield result

        return ScrapeStream(resolve_search())

    def page_url(page):
        return update_url_query(url, pg=page if page > 1 else None)

    def info(content, page, rows):
        actual = getattr(content, "url", None) or page_url(page)
        normalize_url(actual)
        if urlsplit(actual).path.rstrip("/") != urlsplit(url).path.rstrip(
            "/"
        ) and not urlsplit(url).path.rstrip("/").endswith("/search"):
            raise errors.ParseError("Listing redirected to a different resource")
        following = next_page(content, actual)
        if following:
            if int(parse_qs(urlsplit(following).query).get("pg", [1])[0]) != page + 1:
                raise errors.ParseError("Unexpected next page number")
            if urlsplit(following).hostname != urlsplit(actual).hostname:
                raise errors.ParseError("Pagination changed locale/host")
        # No next anchor is insufficient on this site; probe the established
        # numbered route until its real empty page/404 boundary.
        return PageInfo(
            terminal=not rows,
            next_url=following or update_url_query(actual, pg=page + 1),
            next_is_probe=following is None,
        )

    return paginated_stream(
        core=core,
        constructor=constructor,
        page_url=page_url,
        item_extractor=lambda content: extractor(
            content, getattr(content, "url", None) or url
        ),
        page_info=info,
        pages=pages,
        start_page=start_page,
        iterator_config=iterator_config
        or make_iterator_config(
            load_specific_sources=(),
            page_error_mode=ErrorMode.RAISE,
            item_error_mode=ErrorMode.RAISE,
        ),
        terminal_error=lambda error, page: page > 1 and _is_404(error),
        verify_first=True,
    )


def _is_404(error: BaseException) -> bool:
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, HTTPStatusError):
            return error.status_code == 404
        error = getattr(error, "original_error", None) or error.__cause__
    return False


class Client:
    def __init__(
        self,
        core: BaseCore | None = None,
        *,
        base_url: str = HOST,
        orientation: Literal["straight", "gay", "trans"] = "straight",
    ):
        self.core = core if core is not None else BaseCore()
        self._owns_core = core is None
        self.base_url = normalize_url(base_url).rstrip("/")
        if urlsplit(self.base_url).path or urlsplit(self.base_url).query:
            raise ValueError("base_url must contain only the verified host")
        if orientation not in {"straight", "gay", "trans"}:
            raise ValueError("Unknown orientation")
        self.content_url = self.base_url + (
            "/" + orientation if orientation != "straight" else ""
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def close(self):
        if self._owns_core:
            await self.core.close()

    async def get_video(self, url: str, load_html: bool = True) -> Video:
        video = Video(url=url, core=self.core)
        if load_html:
            await video.load_sources("html")
        return video

    async def _get_collection(self, kind, url, load_html):
        result = kind(url=url, core=self.core)
        if load_html:
            await result.load_sources("html")
        return result

    async def get_pornstar(self, url: str, load_html: bool = True) -> Pornstar:
        return await self._get_collection(Pornstar, url, load_html)

    async def get_channel(self, url: str, load_html: bool = True) -> Channel:
        return await self._get_collection(Channel, url, load_html)

    async def get_category(self, url: str, load_html: bool = True) -> Category:
        return await self._get_collection(Category, url, load_html)

    async def get_source(self, url: str, load_html: bool = True) -> Source:
        return await self._get_collection(Source, url, load_html)

    def search(
        self,
        query: str,
        *,
        pages: int | Literal["all"] = 1,
        start_page: int = 1,
        filters: Filters | None = None,
        iterator_config: IteratorConfig | None = None,
    ):
        validate_pagination(pages, start_page)
        if not query.strip() or len(query) > 100:
            raise ValueError("Search query must contain 1–100 characters")
        url = update_url_query(f"{self.content_url}/search", sq=query.strip())
        if filters:
            url = filters.apply(url)
        return _listing(
            self.core,
            url,
            Video,
            extract_videos,
            pages=pages,
            start_page=start_page,
            iterator_config=iterator_config,
        )

    def pornstars(self, *, pages=1, start_page=1, iterator_config=None):
        validate_pagination(pages, start_page)
        return _listing(
            self.core,
            f"{self.content_url}/pornstars",
            Pornstar,
            extract_directory,
            pages=pages,
            start_page=start_page,
            iterator_config=iterator_config,
        )

    def channels(self, *, pages=1, start_page=1, iterator_config=None):
        validate_pagination(pages, start_page)
        return _listing(
            self.core,
            f"{self.content_url}/sites",
            Channel,
            extract_directory,
            pages=pages,
            start_page=start_page,
            iterator_config=iterator_config,
        )

    def categories(self, *, iterator_config=None):
        return _listing(
            self.core,
            f"{self.content_url}/categories",
            Category,
            extract_directory,
            pages=1,
            iterator_config=iterator_config,
        )


def create_parser():
    parser = argparse.ArgumentParser(
        description="Inspect/download public porn.com scenes"
    )
    parser.add_argument("url", help="porn.com /scene/ URL")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output", default="./")
    parser.add_argument("--quality", default="best")
    return parser


async def run_main(argv=None):
    args = create_parser().parse_args(argv)
    async with Client() as client:
        video = await client.get_video(args.url)
        if args.download:
            await video.download(
                DownloadConfigHLS(quality=args.quality, path=args.output, remux=True)
            )
        else:
            print(json.dumps(video.to_dict(), ensure_ascii=False, indent=2))


def main():
    asyncio.run(run_main())
