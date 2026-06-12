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
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS groups
             (chat_id INTEGER PRIMARY KEY, current_question_index INTEGER, lobby_msg_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
             (chat_id INTEGER, user_id INTEGER, name TEXT, score INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS lobby 
             (chat_id INTEGER, user_id INTEGER, name TEXT)''')
    # دو جدول جدید برای ثبت جواب‌ها و پیام‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS round_answers 
             (chat_id INTEGER, user_id INTEGER, q_index INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS q_messages 
             (chat_id INTEGER, message_id INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def update_scoreboard(chat_id):
    """این تابع جدول امتیازات زنده رو توی پیام اول آپدیت میکنه"""
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT lobby_msg_id FROM groups WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    if not row or not row[0]:
        conn.close()
        return
        
    lobby_msg_id = row[0]
    
    # گرفتن لیست همه بازیکنان و امتیازاتشون
    c.execute('''
        SELECT lobby.name, COALESCE(scores.score, 0) as score 
        FROM lobby 
        LEFT JOIN scores ON lobby.chat_id = scores.chat_id AND lobby.user_id = scores.user_id 
        WHERE lobby.chat_id=? 
        ORDER BY score DESC
    ''', (chat_id,))
    players = c.fetchall()
    conn.close()
    
    text = "🏆 جدول زنده امتیازات:\n\n"
    for i, p in enumerate(players, 1):
        text += f"{i}. {p[0]}: {p[1]} امتیاز\n"
        
    try:
        # آپدیت کردن همون پیام اولیه
        bot.edit_message_text(text, chat_id, lobby_msg_id)
    except:
        pass # اگر تغییری نکرده باشه تلگرام ارور میده که نادیده می‌گیریم

def get_user(user_id):
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT score, current_q FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def update_user(user_id, score, current_q):
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, score, current_q) VALUES (?, ?, ?)", 
              (user_id, score, current_q))
    conn.commit()
    conn.close()

def timeout_handler(chat_id, message_id, q_index):
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    conn.close()
    
    # چک می‌کنیم اگر بعد از ۱۵ ثانیه هنوز روی همین سوال بودیم، یعنی زمان تموم شده
    if row and row[0] == q_index:
        try: 
            bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) 
        except: 
            pass
        send_question(chat_id)

def send_question(chat_id):
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    
    current_idx = (row[0] + 1) if row else 1
    
    if current_idx > 10:
        conn.close()
        finish_game(chat_id)
        return

    c.execute("INSERT OR REPLACE INTO groups (chat_id, current_question_index, lobby_msg_id) VALUES (?, ?, COALESCE((SELECT lobby_msg_id FROM groups WHERE chat_id=?), 0))", (chat_id, current_idx, chat_id))
    conn.commit()

    q_data = random.choice(QUESTIONS)
    markup = InlineKeyboardMarkup() 
    for i, option in enumerate(q_data['options']): 
        markup.add(InlineKeyboardButton(option, callback_data=f"ans_{i}_{q_data['correct']}"))

    msg = bot.send_message(chat_id, f"❓ سوال {current_idx} از ۱۰:\n{q_data['question']}", reply_markup=markup)
    
    # ذخیره آیدی پیامِ سوال تا آخر بازی بتونیم پاکش کنیم
    c.execute("INSERT INTO q_messages (chat_id, message_id) VALUES (?, ?)", (chat_id, msg.message_id))
    conn.commit()
    conn.close()

    # روشن کردن تایمر ۱۵ ثانیه‌ای برای این سوال
    threading.Timer(15.0, timeout_handler, args=[chat_id, msg.message_id, current_idx]).start()

@bot.message_handler(commands=['quiz']) 
def start_game(message):
    if message.chat.type in ['group', 'supergroup']:
        chat_id = message.chat.id
        host_id = message.from_user.id
        host_name = message.from_user.first_name
        
        # اتصال به دیتابیس برای ثبت بازیکنان
        conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
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
        if call.from_user.id != host_id:
            bot.answer_callback_query(call.id, "❌ فقط کسی که بازی رو ساخته می‌تونه شروعش کنه!", show_alert=True)
        else:
            # ذخیره آیدی پیام فراخوان برای جدول امتیازات زنده
            c.execute("INSERT OR REPLACE INTO groups (chat_id, current_question_index, lobby_msg_id) VALUES (?, 0, ?)", (chat_id, call.message.message_id))
            conn.commit()
            
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            update_scoreboard(chat_id)
            send_question(chat_id)
            
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def handle_answer(call):
    parts = call.data.split('_')
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_id = call.from_user.id
    
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()

    # ۱. آیا ثبت نام کرده؟
    c.execute("SELECT * FROM lobby WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    if not c.fetchone():
        bot.answer_callback_query(call.id, "⛔️ شما تو بازی ثبت‌نام نکردی! تماشاچی باش.", show_alert=True)
        conn.close()
        return

    c.execute("SELECT current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    current_q_idx_row = c.fetchone()
    if not current_q_idx_row:
        conn.close()
        return
    current_q_idx = current_q_idx_row[0]

    # ۲. آیا قبلاً به این سوال جواب داده؟
    c.execute("SELECT * FROM round_answers WHERE chat_id=? AND user_id=? AND q_index=?", (chat_id, user_id, current_q_idx))
    if c.fetchone():
        bot.answer_callback_query(call.id, "قبلاً جواب دادی! ⏳ صبر کن بقیه هم جواب بدن.")
        conn.close()
        return

    # ۳. ثبت اینکه این شخص به این سوال جواب داد
    c.execute("INSERT INTO round_answers (chat_id, user_id, q_index) VALUES (?, ?, ?)", (chat_id, user_id, current_q_idx))

    # ۴. بررسی جواب و نمایش پیام مخفی (فقط برای خود شخص)
    if int(parts[1]) == int(parts[2]):
        bot.answer_callback_query(call.id, "✅ آفرین! درست بود (+۱۰ امتیاز)")
        c.execute("SELECT score FROM scores WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = c.fetchone()
        if row:
            c.execute("UPDATE scores SET score=? WHERE chat_id=? AND user_id=?", (row[0] + 10, chat_id, user_id))
        else:
            c.execute("INSERT INTO scores (chat_id, user_id, name, score) VALUES (?, ?, ?, 10)", (chat_id, user_id, call.from_user.first_name))
    else:
        bot.answer_callback_query(call.id, "❌ متاسفانه غلط بود!")

    conn.commit()
    
    # ۵. آپدیت جدول امتیازات زنده در پیام اول
    update_scoreboard(chat_id)

    # ۶. بررسی اینکه آیا همه افراد لیست جواب داده‌اند؟
    c.execute("SELECT COUNT(*) FROM lobby WHERE chat_id=?", (chat_id,))
    total_players = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM round_answers WHERE chat_id=? AND q_index=?", (chat_id, current_q_idx))
    answered_players = c.fetchone()[0]

    if answered_players >= total_players:
        # اگر همه جواب داده باشند، دکمه‌های این سوال پاک می‌شود و بلافاصله می‌رود سوال بعدی
        try: 
            bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) 
        except: 
            pass
        conn.close()
        send_question(chat_id)
    else:
        conn.close()

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
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
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
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    
    # ۱. پاک کردن تمام پیام‌های سوالات از گروه تا گروه شلوغ نشود
    c.execute("SELECT message_id FROM q_messages WHERE chat_id=?", (chat_id,))
    for row in c.fetchall():
        try:
            bot.delete_message(chat_id, row[0])
        except:
            pass
            
    # ۲. گرفتن لیست نهایی بازیکنان و محاسبه رتبه‌ها
    c.execute("SELECT lobby_msg_id FROM groups WHERE chat_id=?", (chat_id,))
    lobby_row = c.fetchone()
    
    c.execute('''
        SELECT lobby.name, COALESCE(scores.score, 0) as score 
        FROM lobby 
        LEFT JOIN scores ON lobby.chat_id = scores.chat_id AND lobby.user_id = scores.user_id 
        WHERE lobby.chat_id=? 
        ORDER BY score DESC
    ''', (chat_id,))
    players = c.fetchall()
    
    # ساخت متن نهایی برای معرفی قهرمان‌ها
    text = "🏁 مسابقه به پایان رسید! جدول نهایی قهرمانان:\n\n"
    for i, p in enumerate(players, 1):
        if i == 1:
            text += f"🥇 {p[0]}: {p[1]} امتیاز\n"
        elif i == 2:
            text += f"🥈 {p[0]}: {p[1]} امتیاز\n"
        elif i == 3:
            text += f"🥉 {p[0]}: {p[1]} امتیاز\n"
        else:
            text += f"🔹 {p[0]}: {p[1]} امتیاز\n"
            
    # ویرایش همان پیام اول برای نمایش برندگان
    if lobby_row and lobby_row[0]:
        try:
            bot.edit_message_text(text, chat_id, lobby_row[0])
        except:
            bot.send_message(chat_id, text)
            
    # ۳. پاکسازی نهایی دیتابیس برای اینکه در بازی‌های بعدی مشکلی پیش نیاید
    c.execute("DELETE FROM scores WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM groups WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM lobby WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM round_answers WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM q_messages WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

bot.remove_webhook()

keep_alive()
bot.infinity_polling()
