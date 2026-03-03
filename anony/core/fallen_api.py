import asyncio
import os
import re
import uuid
import aiohttp
import urllib.parse
from typing import Dict, Optional
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
    def __init__(self, retries: int = 3, timeout: int = 15):
        self.api_url = config.API_URL.rstrip("/")
        self.api_key = config.API_KEY
        self.retries = retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL."""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([A-Za-z0-9_-]{11})',
            r'youtube\.com\/embed\/([A-Za-z0-9_-]{11})',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _check_cached_file(self, video_id: str) -> Optional[str]:
        """Fast cache check."""
        extensions = ["webm", "mp3", "m4a", "opus"]

        for ext in extensions:
            filename = self.download_dir / f"{video_id}.{ext}"
            if filename.is_file():
                return str(filename)

        return None

    async def get_track(self, url: str) -> Optional[MusicTrack]:
        endpoint = f"{self.api_url}/api/track?url={urllib.parse.quote(url)}"

        for attempt in range(1, self.retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.get(endpoint, headers=self._get_headers()) as resp:
                        data = await resp.json(content_type=None)

                        if resp.status == 200 and isinstance(data, dict):
                            return MusicTrack.from_dict(data)

                        if attempt == self.retries:
                            error_msg = data.get("message") if isinstance(data, dict) else None
                            status = data.get("status", resp.status) if isinstance(data, dict) else resp.status
                            logger.warning(f"[API ERROR] {error_msg or 'Unexpected error'} (status {status})")
                        return None

            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == self.retries:
                    logger.warning("[FAILED] All retry attempts exhausted.")
            except Exception as e:
                if attempt == self.retries:
                    logger.warning(f"[UNEXPECTED ERROR] {e}")

            await asyncio.sleep(1)

        return None

    async def download_cdn(self, cdn_url: str, video_id: Optional[str] = None) -> Optional[str]:
        """Fast CDN download with minimal overhead."""
        for attempt in range(1, self.retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.get(cdn_url) as resp:
                        if resp.status != 200:
                            return None

                        # Quick filename determination
                        if video_id:
                            ext_match = re.search(r'\.(\w+)(?:\?|$)', cdn_url)
                            ext = ext_match.group(1) if ext_match else "mp3"
                            filename = f"{video_id}.{ext}"
                        else:
                            cd = resp.headers.get("Content-Disposition")
                            if cd:
                                match = re.findall(r'filename="?([^";]+)"?', cd)
                                filename = match[0] if match else f"{uuid.uuid4().hex[:8]}.mp3"
                            else:
                                filename = os.path.basename(cdn_url.split("?")[0]) or f"{uuid.uuid4().hex[:8]}.mp3"

                        save_path = self.download_dir / filename

                        # Fast file existence check
                        if save_path.is_file():
                            return str(save_path)

                        # Fast download with larger chunks
                        with open(save_path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(64 * 1024):
                                if chunk:
                                    f.write(chunk)

                        return str(save_path)

            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt < self.retries:
                    await asyncio.sleep(1)
            except Exception:
                if attempt < self.retries:
                    await asyncio.sleep(1)

        return None

    async def download_track(self, url: str) -> Optional[str]:
        """Fast download with cache check."""
        # Quick cache check
        video_id = self._extract_video_id(url)
        if video_id:
            cached_file = self._check_cached_file(video_id)
            if cached_file:
                return cached_file

        # Get track metadata
        track = await self.get_track(url)
        if not track:
            return None

        dl_url = track.cdnurl

        # Handle Telegram downloads
        tg_match = re.match(r"https?://t\.me/([^/]+)/(\d+)", dl_url)
        if tg_match:
            chat, msg_id = tg_match.groups()
            try:
                msg = await app.get_messages(chat_id=chat, message_ids=int(msg_id))

                # Use video_id for filename if available
                if video_id:
                    file_name = str(self.download_dir / f"{video_id}.mp3")
                else:
                    file_name = str(self.download_dir)

                file_path = await msg.download(file_name=file_name)
                return file_path
            except errors.FloodWait as e:
                await asyncio.sleep(e.value)
                return await self.download_track(url)
            except:
                return None

        # CDN download
        return await self.download_cdn(dl_url, video_id)