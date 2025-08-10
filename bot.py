import os
import requests
import datetime
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)
from openpyxl import Workbook, load_workbook

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
FILE_NAME = "calculations.xlsx"

PRICE, ENGINE, YEAR_OR_RATE, DELIVERY, FREIGHT, BROKER = range(6)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def get_jpy_rate():
    try:
        r = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=8)
        r.raise_for_status()
        data = r.json()
        val = data.get("Valute", {}).get("JPY", {}).get("Value")
        return float(val) if val is not None else None
    except:
        return None

def save_to_excel(row):
    header = [
        "Дата", "Цена ¥", "Курс ¥", "Цена ₽",
        "Двигатель (см³)", "Год выпуска", "Возраст (лет)",
        "Доставка ₽", "Фрахт ₽", "Пошлина ₽", "Утильсбор ₽",
        "НДС ₽", "Брокер ₽", "Итого ₽"
    ]
    try:
        if not os.path.exists(FILE_NAME):
            wb = Workbook()
            ws = wb.active
            ws.append(header)
            wb.save(FILE_NAME)
        wb = load_workbook(FILE_NAME)
        ws = wb.active
        ws.append(row)
        wb.save(FILE_NAME)
    except Exception as e:
        logger.exception(e)

def calc_customs(price_rub, age, cc):
    if age < 3:
        duty = price_rub * 0.48
    else:
        if cc <= 1000:
            duty = cc * 1.5 * 100
        elif cc <= 1500:
            duty = cc * 1.7 * 100
        elif cc <= 1800:
            duty = cc * 2.5 * 100
        elif cc <= 2300:
            duty = cc * 2.7 * 100
        elif cc <= 3000:
            duty = cc * 3.0 * 100
        else:
            duty = cc * 3.6 * 100
    util_fee = 5200 if age < 3 else 8200
    vat = (price_rub + duty) * 0.2
    return duty, util_fee, vat

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rate = get_jpy_rate()
    context.user_data['rate'] = rate
    if rate:
        await update.message.reply_text(f"📈 Курс йены (ЦБ): 1 ¥ = {rate:.4f} ₽\nВведи цену на аукционе (в йенах):")
    else:
        await update.message.reply_text("⚠️ Не удалось получить курс йены. Введи цену на аукционе (в йенах), затем вручную курс (в рублях).")
    return PRICE

async def price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip().replace(",", "").replace(" ", "")
    try:
        context.user_data['price_yen'] = float(txt)
        if context.user_data.get('rate') is None:
            await update.message.reply_text("Введи курс йены к рублю (пример: 0.6123):")
            return YEAR_OR_RATE
        else:
            await update.message.reply_text("Введи объём двигателя (см³):")
            return ENGINE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи число — цену в йенах.")
        return PRICE

async def year_or_rate_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip().replace(",", ".")
    try:
        rate = float(txt)
        context.user_data['rate'] = rate
        await update.message.reply_text("Введи объём двигателя (см³):")
        return ENGINE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи число — курс (например 0.6123).")
        return YEAR_OR_RATE

async def engine_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    try:
        cc = int(txt)
        context.user_data['engine_cc'] = cc
        await update.message.reply_text("Введи год выпуска:")
        return YEAR_OR_RATE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи целое число (см³).")
        return ENGINE

async def year_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    try:
        year = int(txt)
        cy = datetime.datetime.now().year
        if year < 1980 or year > cy:
            await update.message.reply_text(f"Некорректный год. Введи год от 1980 до {cy}.")
            return YEAR_OR_RATE
        context.user_data['year'] = year
        context.user_data['age'] = cy - year
        await update.message.reply_text("Введи стоимость доставки в порт Японии (₽):")
        return DELIVERY
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи год цифрами.")
        return YEAR_OR_RATE

async def delivery_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip().replace(",", ".").replace(" ", "")
    try:
        context.user_data['delivery'] = float(txt)
        await update.message.reply_text("Введи стоимость фрахта (₽):")
        return FREIGHT
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи число (рубли).")
        return DELIVERY

async def freight_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip().replace(",", ".").replace(" ", "")
    try:
        context.user_data['freight'] = float(txt)
        await update.message.reply_text("Введи услуги брокера (₽):")
        return BROKER
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи число (рубли).")
        return FREIGHT

async def broker_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip().replace(",", ".").replace(" ", "")
    try:
        broker = float(txt)
        ctx = context.user_data
        price_yen = ctx['price_yen']
        rate = ctx['rate']
        price_rub = price_yen * rate
        duty, util_fee, vat = calc_customs(price_rub, ctx['age'], ctx['engine_cc'])
        delivery = ctx.get('delivery', 0.0)
        freight = ctx.get('freight', 0.0)
        total = price_rub + delivery + freight + duty + util_fee + vat + broker
        row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            price_yen, rate, round(price_rub, 2),
            ctx['engine_cc'], ctx['year'], ctx['age'],
            delivery, freight, round(duty, 2), util_fee, round(vat, 2), broker, round(total, 2)
        ]
        save_to_excel(row)
        text = (
            "📊 Подробный расчёт:\n\n"
            f"Цена на аукционе: {price_yen:,.0f} ¥ × {rate:.4f} ₽ = {price_rub:,.0f} ₽\n"
            f"Доставка в порт Японии: {delivery:,.0f} ₽\n"
            f"Фрахт: {freight:,.0f} ₽\n"
            f"Пошлина: {duty:,.0f} ₽\n"
            f"Утильсбор: {util_fee:,.0f} ₽\n"
            f"НДС (20%): {vat:,.0f} ₽\n"
            f"Брокер: {broker:,.0f} ₽\n\n"
            f"Возраст авто: {ctx['age']} лет\n"
            f"Итого: {total:,.0f} ₽"
        )
        await update.message.reply_text(text)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи число (рубли).")
        return BROKER
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("Ошибка при расчёте.")
        return ConversationHandler.END

async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not os.path.exists(FILE_NAME):
        await update.message.reply_text("Файл ещё не создан.")
        return
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open(FILE_NAME, "rb"))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ОК, отменено.")
    return ConversationHandler.END

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден.")
        return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price_input)],
            YEAR_OR_RATE: [
                MessageHandler(filters.Regex(r'^[0-9]+(\.[0-9]+)?$') & ~filters.COMMAND, year_or_rate_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, year_input)
            ],
            ENGINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, engine_input)],
            DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_input)],
            FREIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, freight_input)],
            BROKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, broker_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("export", export_excel))
    logger.info("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
