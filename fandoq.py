import threading
import telebot
import json
import random
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from keep_alive import keep_alive

TOKEN = '8987719269:AAGXwnmftbLA0evqHvjd32A7ktkmFbA5Uz4'
bot = telebot.TeleBot(TOKEN)

def load_questions():
    with open('questions.json', 'r', encoding='utf-8') as f:
        return json.load(f)

QUESTIONS = load_questions()

def init_db():
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS groups
             (chat_id INTEGER PRIMARY KEY, current_question_index INTEGER, total_questions INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT score, current_q FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def update_user(user_id, score, current_q):
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, score, current_q) VALUES (?, ?, ?)", 
              (user_id, score, current_q))
    conn.commit()
    conn.close()

def send_question(chat_id):
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    
    current_idx = (row[0] + 1) if row else 1
    
    if current_idx > 10:
        finish_game(chat_id)
        return

    c.execute("INSERT OR REPLACE INTO groups (chat_id, current_question_index) VALUES (?, ?)", (chat_id, current_idx))
    conn.commit()
    conn.close()

    q_data = random.choice(QUESTIONS)
    markup = InlineKeyboardMarkup() # اضافه کردن این خط
    for i, option in enumerate(q_data['options']): # تعریف دکمه‌ها بر اساس سوال
        markup.add(InlineKeyboardButton(option, callback_data=f"ans_{i}_{q_data['answer']}"))

    # 👇 این همون خطیه که جا انداختی! حتماً باید باشه تا سوال فرستاده بشه
    msg = bot.send_message(chat_id, f"❓ سوال {current_idx} از ۱۰:\n{q_data['question']}", reply_markup=markup)

    threading.Timer(15, timeout_handler, args=[chat_id, msg.message_id]).start()

def timeout_handler(chat_id, message_id):
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    if c.fetchone():
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        bot.send_message(chat_id, "⏰ زمان تمام شد! سوال بعدی...")
        send_question(chat_id)
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def handle_answer(call):
    parts = call.data.split('_')
    selected = int(parts[1])
    correct = int(parts[2])
    
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    
    if selected == correct:
        conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO scores (chat_id, user_id, name, score) VALUES (?, ?, ?, COALESCE((SELECT score FROM scores WHERE chat_id=? AND user_id=?), 0) + 10)", 
                  (chat_id, user_id, user_name, chat_id, user_id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ درست بود! ۱۰ امتیاز گرفتی.")
    else:
        bot.answer_callback_query(call.id, "❌ غلط بود!")
    
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    send_question(chat_id)

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type in ['group', 'supergroup']:
        # پیامِ مخصوصِ گروه
        text = "سلام! من فندق هستم 🎮\nبرای شروع بازی کوئیز کافیست دستور /quiz را بفرستید."
        bot.reply_to(message, text)
    else:
        bot_username = "FandoqQuizBot" # آیدی رباتت را اینجا بنویس
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

@bot.message_handler(commands=['rank'])
def show_rank(message):
    chat_id = message.chat.id
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
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

def finish_game(chat_id):
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT name, score FROM scores WHERE chat_id=? ORDER BY score DESC LIMIT 1", (chat_id,))
    winner = c.fetchone()
    if winner:
        text = f"🏆 بازی به پایان رسید!\n\n👑 قهرمان: {winner[0]} با {winner[1]} امتیاز"
    else:
        text = "🏁 بازی تمام شد!"
    bot.send_message(chat_id, text)
    c.execute("DELETE FROM scores WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM groups WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

bot.remove_webhook()

keep_alive()
bot.infinity_polling()
