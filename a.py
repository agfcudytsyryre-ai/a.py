import os
import json
import re
import random
import asyncio
import logging
from contextvars import ContextVar

# ---- Telethon فقط ----
from telethon import TelegramClient, events, Button, utils as tl_utils
from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError, FloodWaitError, 
    ApiIdInvalidError, ChatWriteForbiddenError, PeerIdInvalidError, ChannelPrivateError,
    QueryIdInvalidError
)

logging.getLogger("telethon").setLevel(logging.ERROR)

BOT_TOKEN = "8851309353:AAFgr_aRLPLAEkvEukz3C5GBUtUa2ed_Zes"
API_ID = 20939124
API_HASH = "0c375ccd4809417e19c8fe252290dba5"
SUDO_ID = 1920665874   # ← المطور

DB_FILE = "accounts_data.json"
SUPERS_FILE = "supers_data.json"
SETTINGS_FILE = "settings_data.json"
MESSAGES_FILE = "post_messages.json"
REPLIES_FILE = "replies_data.json"
STORAGE_FILE = "storage_data.json"
USERS_FILE = "users_data.json"

COLORS_USERS_KEY = "__colors_users__"
CURRENT_UI_USER_ID = ContextVar("current_ui_user_id", default=None)

# تهيئة عميل البوت (Telethon)
bot = TelegramClient("main_bot_session", API_ID, API_HASH)

def _get_session_file(chat_id, phone=None):
    if phone:
        clean = phone.replace("+", "").replace(" ", "").replace("-", "")
        return f"user_{chat_id}_{clean}"
    return f"user_{chat_id}"

def get_user_colors_enabled(chat_id):
    try:
        settings = load_db(SETTINGS_FILE)
        users_colors = settings.get(COLORS_USERS_KEY, {})
        return bool(users_colors.get(str(chat_id), True))
    except Exception:
        return True

def set_user_colors_enabled(chat_id, enabled):
    settings = load_db(SETTINGS_FILE)
    users_colors = settings.setdefault(COLORS_USERS_KEY, {})
    users_colors[str(chat_id)] = bool(enabled)
    save_db(settings, SETTINGS_FILE)

db_cache = None
supers_cache = None
settings_cache = None
messages_cache = None
replies_cache = None
storage_cache = None
users_cache = None

def load_db(file_path, force=False):
    global db_cache, supers_cache, settings_cache, messages_cache, replies_cache, storage_cache, users_cache
    if not force:
        if file_path == DB_FILE and db_cache is not None: return db_cache
        if file_path == SUPERS_FILE and supers_cache is not None: return supers_cache
        if file_path == SETTINGS_FILE and settings_cache is not None: return settings_cache
        if file_path == MESSAGES_FILE and messages_cache is not None: return messages_cache
        if file_path == REPLIES_FILE and replies_cache is not None: return replies_cache
        if file_path == STORAGE_FILE and storage_cache is not None: return storage_cache
        if file_path == USERS_FILE and users_cache is not None: return users_cache

    if not os.path.exists(file_path):
        res = {}
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                res = json.load(f)
            except Exception:
                res = {}

    if file_path == DB_FILE: db_cache = res
    elif file_path == SUPERS_FILE: supers_cache = res
    elif file_path == SETTINGS_FILE: settings_cache = res
    elif file_path == MESSAGES_FILE: messages_cache = res
    elif file_path == REPLIES_FILE: replies_cache = res
    elif file_path == STORAGE_FILE: storage_cache = res
    elif file_path == USERS_FILE: users_cache = res
    return res

def save_db(data, file_path):
    global db_cache, supers_cache, settings_cache, messages_cache, replies_cache, storage_cache, users_cache
    if file_path == DB_FILE: db_cache = data
    elif file_path == SUPERS_FILE: supers_cache = data
    elif file_path == SETTINGS_FILE: settings_cache = data
    elif file_path == MESSAGES_FILE: messages_cache = data
    elif file_path == REPLIES_FILE: replies_cache = data
    elif file_path == STORAGE_FILE: storage_cache = data
    elif file_path == USERS_FILE: users_cache = data

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_states = {}
user_clients = {}
cached_groups = {}
publishing_tasks = {}
active_user_clients = {} 

def get_user_timer(chat_id):
    settings = load_db(SETTINGS_FILE)
    return settings.get(chat_id, {}).get("timer", "10 ثوان")

def get_anti_ban(chat_id):
    return load_db(SETTINGS_FILE).get(chat_id, {}).get("anti_ban", False)

def parse_timer_seconds(timer_str):
    timer_str = str(timer_str).strip().lower()
    if "-" in timer_str:
        parts = timer_str.split("-")
        a = parse_timer_seconds(parts[0])
        b = parse_timer_seconds(parts[1])
        return random.randint(min(a, b), max(a, b))
    if timer_str.endswith("s") or "ثواني" in timer_str or "ثانية" in timer_str or "ثوان" in timer_str:
        num = re.findall(r'\d+', timer_str)
        return int(num[0]) if num else 10
    elif timer_str.endswith("m") or "دقائق" in timer_str or "دقيقة" in timer_str:
        num = re.findall(r'\d+', timer_str)
        return int(num[0]) * 60 if num else 60
    elif timer_str.isdigit():
        return int(timer_str)
    return 10

# =============== مساعد الألوان ===============
def get_btn_style(chat_id, color):
    if not get_user_colors_enabled(chat_id):
        return None
    if color in ["primary", "success", "danger"]:
        return color
    return None

def make_btn(chat_id, text, data, color=None):
    return Button.inline(text, data=data, style=get_btn_style(chat_id, color))

def make_url_btn(chat_id, text, url, color=None):
    return Button.url(text, url, style=get_btn_style(chat_id, color))

# =============== الأزرار ===============
def main_keyboard(chat_id=None):
    colors_enabled = get_user_colors_enabled(chat_id) if chat_id is not None else True
    
    buttons = [
        [make_btn(chat_id, "حساباتي 👨‍💻", b"accounts", "primary"), make_btn(chat_id, "السوبرات الحالية 🐣", b"current_super", "primary")],
        [make_btn(chat_id, "إضافة سوبر 🐥", b"add_super", "danger"), make_btn(chat_id, "رسائل النشر 🐥", b"post_msg", "danger")],
        [make_btn(chat_id, "ضبط مدة النشر 🧑‍🍳", b"timer", "danger"), make_btn(chat_id, "إيقاف النشر 🍿", b"stop_post", "success")],
        [make_btn(chat_id, "بدء النشر 🐥", b"start_post", "success"), make_btn(chat_id, "الردود 🧑‍🏫", b"replies", "primary")],
        [make_btn(chat_id, "تخزين 📻", b"storage", "primary"), make_btn(chat_id, "إطفاء الألوان 🌸" if colors_enabled else "تشغيل الألوان 🌸", b"toggle_colors", "success")],
        [make_url_btn(chat_id, "المطوّر 🐥", "https://t.me/u_8_y", "success")]
    ]
    if str(chat_id) == str(SUDO_ID):
        buttons.insert(-1, [make_btn(chat_id, "لوحة التحكم ⚙️", b"admin_panel", "danger")])
    return buttons

def replies_main_keyboard(chat_id):
    replies_db = load_db(REPLIES_FILE).get(chat_id, {})
    welcome_msg = replies_db.get("welcome")
    status_text = "مفعل 🌸" if welcome_msg else "معطل 🥊"
    return [
        [make_btn(chat_id, "الردود 👨‍🏫", b"list_replies", "success"), make_btn(chat_id, "اضف رد 👨‍🏫", b"add_reply", "success")],
        [make_btn(chat_id, "حذف الترحيب 🐥", b"del_welcome", "primary"), make_btn(chat_id, "إضافة ترحيب 👨‍🏫", b"add_welcome", "danger")],
        [make_btn(chat_id, "تجاهل شخص 🐥", b"add_ignore", "success")],
        [make_btn(chat_id, "الرئيسية 🧑‍🌾", b"go_home", "success")]
    ], status_text

def accounts_keyboard(chat_id):
    return [
        [make_btn(chat_id, "إدارة الحسابات 🎨", b"manage_accs", "primary"), make_btn(chat_id, "إضافة حساب 📲", b"add_acc", "success")],
        [make_btn(chat_id, "الرئيسية 🐥", b"go_home", "danger")]
    ]

def home_keyboard(chat_id):
    return [[make_btn(chat_id, "الرئيسية 🐥", b"go_home", "primary")]]

def post_status_keyboard(chat_id, show_stop=True):
    if show_stop:
        return [[make_btn(chat_id, "إيقاف 🛑", b"stop_post", "primary"), make_btn(chat_id, "الرئيسية 🐥", b"go_home", "danger")]]
    return [[make_btn(chat_id, "بدء 🥶", b"start_post", "primary"), make_btn(chat_id, "الرئيسية 🐥", b"go_home", "success")]]

def no_accounts_keyboard(chat_id):
    return [[make_btn(chat_id, "إضافة حساب 🙋‍♂️", b"add_acc", "danger")], [make_btn(chat_id, "الرئيسية 🐥", b"go_home", "danger")]]

def build_groups_page(chat_id, page=0):
    groups = cached_groups.get(chat_id, [])
    start_idx = page * 10
    end_idx = start_idx + 10
    current_page_groups = groups[start_idx:end_idx]
    user_supers = load_db(SUPERS_FILE).get(chat_id, [])
    added_identifiers = {s.get("identifier") if isinstance(s, dict) else str(s) for s in user_supers}
    
    buttons = []
    for idx, g in enumerate(current_page_groups):
        title = g["title"]
        identifier = g["identifier"]
        is_private = g.get("is_private", False)
        
        if is_private:
            group_btn = make_btn(chat_id, f"{title} 🔒", b"private_info", "primary")
        else:
            clean_user = identifier.replace("@", "")
            group_btn = make_url_btn(chat_id, f"{title} 🐥", f"https://t.me/{clean_user}", "primary")
            
        if identifier in added_identifiers:
            action_btn = make_btn(chat_id, "حذف 🐥", f"remove_sup_{idx}_{page}".encode(), "danger")
        else:
            action_btn = make_btn(chat_id, "إضافة 🧑‍🍳", f"save_sup_{idx}_{page}".encode(), "success")
        buttons.append([group_btn, action_btn])

    nav_row = []
    if page > 0:
        nav_row.append(make_btn(chat_id, "السابق ⬅️", f"page_{page - 1}".encode(), "primary"))
    if end_idx < len(groups):
        nav_row.append(make_btn(chat_id, "التالي 👩‍🦽", f"page_{page + 1}".encode(), "success"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([make_btn(chat_id, "إضافة يدويًا 🧑‍🍳", b"manual_add_super", "primary")])
    buttons.append([make_btn(chat_id, "الرئيسية 🐥", b"go_home", "success")])
    return buttons

async def safe_edit(event, text, buttons=None):
    try:
        await event.edit(text, buttons=buttons, link_preview=False)
    except QueryIdInvalidError:
        pass
    except Exception:
        try:
            await event.respond(text, buttons=buttons, link_preview=False)
        except Exception:
            pass

# =============== إدارة الحسابات (Telethon) ===============
async def start_user_client_listener(chat_id, session_file, username):
    if chat_id not in active_user_clients:
        active_user_clients[chat_id] = {}
        
    existing = active_user_clients[chat_id].get(username)
    if existing and existing.is_connected():
        return existing
    
    if existing:
        try: await existing.disconnect()
        except Exception: pass

    client_user = TelegramClient(session_file, API_ID, API_HASH)
    try:
        await client_user.connect()
        if not await client_user.is_user_authorized():
            await client_user.disconnect()
            return None
    except Exception:
        return None

    @client_user.on(events.NewMessage(incoming=True))
    async def incoming_all_handler(event):
        # (كود استقبال الرسائل بقي كما هو لضمان عدم التعقيد)
        try:
            msg = event.message
            sender = await event.get_sender()
            sender_id = str(sender.id) if sender else "غير معروف"
            sender_name = (getattr(sender, "first_name", None) or "مستخدم") if sender else "مستخدم"
            uname = getattr(sender, "username", None) if sender else None

            me = await client_user.get_me()
            is_private = event.is_private
            body_text = (msg.text or getattr(msg, "caption", None) or "")
            is_mentioned = bool(me.username and ("@" + me.username.lower()) in body_text.lower())
            is_reply = False
            
            if msg.reply_to_msg_id:
                try:
                    replied = await msg.get_reply_message()
                    if replied and replied.sender_id == me.id:
                        is_reply = True
                except Exception:
                    pass

            if is_private:
                replies_db = load_db(REPLIES_FILE).get(chat_id, {})
                ignored = replies_db.get("ignored", [])
                if sender_id not in ignored and (uname or "").lower() not in ignored:
                    text_lower = (msg.text or "").strip().lower()
                    word_replies = replies_db.get("word_replies", {})
                    if text_lower in word_replies:
                        await client_user.send_message(msg.chat_id, word_replies[text_lower], reply_to=msg.id)
                    else:
                        welcome = replies_db.get("welcome")
                        if welcome:
                            history_count = 0
                            async for _ in client_user.iter_messages(msg.chat_id, limit=2):
                                history_count += 1
                            if history_count <= 1:
                                await client_user.send_message(msg.chat_id, welcome, reply_to=msg.id)

            if is_private or is_mentioned or is_reply:
                storage_chat = load_db(STORAGE_FILE).get(chat_id)
                if storage_chat:
                    target_chat_id = int(storage_chat)
                    msg_body = msg.text or getattr(msg, "caption", None) or "مرفق"
                    link = None
                    if is_private:
                        link = f"tg://user?id={sender_id}"
                    else:
                        try:
                            chat_entity = await msg.get_chat()
                            cu = getattr(chat_entity, "username", None)
                            if cu:
                                link = f"https://t.me/{cu}/{msg.id}"
                        except Exception:
                            pass

                    log_text = (
                        f"المجموعة : {'الخاص' if is_private else 'مجموعة'}\n"
                        f"⌔┊المـرسـل : {sender_name}"
                        + (f" (@{uname})" if uname else "")
                        + f"\n⌔┊الرســالـه : {msg_body}\n"
                        + (f"⌔┊رابـط الرسـاله : اضغط هنا\n" if link and link.startswith("https://t.me") else "")
                        + f"{msg.chat_id}\n{msg.id}"
                    )
                    markup = [[Button.url("اضغط هنا", link, style="primary")]] if (link and link.startswith("https://t.me")) else None

                    try:
                        if msg.text:
                            await client_user.send_message(target_chat_id, log_text, buttons=markup, link_preview=False)
                        else:
                            try:
                                await client_user.send_file(target_chat_id, msg, caption=log_text, buttons=markup)
                            except Exception:
                                await client_user.send_message(target_chat_id, log_text, buttons=markup, link_preview=False)
                    except Exception:
                        pass
        except Exception:
            pass

    active_user_clients[chat_id][username] = client_user
    return client_user

async def _ensure_user_client(chat_id, acc):
    session_file = acc.get("session_file")
    username = acc.get("username")
    if not session_file: return None
    
    if chat_id not in active_user_clients:
        active_user_clients[chat_id] = {}

    existing = active_user_clients[chat_id].get(username)
    if existing and existing.is_connected():
        return existing
    
    return await start_user_client_listener(chat_id, session_file, username)

async def fetch_and_cache_groups(chat_id):
    user_accs = load_db(DB_FILE).get(chat_id, [])
    if not user_accs: return None
    
    user_client = await _ensure_user_client(chat_id, user_accs[0])
    if not user_client: return None

    try:
        fetched_groups = []
        async for dialog in user_client.iter_dialogs(limit=150):
            entity = dialog.entity
            try:
                is_group = getattr(entity, "megagroup", False) or getattr(entity, "gigagroup", False)
                is_chat = entity.__class__.__name__ == "Chat"
                if not (is_group or is_chat): continue
                username = getattr(entity, "username", None)
                title = getattr(entity, "title", None) or "كروب"
                if username:
                    fetched_groups.append({"title": title, "identifier": f"@{username}", "is_private": False})
                else:
                    fetched_groups.append({"title": title, "identifier": str(entity.id), "is_private": True})
            except Exception:
                continue
        cached_groups[chat_id] = fetched_groups
        return fetched_groups
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return None
    except Exception:
        return None

async def reset_user_session(chat_id):
    if chat_id in user_clients:
        info = user_clients[chat_id]
        if isinstance(info, dict) and info.get("client"):
            try: await info["client"].disconnect()
            except Exception: pass
        user_clients.pop(chat_id, None)
    user_states.pop(chat_id, None)

# =============== حلقة النشر المحسنة (أسرع + تخطي الأخطاء) ===============
async def publishing_loop(chat_id):
    print(f"[{chat_id}] 🚀 بدأ النشر التلقائي...")
    while True:
        try:
            user_supers = load_db(SUPERS_FILE, force=True).get(chat_id, [])
            raw_msgs = load_db(MESSAGES_FILE, force=True).get(chat_id, [])
            user_accs = load_db(DB_FILE, force=True).get(chat_id, [])
            
            active_msgs = [m.get("text", "") if isinstance(m, dict) else str(m) for m in raw_msgs if (isinstance(m, dict) and m.get("active", True)) or isinstance(m, str)]

            if not user_supers or not active_msgs or not user_accs:
                print(f"[{chat_id}] ⚠️ توقف النشر: (حسابات: {len(user_accs)}, سوبرات: {len(user_supers)}, رسائل: {len(active_msgs)})")
                break

            anti_ban = get_anti_ban(chat_id)

            for acc in user_accs:
                acc_name = acc.get("username", "حساب")
                pub_client = await _ensure_user_client(chat_id, acc)
                
                if not pub_client:
                    print(f"[{chat_id}] ❌ تعذر الاتصال بـ {acc_name}")
                    continue

                print(f"[{chat_id}] 🔄 بدء النشر من الحساب: {acc_name}")
                for target in user_supers:
                    identifier = target.get("identifier") if isinstance(target, dict) else str(target)
                    msg_to_send = random.choice(active_msgs)
                    
                    try:
                        # محاولة جلب الكيان أولاً لتجنب خطأ PeerIdInvalid
                        target_param = int(identifier) if (identifier.startswith("-") or identifier.isdigit()) else identifier
                        entity = await pub_client.get_entity(target_param)
                        await pub_client.send_message(entity, msg_to_send)
                        print(f"[{chat_id}] ✅ ({acc_name}) نشر في: {identifier}")
                    except FloodWaitError as e:
                        print(f"[{chat_id}] ⚠️ ({acc_name}) حظر مؤقت {e.seconds} ثانية.")
                        await asyncio.sleep(e.seconds)
                    except Exception as e:
                        print(f"[{chat_id}] ❌ ({acc_name}) فشل في {identifier}: {e}")
                    
                    # تأخير سريع (أو بطيء إذا كان مانع الحظر مفعل)
                    delay = random.uniform(8, 15) if anti_ban else random.uniform(1.5, 3.5)
                    await asyncio.sleep(delay)

                delay_acc = random.uniform(15, 30) if anti_ban else random.uniform(2, 4)
                await asyncio.sleep(delay_acc)

            timer_str = get_user_timer(chat_id)
            wait_time = parse_timer_seconds(timer_str)
            print(f"[{chat_id}] 💤 اكتملت الجولة. انتظار {wait_time} ثانية.")
            await asyncio.sleep(wait_time)
            
        except asyncio.CancelledError:
            print(f"[{chat_id}] 🛑 تم إيقاف النشر.")
            break
        except Exception as e:
            print(f"[{chat_id}] ❌ خطأ في الحلقة: {e}")
            await asyncio.sleep(5)

# =============== الإدارة والاشتراك الإجباري ===============
def get_admin_settings():
    settings = load_db(SETTINGS_FILE)
    if not isinstance(settings, dict): settings = {}
    if not isinstance(settings.get("__force_sub_channels__"), list): settings["__force_sub_channels__"] = []
    return settings

def get_force_sub_channels():
    return get_admin_settings().get("__force_sub_channels__", [])

def is_force_sub_enabled():
    s = get_admin_settings()
    return bool(s.get("__force_sub_enabled__", False)) and bool(s.get("__force_sub_channels__", []))

async def check_user_subscription(user_id):
    channels = get_force_sub_channels()
    if not channels or not is_force_sub_enabled(): return True
    for ch in channels:
        try:
            await bot.get_permissions(int(ch["id"]), int(user_id))
        except Exception:
            return False
    return True

def force_sub_keyboard(chat_id):
    rows = []
    for ch in get_force_sub_channels():
        link = ch.get("link")
        title = ch.get("title") or ch.get("username") or "القناة"
        if link: rows.append([make_url_btn(chat_id, f"الاشتراك في {title} 📢", link, "primary")])
    rows.append([make_btn(chat_id, "تحقق من الاشتراك ✅", b"check_subscription", "success")])
    return rows

def admin_panel_keyboard(chat_id):
    s = get_admin_settings()
    enabled = bool(s.get("__force_sub_enabled__", False))
    channels = s.get("__force_sub_channels__", [])
    photo = s.get("__start_photo__")
    return [
        [make_btn(chat_id, "الاشتراك الإجباري: مفعل 🟢" if enabled else "الاشتراك الإجباري: معطل 🔴", b"admin_toggle_force_sub", "success" if enabled else "danger")],
        [make_btn(chat_id, f"قنوات الاشتراك ({len(channels)}) 📢", b"admin_channels", "primary"), make_btn(chat_id, "إضافة قناة ➕", b"admin_add_channel", "success")],
        [make_btn(chat_id, "تعيين صورة البداية 🖼️", b"admin_set_image", "primary"), make_btn(chat_id, "حذف صورة البداية 🗑️", b"admin_del_image", "danger")],
        [make_btn(chat_id, "حالة صورة البداية: موجودة ✅" if photo else "حالة صورة البداية: غير موجودة ❌", b"admin_noop", "primary")],
        [make_btn(chat_id, "الرئيسية 🐥", b"go_home", "success")]
    ]

def admin_channels_keyboard(chat_id):
    channels = get_force_sub_channels()
    rows = []
    for idx, ch in enumerate(channels):
        title = ch.get("title") or ch.get("username") or str(ch.get("id"))
        if ch.get("link"):
            btn = make_url_btn(chat_id, title, ch.get("link"), "primary")
        else:
            btn = make_btn(chat_id, title, b"admin_noop", "primary")
        rows.append([btn, make_btn(chat_id, "حذف 🗑️", f"admin_del_channel_{idx}".encode(), "danger")])
    rows.append([make_btn(chat_id, "إضافة قناة ➕", b"admin_add_channel", "success")])
    rows.append([make_btn(chat_id, "رجوع ⚙️", b"admin_panel", "primary")])
    return rows

async def send_start_screen(event):
    chat_id = event.chat_id
    sender = await event.get_sender()
    first_name = sender.first_name or "غير معروف"
    text = f"أهلاً بك يا [{first_name}](tg://user?id={chat_id}) 🧑‍🍳\n\nهذا بوت النشر التلقائي للسوبرات\nاستخدم الأزرار بالأسفل للتحكم"
    photo = get_admin_settings().get("__start_photo__")
    
    try:
        if photo:
            await bot.send_file(chat_id, file=photo, caption=text, buttons=main_keyboard(chat_id), link_preview=False)
        else:
            await event.respond(text, buttons=main_keyboard(chat_id), link_preview=False)
    except Exception:
        await bot.send_message(chat_id, text, buttons=main_keyboard(chat_id), link_preview=False)


# =============== معالجة الأحداث (Events) ===============

@bot.on(events.NewMessage(pattern='/start'))
async def start_cmd(event):
    if not event.is_private: return
    chat_id = str(event.chat_id)
    CURRENT_UI_USER_ID.set(chat_id)
    await reset_user_session(chat_id)

    users_db = load_db(USERS_FILE)
    if chat_id not in users_db:
        sender = await event.get_sender()
        username = sender.username
        last_name = sender.last_name or ""
        full_name = " ".join(p for p in [sender.first_name, last_name] if p).strip() or "غير معروف"
        users_db[chat_id] = {
            "id": int(event.sender_id),
            "name": full_name,
            "username": f"@{username}" if username else "لا يوجد",
            "first_name": sender.first_name
        }
        save_db(users_db, USERS_FILE)
        try:
            await bot.send_message(SUDO_ID,
                f"👤 دخول مستخدم جديد للبوت!\n\nالاسم: {full_name}\nالمعرف: {'@' + username if username else 'لا يوجد'}\nالآيدي: {event.sender_id}\nالعدد الكلي: {len(users_db)}")
        except Exception:
            pass

    if str(event.sender_id) != str(SUDO_ID) and not await check_user_subscription(event.sender_id):
        await event.respond("🔒 يجب الاشتراك بالقنوات التالية أولاً.", buttons=force_sub_keyboard(chat_id))
        return

    user_accs = load_db(DB_FILE).get(chat_id, [])
    if user_accs:
        for acc in user_accs:
            sf = acc.get("session_file")
            uname = acc.get("username")
            if sf:
                asyncio.create_task(start_user_client_listener(chat_id, sf, uname))

    await send_start_screen(event)

@bot.on(events.NewMessage(pattern='/admin'))
async def admin_cmd(event):
    if not event.is_private: return
    chat_id = str(event.chat_id)
    CURRENT_UI_USER_ID.set(chat_id)
    if str(event.sender_id) != str(SUDO_ID): return
    await event.respond("⚙️ لوحة تحكم البوت\n\nمن هنا تقدر تدير الاشتراك الإجباري وصورة البداية.", buttons=admin_panel_keyboard(chat_id))

@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel_cmd(event):
    if not event.is_private: return
    chat_id = str(event.chat_id)
    CURRENT_UI_USER_ID.set(chat_id)
    await reset_user_session(chat_id)
    await event.respond("تم إلغاء العملية بنجاح. يمكنك البدء من جديد.", buttons=[[make_btn(chat_id, "العودة للرئيسية 🐥", b"go_home", "primary")]])


@bot.on(events.CallbackQuery)
async def callback_handler(event):
    chat_id = str(event.chat_id)
    CURRENT_UI_USER_ID.set(chat_id)
    data = event.data.decode('utf-8')
    
    # رد سريع جداً على تليجرام لمنع تعليق الزر
    try:
        await event.answer()
    except QueryIdInvalidError:
        pass
    except Exception:
        pass

    if data == "admin_noop": return

    if data == "admin_panel":
        if str(event.sender_id) != str(SUDO_ID): return
        await safe_edit(event, "⚙️ لوحة تحكم البوت", admin_panel_keyboard(chat_id))

    elif data == "admin_toggle_force_sub":
        if str(event.sender_id) != str(SUDO_ID): return
        s = get_admin_settings()
        if not s.get("__force_sub_channels__"):
            return await safe_edit(event, "أضف قناة أولاً.", admin_panel_keyboard(chat_id))
        s["__force_sub_enabled__"] = not bool(s.get("__force_sub_enabled__", False))
        save_db(s, SETTINGS_FILE)
        await safe_edit(event, "⚙️ لوحة التحكم", admin_panel_keyboard(chat_id))

    elif data == "admin_channels":
        if str(event.sender_id) != str(SUDO_ID): return
        chs = get_force_sub_channels()
        text = "📢 قنوات الاشتراك:\n\n" + ("\n".join(f"{i+1}. {c.get('title') or c.get('username')}" for i, c in enumerate(chs)) if chs else "لا توجد قنوات.")
        await safe_edit(event, text, admin_channels_keyboard(chat_id))

    elif data == "admin_add_channel":
        if str(event.sender_id) != str(SUDO_ID): return
        user_states[str(SUDO_ID)] = {"step": "admin_add_channel"}
        await event.respond("📢 أرسل معرف القناة @mychannel (يجب أن يكون البوت عضواً فيها).")

    elif data.startswith("admin_del_channel_"):
        if str(event.sender_id) != str(SUDO_ID): return
        idx = int(data.replace("admin_del_channel_", ""))
        s = get_admin_settings()
        chs = s.get("__force_sub_channels__", [])
        if 0 <= idx < len(chs):
            chs.pop(idx)
            s["__force_sub_channels__"] = chs
            if not chs: s["__force_sub_enabled__"] = False
            save_db(s, SETTINGS_FILE)
        await safe_edit(event, "📢 قنوات الاشتراك:", admin_channels_keyboard(chat_id))

    elif data == "admin_set_image":
        if str(event.sender_id) != str(SUDO_ID): return
        user_states[str(SUDO_ID)] = {"step": "admin_set_image"}
        await event.respond("🖼️ أرسل الصورة الآن.")

    elif data == "admin_del_image":
        if str(event.sender_id) != str(SUDO_ID): return
        s = get_admin_settings()
        s.pop("__start_photo__", None)
        save_db(s, SETTINGS_FILE)
        await safe_edit(event, "تم حذف الصورة 🗑️", admin_panel_keyboard(chat_id))

    elif data == "check_subscription":
        if await check_user_subscription(event.sender_id):
            try: await event.delete()
            except Exception: pass
            await send_start_screen(event)
        else:
            pass

    elif data == "toggle_colors":
        colors_enabled = not get_user_colors_enabled(chat_id)
        set_user_colors_enabled(chat_id, colors_enabled)
        await safe_edit(event, "تم تشغيل الألوان 🌸" if colors_enabled else "تم إطفاء الألوان 🌑", main_keyboard(chat_id))

    elif data == "private_info":
        await safe_edit(event, "🔒 هذا كروب خاص، لا يملك رابطاً عاماً.", main_keyboard(chat_id))

    elif data == "storage":
        current_store = load_db(STORAGE_FILE).get(chat_id, "لا توجد مجموعة تخزين")
        kb = [[make_btn(chat_id, "إنشاء مجموعة تخزين 📻", b"create_storage_group", "primary")], [make_btn(chat_id, "الرئيسية 🐥", b"go_home", "danger")]]
        await safe_edit(event, f"قسم التخزين 📻\n\n`{current_store}`", kb)

    elif data == "create_storage_group":
        storage_db = load_db(STORAGE_FILE)
        user_accs = load_db(DB_FILE).get(chat_id, [])
        if not user_accs:
            return await safe_edit(event, "⚠️ أضف حساباً أولاً.", no_accounts_keyboard(chat_id))
        acc = user_accs[0]
        
        if chat_id in storage_db and storage_db[chat_id]:
            existing_id = storage_db[chat_id]
            is_alive = False
            try:
                check = await _ensure_user_client(chat_id, acc)
                if check:
                    try:
                        await check.get_entity(int(existing_id))
                        is_alive = True
                    except Exception:
                        pass
            except Exception:
                pass
            if is_alive:
                return await safe_edit(event, f"⚠️ لديك مجموعة تخزين قائمة بالفعل!\n`{existing_id}`", home_keyboard(chat_id))
            storage_db.pop(chat_id, None)
            save_db(storage_db, STORAGE_FILE)

        await safe_edit(event, "جاري إنشاء مجموعة التخزين.. 🛡️✨")
        try:
            temp_cli = await _ensure_user_client(chat_id, acc)
            if not temp_cli:
                return await safe_edit(event, "⚠️ تعذر الاتصال بالحساب.", home_keyboard(chat_id))
            result = await temp_cli(CreateChannelRequest(
                title="مجموعة التخزين التلقائي 📻",
                about="تم انشاء هذه المجموعه عن طريق البوت",
                megagroup=True
            ))
            created = result.chats[0]
            new_id = tl_utils.get_peer_id(created)

            try:
                bot_me = await bot.get_me()
                if bot_me and bot_me.username:
                    await temp_cli(InviteToChannelRequest(created, [bot_me.username]))
            except Exception:
                pass

            storage_db[chat_id] = str(new_id)
            save_db(storage_db, STORAGE_FILE)
            await safe_edit(event, f"✅ تم إنشاء المجموعة!\n`{new_id}`", home_keyboard(chat_id))
        except Exception as e:
            await safe_edit(event, f"خطأ أثناء الإنشاء: {e}", home_keyboard(chat_id))

    elif data == "replies":
        kb, status = replies_main_keyboard(chat_id)
        await safe_edit(event, f"الردود التلقائية 😎\nترتيب الخاص: {status}", kb)

    elif data == "add_reply":
        user_states[chat_id] = {"step": "waiting_reply_word"}
        await event.respond("أرسل الكلمة 🐥\nللإلغاء /cancel")

    elif data == "list_replies":
        replies = load_db(REPLIES_FILE).get(chat_id, {}).get("word_replies", {})
        if not replies:
            await safe_edit(event, "لا توجد ردود.", [[make_btn(chat_id, "العودة 🐥", b"replies", "danger")]])
        else:
            text = "الردود:\n\n"
            buttons = []
            for w, r in replies.items():
                text += f"- ({w}) -> ({r})\n"
                buttons.append([make_btn(chat_id, f"حذف ({w}) 🗑️", f"del_rep_{w}".encode(), "danger")])
            buttons.append([make_btn(chat_id, "العودة 🐥", b"replies", "danger")])
            await safe_edit(event, text, buttons)

    elif data.startswith("del_rep_"):
        w = data.replace("del_rep_", "")
        rdb = load_db(REPLIES_FILE)
        if chat_id in rdb and "word_replies" in rdb[chat_id]:
            rdb[chat_id]["word_replies"].pop(w, None)
            save_db(rdb, REPLIES_FILE)
        event.data = b"list_replies"
        await callback_handler(event)

    elif data == "add_welcome":
        user_states[chat_id] = {"step": "waiting_welcome_msg"}
        await event.respond("أرسل نص الترحيب 🌸\nللإلغاء /cancel")

    elif data == "del_welcome":
        rdb = load_db(REPLIES_FILE)
        if chat_id in rdb:
            rdb[chat_id].pop("welcome", None)
            save_db(rdb, REPLIES_FILE)
        kb, status = replies_main_keyboard(chat_id)
        await safe_edit(event, f"تم الحذف 🛑\n\nترتيب الخاص: {status}", kb)

    elif data == "add_ignore":
        user_states[chat_id] = {"step": "waiting_ignore_user"}
        await event.respond("أرسل يوزر أو آيدي 🐥\nللإلغاء /cancel")

    elif data == "stop_post":
        if chat_id in publishing_tasks and not publishing_tasks[chat_id].done():
            publishing_tasks[chat_id].cancel()
            publishing_tasks.pop(chat_id, None)
            await safe_edit(event, "تم إيقاف النشر 🛑", post_status_keyboard(chat_id, show_stop=False))
        else:
            await safe_edit(event, "🥰 النشر متوقف بالفعل", post_status_keyboard(chat_id, show_stop=False))

    elif data == "start_post":
        user_accs = load_db(DB_FILE).get(chat_id, [])
        user_supers = load_db(SUPERS_FILE).get(chat_id, [])
        active_msgs = [m for m in load_db(MESSAGES_FILE).get(chat_id, []) if (isinstance(m, dict) and m.get("active", True)) or isinstance(m, str)]

        if not user_accs:
            await safe_edit(event, "⚠️ أضف حساباً أولاً.", no_accounts_keyboard(chat_id))
        elif not user_supers or not active_msgs:
            await safe_edit(event, "🥰 لا سوبرات أو رسائل مفعلة.", post_status_keyboard(chat_id, show_stop=False))
        elif chat_id in publishing_tasks and not publishing_tasks[chat_id].done():
            await safe_edit(event, "النشر يعمل 🚀", post_status_keyboard(chat_id, show_stop=True))
        else:
            publishing_tasks[chat_id] = asyncio.create_task(publishing_loop(chat_id))
            await safe_edit(event, "بدأ النشر التلقائي 🚀\n(تابع الكونسول لرؤية التفاصيل)", post_status_keyboard(chat_id, show_stop=True))

    elif data in ["post_msg", "back_to_post_msg"]:
        raw_msgs = load_db(MESSAGES_FILE).get(chat_id, [])
        user_msgs = [{"text": m, "active": True} if isinstance(m, str) else m for m in raw_msgs]
        buttons = []
        msg_text = "لا توجد رسائل." if not user_msgs else "الرسائل:\n\n"
        
        for i, m in enumerate(user_msgs, 1):
            st = "مفعلة" if m.get("active", True) else "معطلة"
            msg_text += f"- {i} | {st} | {m.get('text', '')}\n"

        anti_ban = get_anti_ban(chat_id)
        buttons.append([make_btn(chat_id, "مانع الحظر يعمل 🧙‍♂️" if anti_ban else "مانع الحظر متوقف 🧙‍♂️", b"toggle_anti_ban", "success" if anti_ban else "primary")])

        for i in range(len(user_msgs)):
            st = "تعطيل 🧑‍🌾" if user_msgs[i].get("active", True) else "تفعيل 🧙‍♂️"
            buttons.append([
                make_btn(chat_id, "حذف 🧑‍🌾", f"del_msg_{i}".encode(), "primary"),
                make_btn(chat_id, "تعديل 🧑‍🍳", f"edit_msg_{i}".encode(), "success"),
                make_btn(chat_id, st, f"toggle_msg_{i}".encode())
            ])
        buttons.append([make_btn(chat_id, "إضافة رسالة 🐥", b"add_post_msg", "danger")])
        buttons.append([make_btn(chat_id, "الرئيسية 🐥", b"go_home", "danger")])
        
        if data == "back_to_post_msg":
            await event.respond(msg_text, buttons=buttons)
        else:
            await safe_edit(event, msg_text, buttons)

    elif data.startswith("del_msg_"):
        idx = int(data.replace("del_msg_", ""))
        mdb = load_db(MESSAGES_FILE)
        msgs = mdb.get(chat_id, [])
        if 0 <= idx < len(msgs):
            msgs.pop(idx)
            mdb[chat_id] = msgs
            save_db(mdb, MESSAGES_FILE)
        event.data = b"post_msg"
        await callback_handler(event)

    elif data.startswith("toggle_msg_"):
        idx = int(data.replace("toggle_msg_", ""))
        mdb = load_db(MESSAGES_FILE)
        msgs = mdb.get(chat_id, [])
        if 0 <= idx < len(msgs):
            cur = msgs[idx].get("active", True) if isinstance(msgs[idx], dict) else True
            if isinstance(msgs[idx], str):
                msgs[idx] = {"text": msgs[idx], "active": not cur}
            else:
                msgs[idx]["active"] = not cur
            mdb[chat_id] = msgs
            save_db(mdb, MESSAGES_FILE)
        event.data = b"post_msg"
        await callback_handler(event)

    elif data.startswith("edit_msg_"):
        idx = int(data.replace("edit_msg_", ""))
        user_states[chat_id] = {"step": "waiting_edit_msg", "edit_idx": idx}
        await event.respond("أرسل النص الجديد\n\nللإلغاء /cancel")

    elif data == "add_post_msg":
        user_states[chat_id] = {"step": "waiting_post_msg"}
        await event.respond("🐥 أرسل نص الرسالة\n\nللإلغاء /cancel")

    elif data == "toggle_anti_ban":
        sdb = load_db(SETTINGS_FILE)
        sdb.setdefault(chat_id, {})
        sdb[chat_id]["anti_ban"] = not sdb[chat_id].get("anti_ban", False)
        save_db(sdb, SETTINGS_FILE)
        event.data = b"post_msg"
        await callback_handler(event)

    elif data == "timer":
        user_states[chat_id] = {"step": "waiting_timer"}
        await safe_edit(event,
            f"🧑‍🍳 **مدة النشر**\n\nالحالية: {get_user_timer(chat_id)}\n\nأرسل المدة:\n**10s** أو **1m** أو **5m-10m**\n\nللإلغاء /cancel",
            home_keyboard(chat_id))

    elif data == "accounts":
        await safe_edit(event, "إدارة الحسابات 🙋‍♂️", accounts_keyboard(chat_id))

    elif data == "manage_accs":
        user_accs = load_db(DB_FILE).get(chat_id, [])
        if not user_accs:
            await safe_edit(event, "لا تملك حسابات.", no_accounts_keyboard(chat_id))
        else:
            text = "حساباتك المسجلة:\n\n"
            buttons = []
            for a in user_accs:
                u = a.get("username")
                text += f"- {u}\n"
                buttons.append([
                    make_btn(chat_id, "حذف 🧖‍♂️", f"del_{u}".encode(), "success"),
                    make_btn(chat_id, f"الافتراضي ({u}) 🤠", f"set_def_{u}".encode())
                ])
            buttons.append([make_btn(chat_id, "الرئيسية 🐥", b"go_home", "success")])
            await safe_edit(event, text, buttons)

    elif data.startswith("del_") and not data.startswith("del_super_") and not data.startswith("del_msg_") and not data.startswith("del_rep_"):
        target = data.replace("del_", "")
        db = load_db(DB_FILE)
        user_accs = db.get(chat_id, [])
        
        for a in [acc for acc in user_accs if acc.get("username") == target]:
            sf = a.get("session_file")
            if sf and sf != "sessions":
                try: os.remove(f"{sf}.session")
                except Exception: pass
                
        new_accs = [a for a in user_accs if a.get("username") != target]
        db[chat_id] = new_accs
        save_db(db, DB_FILE)

        if chat_id in active_user_clients and target in active_user_clients[chat_id]:
            try: await active_user_clients[chat_id][target].disconnect()
            except Exception: pass
            active_user_clients[chat_id].pop(target, None)

        if not new_accs:
            await safe_edit(event, "لا تملك حسابات.", no_accounts_keyboard(chat_id))
        else:
            event.data = b"manage_accs"
            await callback_handler(event)

    elif data == "add_acc":
        user_states[chat_id] = {"step": "waiting_phone"}
        await safe_edit(event, "إضافة حساب جديد 🐥\n\nأرسل رقم الهاتف مع رمز الدولة (+964)\n\nللإلغاء /cancel")

    elif data == "add_super":
        if not load_db(DB_FILE).get(chat_id, []):
            return await safe_edit(event, "⚠️ أضف حساباً أولاً.", no_accounts_keyboard(chat_id))
        
        await safe_edit(event, "جاري جلب السوبرات في الخلفية.. 🛡️✨ (البوت لن يتجمد)")
        
        async def do_fetch():
            fetched = await fetch_and_cache_groups(chat_id)
            try:
                if not fetched:
                    await event.respond("لم يتم العثور على مجموعات.", buttons=home_keyboard(chat_id))
                else:
                    await event.respond("😷 اختر المجموعة:", buttons=build_groups_page(chat_id, 0))
            except Exception:
                pass
                
        asyncio.create_task(do_fetch())

    elif data.startswith("page_"):
        pg = int(data.replace("page_", ""))
        await safe_edit(event, "😷 اختر المجموعة:", build_groups_page(chat_id, pg))

    elif data.startswith("save_sup_"):
        parts = data.replace("save_sup_", "").rsplit("_", 1)
        idx = int(parts[0])
        pg = int(parts[1]) if len(parts) > 1 else 0
        groups = cached_groups.get(chat_id, [])
        ti = (pg * 10) + idx
        if ti < len(groups):
            sg = groups[ti]
            sdb = load_db(SUPERS_FILE)
            sdb.setdefault(chat_id, [])
            added = {s.get("identifier") if isinstance(s, dict) else str(s) for s in sdb[chat_id]}
            if sg["identifier"] not in added:
                sdb[chat_id].append({"title": sg["title"], "identifier": sg["identifier"], "is_private": sg.get("is_private", False)})
                save_db(sdb, SUPERS_FILE)
        await safe_edit(event, "😷 اختر المجموعة:", build_groups_page(chat_id, pg))

    elif data.startswith("remove_sup_"):
        parts = data.replace("remove_sup_", "").rsplit("_", 1)
        idx = int(parts[0])
        pg = int(parts[1]) if len(parts) > 1 else 0
        groups = cached_groups.get(chat_id, [])
        ti = (pg * 10) + idx
        if ti < len(groups):
            sg = groups[ti]
            sdb = load_db(SUPERS_FILE)
            sdb[chat_id] = [s for s in sdb.get(chat_id, []) if (s.get("identifier") if isinstance(s, dict) else str(s)) != sg["identifier"]]
            save_db(sdb, SUPERS_FILE)
        await safe_edit(event, "😷 اختر المجموعة:", build_groups_page(chat_id, pg))

    elif data == "manual_add_super":
        user_states[chat_id] = {"step": "waiting_super"}
        await safe_edit(event, "🤖 أرسل روابط السوبر (سطر لكل رابط)\nللإلغاء /cancel")

    elif data == "current_super":
        us = load_db(SUPERS_FILE).get(chat_id, [])
        if not us:
            await safe_edit(event, "لا سوبرات.", home_keyboard(chat_id))
        else:
            text = f"السوبرات ({len(us)}):"
            buttons = []
            for item in us:
                if isinstance(item, dict):
                    title = item.get("title", "كروب")
                    ident = str(item.get("identifier", ""))
                    is_priv = item.get("is_private", ident.startswith("-"))
                else:
                    ident = str(item)
                    title = ident
                    is_priv = ident.startswith("-")
                if is_priv or not ident.startswith("@"):
                    gb = make_btn(chat_id, f"{title} 🔒", b"private_info", "primary")
                else:
                    gb = make_url_btn(chat_id, f"{title} 🐥", f"https://t.me/{ident.replace('@', '')}", "primary")
                buttons.append([gb, make_btn(chat_id, "حذف 🧙‍♂️", f"del_super_{ident}".encode(), "primary")])
            buttons.append([make_btn(chat_id, "العودة 🐥", b"go_home", "danger")])
            await safe_edit(event, text, buttons)

    elif data.startswith("del_super_"):
        target = data.replace("del_super_", "")
        sdb = load_db(SUPERS_FILE)
        sdb[chat_id] = [x for x in sdb.get(chat_id, []) if str(x.get("identifier") if isinstance(x, dict) else x) != target]
        save_db(sdb, SUPERS_FILE)
        event.data = b"current_super"
        await callback_handler(event)

    elif data == "go_home":
        await reset_user_session(chat_id)
        sender = await event.get_sender()
        first_name = sender.first_name or "غير معروف"
        await safe_edit(event, f"أهلاً [{first_name}](tg://user?id={chat_id}) 🧑‍🍳\n\nهذا بوت النشر التلقائي", main_keyboard(chat_id))


@bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def message_handler(event):
    if event.raw_text and event.raw_text.startswith('/'): return
    chat_id = str(event.chat_id)
    CURRENT_UI_USER_ID.set(chat_id)
    sd = user_states.get(chat_id, {})
    state = sd.get("step")

    if chat_id == str(SUDO_ID) and state == "admin_add_channel":
        raw = event.raw_text.strip() if event.raw_text else ""
        if not raw.startswith("@") or len(raw) < 2:
            return await event.respond("❌ أرسل @channel")
        try:
            ch = await bot.get_entity(raw)
            if not getattr(ch, "username", None):
                return await event.respond("❌ القناة لا تملك معرفاً عاماً.")
            s = get_admin_settings()
            chs = s.setdefault("__force_sub_channels__", [])
            if any(str(c.get("id")) == str(ch.id) for c in chs):
                user_states.pop(chat_id, None)
                return await event.respond("⚠️ مضافة مسبقاً.", buttons=admin_panel_keyboard(chat_id))
            chs.append({
                "id": ch.id,
                "username": f"@{ch.username}",
                "title": ch.title or ch.username,
                "link": f"https://t.me/{ch.username}"
            })
            save_db(s, SETTINGS_FILE)
            user_states.pop(chat_id, None)
            await event.respond("✅ تمت الإضافة.", buttons=admin_panel_keyboard(chat_id))
        except Exception as e:
            await event.respond(f"❌ تعذر الإضافة: {e}")
        return

    if chat_id == str(SUDO_ID) and state == "admin_set_image":
        if not event.photo:
            return await event.respond("🖼️ أرسل صورة فقط.")
        s = get_admin_settings()
        s["__start_photo__"] = event.photo
        save_db(s, SETTINGS_FILE)
        user_states.pop(chat_id, None)
        await event.respond("✅ تم تعيين صورة البداية.", buttons=admin_panel_keyboard(chat_id))
        return

    if not state or not event.raw_text: return

    if state == "waiting_reply_word":
        word = event.raw_text.strip().lower()
        user_states[chat_id] = {"step": "waiting_reply_text", "word": word}
        await event.respond(f"أرسل الرد للكلمة ({word}) 🐥")

    elif state == "waiting_reply_text":
        rep = event.raw_text.strip()
        word = sd.get("word")
        rdb = load_db(REPLIES_FILE)
        rdb.setdefault(chat_id, {}).setdefault("word_replies", {})
        rdb[chat_id]["word_replies"][word] = rep
        save_db(rdb, REPLIES_FILE)
        kb, _ = replies_main_keyboard(chat_id)
        await event.respond(f"✅ تمت الإضافة للكلمة ({word})", buttons=kb)
        user_states.pop(chat_id, None)

    elif state == "waiting_welcome_msg":
        rdb = load_db(REPLIES_FILE)
        rdb.setdefault(chat_id, {})["welcome"] = event.raw_text.strip()
        save_db(rdb, REPLIES_FILE)
        kb, _ = replies_main_keyboard(chat_id)
        await event.respond("✅ تم تعيين الترحيب.", buttons=kb)
        user_states.pop(chat_id, None)

    elif state == "waiting_ignore_user":
        u = event.raw_text.strip().replace("@", "").lower()
        rdb = load_db(REPLIES_FILE)
        rdb.setdefault(chat_id, {}).setdefault("ignored", [])
        if u not in rdb[chat_id]["ignored"]:
            rdb[chat_id]["ignored"].append(u)
            save_db(rdb, REPLIES_FILE)
        kb, _ = replies_main_keyboard(chat_id)
        await event.respond(f"✅ تم تجاهل ({u})", buttons=kb)
        user_states.pop(chat_id, None)

    elif state == "waiting_post_msg":
        mdb = load_db(MESSAGES_FILE)
        mdb.setdefault(chat_id, []).append({"text": event.raw_text.strip(), "active": True})
        save_db(mdb, MESSAGES_FILE)
        n = len(mdb[chat_id])
        await event.respond(f"تمت الإضافة #{n}", buttons=[[make_btn(chat_id, "العودة 🐥", b"back_to_post_msg", "primary")]])
        user_states.pop(chat_id, None)

    elif state == "waiting_edit_msg":
        idx = sd.get("edit_idx")
        mdb = load_db(MESSAGES_FILE)
        msgs = mdb.get(chat_id, [])
        if 0 <= idx < len(msgs):
            if isinstance(msgs[idx], str):
                msgs[idx] = {"text": event.raw_text.strip(), "active": True}
            else:
                msgs[idx]["text"] = event.raw_text.strip()
            save_db(mdb, MESSAGES_FILE)
            await event.respond(f"تم تعديل #{idx + 1}", buttons=[[make_btn(chat_id, "العودة 🐥", b"back_to_post_msg", "primary")]])
        user_states.pop(chat_id, None)

    elif state == "waiting_timer":
        secs = parse_timer_seconds(event.raw_text.strip())
        sdb = load_db(SETTINGS_FILE)
        sdb.setdefault(chat_id, {})["timer"] = f"{secs} ثوان"
        save_db(sdb, SETTINGS_FILE)
        await event.respond(f"✅ المدة {secs} ثانية", buttons=home_keyboard(chat_id))
        user_states.pop(chat_id, None)

    elif state == "waiting_super":
        lines = [l.strip() for l in event.raw_text.strip().splitlines() if l.strip()]
        sdb = load_db(SUPERS_FILE)
        sdb.setdefault(chat_id, [])
        added_set = {s.get("identifier") if isinstance(s, dict) else str(s) for s in sdb[chat_id]}
        cnt = 0
        for item in lines:
            target = item
            is_priv = False
            if "t.me/" in target:
                c = target.split("t.me/")[-1].replace("/", "")
                if c.startswith("+") or c.startswith("joinchat"):
                    is_priv = True
                    target = c
                else:
                    target = f"@{c}"
            elif not target.startswith("@") and not target.startswith("-"):
                target = f"@{target}"
            elif target.startswith("-"):
                is_priv = True
            if target not in added_set:
                sdb[chat_id].append({"title": target, "identifier": target, "is_private": is_priv})
                added_set.add(target)
                cnt += 1
        save_db(sdb, SUPERS_FILE)
        await event.respond(f"✅ أضيف {cnt} سوبر", buttons=home_keyboard(chat_id))
        user_states.pop(chat_id, None)

    elif state == "waiting_phone":
        phone = event.raw_text.strip().replace(" ", "")

        old = user_clients.get(chat_id)
        if old and old.get("client"):
            try: await old["client"].disconnect()
            except Exception: pass

        await event.respond("جاري إرسال كود التحقق.. 🧑‍🍳")
        session_file = _get_session_file(chat_id, phone)

        uc = TelegramClient(session_file, API_ID, API_HASH)
        try:
            await uc.connect()
            if await uc.is_user_authorized():
                user_clients[chat_id] = {"client": uc, "phone": phone, "session_file": session_file}
                return await finalize_login(chat_id, uc, event)
            
            sent = await uc.send_code_request(phone)
            user_clients[chat_id] = {"client": uc, "phone": phone, "phone_code_hash": sent.phone_code_hash, "session_file": session_file}
            user_states[chat_id] = {"step": "waiting_code"}
            
            await event.respond("وصلك الكود 🐥\n\nأرسل **الأرقام فقط** (مثال: 12345).\n\n⚠️ **تنبيه:** إذا أخطأت في الكود، يجب أن ترسل `/cancel` وتعيد المحاولة من جديد.")
        except ApiIdInvalidError:
            await event.respond("❌ الـ API_ID الخاص بالبوت غير صالح! يرجى مراجعة المطور.")
            user_states.pop(chat_id, None)
        except Exception as e:
            try: await uc.disconnect()
            except Exception: pass
            err = str(e)
            if "UPDATE_APP_TO_LOGIN" in err or "406" in err:
                await event.respond("⚠️ هذا الحساب محظور من تليجرام لاستخدام API غير رسمي.")
            elif "PHONE_NUMBER_BANNED" in err:
                await event.respond("❌ هذا الرقم محظور من تليجرام.")
            else:
                await event.respond(f"خطأ: {e}")
            user_states.pop(chat_id, None)

    elif state == "waiting_code":
        code = re.sub(r'\D', '', event.raw_text)
        
        if not code:
            return await event.respond("❌ يرجى إرسال الأرقام فقط.")
            
        info = user_clients.get(chat_id, {})
        uc = info.get("client")
        phone = info.get("phone")
        pch = info.get("phone_code_hash")
        
        if not uc:
            await event.respond("خطأ في الجلسة. ابدأ من جديد.")
            return await reset_user_session(chat_id)
            
        try:
            await uc.sign_in(phone=phone, code=code, phone_code_hash=pch)
            await finalize_login(chat_id, uc, event)
        except SessionPasswordNeededError:
            user_states[chat_id] = {"step": "waiting_password"}
            await event.respond("🔐 الحساب محمي بكلمة مرور. أرسلها:")
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            await event.respond("❌ الكود خاطئ أو منتهي.\n\n🔴 يرجى إرسال `/cancel` ثم إعادة المحاولة.")
            await reset_user_session(chat_id)
        except Exception as e:
            await event.respond(f"خطأ: {e}")
            await reset_user_session(chat_id)

    elif state == "waiting_password":
        pw = event.raw_text.strip()
        info = user_clients.get(chat_id, {})
        uc = info.get("client")
        if not uc:
            await event.respond("خطأ في الجلسة. ابدأ من جديد.")
            return await reset_user_session(chat_id)
        try:
            await uc.sign_in(password=pw)
            await finalize_login(chat_id, uc, event)
        except Exception as e:
            await event.respond(f"كلمة المرور غير صحيحة: {e}")


@bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_group))
async def group_storage_handler(event):
    CURRENT_UI_USER_ID.set(str(event.sender_id) if event.sender_id else str(event.chat_id))
    try:
        me = await bot.get_me()
        if event.sender_id == me.id: return
        
        storage_chat = load_db(STORAGE_FILE).get(str(SUDO_ID))
        if not storage_chat: return
        if int(event.chat_id) == int(storage_chat): return

        bot_username = (me.username or "").lower()
        is_target = False
        
        if event.is_reply:
            reply = await event.get_reply_message()
            if reply and reply.sender_id == me.id: is_target = True
            
        if bot_username and ("@" + bot_username) in (event.raw_text or "").lower():
            is_target = True

        if not is_target: return

        sender = await event.get_sender()
        sender_name = " ".join(filter(None, [getattr(sender, "first_name", ""), getattr(sender, "last_name", "")])) or "غير معروف"
        if getattr(sender, "username", None):
            sender_name = f"{sender_name} (@{sender.username})"
            
        chat = await event.get_chat()
        title = getattr(chat, "title", "غير معروف")
        msg_body = event.raw_text or "مرفق"
        
        log_text = (
            f"المجموعة : {title}\n"
            f"⌔┊المـرسـل : {sender_name}\n"
            f"⌔┊الرســالـه : {msg_body}\n"
            f"⌔┊رابـط الرسـاله : اضغط هنا\n"
            f"{event.chat_id}\n{event.id}"
        )
        
        chat_username = getattr(chat, "username", None)
        link = f"https://t.me/{chat_username}/{event.id}" if chat_username else None
        markup = [[Button.url("اضغط هنا", link, style="primary")]] if link else None

        msg = await event.get_message()
        if msg.media:
            try:
                await bot.send_file(int(storage_chat), file=msg.media, caption=log_text, buttons=markup)
            except Exception:
                await bot.send_message(int(storage_chat), log_text, buttons=markup, link_preview=False)
        else:
            await bot.send_message(int(storage_chat), log_text, buttons=markup, link_preview=False)
    except Exception:
        pass

async def finalize_login(chat_id, tl_client, event):
    try:
        me = await tl_client.get_me()
        display_username = f"@{me.username}" if me.username else (me.first_name or f"id{me.id}")
        info = user_clients.get(chat_id, {})
        phone_num = info.get("phone", "")
        session_file = info.get("session_file") or _get_session_file(chat_id, phone_num)

        db = load_db(DB_FILE)
        db.setdefault(chat_id, [])
        db[chat_id] = [a for a in db[chat_id] if a.get("username") != display_username and a.get("session_file") != session_file]
        db[chat_id].append({
            "username": display_username,
            "session_file": session_file,
            "phone": phone_num or (me.phone or "")
        })
        save_db(db, DB_FILE)

        try: await tl_client.disconnect()
        except Exception: pass
        await asyncio.sleep(0.3)

        await start_user_client_listener(chat_id, session_file, display_username)

        if chat_id in active_user_clients and display_username in active_user_clients[chat_id]:
            await event.respond(f"✅ تم تسجيل حساب ({display_username}) بنجاح\n📁 الجلسة محفوظة بأمان.", buttons=home_keyboard(chat_id))
        else:
            await event.respond(f"⚠️ تم حفظ الحساب ({display_username}) لكن بدء المراقبة فشل.\nأرسل /start للمحاولة مجدداً.", buttons=home_keyboard(chat_id))
    except Exception as e:
        await event.respond(f"حدث خطأ أثناء حفظ الحساب: {e}")
    finally:
        user_states.pop(chat_id, None)
        user_clients.pop(chat_id, None)


async def main():
    print("Starting Bot...")
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot is Running...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())