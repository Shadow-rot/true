# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

import asyncio
import json
import random

from pyrogram import enums, errors, filters, types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from anony import anon, app, config, db, lang, queue, yt
from anony.core.mongo import MAX_PLAYLISTS, MAX_TRACKS


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
            InlineKeyboardButton(f"play  {pl['name'].title()}", callback_data=f"pl_play_{pl['_id']}"),
            InlineKeyboardButton("view", callback_data=f"pl_view_{pl['_id']}"),
            InlineKeyboardButton("delete", callback_data=f"pl_del_{pl['_id']}"),
        ]
        for pl in playlists
    ])


def _view_buttons(pid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("play", callback_data=f"pl_play_{pid}"),
        InlineKeyboardButton("shuffle", callback_data=f"pl_shuffle_{pid}"),
        InlineKeyboardButton("delete", callback_data=f"pl_del_{pid}"),
    ]])


def _confirm_buttons(pid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("confirm delete", callback_data=f"pl_delconfirm_{pid}"),
        InlineKeyboardButton("cancel", callback_data=f"pl_delcancel_{pid}"),
    ]])


async def _ensure_ub(chat_id: int, reply) -> bool:
    """
    Ensures the userbot client is present in the chat.
    Mirrors checkUB join/unban logic but works for any context.
    Returns True if ready, False if a blocking error occurred (reply already sent).
    """
    if chat_id in db.active_calls:
        return True

    client = await db.get_client(chat_id)
    if not client:
        await reply("No assistant configured for this chat.")
        return False

    ub_id = client.me.id

    try:
        member = await app.get_chat_member(chat_id, ub_id)
        if member.status in (enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.RESTRICTED):
            try:
                await app.unban_chat_member(chat_id=chat_id, user_id=ub_id)
            except Exception:
                await reply(f"Assistant is banned in this chat. Unban user ID: <code>{ub_id}</code>")
                return False

    except errors.ChatAdminRequired:
        await reply("Bot needs admin rights to manage the assistant.")
        return False

    except (errors.UserNotParticipant, errors.exceptions.bad_request_400.UserNotParticipant):
        if hasattr(client, "resolve_peer"):
            try:
                chat = await app.get_chat(chat_id)
                invite_link = chat.username or chat.invite_link
                if not invite_link:
                    invite_link = await app.export_chat_invite_link(chat_id)
            except errors.ChatAdminRequired:
                await reply("Bot needs admin rights to invite the assistant.")
                return False
            except Exception as ex:
                await reply(f"Could not get invite link: {type(ex).__name__}")
                return False

            msg = await reply("Inviting assistant to chat...")
            await asyncio.sleep(2)
            try:
                await client.join_chat(invite_link)
            except errors.UserAlreadyParticipant:
                pass
            except errors.InviteRequestSent:
                await asyncio.sleep(2)
                try:
                    await app.approve_chat_join_request(chat_id, ub_id)
                except errors.HideRequesterMissing:
                    pass
                except Exception as ex:
                    await msg.edit_text(f"Invite error: {type(ex).__name__}")
                    return False
            except Exception as ex:
                await msg.edit_text(f"Invite error: {type(ex).__name__}")
                return False

            try:
                await msg.delete()
            except Exception:
                pass

            try:
                await client.resolve_peer(chat_id)
            except Exception:
                pass

    return True


async def _play_by_id(pid: str, chat_id: int, mention: str, reply, shuffle: bool = False):
    if not await _ensure_ub(chat_id, reply):
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
        return await sent.edit_text(f"Could not fetch track. Support: {config.SUPPORT_CHAT}")

    first_track.user = mention
    position = queue.add(chat_id, first_track)

    for t in tracks[1:]:
        tr = await yt.search(t["url"], video=False)
        if tr:
            tr.user = mention
            queue.add(chat_id, tr)

    label = "Playlist shuffled and queued" if shuffle else "Playlist queued"
    summary = f"{label}\n\n<b>{pl['name'].title()}</b>\nSongs: {len(tracks)}\nBy: {mention}\n\n{_blockquote(tracks)}"

    if position != 0 or await db.get_call(chat_id):
        return await sent.edit_text(summary)

    if not first_track.file_path:
        await sent.edit_text("Downloading...")
        first_track.file_path = await yt.download(first_track.id, video=False)

    await anon.play_media(chat_id=chat_id, message=sent, media=first_track)
    if len(tracks) > 1:
        await app.send_message(chat_id=chat_id, text=summary)


@app.on_message(filters.command("playlist") & ~app.bl_users)
@lang.language()
async def playlist_hndlr(_, m: types.Message) -> None:
    args = m.command[1:]
    if not args:
        return await _cmd_list(m)
    sub = args[0].lower()
    try:
        if sub == "create" and len(args) >= 2:
            await _cmd_create(m, args[1])
        elif sub == "add" and len(args) >= 3:
            await _cmd_add(m, args[1], " ".join(args[2:]))
        elif sub == "remove" and len(args) == 3:
            await _cmd_remove(m, args[1], int(args[2]))
        elif sub == "delete" and len(args) == 2:
            await _cmd_delete(m, args[1])
        elif sub == "view" and len(args) == 2:
            await _cmd_view(m, args[1])
        elif sub == "play" and len(args) == 2:
            await _cmd_play(m, args[1])
        elif sub == "shuffle" and len(args) == 2:
            await _cmd_play(m, args[1], shuffle=True)
        elif sub == "import" and len(args) >= 3:
            await _cmd_import(m, args[1], args[2])
        elif sub == "export" and len(args) == 2:
            await _cmd_export(m, args[1])
        elif sub == "share" and len(args) == 2:
            await _cmd_share(m, args[1])
        else:
            await m.reply_text(
                "<b>Playlist Commands</b>\n\n"
                "/playlist\n"
                "/playlist create &lt;name&gt;\n"
                "/playlist add &lt;name&gt; &lt;song/url&gt;\n"
                "/playlist remove &lt;name&gt; &lt;pos&gt;\n"
                "/playlist delete &lt;name&gt;\n"
                "/playlist view &lt;name&gt;\n"
                "/playlist play &lt;name&gt;\n"
                "/playlist shuffle &lt;name&gt;\n"
                "/playlist import &lt;name&gt; &lt;yt_url&gt;\n"
                "/playlist export &lt;name&gt;\n"
                "/playlist share &lt;name&gt;"
            )
    except ValueError:
        await m.reply_text("Invalid position. Must be a number.")
    except Exception as e:
        await m.reply_text(f"Error: {e}")


async def _cmd_list(m: types.Message):
    playlists = await db.pl_list(m.from_user.id)
    if not playlists:
        return await m.reply_text("No playlists. Use /playlist create &lt;name&gt;")
    lines = []
    for i, pl in enumerate(playlists, 1):
        count = await db.pl_track_count(pl["_id"])
        lines.append(f"<b>{i}.</b> {pl['name'].title()} ({count} songs)")
    await m.reply_text("<b>Your Playlists</b>\n\n" + "\n".join(lines), reply_markup=_list_buttons(playlists))


async def _cmd_create(m: types.Message, name: str):
    pl = await db.pl_create(m.from_user.id, name)
    if pl is None:
        existing = await db.pl_get(m.from_user.id, name)
        return await m.reply_text(
            f"Playlist <b>{name.title()}</b> already exists." if existing else f"Max {MAX_PLAYLISTS} playlists per user."
        )
    await m.reply_text(f"Playlist <b>{name.title()}</b> created.")


async def _cmd_add(m: types.Message, name: str, query: str):
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
    await sent.edit_text(f"Added to <b>{name.title()}</b>: {track.title} - {_fmt(track.duration_sec)}")


async def _cmd_remove(m: types.Message, name: str, pos: int):
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    if not await db.pl_remove_track(pl["_id"], pos):
        return await m.reply_text("Invalid position.")
    await m.reply_text(f"Track #{pos} removed from <b>{name.title()}</b>.")


async def _cmd_delete(m: types.Message, name: str):
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    await m.reply_text(
        f"Delete playlist <b>{name.title()}</b>? This cannot be undone.",
        reply_markup=_confirm_buttons(pl["_id"]),
    )


async def _cmd_view(m: types.Message, name: str):
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    tracks = await db.pl_get_tracks(pl["_id"])
    header = f"<b>Playlist: {pl['name'].title()}</b>\nOwner: {m.from_user.mention}\nTracks: {len(tracks)}\n\n"
    body = _blockquote(tracks) if tracks else "<i>No tracks yet.</i>"
    await m.reply_text(header + body, reply_markup=_view_buttons(pl["_id"]))


async def _cmd_play(m: types.Message, name: str, shuffle: bool = False):
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    await _play_by_id(pl["_id"], m.chat.id, m.from_user.mention, m.reply_text, shuffle)


async def _cmd_import(m: types.Message, name: str, url: str):
    if "playlist" not in url:
        return await m.reply_text("Provide a valid YouTube playlist URL.")
    pl = await db.pl_get(m.from_user.id, name) or await db.pl_create(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Max {MAX_PLAYLISTS} playlists per user.")
    sent = await m.reply_text("Fetching YouTube playlist...")
    yt_tracks = await yt.playlist(config.PLAYLIST_LIMIT, m.from_user.mention, url, video=False)
    if not yt_tracks:
        return await sent.edit_text("Could not fetch YouTube playlist.")
    added = 0
    for t in yt_tracks:
        if await db.pl_add_track(pl["_id"], t.title, t.duration_sec, t.url, t.id, m.from_user.id):
            added += 1
    await sent.edit_text(f"Imported {added} tracks into <b>{name.title()}</b>.")


async def _cmd_export(m: types.Message, name: str):
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    tracks = await db.pl_get_tracks(pl["_id"])
    data = json.dumps(
        {"playlist": pl["name"], "tracks": [{"title": t["title"], "url": t["url"], "duration": t["duration"]} for t in tracks]},
        indent=2, ensure_ascii=False,
    )
    fname = f"/tmp/pl_{pl['_id'][:8]}.json"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(data)
    await m.reply_document(fname, caption=f"Export: <b>{name.title()}</b> - {len(tracks)} tracks")


async def _cmd_share(m: types.Message, name: str):
    pl = await db.pl_get(m.from_user.id, name)
    if not pl:
        return await m.reply_text(f"Playlist <b>{name.title()}</b> not found.")
    me = await app.get_me()
    link = f"https://t.me/{me.username}?start=pl_{pl['_id']}"
    await m.reply_text(
        f"<b>Share: {pl['name'].title()}</b>\nTracks: {await db.pl_track_count(pl['_id'])}\n\n<code>{link}</code>"
    )


@app.on_callback_query(filters.regex(r"^pl_view_(.+)$"))
async def cb_view(_, cq: types.CallbackQuery):
    try:
        pid = cq.matches[0].group(1)
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.answer("Playlist not found.", show_alert=True)
        tracks = await db.pl_get_tracks(pid)
        header = f"<b>Playlist: {pl['name'].title()}</b>\nTracks: {len(tracks)}\n\n"
        body = _blockquote(tracks) if tracks else "<i>No tracks yet.</i>"
        await cq.edit_message_text(header + body, reply_markup=_view_buttons(pid))
        await cq.answer()
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_play_(.+)$"))
async def cb_play(_, cq: types.CallbackQuery):
    try:
        pid = cq.matches[0].group(1)
        if not await db.pl_get_by_id(pid):
            return await cq.answer("Playlist not found.", show_alert=True)
        await cq.answer("Loading playlist...")
        await _play_by_id(pid, cq.message.chat.id, cq.from_user.mention, cq.message.reply_text)
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_shuffle_(.+)$"))
async def cb_shuffle(_, cq: types.CallbackQuery):
    try:
        pid = cq.matches[0].group(1)
        if not await db.pl_get_by_id(pid):
            return await cq.answer("Playlist not found.", show_alert=True)
        await cq.answer("Shuffling...")
        await _play_by_id(pid, cq.message.chat.id, cq.from_user.mention, cq.message.reply_text, shuffle=True)
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_del_(.+)$"))
async def cb_del_prompt(_, cq: types.CallbackQuery):
    try:
        pid = cq.matches[0].group(1)
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.answer("Playlist not found.", show_alert=True)
        if pl["user_id"] != cq.from_user.id:
            return await cq.answer("Only the owner can delete this.", show_alert=True)
        await cq.edit_message_text(
            f"Delete <b>{pl['name'].title()}</b>? Cannot be undone.",
            reply_markup=_confirm_buttons(pid),
        )
        await cq.answer()
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_delconfirm_(.+)$"))
async def cb_del_confirm(_, cq: types.CallbackQuery):
    try:
        pid = cq.matches[0].group(1)
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


@app.on_callback_query(filters.regex(r"^pl_delcancel_(.+)$"))
async def cb_del_cancel(_, cq: types.CallbackQuery):
    try:
        pid = cq.matches[0].group(1)
        pl = await db.pl_get_by_id(pid)
        if not pl:
            return await cq.answer()
        tracks = await db.pl_get_tracks(pid)
        header = f"<b>Playlist: {pl['name'].title()}</b>\nTracks: {len(tracks)}\n\n"
        body = _blockquote(tracks) if tracks else "<i>No tracks yet.</i>"
        await cq.edit_message_text(header + body, reply_markup=_view_buttons(pid))
        await cq.answer("Cancelled.")
    except Exception as e:
        await cq.answer(f"Error: {e}", show_alert=True)
