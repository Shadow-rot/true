# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

import json
import re
import random

from pyrogram import filters, types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from anony import anon, app, config, db, lang, queue, yt
from anony.core.mongo import MAX_PLAYLISTS, MAX_TRACKS
from anony.helpers._play import ensure_ub_in_chat


def _fmt(sec: int) -> str:
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"


def _blockquote(tracks: list[dict]) -> str:
    text = "<blockquote expandable>"
    for i, t in enumerate(tracks, 1):
        line = f"\n<b>{i}.</b> {t['title']} - {_fmt(t['duration'])}"
        if len(text) + len(line) + 14 > 1950:
            text += f"\n...and {len(tracks) - i + 1} more"
            break
        text += line
    return text + "\n</blockquote>"


def _list_buttons(playlists: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"▶ {pl['name'].title()}", callback_data=f"pl_play_{pl['_id']}"),
            InlineKeyboardButton("view", callback_data=f"pl_view_{pl['_id']}"),
            InlineKeyboardButton("✕", callback_data=f"pl_del_{pl['_id']}"),
        ]
        for pl in playlists
    ])


def _view_buttons(pid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶ play", callback_data=f"pl_play_{pid}"),
            InlineKeyboardButton("⇄ shuffle", callback_data=f"pl_shuffle_{pid}"),
        ],
        [
            InlineKeyboardButton("export", callback_data=f"pl_export_{pid}"),
            InlineKeyboardButton("share", callback_data=f"pl_share_{pid}"),
            InlineKeyboardButton("✕ delete", callback_data=f"pl_del_{pid}"),
        ],
    ])


def _confirm_buttons(pid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✓ confirm", callback_data=f"pl_delconfirm_{pid}"),
        InlineKeyboardButton("✕ cancel", callback_data=f"pl_delcancel_{pid}"),
    ]])


def _pid(cq: types.CallbackQuery) -> str | None:
    m = re.search(r"^pl_\w+_(.+)$", cq.data)
    return m.group(1) if m else None


async def _play_by_id(pid: str, chat_id: int, mention: str, reply, shuffle: bool = False):
    if not await ensure_ub_in_chat(chat_id, reply):
        return

    pl = await db.pl_get_by_id(pid)
    if not pl:
        return await reply("Playlist not found.")

    tracks = await db.pl_get_tracks(pid)
    if not tracks:
        return await reply("Playlist is empty.")

    if shuffle:
        random.shuffle(tracks)

    sent = await reply("Loading playlist...")

    first_track = await yt.search(tracks[0]["url"], sent.id, video=False)
    if not first_track:
        return await sent.edit_text(f"Could not fetch first track. Support: {config.SUPPORT_CHAT}")

    first_track.user = mention
    position = queue.add(chat_id, first_track)

    for t in tracks[1:]:
        tr = await yt.search(t["url"], sent.id, video=False)
        if tr:
            tr.user = mention
            queue.add(chat_id, tr)

    label = "Shuffled & queued" if shuffle else "Playlist queued"
    summary = (
        f"{label}\n\n<b>{pl['name'].title()}</b>\n"
        f"Songs: {len(tracks)} · By: {mention}\n\n{_blockquote(tracks)}"
    )

    if position != 0 or await db.get_call(chat_id):
        return await sent.edit_text(summary)

    if not first_track.file_path:
        await sent.edit_text("Downloading...")
        first_track.file_path = await yt.download(first_track.id, video=False)

    await anon.play_media(chat_id=chat_id, message=sent, media=first_track)

    if len(tracks) > 1:
        await app.send_message(chat_id=chat_id, text=summary)


# /pl — list playlists or view one, /pl new <name> — create
@app.on_message(filters.command("pl") & ~app.bl_users)
@lang.language()
async def pl_handler(_, m: types.Message):
    args = m.command[1:]

    if not args:
        playlists = await db.pl_list(m.from_user.id)
        if not playlists:
            return await m.reply_text(
                "No playlists yet.\n\n"
                "<b>Create one:</b> <code>/pl new &lt;name&gt;</code>"
            )
        lines = []
        for i, pl in enumerate(playlists, 1):
            count = await db.pl_track_count(pl["_id"])
            lines.append(f"<b>{i}.</b> {pl['name'].title()} — {count} songs")
        return await m.reply_text(
            "<b>Your Playlists</b>\n\n" + "\n".join(lines),
            reply_markup=_list_buttons(playlists),
        )

    if args[0].lower() == "new" and len(args) >= 2:
        name = args[1]
        pl = await db.pl_create(m.from_user.id, name)
        if pl is None:
            existing = await db.pl_get(m.from_user.id, name)
            return await m.reply_text(
                f"Playlist <b>{name.title()}</b> already exists."
                if existing else
                f"Max {MAX_PLAYLISTS} playlists per user."
            )
        return await m.reply_text(
            f"Playlist <b>{name.title()}</b> created.\n\n"
            f"Add songs: <code>/add {name} &lt;song&gt;</code>"
        )

    name = args[0]
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(
            f"Playlist <b>{name.title()}</b> not found.\n\n"
            f"Create it: <code>/pl new {name}</code>"
        )
    tracks = await db.pl_get_tracks(pl["_id"])
    header = (
        f"<b>{pl['name'].title()}</b>\n"
        f"Owner: {m.from_user.mention} · Tracks: {len(tracks)}\n\n"
    )
    body = _blockquote(tracks) if tracks else "<i>No tracks yet. Use /add to add songs.</i>"
    await m.reply_text(header + body, reply_markup=_view_buttons(pl["_id"]))


# /add <name> <song or url>
@app.on_message(filters.command("add") & ~app.bl_users)
@lang.language()
async def add_handler(_, m: types.Message):
    args = m.command[1:]
    if len(args) < 2:
        return await m.reply_text("Usage: <code>/add &lt;playlist&gt; &lt;song/url&gt;</code>")
    name, query = args[0], " ".join(args[1:])
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    if await db.pl_track_count(pl["_id"]) >= MAX_TRACKS:
        return await m.reply_text(f"Playlist full. Max {MAX_TRACKS} tracks.")
    sent = await m.reply_text("Searching...")
    track = await yt.search(query, sent.id, video=False)
    if not track:
        return await sent.edit_text(f"Not found. Support: {config.SUPPORT_CHAT}")
    result = await db.pl_add_track(pl["_id"], track.title, track.duration_sec, track.url, track.id, m.from_user.id)
    if result is None:
        return await sent.edit_text(f"Playlist full. Max {MAX_TRACKS} tracks.")
    await sent.edit_text(
        f"Added to <b>{name.title()}</b>\n{track.title} — {_fmt(track.duration_sec)}"
    )


# /rm <name> <position>
@app.on_message(filters.command("rm") & ~app.bl_users)
@lang.language()
async def rm_handler(_, m: types.Message):
    args = m.command[1:]
    if len(args) != 2:
        return await m.reply_text("Usage: <code>/rm &lt;playlist&gt; &lt;position&gt;</code>")
    name = args[0]
    try:
        pos = int(args[1])
    except ValueError:
        return await m.reply_text("Position must be a number.")
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    if not await db.pl_remove_track(pl["_id"], pos):
        return await m.reply_text("Invalid position.")
    await m.reply_text(f"Track #{pos} removed from <b>{name.title()}</b>.")


# /pplay <name>
@app.on_message(filters.command("pplay") & ~app.bl_users)
@lang.language()
async def pplay_handler(_, m: types.Message):
    args = m.command[1:]
    if not args:
        return await m.reply_text("Usage: <code>/pplay &lt;playlist&gt;</code>")
    name = args[0]
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    await _play_by_id(pl["_id"], m.chat.id, m.from_user.mention, m.reply_text)


# /pshuffle <name>
@app.on_message(filters.command("pshuffle") & ~app.bl_users)
@lang.language()
async def pshuffle_handler(_, m: types.Message):
    args = m.command[1:]
    if not args:
        return await m.reply_text("Usage: <code>/pshuffle &lt;playlist&gt;</code>")
    name = args[0]
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    await _play_by_id(pl["_id"], m.chat.id, m.from_user.mention, m.reply_text, shuffle=True)


# ── Callback handlers ──────────────────────────────────────────────────────────

@app.on_callback_query(filters.regex(r"^pl_view_"))
async def cb_view(_, cq: types.CallbackQuery):
    try:
        pid = _pid(cq)
        if not pid:
            return await cq.answer("Invalid callback.", show_alert=True)
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.answer("Playlist not found.", show_alert=True)
        tracks = await db.pl_get_tracks(pid)
        header = (
            f"<b>{pl['name'].title()}</b>\n"
            f"Tracks: {len(tracks)}\n\n"
        )
        body = _blockquote(tracks) if tracks else "<i>No tracks yet.</i>"
        await cq.edit_message_text(header + body, reply_markup=_view_buttons(pid))
        await cq.answer()
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_play_"))
async def cb_play(_, cq: types.CallbackQuery):
    await cq.answer()
    try:
        pid = _pid(cq)
        if not pid:
            return await cq.message.reply_text("Invalid callback.")
        if not await db.pl_get_by_id(pid):
            return await cq.message.reply_text("Playlist not found.")
        await _play_by_id(pid, cq.message.chat.id, cq.from_user.mention, cq.message.reply_text)
    except Exception as e:
        await cq.message.reply_text(f"Error: {e}")


@app.on_callback_query(filters.regex(r"^pl_shuffle_"))
async def cb_shuffle(_, cq: types.CallbackQuery):
    await cq.answer()
    try:
        pid = _pid(cq)
        if not pid:
            return await cq.message.reply_text("Invalid callback.")
        if not await db.pl_get_by_id(pid):
            return await cq.message.reply_text("Playlist not found.")
        await _play_by_id(pid, cq.message.chat.id, cq.from_user.mention, cq.message.reply_text, shuffle=True)
    except Exception as e:
        await cq.message.reply_text(f"Error: {e}")


@app.on_callback_query(filters.regex(r"^pl_export_"))
async def cb_export(_, cq: types.CallbackQuery):
    await cq.answer("Exporting...")
    try:
        pid = _pid(cq)
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.message.reply_text("Playlist not found.")
        tracks = await db.pl_get_tracks(pid)
        data = json.dumps(
            {
                "playlist": pl["name"],
                "tracks": [{"title": t["title"], "url": t["url"], "duration": t["duration"]} for t in tracks],
            },
            indent=2, ensure_ascii=False,
        )
        fname = f"/tmp/pl_{pid[:8]}.json"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(data)
        await cq.message.reply_document(
            fname,
            caption=f"Export: <b>{pl['name'].title()}</b> — {len(tracks)} tracks",
        )
    except Exception as e:
        await cq.message.reply_text(f"Error: {e}")


@app.on_callback_query(filters.regex(r"^pl_share_"))
async def cb_share(_, cq: types.CallbackQuery):
    try:
        pid = _pid(cq)
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.answer("Playlist not found.", show_alert=True)
        me = await app.get_me()
        link = f"https://t.me/{me.username}?start=pl_{pid}"
        count = await db.pl_track_count(pid)
        await cq.answer()
        await cq.message.reply_text(
            f"<b>Share: {pl['name'].title()}</b>\n"
            f"Tracks: {count}\n\n"
            f"<code>{link}</code>"
        )
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_del_(?!confirm|cancel)"))
async def cb_del_prompt(_, cq: types.CallbackQuery):
    try:
        pid = _pid(cq)
        if not pid:
            return await cq.answer("Invalid callback.", show_alert=True)
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.answer("Playlist not found.", show_alert=True)
        if pl["user_id"] != cq.from_user.id:
            return await cq.answer("Only the owner can delete this.", show_alert=True)
        await cq.edit_message_text(
            f"Delete <b>{pl['name'].title()}</b>? This cannot be undone.",
            reply_markup=_confirm_buttons(pid),
        )
        await cq.answer()
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_delconfirm_"))
async def cb_del_confirm(_, cq: types.CallbackQuery):
    try:
        pid = _pid(cq)
        if not pid:
            return await cq.answer("Invalid callback.", show_alert=True)
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.answer("Playlist not found.", show_alert=True)
        if pl["user_id"] != cq.from_user.id:
            return await cq.answer("Only the owner can delete this.", show_alert=True)
        await db.pl_delete(pid)
        await cq.edit_message_text(f"Playlist <b>{pl['name'].title()}</b> deleted.")
        await cq.answer()
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_delcancel_"))
async def cb_del_cancel(_, cq: types.CallbackQuery):
    try:
        pid = _pid(cq)
        if not pid:
            return await cq.answer()
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.answer()
        tracks = await db.pl_get_tracks(pid)
        header = f"<b>{pl['name'].title()}</b>\nTracks: {len(tracks)}\n\n"
        body = _blockquote(tracks) if tracks else "<i>No tracks yet.</i>"
        await cq.edit_message_text(header + body, reply_markup=_view_buttons(pid))
        await cq.answer("Cancelled.")
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)
