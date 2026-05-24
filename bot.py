import os
import logging
import psycopg2
from psycopg2.extras import execute_values
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext,
)
from telegram.error import Unauthorized, ChatMigrated, TimedOut

logging.basicConfig(level=logging.INFO)

TOKEN      = os.environ.get("BOT_TOKEN")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://underzero41.github.io/trade-calculator/")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID   = int(os.environ.get("ADMIN_CHAT_ID", "0"))  # твой chat_id — задай в Railway Variables

DEPOSIT, RISK, ENTRY, SL, TP = range(5)

WELCOME_TEXT = (
    "📊 *Just Trade It — Risk Calculator*\n\n"
    "Calculate your exact position size and R:R in seconds. 👇"
)

AFFILIATE_TEXT = (
    "💼 *Trade with more capital than you have:*\n\n"
    "⚡ [Hash Hedge](https://hashhedge.com?fpr=youwillbeamillionaire) — up to $200K funded\n"
    "🚀 [Funding Pips](https://app.fundingpips.com/register?ref=E56D6F7A) — up to $200K funded\n\n"
    "🎓 [Free Trading Course on YouTube](https://www.youtube.com/watch?v=Glp2lgMrL_I&t=1s)"
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    if not DATABASE_URL:
        logging.warning("DATABASE_URL not set — users will not be saved")
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id    BIGINT PRIMARY KEY,
                    username   TEXT,
                    first_name TEXT,
                    joined_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        conn.commit()

def save_user(chat_id: int, username: str, first_name: str):
    if not DATABASE_URL:
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (chat_id, username, first_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (chat_id) DO NOTHING
                """, (chat_id, username, first_name))
            conn.commit()
    except Exception as e:
        logging.error(f"save_user error: {e}")

def get_all_users():
    if not DATABASE_URL:
        return []
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id FROM users")
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logging.error(f"get_all_users error: {e}")
        return []

# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def calc_keyboard():
    """Кнопка открыть калькулятор — добавляется к любому сообщению."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Open Calculator", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])

def affiliate_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Hash Hedge", url="https://hashhedge.com?fpr=youwillbeamillionaire"),
            InlineKeyboardButton("🚀 Funding Pips", url="https://app.fundingpips.com/register?ref=E56D6F7A"),
        ],
        [InlineKeyboardButton("📊 Open Calculator", web_app=WebAppInfo(url=WEB_APP_URL))],
    ])

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    save_user(user.id, user.username or "", user.first_name or "")
    update.message.reply_text(
        WELCOME_TEXT,
        parse_mode="Markdown",
        reply_markup=calc_keyboard(),
    )


def new_calc(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.message.reply_text(
        "💰 *Step 1/5 — Deposit*\n\nEnter your deposit in $:\n_Example: 10000_",
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
        update.message.reply_text("⚠️ Enter a number greater than zero. Example: `10000`", parse_mode="Markdown")
        return DEPOSIT

    update.message.reply_text(
        f"✅ Deposit: *${value:,.0f}*\n\n"
        "📉 *Step 2/5 — Risk %*\n\nWhat % are you risking on this trade?\n_Example: 1_",
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
        update.message.reply_text("⚠️ Enter a number between 0.1 and 10. Example: `1`", parse_mode="Markdown")
        return RISK

    update.message.reply_text(
        f"✅ Risk: *{value}%*\n\n"
        "🎯 *Step 3/5 — Entry price*\n\nEnter your entry price:\n_Example: 1.0850 or 43250_",
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
        update.message.reply_text("⚠️ Enter a valid price. Example: `1.0850`", parse_mode="Markdown")
        return ENTRY

    update.message.reply_text(
        f"✅ Entry: *{value}*\n\n"
        "🛑 *Step 4/5 — Stop Loss*\n\nEnter your stop loss price:\n_Example: 1.0800_",
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
        update.message.reply_text("⚠️ Stop loss must differ from entry price.", parse_mode="Markdown")
        return SL

    update.message.reply_text(
        f"✅ Stop Loss: *{value}*\n\n"
        "💵 *Step 5/5 — Take Profit*\n\nEnter your take profit price:\n_Example: 1.0950_",
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
        update.message.reply_text("⚠️ Take profit must differ from entry price.", parse_mode="Markdown")
        return TP

    return show_result(update, context)


def show_result(update: Update, context: CallbackContext):
    d = context.user_data
    deposit    = d["deposit"]
    risk_pct   = d["risk"]
    entry      = d["entry"]
    sl         = d["sl"]
    tp         = d["tp"]

    risk_usd      = deposit * risk_pct / 100
    sl_dist       = abs(entry - sl) / entry
    position_size = risk_usd / sl_dist
    tp_dist       = abs(tp - entry) / entry
    profit        = position_size * tp_dist
    rr            = profit / risk_usd
    direction     = "📈 LONG" if tp > entry else "📉 SHORT"

    result = (
        f"✅ *Result*\n"
        f"{'─' * 26}\n"
        f"{direction}\n\n"
        f"💰 Deposit:         *${deposit:,.2f}*\n"
        f"⚠️ Risk:            *${risk_usd:,.2f}* ({risk_pct}%)\n"
        f"📏 SL distance:     *{sl_dist*100:.2f}%*\n"
        f"{'─' * 26}\n"
        f"📦 *Position size:  ${position_size:,.2f}*\n"
        f"{'─' * 26}\n"
        f"🎯 Potential profit: *${profit:,.2f}* ({tp_dist*100:.2f}%)\n"
        f"⚖️ R:R:              *1 : {rr:.1f}*\n"
    )

    update.message.reply_text(result, parse_mode="Markdown")
    update.message.reply_text(
        AFFILIATE_TEXT,
        parse_mode="Markdown",
        reply_markup=affiliate_keyboard(),  # уже содержит кнопку калькулятора
    )
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext):
    update.message.reply_text(
        "❌ Cancelled. Tap /start to begin again.",
        reply_markup=calc_keyboard(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Broadcast — только для админа
# ---------------------------------------------------------------------------

def broadcast(update: Update, context: CallbackContext):
    """Использование: /broadcast Текст сообщения"""
    if update.effective_user.id != ADMIN_ID:
        return

    text = " ".join(context.args)
    if not text:
        update.message.reply_text("Usage: /broadcast Your message text")
        return

    users = get_all_users()
    sent, failed = 0, 0

    for chat_id in users:
        try:
            context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=calc_keyboard(),  # кнопка калькулятора к каждому сообщению
            )
            sent += 1
        except (Unauthorized, ChatMigrated):
            failed += 1
        except TimedOut:
            failed += 1
        except Exception as e:
            logging.error(f"Broadcast error for {chat_id}: {e}")
            failed += 1

    update.message.reply_text(f"✅ Sent: {sent} | ❌ Failed: {failed} | Total: {len(users)}")


def users_count(update: Update, context: CallbackContext):
    """Команда /users — показывает сколько пользователей в базе."""
    if update.effective_user.id != ADMIN_ID:
        return
    count = len(get_all_users())
    update.message.reply_text(f"👥 Users in database: *{count}*", parse_mode="Markdown")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    init_db()

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
    dp.add_handler(CommandHandler("broadcast", broadcast, pass_args=True))
    dp.add_handler(CommandHandler("users", users_count))
    dp.add_handler(conv)

    print("✅ Bot is running...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
