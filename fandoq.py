import threading
import telebot
import json
import random
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# تنظیمات سرور برای Render
app = Flask('')
@app.route('/')
def home():
    return "Bot is Alive!"

def run_server():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run_server)
    t.start()

TOKEN = '8987719269:AAGwq_58KYATo9n6AYjIElYGwYUUd3b0Tso'
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
    # این جدول رو اضافه کردم چون تو دیتابیست برای ثبت امتیازها جا افتاده بود
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
             (chat_id INTEGER, user_id INTEGER, name TEXT, score INTEGER)''')
    # این همون جدول جدید برای لیست افرادیه که دکمه "من هستم" رو میزنن
    c.execute('''CREATE TABLE IF NOT EXISTS lobby 
             (chat_id INTEGER, user_id INTEGER, name TEXT)''')
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
        markup.add(InlineKeyboardButton(option, callback_data=f"ans_{i}_{q_data['correct']}"))

    # 👇 این همون خطیه که جا انداختی! حتماً باید باشه تا سوال فرستاده بشه
    msg = bot.send_message(chat_id, f"❓ سوال {current_idx} از ۱۰:\n{q_data['question']}", reply_markup=markup)

@bot.message_handler(commands=['quiz']) 
def start_game(message):
    if message.chat.type in ['group', 'supergroup']:
        chat_id = message.chat.id
        host_id = message.from_user.id
        host_name = message.from_user.first_name
        
        # اتصال به دیتابیس برای ثبت بازیکنان
        conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
        c = conn.cursor()
        
        # پاک کردن لیست قبلی گروه تا بازی جدید تر و تمیز شروع بشه
        c.execute("DELETE FROM lobby WHERE chat_id=?", (chat_id,))
        # ثبت‌نام خودکارِ کسی که مسابقه رو ساخته
        c.execute("INSERT INTO lobby (chat_id, user_id, name) VALUES (?, ?, ?)", (chat_id, host_id, host_name))
        conn.commit()
        conn.close()
        
        # ساختن متن و دکمه‌های شیشه‌ای
        text = f"🎮 فراخوان بازی کوئیز فندق!\n\nکسانی که آماده هستن روی دکمه زیر کلیک کنن.\n\n👥 بازیکنان:\n۱. {host_name}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✋ من هستم!", callback_data="join_lobby"))
        # آیدی سازنده رو تو دکمه مخفی می‌کنیم تا فقط خودش بتونه بازی رو استارت بزنه
        markup.add(InlineKeyboardButton("🚀 شروع مسابقه", callback_data=f"start_lobby_{host_id}"))
        
        bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.reply_to(message, "من فقط در گروه‌ها بازی می‌کنم! برای افزودن به گروه از /start استفاده کن.")

@bot.callback_query_handler(func=lambda call: call.data == 'join_lobby' or call.data.startswith('start_lobby_'))
def lobby_actions(call):
    chat_id = call.message.chat.id
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
    c = conn.cursor()
    
    if call.data == 'join_lobby':
        user_id = call.from_user.id
        c.execute("SELECT * FROM lobby WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        if c.fetchone():
            bot.answer_callback_query(call.id, "تو که تو لیست هستی شیطون! 😄")
        else:
            c.execute("INSERT INTO lobby (chat_id, user_id, name) VALUES (?, ?, ?)", (chat_id, user_id, call.from_user.first_name))
            conn.commit()
            c.execute("SELECT name FROM lobby WHERE chat_id=?", (chat_id,))
            players = c.fetchall()
            text = "🎮 فراخوان بازی کوئیز فندق!\n\nکسانی که آماده هستن روی دکمه زیر کلیک کنن.\n\n👥 بازیکنان:\n"
            for i, p in enumerate(players, 1):
                text += f"{i}. {p[0]}\n"
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=call.message.reply_markup)
            bot.answer_callback_query(call.id, "به مسابقه اضافه شدی! ✅")
            
    elif call.data.startswith('start_lobby_'):
        host_id = int(call.data.split('_')[2])
        if call.from_user.id != host_id:
            bot.answer_callback_query(call.id, "❌ فقط کسی که بازی رو ساخته می‌تونه شروعش کنه!", show_alert=True)
        else:
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            bot.edit_message_text("🚀 بزن بریم! مسابقه شروع شد...", chat_id, call.message.message_id)
            send_question(chat_id)
            
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def handle_answer(call):
    parts = call.data.split('_')
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_id = call.from_user.id
    
    # اتصال دیتابیس (تو کد قبلیت جا افتاده بود)
    conn = sqlite3.connect('quiz_bot.db', check_same_thread=False)
    c = conn.cursor()

    # 👇 قفل اول: چک می‌کنیم آیا کاربر دکمه "من هستم" رو زده بوده یا نه
    c.execute("SELECT * FROM lobby WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    if not c.fetchone():
        bot.answer_callback_query(call.id, "⛔️ شما تو این دور از مسابقه ثبت‌نام نکردی! فقط می‌تونی تماشاچی باشی.", show_alert=True)
        conn.close()
        return

    # 👇 قفل دوم: پاک کردن سریع دکمه‌ها تا بقیه نتونن بزنن
    try:
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
    except:
        bot.answer_callback_query(call.id, "یه نفر دیگه زودتر جواب داد! 🏃‍♂️")
        conn.close()
        return

  # بررسی درست یا غلط بودن جواب
    if int(parts[1]) == int(parts[2]):
        # گرفتن امتیاز فعلی کاربر از دیتابیس
        c.execute("SELECT score FROM scores WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = c.fetchone()
        
        if row:
            # اگه قبلاً امتیاز گرفته، ۱۰ تا به امتیاز قبلیش اضافه کن
            new_score = row[0] + 10
            c.execute("UPDATE scores SET score=? WHERE chat_id=? AND user_id=?", (new_score, chat_id, user_id))
        else:
            # اگه اولین بارشه که تو این دور درست جواب میده، همون ۱۰ رو ثبت کن
            c.execute("INSERT INTO scores (chat_id, user_id, name, score) VALUES (?, ?, ?, 10)", (chat_id, user_id, call.from_user.first_name))
            
        conn.commit()
        bot.answer_callback_query(call.id, "✅ ایول! درست بود.")
        bot.send_message(chat_id, f"🎉 {call.from_user.first_name} زودتر از همه جواب درست رو داد (+۱۰ امتیاز)")
    else:
        bot.answer_callback_query(call.id, "❌ غلط بود!")
        bot.send_message(chat_id, f"❌ {call.from_user.first_name} جواب رو اشتباه داد! بریم سوال بعدی...")
    
    conn.close()
    
    # رفتن بلافاصله به سوال بعدی
    send_question(chat_id)

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
