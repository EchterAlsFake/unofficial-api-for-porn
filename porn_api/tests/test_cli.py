import asyncio
import json
import sys

from .live_helpers import probe


async def test_live_cli_inspect():
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "porn_api",
        "https://www.porn.com/scene/208974141",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    assert process.returncode == 0, stderr.decode()
    result = json.loads(stdout)
    assert result["video_id"] == "208974141"
    assert result["duration"] == 345
    assert result["is_playable"] is True


async def test_live_cli_download(tmp_path):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "porn_api",
        "https://www.porn.com/scene/208974141",
        "--download",
        "--quality",
        "worst",
        "--output",
        str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
    assert process.returncode == 0, stderr.decode()
    paths = list(tmp_path.glob("*.mp4"))
    assert len(paths) == 1
    print("CLI_DOWNLOAD", probe(paths[0], height=360, duration=345))
    paths[0].unlink()
