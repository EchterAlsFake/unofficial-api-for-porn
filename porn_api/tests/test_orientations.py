import pytest

from porn_api import Client

from .live_helpers import ListingObserver


@pytest.mark.parametrize(
    "orientation,slug", [("gay", "twink-porn"), ("trans", "tgirl-porn")]
)
async def test_orientation_routes(client, orientation, slug):
    async with Client(client.core, orientation=orientation) as oriented:
        categories = [r.unwrap() async for r in oriented.categories()]
        assert len(categories) > 20
        assert all(f"/{orientation}/" in c.url for c in categories)
        category = await oriented.get_category(
            f"https://www.porn.com/{orientation}/{slug}"
        )
        assert category.name
        actual = [r.unwrap() async for r in category.videos(pages=2)]
        first = ListingObserver(await client.core.fetch_text(category.url))
        second = ListingObserver(await client.core.fetch_text(category.url + "?pg=2"))
        assert [v.video_id for v in actual] == first.ids + second.ids
        assert len(actual) == (240 if orientation == "gay" else 234)
        # These routes currently have referrals, not internal HLS cards.
        video = await oriented.get_video(actual[0].url)
        assert video.is_playable is False
        assert video.pornstars_names or video.tags
        for method in ("pornstars", "channels"):
            profiles = [r.unwrap() async for r in getattr(oriented, method)()]
            assert profiles and all(f"/{orientation}/" in p.url for p in profiles)
            await profiles[0].load_sources("html")
            assert profiles[0].name and profiles[0].video_count > 0
            listing = [r.unwrap() async for r in profiles[0].videos()]
            expected = ListingObserver(await client.core.fetch_text(profiles[0].url))
            assert [v.video_id for v in listing] == expected.ids
        found = [r.unwrap() async for r in oriented.search(slug.split("-")[0])]
        assert found
        # Root links in the straight directory are directories themselves.
        root = await oriented.get_category(f"https://www.porn.com/{orientation}")
        assert root.is_directory and root.video_count is None
        assert [r.unwrap().url async for r in root.categories()] == [
            c.url for c in categories
        ]
