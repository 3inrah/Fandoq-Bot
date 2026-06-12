import telebot
import json
import random
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from keep_alive import keep_alive

TOKEN = '8987719269:AAGXwnmftbLA0evqHvjd32A7ktkmFbA5Uz4'
bot = telebot.TeleBot(TOKEN)

# ==========================================
# ۱. بارگذاری سوالات از فایل JSON
# ==========================================
def load_questions():
    with open('questions.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# لود کردن سوالات در حافظه (یکبار برای همیشه)
QUESTIONS = load_questions()

# ==========================================
# ۲. تنظیمات دیتابیس
# ==========================================
def init_db():
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    # جدول کاربران و امتیازات گروهی
    c.execute('''CREATE TABLE IF NOT EXISTS scores
                 (chat_id INTEGER, user_id INTEGER, name TEXT, score INTEGER, 
                  PRIMARY KEY (chat_id, user_id))''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute("SELECT score, current_q FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def update_user(user_id, score, current_q):
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, score, current_q) VALUES (?, ?, ?)", 
              (user_id, score, current_q))
    conn.commit()
    conn.close()

# ==========================================
# ۳. منطق ارسال سوال
# ==========================================

def send_question(user_id, message_id=None):
    q_data = random.choice(QUESTIONS)
    
    markup = InlineKeyboardMarkup()
    buttons = []
    
    # اینجا شماره سوال صحیح را به عنوان یک "کلید" در داده‌های دکمه قرار می‌دهیم
    # فرمت جدید: ans_گزینه_ایندکس_سوال_درست
    correct_idx = q_data["correct"]
    
    for i, option in enumerate(q_data["options"]):
        # به دکمه می‌گوییم: اگر روی من کلیک شد، بگو گزینه i انتخاب شده و جواب درست گزینه correct_idx است
        callback_data = f"ans_{i}_{correct_idx}"
        buttons.append(InlineKeyboardButton(option, callback_data=callback_data))
    
    markup.add(buttons[0], buttons[1])
    markup.add(buttons[2], buttons[3])
    
    text = f"❓ سوال:\n{q_data['question']}"
    
    if message_id:
        bot.edit_message_text(text, user_id, message_id, reply_markup=markup)
    else:
        bot.send_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def handle_answer(call):
    # ۱. پردازش جواب
    parts = call.data.split('_')
    selected = int(parts[1])
    correct = int(parts[2])
    
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    
    if selected == correct:
        # ثبت یا آپدیت امتیاز در جدول scores
        conn = sqlite3.connect('quiz_bot.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO scores (chat_id, user_id, name, score) VALUES (?, ?, ?, COALESCE((SELECT score FROM scores WHERE chat_id=? AND user_id=?), 0) + 10)", 
                  (chat_id, user_id, user_name, chat_id, user_id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ درست بود! ۱۰ امتیاز گرفتی.")
    else:
        bot.answer_callback_query(call.id, "❌ غلط بود!")
    
    # ۲. حذف دکمه‌ها و فرستادن سوال بعدی (فقط برای آن گروه)
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    send_question(chat_id)

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # بررسی می‌کنیم که آیا پیام در گروه است یا پی‌وی
    if message.chat.type in ['group', 'supergroup']:
        # پیامِ مخصوصِ گروه
        text = "سلام! من فندق هستم 🎮\nبرای شروع بازی کوئیز کافیست دستور /quiz را بفرستید."
        bot.reply_to(message, text)
    else:
        # پیامِ مخصوصِ پی‌وی (با همان دکمه‌ی افزودن به گروه)
        bot_username = "YOUR_BOT_USERNAME" # آیدی رباتت را اینجا بنویس
        add_link = f"https://t.me/{bot_username}?startgroup=true"
        
        markup = InlineKeyboardMarkup()
        add_button = InlineKeyboardButton("➕ افزودن به گروه", url=add_link)
        markup.add(add_button)
        
        text = (
            "سلام! به ربات کوئیز فندق خوش آمدی 🎮\n\n"
            "این ربات برای بازی‌های گروهی طراحی شده است.\n"
            "برای شروع، من را به گروه خود اضافه کنید."
        )
        bot.reply_to(message, text, reply_markup=markup)
    
@bot.message_handler(commands=['quiz']) 
def start_game(message):
    if message.chat.type in ['group', 'supergroup']:
        send_question(message.chat.id)
    else:
        bot.reply_to(message, "من فقط در گروه‌ها بازی می‌کنم! برای افزودن به گروه از /start استفاده کن.")

# تابع رده‌بندی گروهی که اضافه کردیم:
@bot.message_handler(commands=['rank'])
def show_rank(message):
    chat_id = message.chat.id
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute("SELECT name, score FROM scores WHERE chat_id=? ORDER BY score DESC LIMIT 5", (chat_id,))
    results = c.fetchall()
    conn.close()
    
    if not results:
        bot.reply_to(message, "هنوز امتیازی در این گروه ثبت نشده است!")
        return
        
    text = "🏆 رده‌بندی ۵ نفر برتر این گروه:\n\n"
    for rank, (name, score) in enumerate(results, 1):
        text += f"{rank}. {name}: {score} امتیاز\n"
    bot.reply_to(message, text)

keep_alive()
bot.infinity_polling()
