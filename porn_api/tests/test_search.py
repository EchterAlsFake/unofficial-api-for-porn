import pytest
from base_api import update_url_query
from selectolax.lexbor import LexborHTMLParser

from porn_api import Category, Channel, Filters, Pornstar

from .live_helpers import ListingObserver


async def test_search_redirect_and_empty(client):
    videos = [r.unwrap() async for r in client.search("yoga", pages=2)]
    observations = [
        ListingObserver(
            await client.core.fetch_text(
                update_url_query(
                    "https://www.porn.com/yoga-porn", pg=page if page > 1 else None
                )
            )
        )
        for page in (1, 2)
    ]
    assert [v.video_id for v in videos] == observations[0].ids + observations[1].ids
    assert len(videos) == 234
    assert [r.unwrap() async for r in client.search("zzqwxnonexistent968771")] == []


@pytest.mark.parametrize(
    "filters",
    [
        Filters(added_days=1),
        Filters(added_days=7),
        Filters(added_days=30),
        Filters(added_days=90),
        Filters(added_days=365),
        Filters(source="xVideos"),
        Filters(hd=True),
        Filters(min_minutes=20),
        Filters(max_minutes=10),
        Filters(min_minutes=10, max_minutes=20, hd=True, source="XNXX"),
    ],
)
async def test_live_filters_match_site(client, filters):
    category = await client.get_category("https://www.porn.com/yoga-porn")
    observed = ListingObserver(
        await client.core.fetch_text(filters.apply(category.url))
    )
    actual = [r.unwrap() async for r in category.videos(filters=filters)]
    if not observed.ids:
        # These real added-date boundaries explicitly report page 0.
        assert filters.added_days in {1, 7}
        content = await client.core.fetch_text(filters.apply(category.url))
        assert "This listing goes to page 0" in content
    assert [v.video_id for v in actual] == observed.ids
    # Filter behavior is delegated to the site; comparison deliberately includes
    # its injected internal cards that can fall outside a requested filter.


@pytest.mark.parametrize(
    "method,type_,path",
    [
        ("categories", Category, "/categories"),
        ("pornstars", Pornstar, "/pornstars"),
        ("channels", Channel, "/sites"),
    ],
)
async def test_directories(client, method, type_, path):
    actual = [r.unwrap() async for r in getattr(client, method)()]
    assert actual and all(isinstance(o, type_) and o.name for o in actual)
    p = LexborHTMLParser(await client.core.fetch_text("https://www.porn.com" + path))
    expected = [
        a.attributes["href"] for a in p.css("main .category-list__group a[data-catid]")
    ]
    if not expected:
        expected = [a.attributes["href"] for a in p.css("main .list-global__title a")]
    assert [o.url for o in actual] == expected
    await actual[0].load_fields("name")
    assert actual[0].name


@pytest.mark.parametrize(
    "method,path", [("pornstars", "/pornstars"), ("channels", "/sites")]
)
async def test_complete_directory_pagination(client, method, path):
    from urllib.parse import parse_qs, urljoin, urlsplit

    from base_api.modules.errors import HTTPStatusError

    url = "https://www.porn.com" + path
    expected = []
    seen = set()
    while url:
        assert url not in seen
        seen.add(url)
        try:
            content = await client.core.fetch_text(url)
        except HTTPStatusError as error:
            assert error.status_code == 404 and expected
            break
        p = LexborHTMLParser(content)
        entries = [a.attributes["href"] for a in p.css("main .list-global__title a")]
        if not entries:
            break
        expected.extend(entries)
        n = p.css_first(".pagination a.next")
        href = n.attributes.get("href") if n else None
        page = int(parse_qs(urlsplit(content.url).query).get("pg", [1])[0])
        url = (
            urljoin(content.url, href)
            if href and not href.startswith("javascript:")
            else update_url_query(content.url, pg=page + 1)
        )
    actual = [r.unwrap().url async for r in getattr(client, method)(pages="all")]
    assert expected and actual == expected
    print(
        f"DIRECTORY {method}: pages={len(seen)} expected={len(expected)} actual={len(actual)}"
    )
