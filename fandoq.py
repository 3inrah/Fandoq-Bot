from keep_alive import keep_alive
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3

TOKEN = '8987719269:AAGXwnmftbLA0evqHvjd32A7ktkmFbA5Uz4'
bot = telebot.TeleBot(TOKEN)

# ==========================================
# ۱. تنظیمات پایگاه داده (دیتابیس)
# ==========================================
def init_db():
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    # ساخت جدول برای ذخیره: آیدی کاربر، امتیاز، و شماره سوالی که الان در آن است
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, score INTEGER, current_q INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# ۲. بانک سوالات
# ==========================================
# می‌توانید هر تعداد سوال که خواستید به این لیست اضافه کنید
QUESTIONS = [
    {
        "question": "بزرگترین سیاره منظومه شمسی کدام است؟",
        "options": ["زمین", "مریخ", "مشتری", "زحل"],
        "correct": 2 # شماره گزینه درست (شمارش از صفر شروع می‌شود: مشتری=2)
    },
    {
        "question": "کدام زبان برنامه‌نویسی برای هوش مصنوعی محبوب‌تر است؟",
        "options": ["جاوا", "پایتون", "سی‌شارپ", "پی‌اچ‌پی"],
        "correct": 1
    },
    {
        "question": "پایتخت کشور ژاپن کجاست؟",
        "options": ["پکن", "توکیو", "سئول", "کیوتو"],
        "correct": 1
    }
]

# ==========================================
# ۳. توابع ارتباط با دیتابیس
# ==========================================
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
    # اگر کاربر نبود ایجاد می‌کند، اگر بود آپدیت می‌کند
    c.execute("INSERT OR REPLACE INTO users (user_id, score, current_q) VALUES (?, ?, ?)", 
              (user_id, score, current_q))
    conn.commit()
    conn.close()

# ==========================================
# ۴. دستورات اصلی ربات
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    if not get_user(user_id):
        update_user(user_id, 0, 0) # ثبت‌نام کاربر جدید با امتیاز صفر
    bot.reply_to(message, "سلام! به ربات کوئیز خوش آمدی 🎮\n\n🔹 برای شروع بازی: /quiz\n🔹 برای دیدن امتیازت: /score")

@bot.message_handler(commands=['score'])
def show_score(message):
    user_id = message.chat.id
    user = get_user(user_id)
    if user:
        bot.reply_to(message, f"💰 امتیاز کل شما تا این لحظه: {user[0]}")
    else:
        bot.reply_to(message, "شما هنوز ثبت‌نام نکرده‌اید. لطفا /start را بزنید.")

@bot.message_handler(commands=['quiz'])
def start_quiz(message):
    user_id = message.chat.id
    user = get_user(user_id)
    
    if not user:
        update_user(user_id, 0, 0)
        score = 0
    else:
        score = user[0]
        
    # ریست کردن مرحله به صفر برای شروع مجدد کوئیز، اما حفظ امتیازات قبلی
    update_user(user_id, score, 0)
    send_question(user_id, 0)

# ==========================================
# ۵. سیستم ارسال و پردازش سوالات
# ==========================================
def send_question(user_id, q_index):
    # اگر سوالات تمام شده بود
    if q_index >= len(QUESTIONS):
        user = get_user(user_id)
        bot.send_message(user_id, f"🎉 تبریک! شما به همه سوالات پاسخ دادید.\n\n💰 کل امتیاز شما: {user[0]}")
        return

    q_data = QUESTIONS[q_index]
    markup = InlineKeyboardMarkup()
    
    # ساخت دکمه‌ها برای ۴ گزینه
    buttons = []
    for i, option in enumerate(q_data["options"]):
        # اطلاعات مخفی دکمه: شماره سوال و گزینه انتخاب شده (مثلا ans_0_2)
        callback_data = f"ans_{q_index}_{i}"
        buttons.append(InlineKeyboardButton(option, callback_data=callback_data))
  # چینش دکمه‌ها (دو تا در هر ردیف)
    markup.add(buttons[0], buttons[1])
    markup.add(buttons[2], buttons[3])
    
    bot.send_message(user_id, f"❓ سوال {q_index + 1}: {q_data['question']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def handle_answer(call):
    user_id = call.message.chat.id
    data_parts = call.data.split('_')
    q_index = int(data_parts[1])
    selected_option = int(data_parts[2])
    
    user = get_user(user_id)
    
    # جلوگیری از تقلب یا کلیک روی سوالات قدیمی
    if not user or user[1] != q_index:
        bot.answer_callback_query(call.id, "این سوال منقضی شده است!", show_alert=True)
        return

    score, current_q = user
    correct_option = QUESTIONS[q_index]["correct"]
    
    # بررسی جواب
    if selected_option == correct_option:
        score += 10
        bot.answer_callback_query(call.id, "آفرین! جواب درست بود ✅")
    else:
        bot.answer_callback_query(call.id, "متاسفانه اشتباه بود ❌")
        
    # ثبت پیشرفت در دیتابیس (رفتن به سوال بعدی)
    next_q = q_index + 1
    update_user(user_id, score, next_q)
    
    # پاک کردن دکمه‌های شیشه‌ای از پیام قبلی تا کاربر نتواند دوباره کلیک کند
    bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
    
    # ارسال سوال جدید
    send_question(user_id, next_q)

keep_alive()
print("ربات با موفقیت روشن شد...")
bot.infinity_polling()

# ==========================================
# روشن کردن ربات
# ==========================================
print("ربات با موفقیت روشن شد. به تلگرام بروید و /start را بزنید...")
bot.infinity_polling()