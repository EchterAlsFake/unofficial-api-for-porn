<h1 align="center">Porn.com API</h1>
<p align="center"><em>An asynchronous Python API wrapper and scraper for porn.com</em></p>


<div align="center">
    <a href="https://pepy.tech/project/unofficial-api-for-porn"><img src="https://static.pepy.tech/badge/unofficial-api-for-porn" alt="Downloads"></a>
    <a href="https://github.com/EchterAlsFake/unofficial-api-for-porn/workflows/"><img src="https://github.com/EchterAlsFake/unofficial-api-for-porn/workflows/CodeQL/badge.svg" alt="CodeQL Analysis"/></a>
    <a href="https://echteralsfake.me/ci/unofficial-api-for-porn/badge.svg"><img src="https://echteralsfake.me/ci/unofficial-api-for-porn/badge.svg" alt="Sync API Tests"/></a>
    </div>


# Disclaimer
> [!IMPORTANT]
> This is an unofficial and unaffiliated project. Please read the full disclaimer before use:
> **[DISCLAIMER.md](https://github.com/EchterAlsFake/API_Docs/blob/master/Disclaimer.md)**
>
> By using this project you agree to comply with the target site's rules, copyright/licensing requirements,
> and applicable laws. Do not use it to bypass access controls or scrape at disruptive rates.

---

# Features

| Category | Details |
|---|---|
| **Video Fetching** | Fetch typed scene objects with title, duration, poster, language, performers, categories, availability, and deferred HTML loading |
| **Video Downloading** | Public unencrypted HLS downloads with configurable quality (`best`, `half`, `worst`, or specific resolutions), remuxing, callbacks, and reports |
| **Channel & Pornstar Profiles** | Fetch real channel and pornstar profiles, biographies, native statistics, linked performers, and complete video listings |
| **Category & Source Fetching** | Browse categories, source indexes, and performer/channel directories with pagination |
| **Video Search** | Search videos with the site's added-period, source, duration, and HD filters |
| **Host & Locale Support** | Twelve verified porn.com hosts, plus straight, gay, and trans listing routes |
| **Async-First** | Fully asynchronous (`async` / `await`) built on top of `asyncio` |
| **Built-in Caching** | Shared `BaseCore` response caching and configurable request retries |
| **CLI Support** | Inspect metadata or download scenes — run `porn_api -h` for options |
| **Type Safety** | Type hints and `dataclass`-based media models throughout |

`Video.author_name` and `author_link` expose the channel where the scene supplies
it. Use `await video.get_author()` for the linked profile. Performer names and
real links are available in `pornstars_names` and `pornstars_urls`.

Porn.com includes external referrals as well as native scenes. Referral metadata
remains available, but `is_playable=False` and downloads raise `VideoUnavailable`.
Only the verified `html` metadata source is exposed; no public video JSON API,
account, playlist, or separate Model/User interface was established.

#### Networking Features

The networking layer is provided by the [`eaf_base_api`](https://github.com/EchterAlsFake/eaf_base_api) package and is fully configurable through `RuntimeConfig`:

| Feature | Description |
|---|---|
| **HTTP/1.1, HTTP/2, HTTP/3** | Configurable HTTP version (`v1`, `v2`, `v3` — defaults to HTTP/2) |
| **Browser Impersonation** | Built-in browser fingerprint impersonation via `curl_cffi` (defaults to Chrome) |
| **Custom JA3 Fingerprint** | Override the TLS fingerprint with a custom JA3 string for advanced use cases |
| **Proxy Support** | All proxy types supported (HTTP, HTTPS, SOCKS4, SOCKS5) |
| **Proxy Authentication** | Username/password authentication for proxies |
| **Bandwidth Limiting** | Set a maximum download speed in MB/s (e.g., `2.0`, `3.5`) |
| **DNS over HTTPS** | Configure DNS over HTTPS through the shared backend |
| **SSL Verification** | Toggle SSL certificate verification on or off |
| **Request Delay** | Configurable delay between requests to respect rate limits |
| **Concurrency Control** | Configure item concurrency with `IteratorConfig`; site pagination is traversed sequentially |

---

# Supported Platforms
This API has been live-tested on:

- Linux with CPython 3.15.2, FFmpeg, and ffprobe

The package requires Python 3.12+. Other platforms and interpreter versions have
not been verified for this provider.

---

# Installation

This package is currently unpublished. Install from this checkout:

```bash
pip install -e .
```

Install FFmpeg separately for MP4 remuxing and metadata export. Development
setup and live-test commands are in [USAGE.md](USAGE.md).

---

# Quickstart

### Have a look at the [Documentation](https://docs.echteralsfake.me/porn) for more details

> [!NOTE]
> Porn.com API can also be used from the command line. Do: porn_api -h to see the options

```python
import asyncio
from porn_api import Client, DownloadConfigHLS

async def main():
    # Initialize a Client and close its owned network resources on exit.
    async with Client() as client:
        # Fetch a real Porn.com scene.
        video_object = await client.get_video("https://www.porn.com/scene/208974141")

        # Information from Video objects.
        print(video_object.title)

        # Download the video using the shared backend.
        config = DownloadConfigHLS(quality="best", path="./", remux=True)
        await video_object.download(config)

if __name__ == "__main__":
    asyncio.run(main())
```

---

# Support the Project ❤️

I develop all my projects entirely for free because I enjoy it and want to keep them accessible.
If you find my work useful, please consider supporting me with a small donation — even 1 € makes a big difference and keeps me motivated!

### ☕ Ko-fi
<a href="https://ko-fi.com/EchterAlsFake">https://ko-fi.com/EchterAlsFake</a>

### 💳 PayPal
<a href="https://paypal.me/EchterAlsFake">https://paypal.me/EchterAlsFake</a>

### 🪙 Crypto (350+ currencies supported)
<a href="https://nowpayments.io/donation?api_key=65b1acaf-735d-4d4b-b3d6-c2237c0b57e3" target="_blank" rel="noreferrer noopener">
   <img src="https://nowpayments.io/images/embeds/donation-button-black.svg" alt="Crypto donation button by NOWPayments">
</a>

---

# Contribution
Do you see any issues or having some feature requests? Simply open an Issue or talk
in the discussions.

Pull requests are also welcome.

# License
This API is licensed under the AGPLv3. See the `LICENSE` file for details.

> [!CAUTION]
> **Using this in a proprietary application?**
> Under the AGPLv3, if you integrate, modify, or host this API as part of your application (even over a network), you must open-source your entire application's code under the AGPL. 
>
> If you want to use this API without open-sourcing your own code, you must purchase a commercial license.
> 
> **For commercial licensing, contact:** EchterAlsFakeBS@proton.me
