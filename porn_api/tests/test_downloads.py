import asyncio
import json

import pytest
from base_api import DownloadConfigHLS

from .live_helpers import probe


@pytest.mark.parametrize("identity,locale", [("208974141", "de"), ("208581087", "www")])
async def test_every_rendition_and_selectors(client, tmp_path, identity, locale):
    video = await client.get_video(f"https://{locale}.porn.com/scene/{identity}")
    renditions = await video.get_qualities()
    expected = {360, 480, 1080} if identity == "208974141" else {360, 480, 720}
    assert {r.height for r in renditions} == expected
    matrix = []
    for r in renditions:
        progress = []
        path = tmp_path / f"{identity}-{r.height}.mp4"
        config = DownloadConfigHLS(
            quality=r.height,
            path=str(path),
            no_title=True,
            remux=True,
            return_report=True,
            callback=lambda *counts, progress=progress: progress.append(counts),
        )
        report = await video.download(config)
        assert report.status == "completed"
        assert report.downloaded == report.total > 0
        assert not report.missing
        assert progress and progress[-1][0] > 0
        assert config.m3u8_base_url is None  # Caller configuration is preserved.
        result = probe(path, r.width, r.height, video.duration)
        matrix.append({"selector": r.height, **result})
        path.unlink()
    if identity == "208974141":
        # Presets, absent-resolution fallback, metadata writing, and repeatability.
        for selector, height in [
            ("best", 1080),
            ("half", 480),
            ("worst", 360),
            (720, 480),
            ("worst", 360),
        ]:
            path = tmp_path / f"selector-{selector}.mp4"
            metadata = {"title": video.title, "comment": "porn_api live validation"}
            config = DownloadConfigHLS(
                quality=selector,
                path=str(path),
                no_title=True,
                remux=True,
                return_report=True,
                metadata=metadata,
                callback=lambda *_: None,
            )
            report = await video.download(config)
            assert report.status == "completed"
            result = probe(path, height=height, duration=video.duration)
            assert report.metadata_written
            assert result["tags"]["title"] == video.title
            assert result["tags"]["comment"] == metadata["comment"]
            matrix.append({"selector": selector, **result})
            path.unlink()
    print("DOWNLOAD_MATRIX", identity, json.dumps(matrix, sort_keys=True))


async def test_hls_without_remux(client, tmp_path):
    video = await client.get_video("https://www.porn.com/scene/208974141")
    path = tmp_path / "unremuxed.ts"
    report = await video.download(
        DownloadConfigHLS(
            quality="worst",
            path=str(path),
            no_title=True,
            return_report=True,
            callback=lambda *_: None,
        )
    )
    assert report.status == "completed"
    print("TS_DOWNLOAD", probe(path, width=640, height=360, duration=video.duration))
    path.unlink()


async def test_concurrent_videos_keep_stream_context(client, tmp_path):
    first = await client.get_video("https://de.porn.com/scene/208974141")
    second = await client.get_video("https://www.porn.com/scene/208581087")
    paths = [tmp_path / "first.mp4", tmp_path / "second.mp4"]
    reports = await asyncio.gather(
        *[
            v.download(
                DownloadConfigHLS(
                    quality="worst",
                    path=str(p),
                    no_title=True,
                    remux=True,
                    return_report=True,
                    callback=lambda *_: None,
                )
            )
            for v, p in zip([first, second], paths, strict=True)
        ]
    )
    for video, path, report in zip([first, second], paths, reports, strict=True):
        assert report.status == "completed"
        print(
            "CONCURRENT_DOWNLOAD",
            video.video_id,
            probe(path, height=360, duration=video.duration),
        )
        path.unlink()
