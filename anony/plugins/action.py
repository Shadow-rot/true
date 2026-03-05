from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List
from collections import defaultdict

import pytz
from pyrogram import filters, enums
from pyrogram.enums import ButtonStyle
from pyrogram.types import (
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
    User,
)
from pyrogram.errors import (
    ChatAdminRequired,
    UserAdminInvalid,
    RPCError,
    FloodWait,
    PeerIdInvalid,
    UsernameNotOccupied,
    UsernameInvalid,
)

from anony import app, config
OWNER_ID = 5147822244

KOLKATA_TZ = pytz.timezone("Asia/Kolkata")


class Action(Enum):
    BAN      = "BAN"
    UNBAN    = "UNBAN"
    MUTE     = "MUTE"
    UNMUTE   = "UNMUTE"
    KICK     = "KICK"
    WARN     = "WARN"
    UNWARN   = "UNWARN"
    SBAN     = "SILENT BAN"
    DBAN     = "DELETE + BAN"
    TBAN     = "TEMP BAN"
    TMUTE    = "TEMP MUTE"


class Err(Enum):
    NO_PERMISSION = "PERMISSION DENIED"
    ADMIN_TARGET  = "CANNOT TARGET ADMIN"
    BOT_PERMS     = "MISSING BOT PERMISSIONS"
    BAD_DURATION  = "INVALID DURATION"
    NO_USER       = "USER NOT FOUND"


@dataclass
class Target:
    user:     User
    reason:   Optional[str] = None
    duration: Optional[int] = None


@dataclass
class WarnData:
    count:     int = 0
    reasons:   List[str] = field(default_factory=list)
    last_warn: Optional[datetime] = None


class Cache:
    _store: Dict[str, object] = {}
    _ts:    Dict[str, float]  = {}
    TTL = 300

    @classmethod
    def get(cls, key: str):
        if key in cls._store:
            if time.time() - cls._ts[key] < cls.TTL:
                return cls._store[key]
            cls._store.pop(key, None)
            cls._ts.pop(key, None)
        return None

    @classmethod
    def set(cls, key: str, val):
        cls._store[key] = val
        cls._ts[key] = time.time()

    @classmethod
    def drop(cls, key: str):
        cls._store.pop(key, None)
        cls._ts.pop(key, None)


class DurationParser:
    _units = {
        "s": 1, "sec": 1, "second": 1, "seconds": 1,
        "m": 60, "min": 60, "minute": 60, "minutes": 60,
        "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
        "d": 86400, "day": 86400, "days": 86400,
        "w": 604800, "week": 604800, "weeks": 604800,
    }

    @classmethod
    def parse(cls, s: str) -> Optional[int]:
        if not s:
            return None
        s = s.lower().strip()
        for unit, mult in cls._units.items():
            if s.endswith(unit):
                num = s[: -len(unit)].strip()
                if num.isdigit():
                    return int(num) * mult
        return None

    @classmethod
    def fmt(cls, sec: int) -> str:
        if sec < 60:
            return f"{sec}s"
        if sec < 3600:
            return f"{sec // 60}m"
        if sec < 86400:
            return f"{sec // 3600}h"
        return f"{sec // 86400}d"


class WarnSystem:
    _data: Dict[str, WarnData] = defaultdict(WarnData)
    MAX = 3

    @classmethod
    def add(cls, chat_id: int, user_id: int, reason: str) -> WarnData:
        wd = cls._data[f"{chat_id}:{user_id}"]
        wd.count += 1
        wd.reasons.append(reason or "No reason")
        wd.last_warn = datetime.now(KOLKATA_TZ)
        return wd

    @classmethod
    def remove(cls, chat_id: int, user_id: int) -> Optional[WarnData]:
        wd = cls._data.get(f"{chat_id}:{user_id}")
        if wd and wd.count > 0:
            wd.count -= 1
            if wd.reasons:
                wd.reasons.pop()
            return wd
        return None

    @classmethod
    def get(cls, chat_id: int, user_id: int) -> WarnData:
        return cls._data.get(f"{chat_id}:{user_id}", WarnData())

    @classmethod
    def reset(cls, chat_id: int, user_id: int):
        cls._data.pop(f"{chat_id}:{user_id}", None)


def _now() -> datetime:
    return datetime.now(KOLKATA_TZ)


def _ts() -> str:
    return _now().strftime("%d-%m-%Y %I:%M:%S %p IST")


async def _is_admin(chat_id: int, user_id: int) -> bool:
    key = f"is_admin:{chat_id}:{user_id}"
    cached = Cache.get(key)
    if cached is not None:
        return cached
    try:
        m = await app.get_chat_member(chat_id, user_id)
        result = m.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        )
        Cache.set(key, result)
        return result
    except Exception:
        return False


async def _is_bot_admin(chat_id: int) -> bool:
    key = f"bot_admin:{chat_id}"
    cached = Cache.get(key)
    if cached is not None:
        return cached
    try:
        bot = await app.get_chat_member(chat_id, "me")
        result = bot.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        )
        Cache.set(key, result)
        return result
    except Exception:
        return False


async def _can_restrict(chat_id: int, user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    key = f"restrict:{chat_id}:{user_id}"
    cached = Cache.get(key)
    if cached is not None:
        return cached
    try:
        m = await app.get_chat_member(chat_id, user_id)
        result = (
            m.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
            and bool(m.privileges and m.privileges.can_restrict_members)
        )
        Cache.set(key, result)
        return result
    except Exception:
        return False


async def _can_delete(chat_id: int) -> bool:
    try:
        bot = await app.get_chat_member(chat_id, "me")
        return (
            bot.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
            and bool(bot.privileges and bot.privileges.can_delete_messages)
        )
    except Exception:
        return False


async def _caller_is_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    uid = message.from_user.id
    if uid == OWNER_ID:
        return True
    return await _can_restrict(message.chat.id, uid)


async def _resolve_user(message: Message, allow_duration: bool = False) -> Optional[Target]:
    args = message.text.split(maxsplit=3 if allow_duration else 2)

    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        reason, duration = None, None
        if len(args) > 1:
            if allow_duration:
                duration = DurationParser.parse(args[1])
                if duration:
                    reason = " ".join(args[2:]).strip() or None if len(args) > 2 else None
                else:
                    reason = " ".join(args[1:]).strip() or None
            else:
                reason = " ".join(args[1:]).strip() or None
        return Target(user, reason, duration)

    if len(args) < 2:
        await message.reply_text(
            "<blockquote><b>NO USER SPECIFIED</b></blockquote>\n\n"
            "Reply to a message or provide <code>@username</code> / <code>user_id</code>",
            parse_mode=enums.ParseMode.HTML,
        )
        return None

    user_arg = args[1]
    reason, duration = None, None

    if allow_duration and len(args) > 2:
        duration = DurationParser.parse(args[2])
        if duration:
            reason = args[3] if len(args) > 3 else None
        else:
            reason = " ".join(args[2:]) or None
    elif len(args) > 2:
        reason = " ".join(args[2:]) or None

    try:
        uid = int(user_arg) if user_arg.lstrip("-").isdigit() else user_arg
        user = await app.get_users(uid)
        return Target(user, reason, duration)
    except (PeerIdInvalid, UsernameNotOccupied, UsernameInvalid, KeyError):
        await message.reply_text(
            f"<blockquote><b>USER NOT FOUND</b></blockquote>\n\n"
            f"<code>{user_arg}</code> could not be resolved",
            parse_mode=enums.ParseMode.HTML,
        )
        return None


def _action_text(
    action: Action,
    user: User,
    admin: User,
    reason: Optional[str] = None,
    duration: Optional[int] = None,
    warn: Optional[WarnData] = None,
) -> str:
    lines = [
        f"<blockquote><b>{action.value} EXECUTED</b></blockquote>\n",
        f"<b>Target:</b> {user.mention}",
        f"<b>User ID:</b> <code>{user.id}</code>",
        f"<b>Admin:</b> {admin.mention}",
    ]
    if duration:
        expiry = (_now() + timedelta(seconds=duration)).strftime("%d-%m-%Y %I:%M:%S %p IST")
        lines += [
            f"<b>Duration:</b> <code>{DurationParser.fmt(duration)}</code>",
            f"<b>Expires:</b> <code>{expiry}</code>",
        ]
    if warn:
        lines.append(f"<b>Warns:</b> <code>{warn.count}/{WarnSystem.MAX}</code>")
        if warn.count >= WarnSystem.MAX:
            lines.append("<b>Max warns reached — auto ban triggered</b>")
    if reason:
        lines.append(f"<b>Reason:</b> <i>{reason}</i>")
    lines.append(f"<b>Time:</b> <code>{_ts()}</code>")
    return "\n".join(lines)


def _err_text(err: Err, note: str = "") -> str:
    hints = {
        Err.NO_PERMISSION: "You need admin privileges with restrict permissions",
        Err.ADMIN_TARGET:  "Cannot perform this action on an administrator",
        Err.BOT_PERMS:     "Bot requires admin rights with appropriate permissions",
        Err.BAD_DURATION:  "Invalid duration. Use: <code>30s, 5m, 2h, 1d, 1w</code>",
        Err.NO_USER:       "User could not be found",
    }
    body = note or hints.get(err, "")
    return f"<blockquote><b>{err.value}</b></blockquote>\n\n{body}"


async def _validate(message: Message, user: User, need_bot_admin: bool = True) -> Optional[str]:
    if not await _caller_is_admin(message):
        return _err_text(Err.NO_PERMISSION)
    if need_bot_admin and not await _is_bot_admin(message.chat.id):
        return _err_text(Err.BOT_PERMS)
    if await _is_admin(message.chat.id, user.id):
        return _err_text(Err.ADMIN_TARGET, f"{user.mention} is an administrator")
    return None


def _unban_kb(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Unban",
            callback_data=f"unban:{chat_id}:{user_id}",
            style=ButtonStyle.PRIMARY,
        )
    ]])


def _unwarn_kb(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Remove Warn",
            callback_data=f"unwarn:{chat_id}:{user_id}",
            style=ButtonStyle.PRIMARY,
        )
    ]])


def _full_perms() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=False,
        can_invite_users=True,
        can_pin_messages=False,
        can_manage_topics=False,
    )


async def _rpc(message: Message, coro):
    try:
        return await coro
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await coro
    except (ChatAdminRequired, UserAdminInvalid):
        await message.reply_text(_err_text(Err.BOT_PERMS), parse_mode=enums.ParseMode.HTML)
    except RPCError as e:
        await message.reply_text(
            f"<blockquote><b>RPC ERROR</b></blockquote>\n\n<code>{e}</code>",
            parse_mode=enums.ParseMode.HTML,
        )
    return None


@app.on_message(filters.command("ban") & filters.group)
async def ban_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    err = await _validate(m, t.user)
    if err:
        return await m.reply_text(err, parse_mode=enums.ParseMode.HTML)
    result = await _rpc(m, app.ban_chat_member(m.chat.id, t.user.id))
    if result is not None:
        Cache.drop(f"is_admin:{m.chat.id}:{t.user.id}")
        await m.reply_text(
            _action_text(Action.BAN, t.user, m.from_user, t.reason),
            reply_markup=_unban_kb(m.chat.id, t.user.id),
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("sban") & filters.group)
async def sban_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    err = await _validate(m, t.user)
    if err:
        return await m.reply_text(err, parse_mode=enums.ParseMode.HTML)
    result = await _rpc(m, app.ban_chat_member(m.chat.id, t.user.id))
    if result is not None:
        Cache.drop(f"is_admin:{m.chat.id}:{t.user.id}")
        await m.delete()


@app.on_message(filters.command("dban") & filters.group)
async def dban_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    err = await _validate(m, t.user)
    if err:
        return await m.reply_text(err, parse_mode=enums.ParseMode.HTML)
    if m.reply_to_message and await _can_delete(m.chat.id):
        await m.reply_to_message.delete()
    result = await _rpc(m, app.ban_chat_member(m.chat.id, t.user.id))
    if result is not None:
        Cache.drop(f"is_admin:{m.chat.id}:{t.user.id}")
        await m.reply_text(
            _action_text(Action.DBAN, t.user, m.from_user, t.reason),
            reply_markup=_unban_kb(m.chat.id, t.user.id),
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("tban") & filters.group)
async def tban_cmd(_, m: Message):
    t = await _resolve_user(m, allow_duration=True)
    if not t:
        return
    if not t.duration:
        return await m.reply_text(
            _err_text(Err.BAD_DURATION, "Example: <code>/tban @user 1h reason</code>"),
            parse_mode=enums.ParseMode.HTML,
        )
    if t.duration < 30:
        return await m.reply_text(
            _err_text(Err.BAD_DURATION, "Minimum duration is 30 seconds"),
            parse_mode=enums.ParseMode.HTML,
        )
    if t.duration > 31622400:
        return await m.reply_text(
            _err_text(Err.BAD_DURATION, "Maximum is 366 days — use <code>/ban</code> for permanent"),
            parse_mode=enums.ParseMode.HTML,
        )
    err = await _validate(m, t.user)
    if err:
        return await m.reply_text(err, parse_mode=enums.ParseMode.HTML)
    until = datetime.now() + timedelta(seconds=t.duration)
    result = await _rpc(m, app.ban_chat_member(m.chat.id, t.user.id, until_date=until))
    if result is not None:
        Cache.drop(f"is_admin:{m.chat.id}:{t.user.id}")
        await m.reply_text(
            _action_text(Action.TBAN, t.user, m.from_user, t.reason, t.duration),
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("unban") & filters.group)
async def unban_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    if not await _caller_is_admin(m):
        return await m.reply_text(_err_text(Err.NO_PERMISSION), parse_mode=enums.ParseMode.HTML)
    result = await _rpc(m, app.unban_chat_member(m.chat.id, t.user.id))
    if result is not None:
        await m.reply_text(
            _action_text(Action.UNBAN, t.user, m.from_user, t.reason),
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("mute") & filters.group)
async def mute_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    err = await _validate(m, t.user)
    if err:
        return await m.reply_text(err, parse_mode=enums.ParseMode.HTML)
    result = await _rpc(m, app.restrict_chat_member(m.chat.id, t.user.id, ChatPermissions()))
    if result is not None:
        await m.reply_text(
            _action_text(Action.MUTE, t.user, m.from_user, t.reason),
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("tmute") & filters.group)
async def tmute_cmd(_, m: Message):
    t = await _resolve_user(m, allow_duration=True)
    if not t:
        return
    if not t.duration:
        return await m.reply_text(
            _err_text(Err.BAD_DURATION, "Example: <code>/tmute @user 10m reason</code>"),
            parse_mode=enums.ParseMode.HTML,
        )
    if t.duration < 30:
        return await m.reply_text(
            _err_text(Err.BAD_DURATION, "Minimum duration is 30 seconds"),
            parse_mode=enums.ParseMode.HTML,
        )
    if t.duration > 31622400:
        return await m.reply_text(
            _err_text(Err.BAD_DURATION, "Maximum is 366 days — use <code>/mute</code> for permanent"),
            parse_mode=enums.ParseMode.HTML,
        )
    err = await _validate(m, t.user)
    if err:
        return await m.reply_text(err, parse_mode=enums.ParseMode.HTML)
    until = datetime.now() + timedelta(seconds=t.duration)
    result = await _rpc(m, app.restrict_chat_member(m.chat.id, t.user.id, ChatPermissions(), until_date=until))
    if result is not None:
        await m.reply_text(
            _action_text(Action.TMUTE, t.user, m.from_user, t.reason, t.duration),
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("unmute") & filters.group)
async def unmute_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    if not await _caller_is_admin(m):
        return await m.reply_text(_err_text(Err.NO_PERMISSION), parse_mode=enums.ParseMode.HTML)
    result = await _rpc(m, app.restrict_chat_member(m.chat.id, t.user.id, _full_perms()))
    if result is not None:
        await m.reply_text(
            _action_text(Action.UNMUTE, t.user, m.from_user, t.reason),
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("kick") & filters.group)
async def kick_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    err = await _validate(m, t.user)
    if err:
        return await m.reply_text(err, parse_mode=enums.ParseMode.HTML)
    r = await _rpc(m, app.ban_chat_member(m.chat.id, t.user.id))
    if r is not None:
        await asyncio.sleep(0.5)
        await _rpc(m, app.unban_chat_member(m.chat.id, t.user.id))
        await m.reply_text(
            _action_text(Action.KICK, t.user, m.from_user, t.reason),
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("warn") & filters.group)
async def warn_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    err = await _validate(m, t.user, need_bot_admin=False)
    if err:
        return await m.reply_text(err, parse_mode=enums.ParseMode.HTML)
    wd = WarnSystem.add(m.chat.id, t.user.id, t.reason or "No reason")
    await m.reply_text(
        _action_text(Action.WARN, t.user, m.from_user, t.reason, warn=wd),
        reply_markup=_unwarn_kb(m.chat.id, t.user.id),
        parse_mode=enums.ParseMode.HTML,
    )
    if wd.count >= WarnSystem.MAX:
        try:
            await app.ban_chat_member(m.chat.id, t.user.id)
            WarnSystem.reset(m.chat.id, t.user.id)
            Cache.drop(f"is_admin:{m.chat.id}:{t.user.id}")
        except RPCError:
            pass


@app.on_message(filters.command("unwarn") & filters.group)
async def unwarn_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    if not await _caller_is_admin(m):
        return await m.reply_text(_err_text(Err.NO_PERMISSION), parse_mode=enums.ParseMode.HTML)
    wd = WarnSystem.remove(m.chat.id, t.user.id)
    if wd:
        await m.reply_text(
            _action_text(Action.UNWARN, t.user, m.from_user, warn=wd),
            parse_mode=enums.ParseMode.HTML,
        )
    else:
        await m.reply_text(
            f"<blockquote><b>NO WARNS</b></blockquote>\n\n{t.user.mention} has no warnings",
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command("warns") & filters.group)
async def warns_cmd(_, m: Message):
    t = await _resolve_user(m)
    if not t:
        return
    wd = WarnSystem.get(m.chat.id, t.user.id)
    text = (
        f"<blockquote><b>WARN HISTORY</b></blockquote>\n\n"
        f"<b>User:</b> {t.user.mention}\n"
        f"<b>Total:</b> <code>{wd.count}/{WarnSystem.MAX}</code>\n"
    )
    if wd.reasons:
        text += "\n<b>Reasons:</b>\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(wd.reasons, 1))
    await m.reply_text(text, parse_mode=enums.ParseMode.HTML)


@app.on_callback_query(filters.regex(r"^unban:(-?\d+):(\d+)$"))
async def unban_cb(_, cq: CallbackQuery):
    chat_id = int(cq.matches[0].group(1))
    user_id = int(cq.matches[0].group(2))
    if not cq.from_user:
        return await cq.answer("Cannot identify user", show_alert=True)
    if not await _can_restrict(chat_id, cq.from_user.id):
        return await cq.answer("You cannot unban users", show_alert=True)
    try:
        await app.unban_chat_member(chat_id, user_id)
        await cq.message.edit_text(
            f"<blockquote><b>UNBAN EXECUTED</b></blockquote>\n\n"
            f"<b>User ID:</b> <code>{user_id}</code>\n"
            f"<b>By:</b> {cq.from_user.mention}\n"
            f"<b>Time:</b> <code>{_ts()}</code>",
            parse_mode=enums.ParseMode.HTML,
        )
    except ChatAdminRequired:
        await cq.answer("Bot needs admin rights", show_alert=True)
    except RPCError as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^unwarn:(-?\d+):(\d+)$"))
async def unwarn_cb(_, cq: CallbackQuery):
    chat_id = int(cq.matches[0].group(1))
    user_id = int(cq.matches[0].group(2))
    if not cq.from_user:
        return await cq.answer("Cannot identify user", show_alert=True)
    if not await _can_restrict(chat_id, cq.from_user.id):
        return await cq.answer("You cannot remove warnings", show_alert=True)
    wd = WarnSystem.remove(chat_id, user_id)
    if wd:
        await cq.message.edit_text(
            f"<blockquote><b>WARN REMOVED</b></blockquote>\n\n"
            f"<b>User ID:</b> <code>{user_id}</code>\n"
            f"<b>Remaining:</b> <code>{wd.count}/{WarnSystem.MAX}</code>\n"
            f"<b>By:</b> {cq.from_user.mention}\n"
            f"<b>Time:</b> <code>{_ts()}</code>",
            parse_mode=enums.ParseMode.HTML,
        )
    else:
        await cq.answer("No warnings to remove", show_alert=True)


_HELP_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Ban",        callback_data="mh_ban",      style=ButtonStyle.PRIMARY),
        InlineKeyboardButton("Temp Ban",   callback_data="mh_tban",     style=ButtonStyle.PRIMARY),
        InlineKeyboardButton("Silent Ban", callback_data="mh_sban",     style=ButtonStyle.PRIMARY),
    ],
    [
        InlineKeyboardButton("Mute",       callback_data="mh_mute",     style=ButtonStyle.SUCCESS),
        InlineKeyboardButton("Temp Mute",  callback_data="mh_tmute",    style=ButtonStyle.SUCCESS),
        InlineKeyboardButton("Kick",       callback_data="mh_kick",     style=ButtonStyle.SUCCESS),
    ],
    [
        InlineKeyboardButton("Warn",       callback_data="mh_warn",     style=ButtonStyle.SUCCESS),
        InlineKeyboardButton("Dban",       callback_data="mh_dban",     style=ButtonStyle.SUCCESS),
        InlineKeyboardButton("Overview",   callback_data="mh_overview", style=ButtonStyle.PRIMARY),
    ],
    [
        InlineKeyboardButton("✕ Close",    callback_data="mh_close",    style=ButtonStyle.DANGER),
    ],
])

_BACK_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("Back",     callback_data="mh_menu",  style=ButtonStyle.SUCCESS),
    InlineKeyboardButton("✕ Close",  callback_data="mh_close", style=ButtonStyle.DANGER),
]])

_HELP_DATA: Dict[str, str] = {
    "overview": (
        "<blockquote expandable><b>MODERATION OVERVIEW</b></blockquote>\n\n"
        "<b>Permanent:</b>\n"
        "• <code>/ban</code> — Permanent ban\n"
        "• <code>/sban</code> — Silent ban (command auto-deleted)\n"
        "• <code>/dban</code> — Delete message + ban\n"
        "• <code>/kick</code> — Remove user (can rejoin)\n\n"
        "<b>Temporary:</b>\n"
        "• <code>/tban 1h</code> — Temp ban\n"
        "• <code>/tmute 30m</code> — Temp mute\n\n"
        "<b>Warnings:</b>\n"
        "• <code>/warn</code> — Warn user (3 = auto ban)\n"
        "• <code>/unwarn</code> — Remove a warning\n"
        "• <code>/warns</code> — View warnings\n\n"
        "<b>Undo:</b>\n"
        "• <code>/unban</code> — Unban user\n"
        "• <code>/unmute</code> — Unmute user\n\n"
        "<b>Duration:</b> <code>30s 5m 2h 1d 1w</code>\n"
        "<b>Timezone:</b> IST (Kolkata)"
    ),
    "ban": (
        "<blockquote><b>BAN</b></blockquote>\n\n"
        "Permanently ban a user from the group\n\n"
        "<b>Usage:</b>\n"
        "• <code>/ban</code> — reply to message\n"
        "• <code>/ban @user [reason]</code>\n"
        "• <code>/ban user_id [reason]</code>"
    ),
    "tban": (
        "<blockquote><b>TEMP BAN</b></blockquote>\n\n"
        "Ban a user for a specified duration\n\n"
        "<b>Usage:</b>\n"
        "• <code>/tban @user 1h [reason]</code>\n"
        "• <code>/tban user_id 30m [reason]</code>\n\n"
        "<b>Duration:</b> <code>30s 5m 2h 1d 1w</code>"
    ),
    "sban": (
        "<blockquote><b>SILENT BAN</b></blockquote>\n\n"
        "Ban without notification — command is auto-deleted\n\n"
        "<b>Usage:</b>\n"
        "• <code>/sban</code> — reply to message\n"
        "• <code>/sban @user</code>"
    ),
    "dban": (
        "<blockquote><b>DELETE + BAN</b></blockquote>\n\n"
        "Delete replied message and ban the sender\n\n"
        "<b>Usage:</b>\n"
        "• <code>/dban</code> — reply to message only\n\n"
        "Requires bot delete message permission"
    ),
    "mute": (
        "<blockquote><b>MUTE</b></blockquote>\n\n"
        "Restrict user from sending all message types\n\n"
        "<b>Usage:</b>\n"
        "• <code>/mute</code> — reply to message\n"
        "• <code>/mute @user [reason]</code>"
    ),
    "tmute": (
        "<blockquote><b>TEMP MUTE</b></blockquote>\n\n"
        "Mute a user for a specified duration\n\n"
        "<b>Usage:</b>\n"
        "• <code>/tmute @user 10m [reason]</code>\n"
        "• <code>/tmute user_id 1h [reason]</code>\n\n"
        "<b>Duration:</b> <code>30s 5m 2h 1d 1w</code>"
    ),
    "kick": (
        "<blockquote><b>KICK</b></blockquote>\n\n"
        "Remove user from group — they can rejoin\n\n"
        "<b>Usage:</b>\n"
        "• <code>/kick</code> — reply to message\n"
        "• <code>/kick @user [reason]</code>"
    ),
    "warn": (
        "<blockquote><b>WARN SYSTEM</b></blockquote>\n\n"
        "Issue a warning — 3 warns triggers auto ban\n\n"
        "<b>Usage:</b>\n"
        "• <code>/warn</code> — reply to message\n"
        "• <code>/warn @user [reason]</code>\n"
        "• <code>/warns @user</code> — view warnings\n"
        "• <code>/unwarn @user</code> — remove warning"
    ),
}


@app.on_message(filters.command("modhelp") & filters.group)
async def modhelp_cmd(_, m: Message):
    await m.reply_text(
        "<blockquote><b>MODERATION HELP</b></blockquote>\n\nSelect a command below",
        reply_markup=_HELP_MENU,
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_callback_query(filters.regex(r"^mh_(\w+)$"))
async def modhelp_cb(_, cq: CallbackQuery):
    key = cq.matches[0].group(1)
    if key == "close":
        return await cq.message.delete()
    if key == "menu":
        return await cq.message.edit_text(
            "<blockquote><b>MODERATION HELP</b></blockquote>\n\nSelect a command below",
            reply_markup=_HELP_MENU,
            parse_mode=enums.ParseMode.HTML,
        )
    text = _HELP_DATA.get(key)
    if text:
        await cq.message.edit_text(text, reply_markup=_BACK_KB, parse_mode=enums.ParseMode.HTML)
    else:
        await cq.answer()
