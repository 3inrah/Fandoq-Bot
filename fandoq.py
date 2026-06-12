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
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS groups 
                 (chat_id INTEGER PRIMARY KEY, current_question_index INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
                 (chat_id INTEGER, user_id INTEGER, name TEXT, score INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def send_question(chat_id):
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute("SELECT current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    current_idx = (row[0] + 1) if row else 1
    
    if current_idx > 10:
        finish_game(chat_id)
        conn.close()
        return

    c.execute("INSERT OR REPLACE INTO groups (chat_id, current_question_index) VALUES (?, ?)", (chat_id, current_idx))
    conn.commit()
    conn.close()

    q_data = random.choice(QUESTIONS)
    markup = InlineKeyboardMarkup()
    for i, option in enumerate(q_data['options']):
        markup.add(InlineKeyboardButton(option, callback_data=f"ans_{i}_{q_data['answer']}"))
    
    msg = bot.send_message(chat_id, f"❓ سوال {current_idx} از ۱۰:\n{q_data['question']}", reply_markup=markup)
    threading.Timer(15, timeout_handler, args=[chat_id, msg.message_id]).start()

def timeout_handler(chat_id, message_id):
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute("SELECT current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    if c.fetchone():
        try:
            bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
            bot.send_message(chat_id, "⏰ زمان تمام شد! سوال بعدی...")
            send_question(chat_id)
        except: pass
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def handle_answer(call):
    parts = call.data.split('_')
    selected, correct = int(parts[1]), int(parts[2])
    if selected == correct:
        conn = sqlite3.connect('quiz_bot.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO scores (chat_id, user_id, name, score) VALUES (?, ?, ?, COALESCE((SELECT score FROM scores WHERE chat_id=? AND user_id=?), 0) + 10)", 
                  (call.message.chat.id, call.from_user.id, call.from_user.first_name, call.message.chat.id, call.from_user.id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ درست بود! ۱۰ امتیاز.")
    else:
        bot.answer_callback_query(call.id, "❌ غلط بود!")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    send_question(call.message.chat.id)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type in ['group', 'supergroup']:
        bot.reply_to(message, "سلام! برای شروع بازی از /quiz استفاده کنید.")
    else:
        bot.reply_to(message, "فقط در گروه‌ها کار می‌کنم!")

@bot.message_handler(commands=['quiz'])
def start_game(message):
    if message.chat.type in ['group', 'supergroup']:
        send_question(message.chat.id)

@bot.message_handler(commands=['rank'])
def show_rank(message):
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute("SELECT name, score FROM scores WHERE chat_id=? ORDER BY score DESC LIMIT 5", (message.chat.id,))
    results = c.fetchall()
    conn.close()
    if not results:
        bot.reply_to(message, "هنوز امتیازی ثبت نشده!")
        return
    text = "🏆 رده‌بندی:\n" + "\n".join([f"{i}. {name}: {score}" for i, (name, score) in enumerate(results, 1)])
    bot.reply_to(message, text)

def finish_game(chat_id):
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute("SELECT name, score FROM scores WHERE chat_id=? ORDER BY score DESC LIMIT 1", (chat_id,))
    winner = c.fetchone()
    text = f"🏆 بازی تمام شد!\n👑 قهرمان: {winner[0]} با {winner[1]} امتیاز" if winner else "🏁 بازی تمام شد!"
    bot.send_message(chat_id, text)
    c.execute("DELETE FROM scores WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM groups WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

keep_alive()
bot.infinity_polling()
