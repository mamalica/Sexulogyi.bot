import apscheduler.util
import pytz

def patched_astimezone(tz):
    if tz is None:
        import tzlocal
        tz = tzlocal.get_localzone()
    if not isinstance(tz, pytz.BaseTzInfo):
        tz = pytz.timezone(str(tz))
    return tz

apscheduler.util.astimezone = patched_astimezone

import os
import json
import asyncio
import random
import string
import logging
import threading
import time
import gc

# بارگذاری از فایل .env
from dotenv import load_dotenv
load_dotenv()

from flask import Flask
app = Flask(__name__)

@app.route("/")
def hello():
    return "سلام شومبول طلای من رباتت فعاله❤️😁"

@app.route("/keep-alive")
def keep_alive():
    activity_monitor.record_activity()
    return "✅ Bot is awake!"

@app.route("/health")
def health_check():
    return {
        "status": "active" if activity_monitor.check_health() else "sleeping",
        "last_activity": activity_monitor.last_activity
    }

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    Defaults
)

# ===== سیستم مانیتورینگ فعالیت =====
class ActivityMonitor:
    def __init__(self):
        self.last_activity = time.time()

    def record_activity(self):
        self.last_activity = time.time()

    def check_health(self):
        return time.time() - self.last_activity < 120

activity_monitor = ActivityMonitor()

# ===== تابع keep-alive داخلی =====
def internal_keep_alive():
    """ارسال پیام‌های داخلی برای فعال نگه داشتن ربات"""
    while True:
        try:
            if not activity_monitor.check_health():
                logging.warning("🔔 Wake-up call sent to bot")
            activity_monitor.record_activity()
            time.sleep(45)
        except Exception as e:
            logging.error(f"Keep-alive error: {e}")
            time.sleep(60)

# ===== تابع پاکسازی خودکار =====
def auto_cleanup():
    """پاکسازی هر 5 دقیقه"""
    while True:
        time.sleep(300)
        try:
            global _pending_users, _user_state, _admin_temp_packages, _pending_payments, _payment_receipts
            for data_dict in [_pending_users, _user_state, _admin_temp_packages, _pending_payments, _payment_receipts]:
                if len(data_dict) > 200:
                    data_dict.clear()
            gc.collect()
        except:
            pass

# ===== تنظیمات بهینه‌شده =====
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN یافت نشد! لطفا در PythonAnywhere تنظیم کنید")

CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
SECOND_CHANNEL_USERNAME = os.getenv("SECOND_CHANNEL_USERNAME")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except (ValueError, TypeError):
    ADMIN_ID = 0
    logging.warning("⚠️ ADMIN_ID معتبر نیست")

# ===== فایل‌های ذخیره‌سازی بهینه =====
VIDEO_DB_FILE = "videos.json"
USERS_FILE = "users.json"

# ===== کش در حافظه برای کاهش I/O =====
_videos_cache = None
_users_cache = None
_user_state = {}
_pending_users = {}
_admin_temp_packages = {}
_pending_payments = {}
_payment_receipts = {}

# ===== مدیریت حافظه و ذخیره‌سازی بهینه =====
def _ensure_files():
    """ایجاد فایل‌های ضروری با مصرف کمینه"""
    try:
        if not os.path.exists(VIDEO_DB_FILE):
            with open(VIDEO_DB_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False)
        if not os.path.exists(USERS_FILE):
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
    except Exception as e:
        logging.warning(f"خطا در ایجاد فایل‌ها: {e}")

def load_videos():
    """لود ویدیوها با کش کردن"""
    global _videos_cache
    if _videos_cache is not None:
        return _videos_cache.copy()
    try:
        with open(VIDEO_DB_FILE, "r", encoding="utf-8") as f:
            _videos_cache = json.load(f)
        return _videos_cache.copy()
    except Exception as e:
        logging.error(f"خطا در لود ویدیوها: {e}")
        return {}

def save_videos(data):
    """ذخیره ویدیوها با بهینه‌سازی"""
    global _videos_cache
    try:
        with open(VIDEO_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _videos_cache = data.copy()
    except Exception as e:
        logging.error(f"خطا در ذخیره ویدیوها: {e}")

def load_users():
    """لود کاربران با کش کردن"""
    global _users_cache
    if _users_cache is not None:
        return _users_cache.copy()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            _users_cache = json.load(f)
        return _users_cache.copy()
    except Exception as e:
        logging.error(f"خطا در لود کاربران: {e}")
        return []

def save_users(data):
    """ذخیره کاربران با بهینه‌سازی"""
    global _users_cache
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        _users_cache = data.copy()
    except Exception as e:
        logging.error(f"خطا در ذخیره کاربران: {e}")

def generate_code(length=6):
    """کد کوتاه‌تر برای صرفه‌جویی"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def add_user(user_id):
    """افزودن کاربر با بهینه‌سازی"""
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        save_users(users)

# ===== بررسی عضویت بهینه‌شده =====
async def is_member(chat_id, user_id, context):
    """بررسی عضویت با هندلینگ خطا"""
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.warning(f"خطا در بررسی عضویت {user_id}: {e}")
        return False

# ===== پنل ادمین بهینه‌شده =====
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity_monitor.record_activity()
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ فقط ادمین دسترسی دارد.")
        return

    keyboard = [
        [InlineKeyboardButton("📤 آپلود ویدیو", callback_data="upload_video"),
         InlineKeyboardButton("📦 آپلود پکیج", callback_data="upload_package")],
        [InlineKeyboardButton("💳 پکیج پولی", callback_data="upload_paid_package")]
    ]
    await update.message.reply_text("پنل مدیریت:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity_monitor.record_activity()
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ فقط ادمین دسترسی دارد.")
        return

    user_id = query.from_user.id
    data = query.data or ""

    if data == "upload_video":
        _user_state[user_id] = "uploading"
        await query.edit_message_text("🎬 لطفاً ویدیو رو ارسال کن شومبول طلا.")

    elif data == "upload_package":
        _user_state[user_id] = "uploading_package"
        _admin_temp_packages[user_id] = []
        keyboard = [
            [InlineKeyboardButton("✅ پایان و ثبت پکیج", callback_data="finish_package"),
             InlineKeyboardButton("❌ لغو", callback_data="cancel_upload")]
        ]
        await query.edit_message_text(
            "📦 اکنون ویدیوها را یکی‌یکی ارسال کن (حداکثر 8). پس از اتمام 'پایان و ثبت پکیج' را بزن.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "upload_paid_package":
        _user_state[user_id] = "uploading_paid_package"
        _admin_temp_packages[user_id] = []
        keyboard = [
            [InlineKeyboardButton("✅ پایان و ثبت پکیج پولی", callback_data="finish_paid_package"),
             InlineKeyboardButton("❌ لغو", callback_data="cancel_upload")]
        ]
        await query.edit_message_text(
            "💳 حالا ویدیوهای پکیج ویژه رو یکی‌یکی بفرست (حداکثر 8). بعد 'پایان و ثبت پکیج پولی' رو بزن.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "finish_package":
        temp = _admin_temp_packages.get(user_id, [])
        if not temp:
            await query.edit_message_text("⚠️ هیچ ویدیویی برای ثبت وجود ندارد.")
            return

        code = generate_code()
        vids = load_videos()
        vids[code] = {"type": "package", "files": temp.copy()}
        save_videos(vids)
        link = f"https://t.me/{context.bot.username}?start={code}"
        _user_state.pop(user_id, None)
        _admin_temp_packages.pop(user_id, None)
        await query.edit_message_text(f"✅ پکیج ذخیره شد! ({len(temp)} ویدیو)\n🔗 لینک: {link}")

    elif data == "finish_paid_package":
        temp = _admin_temp_packages.get(user_id, [])
        if not temp:
            await query.edit_message_text("⚠️ هیچ ویدیویی برای ثبت وجود ندارد.")
            return

        code = generate_code()
        vids = load_videos()
        vids[code] = {
            "type": "paid",
            "files": temp.copy(),
            "price": 99000,
            "card": "6037991775906427",
            "currency": "IRR"
        }
        save_videos(vids)
        link = f"https://t.me/{context.bot.username}?start={code}"
        _user_state.pop(user_id, None)
        _admin_temp_packages.pop(user_id, None)
        await query.edit_message_text(f"✅ پکیج پولی ذخیره شد! ({len(temp)} ویدیو)\n🔗 لینک: {link}\nقیمت: ۹۹٬۰۰۰ تومان\nکارت: 6037991775906427")

    elif data == "cancel_upload":
        _user_state.pop(user_id, None)
        _admin_temp_packages.pop(user_id, None)
        await query.edit_message_text("❌ آپلود کنسل شد.")

# ===== دریافت ویدیو از ادمین با بهینه‌سازی =====
MAX_PACKAGE_SIZE = 8

async def handle_video_from_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity_monitor.record_activity()
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("فیلمتو بفرس دودول طلا😁😘.")
        return

    file_id = video.file_id
    state = _user_state.get(user.id)

    if state == "uploading":
        code = generate_code()
        vids = load_videos()
        vids[code] = file_id
        save_videos(vids)
        link = f"https://t.me/{context.bot.username}?start={code}"
        await update.message.reply_text(f"✅ ذخیره شد!\n🔗 لینک: {link}")
        _user_state.pop(user.id, None)
        return

    if state == "uploading_package":
        tmp = _admin_temp_packages.setdefault(user.id, [])
        if len(tmp) >= MAX_PACKAGE_SIZE:
            await update.message.reply_text(f"⚠️ حداکثر {MAX_PACKAGE_SIZE} ویدیو.")
            return
        tmp.append(file_id)
        await update.message.reply_text(f"ویدیو دریافت شد ({len(tmp)}/{MAX_PACKAGE_SIZE}).")
        return

    if state == "uploading_paid_package":
        tmp = _admin_temp_packages.setdefault(user.id, [])
        if len(tmp) >= MAX_PACKAGE_SIZE:
            await update.message.reply_text(f"⚠️ حداکثر {MAX_PACKAGE_SIZE} ویدیو.")
            return
        tmp.append(file_id)
        await update.message.reply_text(f"ویدیوی پکیج پولی دریافت شد ({len(tmp)}/{MAX_PACKAGE_SIZE}).")
        return

# ===== هندل فرمان /start بهینه‌شده =====
async def start_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity_monitor.record_activity()
    user = update.effective_user
    if not user:
        return

    add_user(user.id)
    args = context.args

    if not args:
        await update.message.reply_text("سلام عزیزم برای دریافت ویدیو ها، عضو دو کانال شو.")
        return

    code = args[0]
    vids = load_videos()

    if code not in vids:
        await update.message.reply_text("❌ لینک نامعتبر است.")
        return

    entry = vids[code]

    # اگر پکیج پولی است -> درخواست فیش از کاربر
    if isinstance(entry, dict) and entry.get("type") == "paid":
        card = entry.get("card", "6037991775906427")
        price = entry.get("price", 99000)
        _pending_payments[user.id] = code
        await update.message.reply_text(
            f"🔒 این پکیج پولی است.\nلطفاً مبلغ {price:,} تومان را به کارت {card} واریز کنید و فیش واریزی را همین‌جا ارسال کنید.\nبلافاصله پس از تایید تراکنش توسط ادمین، پکیج ویژه در اختیار شما قرار خواهد گرفت."
        )
        return

    # ادامه‌ی بررسی عضویت برای پکیج‌های رایگان یا ویدیوی تکی
    user_id = user.id
    is_in_first, is_in_second = await asyncio.gather(
        is_member(CHANNEL_ID, user_id, context),
        is_member(f"@{SECOND_CHANNEL_USERNAME}", user_id, context)
    )

    if not (is_in_first and is_in_second):
        _pending_users[user_id] = code
        buttons = []
        if not is_in_first:
            buttons.append([InlineKeyboardButton("📢 سکسولوژی", url=f"https://t.me/{CHANNEL_USERNAME}")])
        if not is_in_second:
            buttons.append([InlineKeyboardButton("📢 سکسی لند", url=f"https://t.me/{SECOND_CHANNEL_USERNAME}")])
        buttons.append([InlineKeyboardButton("✅ بررسی عضویت", callback_data=f"check_{code}")])
        await update.message.reply_text("🔒 لطفاً در کانال‌ها عضو شو:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    await _deliver_content(update, context, code, vids)

async def _deliver_content(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str, vids: dict):
    """تحویل محتوا با مدیریت خطا"""
    entry = vids.get(code)
    if not entry:
        await update.message.reply_text("❌ محتوای مورد نظر یافت نشد.")
        return

    try:
        if isinstance(entry, dict) and entry.get("type") == "package":
            await send_package(update, context, entry.get("files", []))
        else:
            await send_video(update, context, entry)
    except Exception as e:
        logging.error(f"خطا در ارسال محتوا: {e}")
        await update.message.reply_text("❌ خطا در ارسال محتوا. لطفاً مجدداً تلاش کنید.")

# ===== دکمه بررسی عضویت بهینه‌شده =====
async def handle_check_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity_monitor.record_activity()
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if user_id not in _pending_users:
        await query.edit_message_text("❌ لینک پیدا نشد یا منقضی شده.")
        return

    code = _pending_users[user_id]
    vids = load_videos()

    if code not in vids:
        await query.edit_message_text("❌ لینک معتبر نیست.")
        return

    is_in_first, is_in_second = await asyncio.gather(
        is_member(CHANNEL_ID, user_id, context),
        is_member(f"@{SECOND_CHANNEL_USERNAME}", user_id, context)
    )

    if not (is_in_first and is_in_second):
        buttons = []
        if not is_in_first:
            buttons.append([InlineKeyboardButton("📢 سکسولوژی", url=f"https://t.me/{CHANNEL_USERNAME}")])
        if not is_in_second:
            buttons.append([InlineKeyboardButton("📢 سکسی لند", url=f"https://t.me/{SECOND_CHANNEL_USERNAME}")])
        buttons.append([InlineKeyboardButton("✅ بررسی مجدد", callback_data=f"check_{code}")])
        await query.edit_message_text("⛔ هنوز عضویت کامل نشده.", reply_markup=InlineKeyboardMarkup(buttons))
        return

    del _pending_users[user_id]
    try:
        await context.bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except:
        pass

    await _deliver_content(Update(update.update_id, message=query.message), context, code, vids)

# ===== ارسال ویدیو با مدیریت خطا =====
async def send_video(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str):
    try:
        msg = await update.message.reply_video(
            file_id,
            caption="🎥 ❌ویدیو تا ۲۰ ثانیه قابل مشاهده است❌."
        )
        asyncio.create_task(_del_after(context, msg.chat.id, msg.message_id, 20))
    except Exception as e:
        logging.error(f"خطا در ارسال ویدیو: {e}")
        try:
            msg = await context.bot.send_video(
                chat_id=update.message.chat.id,
                video=file_id,
                caption="🎥 ویدیو تا ۲۰ ثانیه قابل مشاهده است."
            )
            asyncio.create_task(_del_after(context, msg.chat.id, msg.message_id, 20))
        except Exception as e2:
            logging.error(f"خطای دوم در ارسال ویدیو: {e2}")
            await update.message.reply_text("❌ خطا در ارسال ویدیو.")

async def _del_after(context, chat_id, message_id, delay):
    """حذف پیام پس از تاخیر"""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logging.debug(f"خطا در حذف پیام: {e}")

# ===== ارسال پکیج بهینه‌شده =====
async def send_package(update: Update, context: ContextTypes.DEFAULT_TYPE, files: list):
    if not files:
        await update.message.reply_text("❌ پکیج خالی یا منقضی شده.")
        return

    success_count = 0
    for fid in files:
        try:
            msg = await context.bot.send_video(
                chat_id=update.message.chat.id,
                video=fid,
                caption="🎥فیلم ها بعد از 20 ثانیه به طور خودکار حذف خواهند شد❌"
            )
            asyncio.create_task(_del_after(context, msg.chat.id, msg.message_id, 20))
            success_count += 1
            await asyncio.sleep(0.2)
        except Exception as e:
            logging.warning(f"خطا در ارسال ویدیو از پکیج: {e}")
            continue

    if success_count == 0:
        await update.message.reply_text("❌ خطا در ارسال تمام ویدیوهای پکیج.")
    elif success_count < len(files):
        await update.message.reply_text(f"⚠️ {success_count} از {len(files)} ویدیو ارسال شد.")

# ===== نمایش اعضا =====
async def show_member_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity_monitor.record_activity()
    if update.effective_user.id != ADMIN_ID:
        return
    users = load_users()
    await update.message.reply_text(f"👥 اعضای ربات: {len(users)} نفر")

# ===== اجرای اصلی بهینه‌شده =====
def main():
    if not BOT_TOKEN:
        logging.error("❌ BOT_TOKEN تنظیم نشده!")
        return

    _ensure_files()

    # راه‌اندازی threads کمکی
    try:
        threading.Thread(target=internal_keep_alive, daemon=True).start()
        threading.Thread(target=auto_cleanup, daemon=True).start()
    except:
        pass

    defaults = Defaults(parse_mode="HTML")
    app_bot = ApplicationBuilder()\
        .token(BOT_TOKEN)\
        .concurrent_updates(True)\
        .defaults(defaults)\
        .pool_timeout(5)\
        .connect_timeout(5)\
        .read_timeout(5)\
        .write_timeout(5)\
        .get_updates_read_timeout(5)\
        .build()

    handlers = [
        CommandHandler("admin", admin_panel),
        CallbackQueryHandler(handle_admin_buttons, pattern="^upload_video$"),
        CallbackQueryHandler(handle_admin_buttons, pattern="^upload_package$"),
        CallbackQueryHandler(handle_admin_buttons, pattern="^upload_paid_package$"),
        CallbackQueryHandler(handle_admin_buttons, pattern="^(finish_package|finish_paid_package|cancel_upload)$"),
        CallbackQueryHandler(handle_check_button, pattern="^check_"),
        MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video_from_admin),
        CommandHandler("start", start_link),
        CommandHandler("member", show_member_count)
    ]

    for handler in handlers:
        app_bot.add_handler(handler)

    logging.warning("🤖 Bot is running... (Anti-Sleep Optimized)")
    app_bot.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
        close_loop=False,
        poll_interval=0.1,
        timeout=5,
        bootstrap_retries=3,
    )

if __name__ == "__main__":
    print("🚀 راه‌اندازی ربات اصلی با تمام قابلیت‌ها...")
    main()
