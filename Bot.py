import logging
from datetime import datetime, timedelta
import json
import os
import schedule
import threading
import time

# --- إعدادات التسجيل (Logging) ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- استيراد مكتبة python-telegram-bot ---
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, filters

# --- إعدادات البوت (TELEGRAM_BOT_TOKEN) ---
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    logger.error("خطأ: لم يتم تعيين متغير البيئة BOT_TOKEN. يرجى تعيينه في Railway.")
    exit(1)

updater = Updater(TELEGRAM_BOT_TOKEN)
dispatcher = updater.dispatcher
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ------------ وظائف قواعد البيانات (JSON File Storage) ------------
MEMBERS_FILE = "members.json"
TASKS_FILE = "tasks.json"

def load_json(filename):
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"File {filename} not found, returning empty data.")
        return {} if "members" in filename else []
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {filename}, returning empty data.")
        return {} if "members" in filename else []

def save_json(filename, data):
    try:
        with open(filename, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"Data saved to {filename} successfully.")
    except Exception as e:
        logger.error(f"Error saving data to {filename}: {e}")

# ------------ أوامر البوت (Command Handlers) ------------

async def start(update: Update, context: CallbackContext) -> None:
    user_name = update.effective_user.first_name
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"✅ مرحباً بك يا {user_name}!\nChat ID: `{chat_id}`\n\n"
        "مرحباً بك! أنا بوت التذكيرات للمهام.\n"
        "لاستخدام البوت، اتبع التعليمات التالية:\n"
        "/add_member <username>|<chat_id> - لإضافة عضو جديد (مثال: /add_member احمد|123456789)\n"
        "/add_task <المهمة>|<تاريخ_الاستحقاق YYYY-MM-DD>|<اسم_المسؤول> - لإضافة مهمة (مثال: /add_task إعداد_التقرير|2025-07-20|احمد)\n"
        "/show_tasks - لعرض جميع المهام"
    )

async def add_member(update: Update, context: CallbackContext) -> None:
    try:
        if not context.args or '|' not in context.args[0]:
            await update.message.reply_text("❌ صيغة خاطئة. يرجى استخدام: /add_member <username>|<chat_id>\nمثال: /add_member احمد|123456789")
            return

        parts = context.args[0].split('|')
        if len(parts) != 2:
            await update.message.reply_text("❌ صيغة خاطئة. يرجى استخدام: /add_member <username>|<chat_id>\nمثال: /add_member احمد|123456789")
            return

        username = parts[0].strip()
        chat_id_str = parts[1].strip()

        if not chat_id_str.isdigit():
            await update.message.reply_text("❌ الـ Chat ID يجب أن يكون رقماً.")
            return

        chat_id = int(chat_id_str)

        members = load_json(MEMBERS_FILE)
        if not isinstance(members, dict): 
            members = {}

        if username in members:
            await update.message.reply_text(f"⚠️ العضو {username} موجود بالفعل.")
            return

        members[username] = {"chat_id": chat_id}
        save_json(MEMBERS_FILE, members)
        await update.message.reply_text(f"✅ تمت إضافة العضو {username} بنجاح (Chat ID: `{chat_id}`).")
    except Exception as e:
        logger.error(f"Error in add_member: {e}")
        await update.message.reply_text(f"❌ حدث خطأ أثناء إضافة العضو. يرجى التأكد من الصيغة الصحيحة.\nالخطأ: {e}")

async def add_task(update: Update, context: CallbackContext) -> None:
    try:
        if not context.args or '|' not in context.args[0]:
            await update.message.reply_text("❌ صيغة خاطئة. يرجى استخدام: /add_task <المهمة>|<تاريخ_الاستحقاق YYYY-MM-DD>|<المسؤول_username>\nمثال: /add_task إعداد_التقرير|2025-07-20|احمد")
            return

        parts = context.args[0].split('|')
        if len(parts) != 3:
            await update.message.reply_text("❌ صيغة خاطئة. يرجى استخدام: /add_task <المهمة>|<YYYY-MM-DD>|<اسم_المسؤول>\nمثال: /add_task إعداد_التقرير|2025-07-20|احمد")
            return

        task_description = parts[0].strip()
        deadline_str = parts[1].strip()
        assigned_username = parts[2].strip()

        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text("❌ تنسيق التاريخ غير صحيح. يرجى استخدام YYYY-MM-DD.")
            return

        members = load_json(MEMBERS_FILE)
        if not isinstance(members, dict) or assigned_username not in members:
            await update.message.reply_text(f"❌ العضو '{assigned_username}' غير مسجل. يرجى إضافة العضو أولاً باستخدام /add_member.")
            return

        assigned_chat_id = members[assigned_username]["chat_id"]

        task_data = {
            "task": task_description,
            "deadline": deadline_str,
            "assigned_to": assigned_username,
            "chat_id": assigned_chat_id
        }
        tasks = load_json(TASKS_FILE)
        if not isinstance(tasks, list):
            tasks = []

        tasks.append(task_data)
        save_json(TASKS_FILE, tasks)
        await update.message.reply_text(f"✅ تمت إضافة المهمة:\nالمهمة: {task_description}\nالموعد: {deadline_str}\nالمسؤول: {assigned_username}")
    except Exception as e:
        logger.error(f"Error in add_task: {e}")
        await update.message.reply_text(f"❌ حدث خطأ أثناء إضافة المهمة. يرجى التأكد من الصيغة الصحيحة.\nالخطأ: {e}")

async def show_tasks(update: Update, context: CallbackContext) -> None:
    tasks = load_json(TASKS_FILE)
    if not tasks:
        await update.message.reply_text("📭 لا توجد مهام حالياً.")
    else:
        text = "📋 المهام:\n\n"
        for i, t in enumerate(tasks):
            text += (f"🔹 {i+1}. {t['task']}\n"
                     f"   الموعد: {t['deadline']}\n"
                     f"   المسؤول: {t['assigned_to']}\n"
                     "--------------------\n")
        await update.message.reply_text(text)

# ------------ وظيفة إرسال التذكيرات (تُشغل بواسطة Scheduler) ------------
async def send_reminders_scheduled() -> None:
    tasks = load_json(TASKS_FILE)
    today = datetime.now().date()

    reminded_tasks_today = [] 

    for t in tasks:
        try:
            deadline = datetime.strptime(t["deadline"], "%Y-%m-%d").date()
            days_left = (deadline - today).days

            message_text = ""
            if days_left == 7:
                message_text = f"📌 تذكير: المهمة '{t['task']}' مستحقة خلال أسبوع ({t['deadline']})."
            elif days_left == 2:
                message_text = f"📌 تذكير: المهمة '{t['task']}' مستحقة خلال يومين ({t['deadline']})."
            elif days_left == 1:
                message_text = f"📌 تذكير: المهمة '{t['task']}' مستحقة غداً ({t['deadline']})."
            elif days_left == 0:
                message_text = f"🚨 تنبيه: المهمة '{t['task']}' مستحقة اليوم!"

            if message_text:
                assigned_chat_id = t.get("chat_id")
                if assigned_chat_id and (t['task'], t['deadline'], days_left) not in reminded_tasks_today:
                    try:
                        await bot.send_message(chat_id=assigned_chat_id, text=message_text)
                        logger.info(f"Sent reminder for task '{t['task']}' to {t['assigned_to']} (chat_id: {assigned_chat_id})")
                        reminded_tasks_today.append((t['task'], t['deadline'], days_left))
                    except Exception as send_e:
                        logger.error(f"Failed to send message to {assigned_chat_id} for task '{t['task']}': {send_e}")
        except Exception as e:
            logger.error(f"Error processing reminder for task {t.get('task', 'N/A')}: {e}")

# ------------ وظيفة الجدولة (Scheduler) التي تعمل في Thread منفصلة ------------
def run_scheduler_thread():
    schedule_time = os.environ.get("REMINDER_TIME", "09:00")

    loop = asyncio.get_event_loop()
    schedule.every().day.at(schedule_time).do(lambda: asyncio.run_coroutine_threadsafe(send_reminders_scheduled(), loop))

    logger.info(f"Scheduler started. Reminders will be checked daily at {schedule_time}.")
    while True:
        schedule.run_pending()
        time.sleep(1)

# ------------ وظيفة التشغيل الرئيسية للبوت على Railway ------------
def main():
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("add_member", add_member))
    dispatcher.add_handler(CommandHandler("add_task", add_task))
    dispatcher.add_handler(CommandHandler("show_tasks", show_tasks))

    scheduler_thread = threading.Thread(target=run_scheduler_thread)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    logger.info("✅ البوت يعمل وجاهز لاستقبال الأوامر.")
    updater.start_polling()

    updater.idle() 
    logger.info("البوت توقف.")

if __name__ == "__main__":
    # Python-telegram-bot's updater.start_polling() creates and manages its own event loop,
    # so we don't explicitly need asyncio.run(main()) here. Just calling main() is enough.
    main()

