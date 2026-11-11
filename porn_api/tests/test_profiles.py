from collections import Counter, defaultdict

import pytest
from base_api import IteratorConfig, ResultOrder, update_url_query
from base_api.modules.errors import PageFetchError

from .live_helpers import ListingObserver, observe_pages


@pytest.mark.parametrize(
    "kind,slug,name",
    [
        ("channel", "bratty-sis", "Bratty Sis"),
        ("channel", "brazzers", "Brazzers"),
        ("pornstar", "azumi-mizushima", "Azumi Mizushima"),
        ("pornstar", "mia-khalifa", "Mia Khalifa"),
    ],
)
async def test_complete_profile_reconciliation(client, kind, slug, name):
    url = "https://www.porn.com/" + slug
    profile = await getattr(client, "get_" + kind)(url)
    assert profile.name == name
    assert profile.description and profile.profile_id
    observed = await observe_pages(client.core, url)
    assert observed[0].ids
    actual = defaultdict(list)
    async for result in profile.videos(pages="all"):
        video = result.unwrap()
        assert video.title and video.thumbnail_url and video.length
        actual[result.page_index].append(video.video_id)
    assert list(actual.values()) == [p.ids for p in observed]
    expected_ids = [identity for page in observed for identity in page.ids]
    actual_ids = [identity for ids in actual.values() for identity in ids]
    assert actual_ids == expected_ids
    assert Counter(actual_ids) == Counter(expected_ids)
    duplicates = {
        identity: count for identity, count in Counter(actual_ids).items() if count > 1
    }
    slots = sum(p.slots for p in observed)
    ad_slots = sum(p.ads for p in observed)
    # The advertised count includes records replaced by native advertisements.
    assert slots == profile.video_count
    if slug == "mia-khalifa":
        # Numeric pages 14–23 still exist after Next is disabled at page 13.
        assert len(observed) == 23
    assert len(actual_ids) + ad_slots == slots
    print(
        f"RECONCILIATION {slug}: pages={len(observed)} expected={len(expected_ids)} "
        f"actual={len(actual_ids)} advertised={profile.video_count} replaced_by_ads={ad_slots} "
        f"per_page={[len(p.ids) for p in observed]} duplicates={duplicates}"
    )
    last = len(observed)
    assert [
        r.unwrap().video_id async for r in profile.videos(start_page=last)
    ] == observed[-1].ids
    if slug in {"azumi-mizushima", "mia-khalifa"}:
        with pytest.raises(PageFetchError) as captured:
            _ = [
                r.unwrap()
                async for r in profile.videos(start_page=last + 1, pages="all")
            ]
        assert captured.value.original_error.status_code == 404
    else:
        assert [
            r.unwrap().video_id
            async for r in profile.videos(start_page=last + 1, pages="all")
        ] == []
    if last > 2:
        middle = last // 2
        assert [
            r.unwrap().video_id
            async for r in profile.videos(start_page=middle, pages=2)
        ] == observed[middle - 1].ids + observed[middle].ids
        assert (
            len(observed[-1].ids) < 117
        )  # Partial final page in both multipage examples.
    # Completion ordering retains the complete set when selected by the caller.
    unordered = [
        r.unwrap().video_id
        async for r in profile.videos(
            iterator_config=IteratorConfig(order=ResultOrder.COMPLETION)
        )
    ]
    assert set(unordered) == set(observed[0].ids)


@pytest.mark.parametrize(
    "getter,path,expected",
    [
        ("get_category", "yoga-porn", "Yoga Porn"),
        ("get_source", "xnxx", "XNXX"),
    ],
)
async def test_category_and_source_pages(client, getter, path, expected):
    collection = await getattr(client, getter)("https://www.porn.com/" + path)
    assert collection.name == expected
    assert collection.video_count > 100
    actual = [r.unwrap() async for r in collection.videos(pages=2)]
    first = ListingObserver(await client.core.fetch_text(collection.url))
    second = ListingObserver(
        await client.core.fetch_text(update_url_query(collection.url, pg=2))
    )
    assert [v.video_id for v in actual] == first.ids + second.ids
    assert len(actual) == 234


async def test_profile_specific_metadata(client):
    star = await client.get_pornstar("https://www.porn.com/azumi-mizushima")
    assert star.info["Gender"] == "Female"
    assert star.info["Height"] == "167cm"
    assert star.info["Birth place"] == "Japan"
    assert star.info["Birthday"] == "October 12, 1988"
    assert star.info["Total Videos"] == "1"
    channel = await client.get_channel("https://www.porn.com/brazzers", load_html=False)
    assert "name" not in channel.to_dict()
    await channel.load_fields("name")
    assert channel.name == "Brazzers"
    assert channel.info["Official Website"] == "Visit Brazzers"
