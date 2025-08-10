import os
import requests
import pandas as pd
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

PRICE, ENGINE, YEAR = range(3)
TOKEN = "8354759421:AAF_artiTXJ-S2_DaJL1CI1pk-3pvXk7HUM"

def get_yen_rate():
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    response = requests.get(url)
    response.encoding = "windows-1251"
    if "JPY" in response.text:
        start = response.text.find("<CharCode>JPY</CharCode>")
        value_tag = "<Value>"
        start_val = response.text.find(value_tag, start) + len(value_tag)
        end_val = response.text.find("</Value>", start_val)
        rate_str = response.text[start_val:end_val].replace(",", ".")
        return float(rate_str) / 100
    return 0.65

def calc_customs(price_yen, engine_cc, year):
    rate = get_yen_rate()
    price_rub = price_yen * rate
    age = datetime.now().year - year

    # Пошлина
    if age < 3:
        duty = max(price_rub * 0.48, engine_cc * 3.5)
    elif 3 <= age <= 5:
        if engine_cc <= 1000:
            duty = engine_cc * 1.5
        elif engine_cc <= 1500:
            duty = engine_cc * 1.7
        elif engine_cc <= 1800:
            duty = engine_cc * 2.5
        elif engine_cc <= 2300:
            duty = engine_cc * 2.7
        elif engine_cc <= 3000:
            duty = engine_cc * 3.0
        else:
            duty = engine_cc * 3.6
    else:
        if engine_cc <= 1000:
            duty = engine_cc * 3.0
        elif engine_cc <= 1500:
            duty = engine_cc * 3.2
        elif engine_cc <= 1800:
            duty = engine_cc * 3.5
        elif engine_cc <= 2300:
            duty = engine_cc * 4.8
        elif engine_cc <= 3000:
            duty = engine_cc * 5.0
        else:
            duty = engine_cc * 5.7

    # Утильсбор
    coeff = 0.17 if age < 3 else 0.26
    util = 3400 * coeff

    # НДС
    nds = (price_rub + duty + util) * 0.2

    total = price_rub + duty + util + nds

    return {
        "Курс йены": rate,
        "Цена в йенах": price_yen,
        "Цена в рублях": round(price_rub, 2),
        "Пошлина": round(duty, 2),
        "Утильсбор": round(util, 2),
        "НДС": round(nds, 2),
        "Итоговая цена": round(total, 2)
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введи цену на аукционе (в йенах):")
    return PRICE

async def price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["price"] = int(update.message.text.replace(" ", ""))
        await update.message.reply_text("Введи объём двигателя (см³ или литры):")
        return ENGINE
    except ValueError:
        await update.message.reply_text("❌ Введи число (йены).")
        return PRICE

async def engine_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(",", "."))
        if val < 10:
            val *= 1000
        context.user_data["engine"] = int(val)
        await update.message.reply_text("Введи год выпуска:")
        return YEAR
    except ValueError:
        await update.message.reply_text("❌ Введи число (например, 1500 или 1.5).")
        return ENGINE

async def year_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["year"] = int(update.message.text)
        data = calc_customs(
            context.user_data["price"],
            context.user_data["engine"],
            context.user_data["year"]
        )

        text = "\n".join([f"{k}: {v}" for k, v in data.items()])
        await update.message.reply_text(f"📊 Результат:\n{text}")

        df = pd.DataFrame(list(data.items()), columns=["Параметр", "Значение"])
        file_path = "calc.xlsx"
        df.to_excel(file_path, index=False)
        await update.message.reply_document(InputFile(file_path))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введи год числом.")
        return YEAR

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог завершён.")
    return ConversationHandler.END

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price_input)],
            ENGINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, engine_input)],
            YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, year_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()
