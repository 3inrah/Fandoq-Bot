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
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, score INTEGER, current_q INTEGER)''')
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
    # انتخاب یک سوال کاملا رندوم از لیست QUESTIONS
    q_data = random.choice(QUESTIONS)
    
    markup = InlineKeyboardMarkup()
    buttons = []
    # پیدا کردن ایندکس جواب درست برای callback
    correct_idx = q_data["correct"]
    
    for i, option in enumerate(q_data["options"]):
        is_correct = "" if i == q_data["correct"] else "0"
        callback_data = f"ans_{is_correct}"
        buttons.append(InlineKeyboardButton(option, callback_data=callback_data))
    
    markup.add(buttons[0], buttons[1])
    markup.add(buttons[2], buttons[3])
    
    text = f"❓ سوال:\n{q_data['question']}"
    
    if message_id:
        bot.edit_message_text(text, user_id, message_id, reply_markup=markup)
    else:
        bot.send_message(user_id, text, reply_markup=markup)

# ==========================================
# ۴. پردازش جواب کاربر
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def handle_answer(call):
    # دریافت وضعیت از دکمه (ans_1 یعنی درست، ans_0 یعنی غلط)
    is_correct = call.data.split('_')[1]
    
    if is_correct == "1":
        bot.answer_callback_query(call.id, "✅ آفرین! درست بود.")
        # اینجا امتیاز را هم اضافه کن (update_user)
    else:
        bot.answer_callback_query(call.id, "❌ اشتباه بود!")
    
    # بعد از پاسخ، دکمه‌ها را حذف کن تا کاربر دوباره کلیک نکند
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    
    # ارسال سوال بعدی
    send_question(call.message.chat.id)

@bot.message_handler(commands=['start', 'quiz'])
def start_game(message):
    send_question(message.chat.id)

keep_alive()
bot.infinity_polling()
