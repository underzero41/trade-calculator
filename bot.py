import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://underzero41.github.io/trade-calculator/")

DEPOSIT, RISK, ENTRY, SL, TP = range(5)

WELCOME_TEXT = (
    "📊 *Just Trade It — Risk Calculator*\n\n"
    "Рассчитай точный объём позиции и R:R за секунды.\n"
    "Все поля заполняются сразу — как в настоящем приложении 👇"
)


def start_keyboard():
    from telegram import WebAppInfo
    if WEB_APP_URL:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Открыть калькулятор", web_app=WebAppInfo(url=WEB_APP_URL))]
        ])
    # fallback пока нет хостинга
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Рассчитать сделку", callback_data="new_calc")]
    ])


def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        WELCOME_TEXT,
        parse_mode="Markdown",
        reply_markup=start_keyboard(),
    )


def new_calc(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.message.reply_text(
        "💰 *Шаг 1/5 — Депозит*\n\nВведи размер депозита в $:\n_Пример: 10000_",
        parse_mode="Markdown",
    )
    return DEPOSIT


def get_deposit(update: Update, context: CallbackContext):
    try:
        value = float(update.message.text.replace(",", ".").replace(" ", ""))
        if value <= 0:
            raise ValueError
        context.user_data["deposit"] = value
    except ValueError:
        update.message.reply_text("⚠️ Введи число больше нуля. Например: `10000`", parse_mode="Markdown")
        return DEPOSIT

    update.message.reply_text(
        f"✅ Депозит: *${value:,.0f}*\n\n"
        "📉 *Шаг 2/5 — Риск %*\n\nСколько % готов рискнуть в этой сделке?\n_Пример: 1_",
        parse_mode="Markdown",
    )
    return RISK


def get_risk(update: Update, context: CallbackContext):
    try:
        value = float(update.message.text.replace(",", ".").replace("%", "").strip())
        if not (0 < value <= 10):
            raise ValueError
        context.user_data["risk"] = value
    except ValueError:
        update.message.reply_text("⚠️ Введи число от 0.1 до 10. Например: `1`", parse_mode="Markdown")
        return RISK

    update.message.reply_text(
        f"✅ Риск: *{value}%*\n\n"
        "🎯 *Шаг 3/5 — Точка входа*\n\nВведи цену входа:\n_Пример: 1.0850 или 43250_",
        parse_mode="Markdown",
    )
    return ENTRY


def get_entry(update: Update, context: CallbackContext):
    try:
        value = float(update.message.text.replace(",", ".").replace(" ", ""))
        if value <= 0:
            raise ValueError
        context.user_data["entry"] = value
    except ValueError:
        update.message.reply_text("⚠️ Введи корректную цену. Например: `1.0850`", parse_mode="Markdown")
        return ENTRY

    update.message.reply_text(
        f"✅ Вход: *{value}*\n\n"
        "🛑 *Шаг 4/5 — Стоп-лосс*\n\nВведи цену стоп-лосса:\n_Пример: 1.0800_",
        parse_mode="Markdown",
    )
    return SL


def get_sl(update: Update, context: CallbackContext):
    try:
        value = float(update.message.text.replace(",", ".").replace(" ", ""))
        entry = context.user_data["entry"]
        if value <= 0 or value == entry:
            raise ValueError
        context.user_data["sl"] = value
    except ValueError:
        update.message.reply_text("⚠️ СЛ должен отличаться от точки входа.", parse_mode="Markdown")
        return SL

    update.message.reply_text(
        f"✅ Стоп-лосс: *{value}*\n\n"
        "💵 *Шаг 5/5 — Тейк-профит*\n\nВведи цену тейк-профита:\n_Пример: 1.0950_",
        parse_mode="Markdown",
    )
    return TP


def get_tp(update: Update, context: CallbackContext):
    try:
        value = float(update.message.text.replace(",", ".").replace(" ", ""))
        entry = context.user_data["entry"]
        if value <= 0 or value == entry:
            raise ValueError
        context.user_data["tp"] = value
    except ValueError:
        update.message.reply_text("⚠️ ТП должен отличаться от точки входа.", parse_mode="Markdown")
        return TP

    return show_result(update, context)


def show_result(update: Update, context: CallbackContext):
    d = context.user_data
    deposit = d["deposit"]
    risk_pct = d["risk"]
    entry = d["entry"]
    sl = d["sl"]
    tp = d["tp"]

    risk_usd = deposit * risk_pct / 100
    sl_dist = abs(entry - sl) / entry
    position_size = risk_usd / sl_dist

    tp_dist = abs(tp - entry) / entry
    profit = position_size * tp_dist
    rr = profit / risk_usd

    direction = "📈 LONG" if tp > entry else "📉 SHORT"

    result = (
        f"✅ *Результат расчёта*\n"
        f"{'─' * 26}\n"
        f"{direction}\n\n"
        f"💰 Депозит:          *${deposit:,.2f}*\n"
        f"⚠️ Риск:             *${risk_usd:,.2f}* ({risk_pct}%)\n"
        f"📏 СЛ расстояние:    *{sl_dist*100:.2f}%*\n"
        f"{'─' * 26}\n"
        f"📦 *Объём позиции:   ${position_size:,.2f}*\n"
        f"{'─' * 26}\n"
        f"🎯 Потенциал:        *${profit:,.2f}* ({tp_dist*100:.2f}%)\n"
        f"⚖️ R:R:              *1 : {rr:.1f}*\n"
    )

    update.message.reply_text(result, parse_mode="Markdown")
    update.message.reply_text(
        AFFILIATE_TEXT,
        parse_mode="Markdown",
        reply_markup=affiliate_keyboard(),
    )
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Расчёт отменён. Нажми /start чтобы начать заново.")
    return ConversationHandler.END


def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(new_calc, pattern="^new_calc$")],
        states={
            DEPOSIT: [MessageHandler(Filters.text & ~Filters.command, get_deposit)],
            RISK:    [MessageHandler(Filters.text & ~Filters.command, get_risk)],
            ENTRY:   [MessageHandler(Filters.text & ~Filters.command, get_entry)],
            SL:      [MessageHandler(Filters.text & ~Filters.command, get_sl)],
            TP:      [MessageHandler(Filters.text & ~Filters.command, get_tp)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv)

    print("✅ Bot is running...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
