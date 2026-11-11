import asyncio
from contextlib import aclosing

import pytest
from base_api import DataNotLoadedError, MediaLoadError
from selectolax.lexbor import LexborHTMLParser

from porn_api import Pornstar, errors
from porn_api.modules.consts import HOSTS


@pytest.mark.parametrize(
    "identity,duration,performers",
    [
        ("208327863", 606, ["Wow Love", "Wowlove2"]),
        ("208974141", 345, ["Boomerangwhite", "Coupleofhotsins"]),
        ("208581087", 632, ["Diamondick", "Rose G Empire"]),
    ],
)
async def test_metadata_and_lazy_html(client, identity, duration, performers):
    url = f"https://www.porn.com/scene/{identity}"
    video = await client.get_video(url, load_html=False)
    assert video.loaded_sources == frozenset()
    assert "title" not in video.to_dict()
    with pytest.raises(DataNotLoadedError):
        _ = video.title
    await asyncio.gather(video.load_fields("title"), video.load_sources("html"))
    assert video.loaded_sources == {"html"}
    assert video.duration == duration
    assert video.pornstars_names == performers
    page = LexborHTMLParser(await client.core.fetch_text(url))
    assert video.title == page.css_first("main h1").text(strip=True)
    assert video.thumbnail_url == page.css_first("video[data-hls]").attributes["poster"]
    assert video.tags == [
        n.text(strip=True)
        for n in page.css(".video-player__details .video-player__tags a")
    ]
    assert len(video.tags) == len(video.categories_urls) > 0
    assert video.is_playable is True
    assert video.unavailable_reason is None
    assert video.thumbnail_count == 30
    assert video.language == "en-US"
    assert video.author_name is None  # No studio/channel is supplied on these scenes.
    assert video.embed_url is None
    assert await video.get_author() is None
    repeated = (await client.get_video(url)).to_dict()
    original = video.to_dict()
    # A first response can set a new session cookie and change the next signed URL.
    assert repeated.pop("m3u8_base_url")
    assert original.pop("m3u8_base_url")
    assert repeated == original
    await video.load_sources("html")  # Idempotent repeated load.


@pytest.mark.parametrize("host", sorted(HOSTS))
async def test_verified_host_locale_and_media(client, host):
    video = await client.get_video(f"https://{host}/scene/208327863")
    expected = {
        "de": "de-DE",
        "es": "es-ES",
        "fr": "fr-FR",
        "it": "it-IT",
        "jp": "ja-JP",
        "ru": "ru-RU",
        "nl": "nl-NL",
        "pt": "pt-BR",
        "pl": "pl-PL",
        "se": "sv-SE",
    }.get(host.split(".")[0], "en-US")
    assert video.language == expected
    assert video.duration == 606
    assert video.video_id == "208327863"
    assert host in video.url
    qualities = await video.get_qualities()
    assert {r.height for r in qualities} == {360, 480, 1080}
    assert (await client.core.fetch_text(qualities[0].url)).startswith("#EXTM3U")
    profile = await client.get_pornstar(f"https://{host}/azumi-mizushima")
    assert profile.video_count == 1
    assert profile.language == expected
    assert [r.unwrap().video_id async for r in profile.videos(pages="all")] == [
        "205464990"
    ]


async def test_referral_scene_and_relationships(client):
    video = await client.get_video("https://www.porn.com/scene/186254188")
    assert (
        video.title
        == "Bratty Sis - BFF Catches StepBro Creaming His Sisters Pussy! S6:E8"
    )
    assert video.pornstars_names == ["Athena Faris"]
    assert video.pornstars_urls == ["https://www.porn.com/athena-faris"]
    assert video.is_playable is False
    assert video.m3u8_base_url is None
    assert video.duration is None
    assert "cannot be played" in video.unavailable_reason
    stars = await video.get_pornstars()
    assert len(stars) == 1 and isinstance(stars[0], Pornstar)
    assert stars[0].name == "Athena Faris"
    with pytest.raises(errors.VideoUnavailable):
        await video.get_qualities()
    channel = await client.get_channel("https://www.porn.com/bratty-sis")
    referrals = [r.unwrap() async for r in channel.videos()]
    assert referrals[0].source_name == "XNXX"
    source = await referrals[0].get_source()
    assert source.name == "XNXX"
    await referrals[0].load_sources("html")
    assert referrals[0].length == "12 min"  # Preserve listing-only metadata.
    assert referrals[0].thumbnail_url and referrals[0].rating == 71
    assert referrals[0].is_playable is False
    related = [r.unwrap() async for r in video.related_videos()]
    assert len(related) == 40
    assert all(v.video_id != video.video_id for v in related)
    assert all(v.title and v.rating is not None for v in related)
    # The caller may stop without leaking the Helper's page/item tasks.
    stream = video.related_videos()
    async with aclosing(stream):
        assert (await anext(stream)).unwrap().title


async def test_missing_scene_is_an_error(client):
    with pytest.raises(MediaLoadError) as captured:
        await client.get_video("https://www.porn.com/scene/999999999999")
    assert isinstance(captured.value.__cause__, errors.NotFound)
