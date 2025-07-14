import logging
import time
import json
from datetime import datetime, timedelta
import asyncio
import threading
import os # هذا الاستيراد الجديد لقراءة متغيرات البيئة

# --- إعدادات التسجيل (Logging) ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Import Pyrogram client and related modules
from pyrogram import Client, filters, idle
import schedule

# --- إعدادات البوت (Pyrogram Client) ---
# 🛑 ستتم قراءة هذه القيم من متغيرات البيئة في Render لضمان الأمان
# تأكد من تعيين هذه المتغيرات في إعدادات Render (Environment Variables)
# os.environ.get("VARIABLE_NAME") يقوم بقراءة قيمة المتغير من البيئة.
# يمكن وضع قيمة افتراضية كـ fallback عند التطوير المحلي، لكن لا تفعل ذلك مع بيانات حساسة.
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# تحقق بسيط لضمان أن المتغيرات قد تم تحميلها (مفيد للاختبار)
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("خطأ: لم يتم تعيين متغيرات البيئة (API_ID, API_HASH, BOT_TOKEN). يرجى تعيينها في Render.")
    # يمكنك الخروج من البرنامج أو استخدام قيم افتراضية للاختبار المحلي فقط
    # exit(1) # لإيقاف البوت إذا كانت المتغيرات غير موجودة


app = Client("team_reminder_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ------------ وظائف قواعد البيانات (JSON File Storage) ------------
# في Render، هذه الملفات ستكون مؤقتة وتفقد عند كل إعادة نشر أو إعادة تشغيل.
# إذا كنت تحتاج إلى تخزين دائم للبيانات، فستحتاج إلى استخدام قاعدة بيانات خارجية (مثل PostgreSQL)
# أو خدمة تخزين سحابي. لكن للاختبار والتجربة، ملفات JSON ستعمل.
def load_json(filename):
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"File {filename} not found, returning empty list.")
        return []
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {filename}, returning empty list.")
        return []

def save_json(filename, data):
    try:
        with open(filename, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"Data saved to {filename} successfully.")
    except Exception as e:
        logger.error(f"Error saving data to {filename}: {e}")

# ------------ أوامر البوت (Pyrogram Handlers) ------------

@app.on_message(filters.command("start"))
async def start_command(client: Client, message):
    await message.reply(f"✅ تم تسجيلك يا {message.from_user.first_name}\nChat ID: `{message.chat.id}`\n\n"
                        "استخدم /add_member لتسجيل الأعضاء الآخرين (بواسطة المسؤول).\n"
                        "استخدم /add_task لإضافة مهمة.\n"
                        "استخدم /show_tasks لعرض المهام.")

@app.on_message(filters.command("add_member"))
async def add_member_command(client: Client, message):
    try:
        if len(message.command) < 2 or '|' not in message.text:
            await message.reply("❌ صيغة خاطئة. يرجى استخدام: /add_member <username>|<chat_id>\nمثال: /add_member احمد|123456789")
            return

        # للتأكد من فصل الأمر عن الوسائط
        command_prefix, *args = message.text.split(maxsplit=1)
        if not args:
            await message.reply("❌ صيغة خاطئة. يرجى استخدام: /add_member <username>|<chat_id>\nمثال: /add_member احمد|123456789")
            return

        parts = args[0].split('|')
        if len(parts) != 2:
            await message.reply("❌ صيغة خاطئة. يرجى استخدام: /add_member <username>|<chat_id>\nمثال: /add_member احمد|123456789")
            return
        
        username = parts[0].strip()
        chat_id_str = parts[1].strip()

        if not chat_id_str.isdigit():
            await message.reply("❌ الـ Chat ID يجب أن يكون رقماً.")
            return

        chat_id = int(chat_id_str)

        members = load_json("members.json")

        if any(m['username'] == username for m in members):
            await message.reply(f"⚠️ العضو {username} موجود بالفعل.")
            return
        
        member = {"username": username, "chat_id": chat_id}
        members.append(member)
        save_json("members.json", members)
        await message.reply(f"✅ تمت إضافة العضو {username} بنجاح (Chat ID: `{chat_id}`).")
    except Exception as e:
        logger.error(f"Error in add_member: {e}")
        await message.reply(f"❌ حدث خطأ أثناء إضافة العضو. يرجى التأكد من الصيغة الصحيحة.\nالخطأ: {e}")


@app.on_message(filters.command("add_task"))
async def add_task_command(client: Client, message):
    try:
        if len(message.command) < 2 or '|' not in message.text:
            await message.reply("❌ صيغة خاطئة. يرجى استخدام: /add_task <المهمة>|<تاريخ_الاستحقاق YYYY-MM-DD>|<المسؤول_username>\nمثال: /add_task إعداد_التقرير|2025-07-20|احمد")
            return

        # للتأكد من فصل الأمر عن الوسائط
        command_prefix, *args = message.text.split(maxsplit=1)
        if not args:
            await message.reply("❌ صيغة خاطئة. يرجى استخدام: /add_task <المهمة>|<YYYY-MM-DD>|<اسم_المسؤول>\nمثال: /add_task إعداد_التقرير|2025-07-20|احمد")
            return

        parts = args[0].split('|')
        if len(parts) != 3:
            await message.reply("❌ صيغة خاطئة. يرجى استخدام: /add_task <المهمة>|<YYYY-MM-DD>|<اسم_المسؤول>\nمثال: /add_task إعداد_التقرير|2025-07-20|احمد")
            return

        task = parts[0].strip()
        deadline_str = parts[1].strip()
        assigned_username = parts[2].strip()

        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        except ValueError:
            await message.reply("❌ تنسيق التاريخ غير صحيح. يرجى استخدام YYYY-MM-DD.")
            return

        members = load_json("members.json")
        member = next((m for m in members if m["username"] == assigned_username), None)
        
        if not member:
            await message.reply(f"❌ العضو '{assigned_username}' غير مسجل. يرجى إضافة العضو أولاً باستخدام /add_member.")
            return
        
        task_data = {
            "task": task,
            "deadline": deadline_str,
            "assigned_to": assigned_username,
            "chat_id": member["chat_id"]
        }
        tasks = load_json("tasks.json")
        tasks.append(task_data)
        save_json("tasks.json", tasks)
        await message.reply(f"✅ تمت إضافة المهمة:\nالمهمة: {task}\nالموعد: {deadline_str}\nالمسؤول: {assigned_username}")
    except Exception as e:
        logger.error(f"Error in add_task: {e}")
        await message.reply(f"❌ حدث خطأ أثناء إضافة المهمة. يرجى التأكد من الصيغة الصحيحة.\nالخطأ: {e}")

@app.on_message(filters.command("show_tasks"))
async def show_tasks_command(client: Client, message):
    tasks = load_json("tasks.json")
    if not tasks:
        await message.reply("📭 لا توجد مهام حالياً.")
    else:
        text = "📋 المهام:\n\n"
        for i, t in enumerate(tasks):
            text += (f"🔹 {i+1}. {t['task']}\n"
                     f"   الموعد: {t['deadline']}\n"
                     f"   المسؤول: {t['assigned_to']}\n"
                     "--------------------\n")
        await message.reply(text)

# ------------ وظيفة إرسال التذكيرات (تُشغل بواسطة Scheduler) ------------
async def send_reminders():
    tasks = load_json("tasks.json")
    today = datetime.now().date()
    
    # قائمة لتتبع التذكيرات التي تم إرسالها لهذا اليوم لتجنب التكرار
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
                if (t['task'], t['deadline'], days_left) not in reminded_tasks_today:
                    assigned_chat_id = t["chat_id"]
                    try:
                        await app.send_message(assigned_chat_id, message_text)
                        logger.info(f"Sent reminder for task '{t['task']}' to {t['assigned_to']} (chat_id: {assigned_chat_id})")
                        reminded_tasks_today.append((t['task'], t['deadline'], days_left))
                    except Exception as send_e:
                        logger.error(f"Failed to send message to {assigned_chat_id} for task '{t['task']}': {send_e}")
        except Exception as e:
            logger.error(f"Error processing reminder for task {t.get('task', 'N/A')}: {e}")

# ------------ وظيفة الجدولة (Scheduler) التي تعمل في Thread منفصلة ------------
def run_scheduler():
    """
    يقوم بتشغيل جدولة التذكيرات في حلقة منفصلة.
    """
    # جدولة التذكيرات لترسل في وقت معين كل يوم
    # يمكنك تغيير "14:35" إلى الوقت الذي تريده (مثال: "09:00" صباحاً)
    schedule_time = os.environ.get("REMINDER_TIME", "09:00") # قراءة وقت التذكير من متغير البيئة
    schedule.every().day.at(schedule_time).do(lambda: asyncio.create_task(send_reminders()))
    
    logger.info(f"Scheduler started. Reminders will be checked daily at {schedule_time}.")
    while True:
        schedule.run_pending()
        time.sleep(1) # تحقق كل ثانية (يمكن زيادتها لتقليل استهلاك CPU)

# ------------ وظيفة التشغيل الرئيسية للبوت على Render ------------
async def main_bot_runner():
    """
    تبدأ تشغيل البوت وتنتظر حتى يتم إيقافه.
    هذه الدالة هي نقطة الدخول الرئيسية للتشغيل المستمر على Render كـ Background Worker.
    """
    # ابدأ البوت
    await app.start()
    logger.info("✅ البوت يعمل وجاهز لاستقبال الأوامر.")

    # ابدأ جدولة التذكيرات في Thread منفصلة
    # هذا يضمن أن البوت يستقبل الأوامر بينما تعمل الجدولة في الخلفية
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True # يجعل الثريد تتوقف عند توقف البرنامج الرئيسي
    scheduler_thread.start()
    
    # idle() تجعل البوت يعمل حتى يتم إيقافه يدوياً أو بواسطة Render لإعادة النشر
    await idle() 
    
    # عند إيقاف البوت، يقوم بإنهاء الاتصال
    await app.stop()
    logger.info("البوت توقف.")

# هذا الجزء يضمن تشغيل دالة main_bot_runner عند بدء الملف بواسطة Render
if __name__ == "__main__":
    asyncio.run(main_bot_runner())

