import asyncio
import os
import re
import uuid
import aiohttp
import urllib.parse
from typing import Optional
from pathlib import Path
from dataclasses import dataclass

from pyrogram import errors
from anony import config, logger, app


@dataclass
class MusicTrack:
    cdnurl: str
    url: str
    id: str
    key: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "MusicTrack":
        return cls(
            cdnurl=data.get("cdnurl", ""),
            url=data.get("url", ""),
            id=data.get("id", ""),
            key=data.get("key"),
        )


class FallenApi:
    _VIDEO_ID_RE = re.compile(
        r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
    )

    def __init__(self, retries: int = 3, timeout: int = 15):
        self.api_url = config.API_URL.rstrip("/")
        self.api_key = config.API_KEY
        self.retries = retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector,
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _extract_video_id(self, url: str) -> Optional[str]:
        match = self._VIDEO_ID_RE.search(url)
        return match.group(1) if match else None

    def _cached(self, video_id: str) -> Optional[str]:
        for ext in ("webm", "mp3", "m4a", "opus"):
            path = self.download_dir / f"{video_id}.{ext}"
            if path.is_file():
                return str(path)
        return None

    async def get_track(self, url: str) -> Optional[MusicTrack]:
        endpoint = f"{self.api_url}/api/track?url={urllib.parse.quote(url)}"
        session = await self._get_session()

        for attempt in range(1, self.retries + 1):
            try:
                async with session.get(endpoint) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200 and isinstance(data, dict):
                        return MusicTrack.from_dict(data)
                    if attempt == self.retries:
                        msg = data.get("message", "Unexpected error") if isinstance(data, dict) else "Unexpected error"
                        logger.warning("API error: %s (HTTP %s)", msg, resp.status)
                    return None
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == self.retries:
                    logger.warning("API unreachable after %d attempts.", self.retries)
            except Exception as e:
                if attempt == self.retries:
                    logger.warning("Unexpected API error: %s", e)

            await asyncio.sleep(1)

        return None

    async def download_cdn(self, cdn_url: str, video_id: Optional[str] = None) -> Optional[str]:
        session = await self._get_session()

        for attempt in range(1, self.retries + 1):
            try:
                async with session.get(cdn_url) as resp:
                    if resp.status != 200:
                        return None

                    if video_id:
                        ext_match = re.search(r"\.(\w+)(?:\?|$)", cdn_url)
                        ext = ext_match.group(1) if ext_match else "mp3"
                        filename = f"{video_id}.{ext}"
                    else:
                        cd = resp.headers.get("Content-Disposition", "")
                        match = re.findall(r'filename="?([^";]+)"?', cd)
                        filename = (
                            match[0]
                            if match
                            else os.path.basename(cdn_url.split("?")[0]) or f"{uuid.uuid4().hex[:8]}.mp3"
                        )

                    save_path = self.download_dir / filename
                    if save_path.is_file():
                        return str(save_path)

                    with open(save_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(256 * 1024):
                            f.write(chunk)

                    return str(save_path)

            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt < self.retries:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.warning("CDN download error: %s", e)
                if attempt < self.retries:
                    await asyncio.sleep(1)

        return None

    async def download_track(self, url: str) -> Optional[str]:
        video_id = self._extract_video_id(url)

        if video_id:
            cached = self._cached(video_id)
            if cached:
                return cached

        track = await self.get_track(url)
        if not track:
            return None

        dl_url = track.cdnurl
        tg_match = re.match(r"https?://t\.me/([^/]+)/(\d+)", dl_url)

        if tg_match:
            chat, msg_id = tg_match.groups()
            try:
                msg = await app.get_messages(chat_id=chat, message_ids=int(msg_id))
                dest = str(self.download_dir / f"{video_id}.mp3") if video_id else str(self.download_dir)
                return await msg.download(file_name=dest)
            except errors.FloodWait as e:
                await asyncio.sleep(e.value)
                return await self.download_track(url)
            except Exception as e:
                logger.warning("Telegram download failed: %s", e)
                return None

        return await self.download_cdn(dl_url, video_id)
