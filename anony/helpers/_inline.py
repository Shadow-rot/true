from pyrogram import types, Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery

from anony import app, config, lang
from anony.core.lang import lang_codes


class Inline:
    def __init__(self):
        self.ikm = types.InlineKeyboardMarkup
        self.ikb = types.InlineKeyboardButton
        self.register_callbacks()

    def register_callbacks(self):
        @app.on_callback_query(filters.regex("^controls status"))
        async def status_noop(client: Client, callback_query: CallbackQuery):
            await callback_query.answer()

    def _btn(
        self,
        text: str,
        callback_data: str,
        style: ButtonStyle = None
    ) -> types.InlineKeyboardButton:
        kwargs = {"text": text, "callback_data": callback_data}
        if style is not None:
            kwargs["style"] = style
        return self.ikb(**kwargs)

    # ❌ Cancel Download (Red)
    def cancel_dl(self, text: str) -> types.InlineKeyboardMarkup:
        return self.ikm([
            [
                self._btn(f"x  {text}", "cancel_dl", ButtonStyle.DANGER)
            ]
        ])

    # 🎵 Player Controls (3 Color Version)
    def controls(
        self,
        chat_id: int,
        status: str = None,
        timer: str = None,
        remove: bool = False,
    ) -> types.InlineKeyboardMarkup:

        keyboard = []

        # Status / Timer Row (Blue)
        if status:
            keyboard.append(
                [self._btn(status, f"controls status {chat_id}", ButtonStyle.PRIMARY)]
            )
        elif timer:
            keyboard.append(
                [self._btn(timer, f"controls status {chat_id}", ButtonStyle.PRIMARY)]
            )

        if not remove:
            keyboard.append([
<<<<<<< HEAD
                self._btn("|<<", f"controls replay {chat_id}", ButtonStyle.PRIMARY),  # Blue
                self._btn("|>", f"controls resume {chat_id}", ButtonStyle.SUCCESS),  # Green
                self._btn("||", f"controls pause {chat_id}", ButtonStyle.DANGER),    # Red
                self._btn(">>|", f"controls skip {chat_id}", ButtonStyle.PRIMARY),   # Blue
                self._btn("[]", f"controls stop {chat_id}", ButtonStyle.DANGER),     # Red
=======
                self._btn("|<<", f"controls replay {chat_id}"),
                self._btn(
                    "|>", f"controls resume {chat_id}", ButtonStyle.SUCCESS),
                self._btn("||", f"controls pause {chat_id}"),
                self._btn(">>|", f"controls skip {chat_id}"),
                self._btn(
                    "[]", f"controls stop {chat_id}", ButtonStyle.DANGER),
>>>>>>> b25cf5d (lol)
            ])

        return self.ikm(keyboard)

    # 📖 Help Menu
    def help_markup(
        self,
        _lang: dict,
        back: bool = False
    ) -> types.InlineKeyboardMarkup:

        if back:
            rows = [[
                self._btn(f"<< {_lang['back']}",
                          "help back", ButtonStyle.SUCCESS),
                self._btn(f"x  {_lang['close']}",
                          "help close", ButtonStyle.DANGER),
            ]]
        else:
<<<<<<< HEAD
            cbs = [
                "admins", "auth", "blist", "lang",
                "ping", "play", "queue", "stats", "sudo"
            ]

=======
            cbs = ["admins", "auth", "blist", "lang",
                   "ping", "play", "queue", "stats", "sudo"]
>>>>>>> b25cf5d (lol)
            buttons = [
                self._btn(_lang[f"help_{i}"], f"help {cb}", ButtonStyle.PRIMARY)
                for i, cb in enumerate(cbs)
            ]
<<<<<<< HEAD

            rows = [
                buttons[i:i + 3]
                for i in range(0, len(buttons), 3)
            ]
=======
            rows = [buttons[i: i + 3] for i in range(0, len(buttons), 3)]
>>>>>>> b25cf5d (lol)

        return self.ikm(rows)

    # 🌍 Language Selector
    def lang_markup(self, _lang: str) -> types.InlineKeyboardMarkup:
        langs = lang.get_languages()

        buttons = [
            self.ikb(
                text=f"{name} ({code}){' [x]' if code == _lang else ''}",
                callback_data=f"lang_change {code}",
                style=ButtonStyle.SUCCESS if code == _lang else ButtonStyle.PRIMARY,
            )
            for code, name in langs.items()
        ]
<<<<<<< HEAD

        rows = [
            buttons[i:i + 2]
            for i in range(0, len(buttons), 2)
        ]

=======
        rows = [buttons[i: i + 2] for i in range(0, len(buttons), 2)]
>>>>>>> b25cf5d (lol)
        return self.ikm(rows)

    # 🏓 Ping
    def ping_markup(self, text: str) -> types.InlineKeyboardMarkup:
        return self.ikm([
            [
                self.ikb(text=text, url=config.SUPPORT_CHAT)
            ]
        ])

<<<<<<< HEAD
    # ▶ Force Play (Blue)
    def play_queued(
        self,
        chat_id: int,
        item_id: str,
        _text: str
    ) -> types.InlineKeyboardMarkup:

        return self.ikm([
            [
                self._btn(
                    _text,
                    f"controls force {chat_id} {item_id}",
                    ButtonStyle.PRIMARY
                )
            ]
        ])

    # ⏯ Queue Toggle
    def queue_markup(
        self,
        chat_id: int,
        _text: str,
        playing: bool
    ) -> types.InlineKeyboardMarkup:
=======
    def play_queued(self, chat_id: int, item_id: str, _text: str) -> types.InlineKeyboardMarkup:
        return self.ikm([[
            self._btn(
                _text, f"controls force {chat_id} {item_id}", ButtonStyle.PRIMARY)
        ]])
>>>>>>> b25cf5d (lol)

        action = "pause" if playing else "resume"
        style = ButtonStyle.DANGER if playing else ButtonStyle.SUCCESS

        return self.ikm([
            [
                self._btn(
                    _text,
                    f"controls {action} {chat_id} q",
                    style
                )
            ]
        ])

    # ⚙ Settings
    def settings_markup(
        self,
        lang: dict,
        admin_only: bool,
        cmd_delete: bool,
        language: str,
        chat_id: int,
    ) -> types.InlineKeyboardMarkup:

        return self.ikm([
            [
<<<<<<< HEAD
                self._btn(f"{lang['play_mode']} ->", "settings", ButtonStyle.PRIMARY),
                self._btn(str(admin_only), "settings play", ButtonStyle.SUCCESS),
            ],
            [
                self._btn(f"{lang['cmd_delete']} ->", "settings", ButtonStyle.PRIMARY),
                self._btn(str(cmd_delete), "settings delete", ButtonStyle.DANGER),
=======
                self._btn(f"{lang['play_mode']} ->", "settings"),
                self._btn(str(admin_only), "settings play",
                          ButtonStyle.SUCCESS),
            ],
            [
                self._btn(f"{lang['cmd_delete']} ->", "settings"),
                self._btn(str(cmd_delete), "settings delete",
                          ButtonStyle.DANGER),
>>>>>>> b25cf5d (lol)
            ],
            [
                self._btn(f"{lang['language']} ->", "settings", ButtonStyle.PRIMARY),
                self._btn(lang_codes[language], "language"),
            ],
        ])

    # 🚀 Start Menu
    def start_key(
        self,
        lang: dict,
        private: bool = False
    ) -> types.InlineKeyboardMarkup:

        return self.ikm([
            [
                self.ikb(
                    text=f"+ {lang['add_me']}",
                    url=f"https://t.me/{app.username}?startgroup=true",
                    style=ButtonStyle.SUCCESS
                )
            ],
            [
                self._btn(lang["help"], "help", ButtonStyle.PRIMARY),
                self._btn(lang["language"], "language", ButtonStyle.PRIMARY),
            ],
            [
                self.ikb(text=lang["support"], url=config.SUPPORT_CHAT),
                self.ikb(text=lang["channel"], url=config.SUPPORT_CHANNEL),
            ],
        ])

    # 🔗 YouTube Buttons
    def yt_key(self, link: str) -> types.InlineKeyboardMarkup:
        return self.ikm([
            [
                self.ikb(text="[c] Copy", copy_text=link),
                self.ikb(text="[->] Open", url=link),
            ]
        ])