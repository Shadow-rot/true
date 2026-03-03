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

    def __init__(self, retries: int = 3, timeout: int = 20):
        raw_url = getattr(config, "API_URL", None)
        raw_key = getattr(config, "API_KEY", None)

        self.api_url: str = raw_url.rstrip("/") if raw_url else ""
        self.api_key: str = raw_key if raw_key else ""
        self.configured: bool = bool(self.api_url and self.api_key)

        if not self.configured:
            logger.warning(
                "FallenApi not configured: %s",
                "API_URL missing" if not self.api_url else "API_KEY missing",
            )
        else:
            logger.info("FallenApi ready → %s", self.api_url)

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
        logger.info("FallenApi → GET %s", endpoint)
        session = await self._get_session()

        for attempt in range(1, self.retries + 1):
            try:
                async with session.get(endpoint) as resp:
                    raw = await resp.text()
                    logger.info(
                        "FallenApi ← HTTP %s (attempt %d/%d): %s",
                        resp.status, attempt, self.retries,
                        raw[:300],
                    )
                    if resp.status == 200:
                        try:
                            data = __import__("json").loads(raw)
                        except Exception:
                            logger.warning("FallenApi: response is not valid JSON.")
                            return None
                        if isinstance(data, dict) and data.get("cdnurl"):
                            return MusicTrack.from_dict(data)
                        logger.warning("FallenApi: missing 'cdnurl' in response: %s", data)
                        return None

                    logger.warning(
                        "FallenApi: HTTP %s on attempt %d/%d — will %s.",
                        resp.status, attempt, self.retries,
                        "retry" if attempt < self.retries else "give up",
                    )

            except asyncio.TimeoutError:
                logger.warning("FallenApi: timeout on attempt %d/%d.", attempt, self.retries)
            except aiohttp.ClientError as e:
                logger.warning("FallenApi: connection error on attempt %d/%d: %s", attempt, self.retries, e)
            except Exception as e:
                logger.warning("FallenApi: unexpected error on attempt %d/%d: %s", attempt, self.retries, e)

            if attempt < self.retries:
                await asyncio.sleep(2)

        logger.warning("FallenApi: all %d attempts failed for %s", self.retries, url)
        return None

    async def download_cdn(self, cdn_url: str, video_id: Optional[str] = None) -> Optional[str]:
        logger.info("FallenApi CDN download → %s", cdn_url)
        session = await self._get_session()

        for attempt in range(1, self.retries + 1):
            try:
                async with session.get(cdn_url) as resp:
                    if resp.status != 200:
                        logger.warning("CDN returned HTTP %s (attempt %d/%d).", resp.status, attempt, self.retries)
                        if attempt < self.retries:
                            await asyncio.sleep(2)
                        continue

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
                        logger.info("CDN: already cached at %s", save_path)
                        return str(save_path)

                    with open(save_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(256 * 1024):
                            f.write(chunk)

                    logger.info("CDN: saved to %s", save_path)
                    return str(save_path)

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning("CDN error on attempt %d/%d: %s", attempt, self.retries, e)
                if attempt < self.retries:
                    await asyncio.sleep(2)
            except Exception as e:
                logger.warning("CDN unexpected error: %s", e)
                if attempt < self.retries:
                    await asyncio.sleep(2)

        return None

    async def download_track(self, url: str) -> Optional[str]:
        if not self.configured:
            logger.warning("FallenApi.download_track called but API is not configured.")
            return None

        video_id = self._extract_video_id(url)
        logger.info("FallenApi.download_track: url=%s video_id=%s", url, video_id)

        if video_id:
            cached = self._cached(video_id)
            if cached:
                logger.info("FallenApi: cache hit → %s", cached)
                return cached

        track = await self.get_track(url)
        if not track:
            return None

        logger.info("FallenApi: track resolved → cdnurl=%s", track.cdnurl)
        dl_url = track.cdnurl

        tg_match = re.match(r"https?://t\.me/([^/]+)/(\d+)", dl_url)
        if tg_match:
            chat, msg_id = tg_match.groups()
            logger.info("FallenApi: downloading from Telegram %s/%s", chat, msg_id)
            try:
                msg = await app.get_messages(chat_id=chat, message_ids=int(msg_id))
                dest = str(self.download_dir / f"{video_id}.mp3") if video_id else str(self.download_dir)
                path = await msg.download(file_name=dest)
                logger.info("FallenApi: Telegram download complete → %s", path)
                return path
            except errors.FloodWait as e:
                logger.warning("FallenApi: FloodWait %ds — retrying.", e.value)
                await asyncio.sleep(e.value)
                return await self.download_track(url)
            except Exception as e:
                logger.warning("FallenApi: Telegram download failed: %s", e)
                return None

        return await self.download_cdn(dl_url, video_id)
