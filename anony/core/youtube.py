import os
import re
import time
import random
import asyncio
import aiohttp
import yt_dlp
from pathlib import Path

from py_yt import Playlist, VideosSearch

from anony import logger, config
from anony.helpers import Track, utils

from .fallen_api import FallenApi


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies: list[str] = []
        self.checked = False
        self.warned = False
        self.fallen = FallenApi()
        self.cookie_dir = "anony/cookies"
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

    def get_cookies(self) -> str | None:
        if not self.checked:
            self.cookies = [
                f"{self.cookie_dir}/{f}"
                for f in os.listdir(self.cookie_dir)
                if f.endswith(".txt")
            ]
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("No cookies found; downloads may fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies...")
        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(urls):
                path = f"{self.cookie_dir}/cookie_{i}.txt"
                link = "https://batbin.me/api/v2/paste/" + url.split("/")[-1]
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(path, "wb") as f:
                        f.write(await resp.read())
        logger.info("Cookies saved.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        results = await (VideosSearch(query, limit=1, with_live=False)).next()
        if not results or not results["result"]:
            return None
        data = results["result"][0]
        return Track(
            id=data.get("id"),
            channel_name=data.get("channel", {}).get("name"),
            duration=data.get("duration"),
            duration_sec=utils.to_seconds(data.get("duration")),
            message_id=m_id,
            title=data.get("title")[:25],
            thumbnail=data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0],
            url=data.get("link"),
            view_count=data.get("viewCount", {}).get("short"),
            video=video,
        )

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                tracks.append(Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0],
                    url=data.get("link", "").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                ))
        except Exception as e:
            logger.warning("Playlist fetch failed: %s", e)
        return tracks

    def _cached(self, video_id: str, video: bool = False) -> str | None:
        exts = ["mp4", "webm"] if video else ["webm", "mp3", "m4a"]
        for ext in exts:
            path = self.download_dir / f"{video_id}.{ext}"
            if path.is_file():
                return str(path)
        return None

    def _build_extractor_args(self, cookie: str | None) -> dict:
        player_clients = (
            ["tv", "web_creator", "mweb", "default"]
            if cookie
            else ["web_safari", "web_embedded", "mweb"]
        )
        args: dict = {"player_client": player_clients}
        po_token = getattr(config, "PO_TOKEN", None)
        if po_token:
            args["po_token"] = [f"mweb.gvs+{po_token}", f"mweb.player+{po_token}"]
        return {"youtube": args}

    def _build_opts(self, video: bool, cookie: str | None) -> dict:
        base = {
            "outtmpl": str(self.download_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "noprogress": True,
            "noplaylist": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "overwrites": False,
            "retries": 10,
            "fragment_retries": 10,
            "concurrent_fragment_downloads": 4,
            "http_chunk_size": 10 * 1024 * 1024,
            "extractor_args": self._build_extractor_args(cookie),
        }
        if cookie:
            base["cookiefile"] = cookie
        if video:
            return {
                **base,
                "format": "bestvideo[height<=?720][width<=?1280][ext=mp4]+bestaudio/best[height<=?720]",
                "merge_output_format": "mp4",
            }
        return {
            **base,
            "format": "bestaudio[ext=webm][acodec=opus]/bestaudio",
        }

    async def download(self, video_id: str, video: bool = False) -> str | None:
        cached = self._cached(video_id, video)
        if cached:
            return cached

        if not video:
            if not config.API_URL or not config.API_KEY:
                logger.warning(
                    "FallenApi skipped for %s: %s is not set in config.",
                    video_id,
                    "API_URL" if not config.API_URL else "API_KEY",
                )
            else:
                logger.info("Trying FallenApi for %s...", video_id)
                path = await self.fallen.download_track(self.base + video_id)
                if path:
                    logger.info("FallenApi OK: %s", path)
                    return path
                logger.warning("FallenApi failed for %s; falling back to yt-dlp.", video_id)

        cookie = self.get_cookies()
        opts = self._build_opts(video, cookie)
        clients = opts["extractor_args"]["youtube"]["player_client"]
        has_po = bool(opts["extractor_args"]["youtube"].get("po_token"))

        logger.info(
            "yt-dlp: %s | cookie=%s | po_token=%s | clients=%s",
            video_id, bool(cookie), has_po, clients,
        )
        if not cookie and not has_po:
            logger.warning(
                "No cookies and no PO_TOKEN set. YouTube will likely reject this request. "
                "Add cookies to %s or set PO_TOKEN in config. "
                "See: https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide",
                self.cookie_dir,
            )

        def _run() -> str | None:
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    ydl.download([self.base + video_id])
                except yt_dlp.utils.DownloadError as e:
                    logger.warning("yt-dlp download error: %s", e)
                    if cookie and cookie in self.cookies:
                        self.cookies.remove(cookie)
                    return None
                except yt_dlp.utils.ExtractorError as e:
                    logger.warning("yt-dlp extractor error: %s", e)
                    return None
            result = self._cached(video_id, video)
            return result or (str(self.download_dir / f"{video_id}.{'mp4' if video else 'webm'}") if Path(self.download_dir / f"{video_id}.{'mp4' if video else 'webm'}").is_file() else None)

        return await asyncio.to_thread(_run)

    async def clear_cache(self, older_than_days: int = 7) -> int:
        cutoff = time.time() - older_than_days * 86400
        deleted = 0
        try:
            for path in self.download_dir.iterdir():
                if path.is_file() and path.stat().st_mtime < cutoff:
                    try:
                        path.unlink()
                        deleted += 1
                    except OSError:
                        pass
        except OSError:
            pass
        return deleted

    def get_cache_size(self) -> tuple[int, float]:
        try:
            files = [p for p in self.download_dir.iterdir() if p.is_file()]
            total = sum(p.stat().st_size for p in files)
            return len(files), round(total / (1024 * 1024), 2)
        except OSError:
            return 0, 0.0
