import os
import re
import logging
import tempfile
from datetime import datetime

import requests
import pandas as pd
import xml.etree.ElementTree as ET

from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

PRICE, ENGINE, YEAR = range(3)

# Берём токен из переменной окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ Не найден токен. Установите переменную окружения TELEGRAM_BOT_TOKEN.")

def get_yen_rate(default_rate: float = 0.65) -> float:
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "windows-1251"
        xml_text = resp.text

        root = ET.fromstring(xml_text)
        for valute in root.findall("Valute"):
            code = valute.findtext("CharCode")
            if code and code.upper() == "JPY":
                value_text = valute.findtext("Value")
                nominal_text = valute.findtext("Nominal")
                if value_text is None:
                    continue
                value = float(value_text.replace(",", "."))
                nominal = int(nominal_text) if nominal_text and nominal_text.isdigit() else 1
                return value / nominal
        logger.warning("JPY not found in CBR response; using fallback rate")
        return default_rate
    except Exception as e:
        logger.exception("Ошибка при получении курса йены: %s", e)
        return default_rate

def calc_customs(price_yen: float, engine_cc: int, year: int) -> dict:
    rate = get_yen_rate()
    price_rub = price_yen * rate
    current_year = datetime.now().year
    age = current_year - year

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

    coeff = 0.17 if age < 3 else 0.26
    util = 3400 * coeff
    nds = (price_rub + duty + util) * 0.2
    total = price_rub + duty + util + nds

    return {
        "Курс йены (RUB за 1 JPY)": round(rate, 6),
        "Цена в йенах (JPY)": int(price_yen),
        "Цена в рублях (RUB)": round(price_rub, 2),
        "Возраст автомобиля (лет)": age,
        "Пошлина (RUB)": round(duty, 2),
        "Утильсбор (RUB)": round(util, 2),
        "НДС (RUB)": round(nds, 2),
        "Итоговая цена (RUB)": round(total, 2),
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введи цену на аукционе (в йенах):")
    return PRICE

def _parse_int_from_text(text: str) -> int:
    cleaned = re.sub(r"[^\d]", "", text)
    if not cleaned:
        raise ValueError("Чисел не найдено")
    return int(cleaned)

async def price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        price = _parse_int_from_text(text)
        if price <= 0:
            raise ValueError("Цена должна быть положительной")
        context.user_data["price"] = price
        await update.message.reply_text("Введи объём двигателя (см³ или литры, например: 1500 или 1.5):")
        return ENGINE
    except ValueError:
        await update.message.reply_text("❌ Введи корректную цену (число в йенах, например 250000).")
        return PRICE

async def engine_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    try:
        val = float(text)
        if val < 10:
            val *= 1000
        engine_cc = int(round(val))
        if engine_cc <= 50 or engine_cc > 15000:
            await update.message.reply_text("❌ Некорректный объём двигателя. Введи значение в см³ или в литрах.")
            return ENGINE
        context.user_data["engine"] = engine_cc
        await update.message.reply_text("Введи год выпуска (например, 2014):")
        return YEAR
    except ValueError:
        await update.message.reply_text("❌ Введи число (например, 1500 или 1.5).")
        return ENGINE

async def year_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    current_year = datetime.now().year
    try:
        year = int(re.sub(r"[^\d]", "", text))
        if year < 1900 or year > current_year:
            await update.message.reply_text(f"❌ Введи корректный год между 1900 и {current_year}.")
            return YEAR
        context.user_data["year"] = year

        data = calc_customs(
            context.user_data["price"],
            context.user_data["engine"],
            context.user_data["year"],
        )

        lines = [f"{k}: {v}" for k, v in data.items()]
        result_text = "📊 Результат расчёта:\n" + "\n".join(lines)
        await update.message.reply_text(result_text)

        try:
            df = pd.DataFrame(list(data.items()), columns=["Параметр", "Значение"])
            with tempfile.NamedTemporaryFile(prefix="calc_", suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            df.to_excel(tmp_path, index=False)
            await update.message.reply_document(InputFile(tmp_path))
        except Exception as e:
            logger.exception("Ошибка при создании/отправке Excel файла: %s", e)
            await update.message.reply_text("⚠️ Не удалось создать/отправить Excel-файл, но расчёт показан выше.")
        finally:
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception as e:
                logger.warning("Не удалось удалить временный файл: %s", e)

        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введи год числом (например, 2014).")
        return YEAR

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог завершён.")
    return ConversationHandler.END

def main():
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
    logger.info("Bot started. Запуск долгого опроса (polling).")
    app.run_polling()

if __name__ == "__main__":
    main()
