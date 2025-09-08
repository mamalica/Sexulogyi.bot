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
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "سلام شومبول طلای من رباتت فعاله❤️😁 "

# برای اجرای دستی (نه نیاز نیست در PythonAnywhere)
# if __name__ == "__main__":
#     app.()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv
load_dotenv()

# ===== تنظیمات پایه =====
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
SECOND_CHANNEL_USERNAME = os.getenv("SECOND_CHANNEL_USERNAME")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

VIDEO_DB_FILE = "videos.json"
USERS_FILE = "users.json"
user_state = {}
pending_users = {}

# ===== ساخت فایل‌ها در صورت نبود =====
for file in [VIDEO_DB_FILE, USERS_FILE]:
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            json.dump({} if file == VIDEO_DB_FILE else [], f)

# ===== مدیریت ویدیوها =====
def load_videos():
    with open(VIDEO_DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_videos(data):
    with open(VIDEO_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def generate_code(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# ===== مدیریت کاربران =====
def load_users():
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(data):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def add_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        save_users(users)

# ===== بررسی عضویت =====
async def is_member(chat_id, user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ===== پنل ادمین =====
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ فقط ادمین دسترسی دارد.")
        return
    btn = InlineKeyboardButton("📤 آپلود ویدیو", callback_data="upload_video")
    await update.message.reply_text("پنل مدیریت:", reply_markup=InlineKeyboardMarkup([[btn]]))

async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ فقط ادمین دسترسی دارد.")
        return
    if query.data == "upload_video":
        user_state[ADMIN_ID] = "uploading"
        await query.edit_message_text("🎬 لطفاً ویدیو را ارسال کنید.")

# ===== دریافت و ذخیره ویدیو از ادمین =====
async def handle_video_from_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID or user_state.get(ADMIN_ID) != "uploading":
        return

    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("فیلمتو بفرس دودول طلا😁😘  .")

    code = generate_code()
    file_id = video.file_id
    vids = load_videos()
    vids[code] = file_id
    save_videos(vids)

    link = f"https://t.me/{context.bot.username}?start={code}"
    await update.message.reply_text(f"✅ ذخیره شد!\n🔗 لینک: {link}")
    user_state[ADMIN_ID] = None

# ===== هندل فرمان /start =====
async def start_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    add_user(user.id)

    args = context.args
    if not args:
        await update.message.reply_text("سلام! برای دریافت ویدیو، عضو دو کانال شو.")
        return

    code = args[0]
    vids = load_videos()
    if code not in vids:
        await update.message.reply_text("❌ لینک نامعتبر است.")
        return

    user_id = user.id
    is_in_first = await is_member(CHANNEL_ID, user_id, context)
    is_in_second = await is_member(f"@{SECOND_CHANNEL_USERNAME}", user_id, context)

    if not (is_in_first and is_in_second):
        pending_users[user_id] = code
        buttons = []
        if not is_in_first:
            buttons.append([InlineKeyboardButton("📢 عضویت در سکسولوژی", url=f"https://t.me/{CHANNEL_USERNAME}")])
        if not is_in_second:
            buttons.append([InlineKeyboardButton("📢 عضویت در سکسی لند", url=f"https://t.me/{SECOND_CHANNEL_USERNAME}")])
        buttons.append([InlineKeyboardButton("✅ بررسی عضویت", callback_data=f"check_{code}")])
        await update.message.reply_text("🔒 لطفاً در کانال‌های زیر عضو شو:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    await send_video(update, context, vids[code])

# ===== دکمه بررسی عضویت =====
async def handle_check_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if user_id not in pending_users:
        await query.edit_message_text("❌ لینک پیدا نشد یا منقضی شده.")
        return

    code = pending_users[user_id]
    vids = load_videos()
    if code not in vids:
        await query.edit_message_text("❌ لینک معتبر نیست.")
        return

    is_in_first = await is_member(CHANNEL_ID, user_id, context)
    is_in_second = await is_member(f"@{SECOND_CHANNEL_USERNAME}", user_id, context)

    if not (is_in_first and is_in_second):
        buttons = []
        if not is_in_first:
            buttons.append([InlineKeyboardButton("📢 عضویت در سکسولوژی", url=f"https://t.me/{CHANNEL_USERNAME}")])
        if not is_in_second:
            buttons.append([InlineKeyboardButton("📢 عضویت در سکسی لند", url=f"https://t.me/{SECOND_CHANNEL_USERNAME}")])
        buttons.append([InlineKeyboardButton("✅ بررسی مجدد", callback_data=f"check_{code}")])
        await query.edit_message_text(
            "⛔ هنوز عضویت کامل نشده. فقط کانال‌هایی که عضو نیستی نمایش داده میشه:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    del pending_users[user_id]
    await context.bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    dummy_update = Update(update.update_id, message=query.message)
    await send_video(dummy_update, context, vids[code])

# ===== ارسال و حذف ویدیو =====
async def send_video(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str):
    msg = await update.message.reply_video(
        file_id,
        caption="🎥😘 این  ویدیو تا ۲۰ ثانیه قابل مشاهده است. لطفا در پیام های ذخیره شده خود ذخیره‌اش کن 🔴"
    )
    await asyncio.sleep(15)
    try:
        await context.bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)
    except:
        pass

# ===== نمایش تعداد اعضا برای ادمین =====
async def show_member_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    users = load_users()
    await update.message.reply_text(f"👥 تعداد اعضای ربات: {len(users)} نفر")

# ===== اجرای اصلی =====
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(handle_admin_buttons, pattern="^upload_video$"))
    app.add_handler(CallbackQueryHandler(handle_check_button, pattern="^check_"))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video_from_admin))
    app.add_handler(CommandHandler("start", start_link))
    app.add_handler(CommandHandler("member", show_member_count))

    logging.info("🤖 Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
