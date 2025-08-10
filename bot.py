import os
import telebot

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6715276059"))

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "Привет! Отправь мне цену аукциона, а я рассчитаю стоимость автомобиля из Японии.")

@bot.message_handler(commands=['export'])
def export_data(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "У вас нет доступа к этой команде.")
        return
    try:
        with open("calculations.xlsx", "rb") as f:
            bot.send_document(message.chat.id, f)
    except FileNotFoundError:
        bot.reply_to(message, "Файл с расчетами пока не создан.")

@bot.message_handler(func=lambda m: True)
def calculate_price(message):
    try:
        auction_price = float(message.text.replace(" ", "").replace(",", "."))
        # Здесь можно поменять коэффициенты на твои
        shipping = 1000
        fee = 500
        total = auction_price + shipping + fee
        bot.reply_to(message, f"Стоимость с доставкой и сбором: {total:,.0f} ¥")
    except ValueError:
        bot.reply_to(message, "Пожалуйста, введи цену числом.")

print("Бот запущен...")
bot.polling(none_stop=True)
