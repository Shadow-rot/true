# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import re
import yt_dlp
import random
import asyncio
import aiohttp
from pathlib import Path

from py_yt import Playlist, VideosSearch

from anony import logger, config
from anony.helpers import Track, utils

from .fallen_api import FallenApi


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.fallen = FallenApi()
        self.cookie_dir = "anony/cookies"
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        self.warned = False
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

    def get_cookies(self):
        if not self.checked:
            for file in os.listdir(self.cookie_dir):
                if file.endswith(".txt"):
                    self.cookies.append(f"{self.cookie_dir}/{file}")
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(urls):
                path = f"{self.cookie_dir}/cookie_{i}.txt"
                link = "https://batbin.me/api/v2/paste/" + url.split("/")[-1]
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(path, "wb") as fw:
                        fw.write(await resp.read())
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        _search = VideosSearch(query, limit=1, with_live=False)
        results = await _search.next()
        if results and results["result"]:
            data = results["result"][0]
            return Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")),
                message_id=m_id,
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                video=video,
            )
        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails")[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except:
            pass
        return tracks

    def _check_cached_file(self, video_id: str, video: bool = False) -> str | None:
        """Fast cache check with minimal overhead."""
        extensions = ["mp4", "webm"] if video else ["webm", "mp3", "m4a"]

        for ext in extensions:
            filename = self.download_dir / f"{video_id}.{ext}"
            if filename.is_file():
                return str(filename)

        return None

    async def download(self, video_id: str, video: bool = False) -> str | None:
        """Download video/audio with fast caching."""
        url = self.base + video_id

        # Quick cache check
        cached_file = self._check_cached_file(video_id, video)
        if cached_file:
            return cached_file

        # Try API download first (for audio only)
        if not video and config.API_KEY and config.API_URL:
            if file_path := await self.fallen.download_track(url):
                return file_path

        # Download using yt-dlp
        ext = "mp4" if video else "webm"
        filename = str(self.download_dir / f"{video_id}.{ext}")

        cookie = self.get_cookies()
        base_opts = {
            "outtmpl": str(self.download_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "nocheckcertificate": True,
            "cookiefile": cookie,
        }

        if video:
            ydl_opts = {
                **base_opts,
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio[ext=webm][acodec=opus]",
            }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
                    if cookie: 
                        self.cookies.remove(cookie)
                    return None
                except Exception as ex:
                    logger.warning("Download failed: %s", ex)
                    return None

            return filename if Path(filename).is_file() else None

        return await asyncio.to_thread(_download)

    async def clear_cache(self, older_than_days: int = 7) -> int:
        """Clear cached files older than specified days."""
        import time

        deleted_count = 0
        current_time = time.time()
        max_age_seconds = older_than_days * 24 * 60 * 60

        try:
            for file_path in self.download_dir.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        try:
                            file_path.unlink()
                            deleted_count += 1
                        except:
                            pass
        except:
            pass

        return deleted_count

    def get_cache_size(self) -> tuple[int, int]:
        """Get cache statistics (file_count, total_size_mb)."""
        try:
            file_count = 0
            total_size = 0

            for file_path in self.download_dir.iterdir():
                if file_path.is_file():
                    file_count += 1
                    total_size += file_path.stat().st_size

            size_mb = total_size / (1024 * 1024)
            return file_count, round(size_mb, 2)
        except:
            return 0, 0