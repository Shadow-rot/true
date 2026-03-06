# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

from datetime import datetime, timezone
from random import randint
from time import time
from uuid import uuid4

from pymongo import AsyncMongoClient

from anony import config, logger, userbot

MAX_PLAYLISTS = 10
MAX_TRACKS = 200
MAX_WARNS = 3


class MongoDB:
    def __init__(self):
        self.mongo = AsyncMongoClient(config.MONGO_URL, serverSelectionTimeoutMS=12500)
        self.db = self.mongo.Anon

        self.admin_list = {}
        self.active_calls = {}
        self.admin_play = []
        self.blacklisted = []
        self.cmd_delete = []
        self.notified = []
        self.cache = self.db.cache
        self.logger = False

        self.assistant = {}
        self.assistantdb = self.db.assistant

        self.auth = {}
        self.authdb = self.db.auth

        self.chats = []
        self.chatsdb = self.db.chats

        self.lang = {}
        self.langdb = self.db.lang

        self.users = []
        self.usersdb = self.db.users

        self.playlistsdb = self.db.playlists
        self.tracksdb = self.db.playlist_tracks
        self.warnsdb = self.db.warns

    async def connect(self) -> None:
        try:
            start = time()
            await self.mongo.admin.command("ping")
            logger.info(f"Database connection successful. ({time() - start:.2f}s)")
            await self.load_cache()
        except Exception as e:
            raise SystemExit(f"Database connection failed: {type(e).__name__}") from e

    async def close(self) -> None:
        await self.mongo.close()
        logger.info("Database connection closed.")

    # ── CACHE ────────────────────────────────────────────────────────────────

    async def get_call(self, chat_id: int) -> bool:
        return chat_id in self.active_calls

    async def add_call(self, chat_id: int) -> None:
        self.active_calls[chat_id] = 1

    async def remove_call(self, chat_id: int) -> None:
        self.active_calls.pop(chat_id, None)

    async def playing(self, chat_id: int, paused: bool = None) -> bool | None:
        if paused is not None:
            self.active_calls[chat_id] = int(not paused)
        return bool(self.active_calls.get(chat_id, 0))

    async def get_admins(self, chat_id: int, reload: bool = False) -> list[int]:
        from anony.helpers._admins import reload_admins
        if chat_id not in self.admin_list or reload:
            self.admin_list[chat_id] = await reload_admins(chat_id)
        return self.admin_list[chat_id]

    # ── AUTH ─────────────────────────────────────────────────────────────────

    async def _get_auth(self, chat_id: int) -> set[int]:
        if chat_id not in self.auth:
            doc = await self.authdb.find_one({"_id": chat_id}) or {}
            self.auth[chat_id] = set(doc.get("user_ids", []))
        return self.auth[chat_id]

    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        return user_id in await self._get_auth(chat_id)

    async def add_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id not in users:
            users.add(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$addToSet": {"user_ids": user_id}}, upsert=True
            )

    async def rm_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id in users:
            users.discard(user_id)
            await self.authdb.update_one({"_id": chat_id}, {"$pull": {"user_ids": user_id}})

    async def get_auths(self, chat_id: int) -> list[int]:
        return list(await self._get_auth(chat_id))

    # ── ASSISTANT ─────────────────────────────────────────────────────────────

    async def set_assistant(self, chat_id: int) -> int:
        num = randint(1, len(userbot.clients))
        await self.assistantdb.update_one({"_id": chat_id}, {"$set": {"num": num}}, upsert=True)
        self.assistant[chat_id] = num
        return num

    async def get_assistant(self, chat_id: int):
        from anony import anon
        if chat_id not in self.assistant:
            doc = await self.assistantdb.find_one({"_id": chat_id})
            num = doc["num"] if doc else await self.set_assistant(chat_id)
            self.assistant[chat_id] = num
        return anon.clients[self.assistant[chat_id] - 1]

    async def get_client(self, chat_id: int):
        if chat_id not in self.assistant:
            await self.get_assistant(chat_id)
        return {1: userbot.one, 2: userbot.two, 3: userbot.three}.get(self.assistant[chat_id])

    # ── BLACKLIST ─────────────────────────────────────────────────────────────

    async def add_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted.append(chat_id)
            return await self.cache.update_one(
                {"_id": "bl_chats"}, {"$addToSet": {"chat_ids": chat_id}}, upsert=True
            )
        await self.cache.update_one(
            {"_id": "bl_users"}, {"$addToSet": {"user_ids": chat_id}}, upsert=True
        )

    async def del_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted.remove(chat_id)
            return await self.cache.update_one({"_id": "bl_chats"}, {"$pull": {"chat_ids": chat_id}})
        await self.cache.update_one({"_id": "bl_users"}, {"$pull": {"user_ids": chat_id}})

    async def get_blacklisted(self, chat: bool = False) -> list[int]:
        if chat:
            if not self.blacklisted:
                doc = await self.cache.find_one({"_id": "bl_chats"})
                self.blacklisted.extend(doc.get("chat_ids", []) if doc else [])
            return self.blacklisted
        doc = await self.cache.find_one({"_id": "bl_users"})
        return doc.get("user_ids", []) if doc else []

    # ── CHATS ─────────────────────────────────────────────────────────────────

    async def is_chat(self, chat_id: int) -> bool:
        return chat_id in self.chats

    async def add_chat(self, chat_id: int) -> None:
        if not await self.is_chat(chat_id):
            self.chats.append(chat_id)
            await self.chatsdb.insert_one({"_id": chat_id})

    async def rm_chat(self, chat_id: int) -> None:
        if await self.is_chat(chat_id):
            self.chats.remove(chat_id)
            await self.chatsdb.delete_one({"_id": chat_id})

    async def get_chats(self) -> list:
        if not self.chats:
            self.chats.extend([chat["_id"] async for chat in self.chatsdb.find()])
        return self.chats

    # ── CMD DELETE ────────────────────────────────────────────────────────────

    async def get_cmd_delete(self, chat_id: int) -> bool:
        if chat_id not in self.cmd_delete:
            doc = await self.chatsdb.find_one({"_id": chat_id})
            if doc and doc.get("cmd_delete"):
                self.cmd_delete.append(chat_id)
        return chat_id in self.cmd_delete

    async def set_cmd_delete(self, chat_id: int, delete: bool = False) -> None:
        if delete:
            self.cmd_delete.append(chat_id)
        else:
            self.cmd_delete.remove(chat_id)
        await self.chatsdb.update_one({"_id": chat_id}, {"$set": {"cmd_delete": delete}}, upsert=True)

    # ── LANGUAGE ──────────────────────────────────────────────────────────────

    async def set_lang(self, chat_id: int, lang_code: str):
        await self.langdb.update_one({"_id": chat_id}, {"$set": {"lang": lang_code}}, upsert=True)
        self.lang[chat_id] = lang_code

    async def get_lang(self, chat_id: int) -> str:
        if chat_id not in self.lang:
            doc = await self.langdb.find_one({"_id": chat_id})
            self.lang[chat_id] = doc["lang"] if doc else config.LANG_CODE
        return self.lang[chat_id]

    # ── LOGGER ────────────────────────────────────────────────────────────────

    async def is_logger(self) -> bool:
        return self.logger

    async def get_logger(self) -> bool:
        doc = await self.cache.find_one({"_id": "logger"})
        if doc:
            self.logger = doc["status"]
        return self.logger

    async def set_logger(self, status: bool) -> None:
        self.logger = status
        await self.cache.update_one({"_id": "logger"}, {"$set": {"status": status}}, upsert=True)

    # ── PLAY MODE ─────────────────────────────────────────────────────────────

    async def get_play_mode(self, chat_id: int) -> bool:
        if chat_id not in self.admin_play:
            doc = await self.chatsdb.find_one({"_id": chat_id})
            if doc and doc.get("admin_play"):
                self.admin_play.append(chat_id)
        return chat_id in self.admin_play

    async def set_play_mode(self, chat_id: int, remove: bool = False) -> None:
        if remove and chat_id in self.admin_play:
            self.admin_play.remove(chat_id)
        else:
            self.admin_play.append(chat_id)
        await self.chatsdb.update_one(
            {"_id": chat_id}, {"$set": {"admin_play": not remove}}, upsert=True
        )

    # ── SUDO ──────────────────────────────────────────────────────────────────

    async def add_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$addToSet": {"user_ids": user_id}}, upsert=True
        )

    async def del_sudo(self, user_id: int) -> None:
        await self.cache.update_one({"_id": "sudoers"}, {"$pull": {"user_ids": user_id}})

    async def get_sudoers(self) -> list[int]:
        doc = await self.cache.find_one({"_id": "sudoers"})
        return doc.get("user_ids", []) if doc else []

    # ── USERS ─────────────────────────────────────────────────────────────────

    async def is_user(self, user_id: int) -> bool:
        return user_id in self.users

    async def add_user(self, user_id: int) -> None:
        if not await self.is_user(user_id):
            self.users.append(user_id)
            await self.usersdb.insert_one({"_id": user_id})

    async def rm_user(self, user_id: int) -> None:
        if await self.is_user(user_id):
            self.users.remove(user_id)
            await self.usersdb.delete_one({"_id": user_id})

    async def get_users(self) -> list:
        if not self.users:
            self.users.extend([user["_id"] async for user in self.usersdb.find()])
        return self.users

    # ── PLAYLIST ──────────────────────────────────────────────────────────────

    async def pl_create(self, user_id: int, name: str) -> dict | None:
        try:
            count = await self.playlistsdb.count_documents({"user_id": user_id})
            if count >= MAX_PLAYLISTS:
                return None
            doc = {"_id": str(uuid4()), "user_id": user_id, "name": name.lower()}
            await self.playlistsdb.insert_one(doc)
            return doc
        except Exception:
            return None

    async def pl_get(self, user_id: int, name: str) -> dict | None:
        try:
            return await self.playlistsdb.find_one({"user_id": user_id, "name": name.lower()})
        except Exception:
            return None

    async def pl_get_by_id(self, pid: str) -> dict | None:
        try:
            return await self.playlistsdb.find_one({"_id": pid})
        except Exception:
            return None

    async def pl_list(self, user_id: int) -> list[dict]:
        try:
            return await self.playlistsdb.find({"user_id": user_id}).to_list(MAX_PLAYLISTS)
        except Exception:
            return []

    async def pl_delete(self, pid: str) -> None:
        try:
            await self.playlistsdb.delete_one({"_id": pid})
            await self.tracksdb.delete_many({"playlist_id": pid})
        except Exception:
            pass

    async def pl_add_track(self, pid: str, title: str, duration: int, url: str, video_id: str, added_by: int) -> dict | None:
        try:
            count = await self.tracksdb.count_documents({"playlist_id": pid})
            if count >= MAX_TRACKS:
                return None
            doc = {
                "_id": str(uuid4()),
                "playlist_id": pid,
                "title": title,
                "duration": duration,
                "url": url,
                "video_id": video_id,
                "added_by": added_by,
            }
            await self.tracksdb.insert_one(doc)
            return doc
        except Exception:
            return None

    async def pl_get_tracks(self, pid: str) -> list[dict]:
        try:
            return await self.tracksdb.find({"playlist_id": pid}).to_list(MAX_TRACKS)
        except Exception:
            return []

    async def pl_remove_track(self, pid: str, position: int) -> bool:
        try:
            tracks = await self.pl_get_tracks(pid)
            if position < 1 or position > len(tracks):
                return False
            await self.tracksdb.delete_one({"_id": tracks[position - 1]["_id"]})
            return True
        except Exception:
            return False

    async def pl_track_count(self, pid: str) -> int:
        try:
            return await self.tracksdb.count_documents({"playlist_id": pid})
        except Exception:
            return 0

    # ── WARNS ─────────────────────────────────────────────────────────────────

    async def warn_add(self, chat_id: int, user_id: int, reason: str) -> dict:
        key = f"{chat_id}:{user_id}"
        await self.warnsdb.update_one(
            {"_id": key},
            {
                "$inc": {"count": 1},
                "$push": {"reasons": reason or "No reason"},
                "$set": {"last_warn": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        return await self.warn_get(chat_id, user_id)

    async def warn_remove(self, chat_id: int, user_id: int) -> dict | None:
        doc = await self.warnsdb.find_one({"_id": f"{chat_id}:{user_id}"})
        if not doc or doc.get("count", 0) == 0:
            return None
        await self.warnsdb.update_one(
            {"_id": f"{chat_id}:{user_id}"},
            {"$inc": {"count": -1}, "$pop": {"reasons": 1}},
        )
        return await self.warn_get(chat_id, user_id)

    async def warn_get(self, chat_id: int, user_id: int) -> dict:
        doc = await self.warnsdb.find_one({"_id": f"{chat_id}:{user_id}"})
        return doc if doc else {"count": 0, "reasons": []}

    async def warn_reset(self, chat_id: int, user_id: int) -> None:
        await self.warnsdb.delete_one({"_id": f"{chat_id}:{user_id}"})

    # ── MIGRATION / STARTUP ───────────────────────────────────────────────────

    async def migrate_coll(self) -> None:
        logger.info("Migrating users and chats from old collections...")
        users, musers, mchats = [], [], []
        seen_chats, seen_users = set(), set()
        users.extend([user async for user in self.usersdb.find()])
        users.extend([user async for user in self.db.tgusersdb.find()])

        for user in users:
            _id = user.get("_id")
            user_id = _id if isinstance(_id, int) else int(user.get("user_id"))
            if user_id in seen_users:
                continue
            seen_users.add(user_id)
            musers.append({"_id": user_id})

        await self.usersdb.drop()
        await self.db.tgusersdb.drop()
        if musers:
            await self.usersdb.insert_many(musers)

        async for chat in self.chatsdb.find():
            _id = chat.get("_id")
            chat_id = _id if isinstance(_id, int) else int(chat.get("chat_id"))
            if chat_id in seen_chats:
                continue
            seen_chats.add(chat_id)
            mchats.append({"_id": chat_id})

        await self.chatsdb.drop()
        if mchats:
            await self.chatsdb.insert_many(mchats)

        await self.cache.insert_one({"_id": "migrated"})
        logger.info("Migration completed successfully.")

    async def load_cache(self) -> None:
        doc = await self.cache.find_one({"_id": "migrated"})
        if not doc:
            await self.migrate_coll()
        await self.get_chats()
        await self.get_users()
        await self.get_blacklisted(True)
        await self.get_logger()
        await self.playlistsdb.create_index([("user_id", 1), ("name", 1)], unique=True)
        await self.tracksdb.create_index([("playlist_id", 1)])
        await self.warnsdb.create_index([("_id", 1)])
        logger.info("Database cache loaded.")