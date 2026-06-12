import threading
import telebot
import json
import random
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

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
    c.execute('''CREATE TABLE IF NOT EXISTS round_answers_v2 
             (chat_id INTEGER, user_id INTEGER, q_index INTEGER, is_correct INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS q_messages 
             (chat_id INTEGER, message_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS asked_questions 
             (chat_id INTEGER, q_index INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def update_scoreboard(chat_id):
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT lobby_msg_id, current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    if not row or not row[0]:
        conn.close()
        return
        
    lobby_msg_id = row[0]
    current_q = row[1]
    
    c.execute('''
        SELECT lobby.user_id, lobby.name, COALESCE(scores.score, 0) as score 
        FROM lobby 
        LEFT JOIN scores ON lobby.chat_id = scores.chat_id AND lobby.user_id = scores.user_id 
        WHERE lobby.chat_id=? 
        ORDER BY score DESC
    ''', (chat_id,))
    players = c.fetchall()
    
    text = "🏆 <b>جدول زنده امتیازات:</b>\n➖➖➖➖➖➖➖➖\n"
    for i, p in enumerate(players, 1):
        user_id = p[0]
        name = p[1]
        score = p[2]
        
        c.execute("SELECT q_index, is_correct FROM round_answers_v2 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        answers = {r[0]: r[1] for r in c.fetchall()}
        
        bar = ""
        for q in range(1, 11): 
            if q in answers:
                bar += "🟩" if answers[q] == 1 else "🟥"
            elif q < current_q:
                bar += "⬜️" 
            else:
                bar += "⬜️" 
                
        text += f"\u200F<b>{i}.</b> {name}: <code>{score}</code> امتیاز\n\u200F{bar}\n\n"
        
    try:
        bot.edit_message_text(text, chat_id, lobby_msg_id, parse_mode='HTML')
    except:
        pass
    conn.close()
        
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
    
    if row and row[0] == q_index:
        c.execute("UPDATE q_messages SET message_id = -message_id WHERE chat_id=? AND message_id=?", (chat_id, message_id))
        if c.rowcount > 0:
            conn.commit()
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) 
            except: pass
            send_question(chat_id)
            
    conn.close()

def send_question(chat_id):
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()

    # اینجا با دستور abs() علامت منفی قفل رو برمی‌داریم تا پیام بتونه پاک بشه
    c.execute("SELECT message_id FROM q_messages WHERE chat_id=?", (chat_id,))
    for row in c.fetchall():
        try:
            bot.delete_message(chat_id, abs(row[0]))
        except:
            pass
    c.execute("DELETE FROM q_messages WHERE chat_id=?", (chat_id,))
    conn.commit()

    c.execute("SELECT current_question_index FROM groups WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    current_idx = row[0] if row else 0
    new_idx = current_idx + 1
    
    if new_idx > 10:
        conn.close()
        finish_game(chat_id)
        return

    c.execute("UPDATE groups SET current_question_index=? WHERE chat_id=?", (new_idx, chat_id))
    conn.commit()

    c.execute("SELECT q_index FROM asked_questions WHERE chat_id=?", (chat_id,))
    asked_indices = set(row[0] for row in c.fetchall())
    
    all_indices = set(range(len(QUESTIONS)))
    available_indices = list(all_indices - asked_indices)
    
    if not available_indices:
        c.execute("DELETE FROM asked_questions WHERE chat_id=?", (chat_id,))
        conn.commit()
        available_indices = list(all_indices)
    
    chosen_index = random.choice(available_indices)
    q_data = QUESTIONS[chosen_index]
    
    c.execute("INSERT INTO asked_questions (chat_id, q_index) VALUES (?, ?)", (chat_id, chosen_index))
    conn.commit()

    markup = InlineKeyboardMarkup(row_width=2) 
    buttons = []
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, option in enumerate(q_data['options']): 
        btn_text = f"{emojis[i]} {option}" if i < len(emojis) else option
        buttons.append(InlineKeyboardButton(btn_text, callback_data=f"ans_{i}_{q_data['correct']}"))
    markup.add(*buttons)

    persian_idx = str(new_idx).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
    text = f"❓ <b>سوال {persian_idx} از ۱۰</b>\n➖➖➖➖➖➖➖➖\n<i>{q_data['question']}</i>"
    
    msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
    
    c.execute("INSERT INTO q_messages (chat_id, message_id) VALUES (?, ?)", (chat_id, msg.message_id))
    conn.commit()
    conn.close()

    threading.Timer(15.0, timeout_handler, args=[chat_id, msg.message_id, new_idx]).start()

@bot.message_handler(commands=['quiz']) 
def start_game(message):
    if message.chat.type in ['group', 'supergroup']:
        chat_id = message.chat.id
        host_id = message.from_user.id
        host_name = message.from_user.first_name
        
        conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
        c = conn.cursor()
        
        c.execute("DELETE FROM lobby WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM scores WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM groups WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM round_answers_v2 WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM q_messages WHERE chat_id=?", (chat_id,))
        
        c.execute("INSERT INTO lobby (chat_id, user_id, name) VALUES (?, ?, ?)", (chat_id, host_id, host_name))
        conn.commit()
        conn.close()
        
        text = f"🎮 <b>فراخوان بازی کوئیز فندق!</b>\n\nکسانی که آماده هستن روی دکمه زیر کلیک کنن.\n➖➖➖➖➖➖➖➖\n👥 <b>بازیکنان:</b>\n<b>۱.</b> {host_name}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✋ من هستم!", callback_data="join_lobby"))
        markup.add(InlineKeyboardButton("🚀 شروع مسابقه", callback_data=f"start_lobby_{host_id}"))
        
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
    else:
        bot.reply_to(message, "من فقط در گروه‌ها بازی می‌کنم! برای افزودن به گروه از /start استفاده کن.")

@bot.callback_query_handler(func=lambda call: call.data == 'join_lobby' or call.data.startswith('start_lobby_'))
def lobby_actions(call):
    chat_id = call.message.chat.id
    
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    
    if call.data == 'join_lobby':
        user_id = call.from_user.id
        try:
            c.execute("SELECT * FROM lobby WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            if c.fetchone():
                bot.answer_callback_query(call.id, "تو که تو لیست هستی شیطون! 😄")
            else:
                c.execute("INSERT INTO lobby (chat_id, user_id, name) VALUES (?, ?, ?)", (chat_id, user_id, call.from_user.first_name))
                conn.commit()
                
                c.execute("SELECT name FROM lobby WHERE chat_id=?", (chat_id,))
                players = c.fetchall()
                text = "🎮 <b>فراخوان بازی کوئیز فندق!</b>\n\nکسانی که آماده هستن روی دکمه زیر کلیک کنن.\n➖➖➖➖➖➖➖➖\n👥 <b>بازیکنان:</b>\n"
                for i, p in enumerate(players, 1):
                    text += f"<b>{i}.</b> {p[0]}\n"
                
                try:
                    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=call.message.reply_markup, parse_mode='HTML')
                except:
                    pass
                    
                bot.answer_callback_query(call.id, "به مسابقه اضافه شدی! ✅")
        except Exception as e:
            bot.answer_callback_query(call.id, "⛔️ یه مشکلی تو دیتابیس پیش اومد!")
            
    elif call.data.startswith('start_lobby_'):
        host_id = int(call.data.split('_')[2])
        if call.from_user.id != host_id:
            bot.answer_callback_query(call.id, "❌ فقط کسی که بازی رو ساخته می‌تونه شروعش کنه!", show_alert=True)
        else:
            c.execute("INSERT OR REPLACE INTO groups (chat_id, current_question_index, lobby_msg_id) VALUES (?, 0, ?)", (chat_id, call.message.message_id))
            conn.commit()
            
            try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None) 
            except: pass
            
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

    c.execute("SELECT * FROM round_answers_v2 WHERE chat_id=? AND user_id=? AND q_index=?", (chat_id, user_id, current_q_idx))
    if c.fetchone():
        bot.answer_callback_query(call.id, "قبلاً جواب دادی! ⏳ صبر کن بقیه هم جواب بدن.")
        conn.close()
        return

    is_correct = 1 if int(parts[1]) == int(parts[2]) else 0
    c.execute("INSERT INTO round_answers_v2 (chat_id, user_id, q_index, is_correct) VALUES (?, ?, ?, ?)", (chat_id, user_id, current_q_idx, is_correct))

    if is_correct:
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
    update_scoreboard(chat_id)

    c.execute("SELECT COUNT(*) FROM lobby WHERE chat_id=?", (chat_id,))
    total_players = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM round_answers_v2 WHERE chat_id=? AND q_index=?", (chat_id, current_q_idx))
    answered_players = c.fetchone()[0]

    if answered_players >= total_players:
        c.execute("UPDATE q_messages SET message_id = -message_id WHERE chat_id=? AND message_id=?", (chat_id, message_id))
        if c.rowcount == 0:
            conn.close()
            return
        conn.commit()
        
        try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) 
        except: pass
        conn.close()
        send_question(chat_id)
    else:
        conn.close()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type in ['group', 'supergroup']:
        text = "سلام! من <b>فندق</b> هستم 🎮\nبرای شروع مسابقه کافیست دستور /quiz را بفرستید."
        bot.reply_to(message, text, parse_mode='HTML')
    else:
        bot_username = bot.get_me().username
        add_link = f"https://t.me/{bot_username}?startgroup=true"
        
        markup = InlineKeyboardMarkup()
        add_button = InlineKeyboardButton("➕ افزودن به گروه", url=add_link)
        markup.add(add_button)
        
        text = (
            "سلام! به ربات <b>کوئیز فندق</b> خوش آمدی 🎮\n➖➖➖➖➖➖➖➖\n"
            "این ربات برای بازی‌های گروهی و رقابتی طراحی شده است.\n"
            "برای شروع، من را به گروه خود اضافه کنید."
        )
        bot.reply_to(message, text, reply_markup=markup, parse_mode='HTML')

@bot.message_handler(commands=['rank'])
def show_rank(message):
    chat_id = message.chat.id
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT name, score FROM scores WHERE chat_id=? ORDER BY score DESC LIMIT 5", (chat_id,))
    results = c.fetchall()
    conn.close()
    
    if not results:
        bot.reply_to(message, "هنوز امتیازی در این گروه ثبت نشده است! 🤷‍♂️")
        return
        
    text = "🏆 <b>رده‌بندی ۵ نفر برتر این گروه:</b>\n➖➖➖➖➖➖➖➖\n"
    for rank, (name, score) in enumerate(results, 1):
        text += f"<b>{rank}.</b> {name}: <code>{score}</code> امتیاز\n"
    bot.reply_to(message, text, parse_mode='HTML')

def finish_game(chat_id):
    conn = sqlite3.connect('quiz_bot2.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute("SELECT message_id FROM q_messages WHERE chat_id=?", (chat_id,))
    for row in c.fetchall():
        try:
            bot.delete_message(chat_id, row[0])
        except:
            pass
            
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
            
    if lobby_row and lobby_row[0]:
        try:
            bot.edit_message_text(text, chat_id, lobby_row[0])
        except:
            bot.send_message(chat_id, text)
            
    c.execute("DELETE FROM scores WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM groups WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM lobby WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM round_answers_v2 WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM q_messages WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

bot.remove_webhook()

keep_alive()
bot.infinity_polling()
