"""
$description Kick, a gaming livestreaming platform
$url kick.com
$type live, vod
"""

import os
import re
import logging

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream
from streamlink.utils.parse import parse_json
from streamlink.exceptions import PluginError
from seleniumwire import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By

log = logging.getLogger(__name__)


@pluginmatcher(
    re.compile(
        # https://github.com/yt-dlp/yt-dlp/blob/9b7a48abd1b187eae1e3f6c9839c47d43ccec00b/yt_dlp/extractor/kick.py#LL33-L33C111
        r"https?://(?:www\.)?kick\.com/(?!(?:video|categories|search|auth)(?:[/?#]|$))(?P<channel>[\w_-]+)$",
    ),
    name="live",
)
@pluginmatcher(
    re.compile(
        # https://github.com/yt-dlp/yt-dlp/blob/2d5cae9636714ff922d28c548c349d5f2b48f317/yt_dlp/extractor/kick.py#LL84C18-L84C104
        r"https?://(?:www\.)?kick\.com/video/(?P<video_id>[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12})",
    ),
    name="vod",
)
@pluginmatcher(
    re.compile(
        r"https?://(?:www\.)?kick\.com/(?!(?:video|categories|search|auth)(?:[/?#]|$))(?P<channel>[\w_-]+)\?clip=(?P<clip_id>[\w_]+)$",
    ),
    name="clip",
)
class Kick(Plugin):
    def _get_streams(self):
        API_BASE_URL = "https://kick.com/api"

        _LIVE_SCHEMA = validate.Schema(
            validate.parse_json(),
            {
                "playback_url": validate.url(path=validate.endswith(".m3u8")),
                "livestream": {
                    "is_live": True,
                    "id": int,
                    "session_title": str,
                    "categories": [{"name": str}],
                },
                "user": {"username": str},
            },
            validate.union_get(
                "playback_url",
                ("livestream", "id"),
                ("user", "username"),
                ("livestream", "session_title"),
                ("livestream", "categories", 0, "name"),
            ),
        )

        _VIDEO_SCHEMA = validate.Schema(
            validate.parse_json(),
            {
                "source": validate.url(path=validate.endswith(".m3u8")),
                "id": int,
                "livestream": {
                    "channel": {"user": {"username": str}},
                    "session_title": str,
                    "categories": [{"name": str}],
                },
            },
            validate.union_get(
                "source",
                "id",
                ("livestream", "channel", "user", "username"),
                ("livestream", "session_title"),
                ("livestream", "categories", 0, "name"),
            ),
        )

        _CLIP_SCHEMA = validate.Schema(
            validate.parse_json(),
            {
                "clip": {
                    "video_url": validate.url(path=validate.endswith(".m3u8")),
                    "id": str,
                    "channel": {"username": str},
                    "title": str,
                    "category": {"name": str},
                },
            },
            validate.union_get(
                ("clip", "video_url"),
                ("clip", "id"),
                ("clip", "channel", "username"),
                ("clip", "title"),
                ("clip", "category", "name"),
            ),
        )

        live, vod, clip = (
            self.matches["live"],
            self.matches["vod"],
            self.matches["clip"],
        )

        try:
            options = webdriver.FirefoxOptions()
            options.add_argument('--headless')
            options.add_argument("--no-sandbox")
            proxy=os.getenv("PROXY")
            proxy_settings = {
            'proxy': {
                'http': 'http://'+proxy,
                'https': 'https://'+proxy,
                'no_proxy': 'localhost:127.0.0.1',
                }
             }
            service = FirefoxService(executable_path="/home/site/wwwroot/geckodriver")
            driver = webdriver.Firefox(service=service, options=options,seleniumwire_options=proxy_settings)
            url = "{0}/{1}/{2}".format(
                API_BASE_URL,
                *(
                    ["v1/channels", self.match["channel"]]
                    if live
                    else (
                        ["v1/video", self.match["video_id"]]
                        if vod
                        else ["v2/clips", self.match["clip_id"]]
                    )
                )
            )
            driver.get(url)
            page_source = driver.find_element(By.TAG_NAME, "body").text
            url, self.id, self.author, self.title, self.category = (
                _LIVE_SCHEMA if live else (_VIDEO_SCHEMA if vod else _CLIP_SCHEMA)
            ).validate(page_source)

        except (PluginError, TypeError) as err:
            log.debug(err)
            return
        
        finally:
            driver.quit()

        if live or vod:
            yield from HLSStream.parse_variant_playlist(self.session, url).items()
        elif (
            clip and self.author.casefold() == self.match["channel"].casefold()
        ):  
            yield "source", HLSStream(self.session, url)


__plugin__ = Kick
