#!/usr/bin/env python3
"""
Bot Telegram Mie_Bot 1.0
Fitur:
  - Menu utama dengan 2 tombol
  - Daftar Broker Valetax (link langsung)
  - Signal XAUUSD dengan format lengkap
"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ─────────────────────────────────────────
#  KONFIGURASI
# ─────────────────────────────────────────
BOT_TOKEN    = "8973783812:AAE4iXqQ-hWnVpzToGjn2oOcwomfcY_K5hA"
VALETAX_URL  = "https://ma.valetax.com/p/6826903"

# ─────────────────────────────────────────
#  DATA SIGNAL (update manual sesuai analisis)
# ─────────────────────────────────────────
SIGNAL = {
    "pair"   : "XAUUSD",
    "entry"  : "4.250 – 4.265",
    "arah"   : "SELL",          # ganti BUY atau SELL
    "sl"     : "4.335",
    "tp1"    : "4.155",
    "tp2"    : "4.040",
    "rr"     : "1 : 2.5",
    "tf"     : "15M",
}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════
#  HELPER — keyboard & pesan
# ══════════════════════════════════════════

def menu_utama() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋  Daftar Broker Valetax", callback_data="daftar_broker")],
        [InlineKeyboardButton("📊  Signal XAUUSD",         callback_data="signal_xauusd")],
    ])

def menu_kembali() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄  Refresh Signal",  callback_data="signal_xauusd")],
        [InlineKeyboardButton("🏠  Kembali ke Menu", callback_data="menu_utama")],
    ])

def menu_broker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗  Daftar Sekarang di Valetax", url=VALETAX_URL)],
        [InlineKeyboardButton("🏠  Kembali ke Menu",            callback_data="menu_utama")],
    ])

def teks_sambutan(nama: str) -> str:
    return (
        f"Selamat datang di bot *Mie\\_Bot 1\\.0* 👋\n"
        f"Halo *{nama}*, silakan pilih menu di bawah ini :"
    )

def teks_broker() -> str:
    return (
        "🏦 *DAFTAR BROKER VALETAX*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ *Regulasi*      : FSC Mauritius\n"
        "✅ *Leverage*      : Hingga 1:1000\n"
        "✅ *Deposit Min*   : \\$10\n"
        "✅ *Spread*        : Mulai 0\\.1 pips\n"
        "✅ *Platform*      : MT4 / MT5\n"
        "✅ *Metode Deposit*: Bank Lokal / USDT\n\n"
        "📌 Klik tombol di bawah untuk mendaftar :"
    )

def teks_signal() -> str:
    waktu = datetime.now().strftime("%Y\\-%m\\-%d %H:%M")
    arah  = SIGNAL["arah"]
    emoji = "✅ BUY" if arah == "BUY" else "⭕ SELL"
    return (
        "📊 *SIGNAL MARKET*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *Pair*                   : `{SIGNAL['pair']}`\n"
        f"⏰ *Waktu Analisis*   : `{waktu}`\n"
        f"💰 *Harga Entry \\({SIGNAL['tf']}\\)* : `{SIGNAL['entry']}`\n"
        f"📈 *Rekomendasi*     : *{emoji}*\n"
        f"🛑 *Stop Loss*            : `{SIGNAL['sl']}`\n"
        f"🎯 *Take Profit 1*       : `{SIGNAL['tp1']}`\n"
        f"🎯 *Take Profit 2*       : `{SIGNAL['tp2']}`\n"
        f"📐 *Risk / Reward*     : `{SIGNAL['rr']}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ _Gunakan manajemen risiko yang ketat\\!_"
    )


# ══════════════════════════════════════════
#  HANDLER
# ══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    nama = update.effective_user.first_name or "Trader"
    await update.message.reply_text(
        teks_sambutan(nama),
        parse_mode="MarkdownV2",
        reply_markup=menu_utama(),
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data  = query.data

    if data == "menu_utama":
        nama = query.from_user.first_name or "Trader"
        await query.edit_message_text(
            teks_sambutan(nama),
            parse_mode="MarkdownV2",
            reply_markup=menu_utama(),
        )

    elif data == "daftar_broker":
        await query.edit_message_text(
            teks_broker(),
            parse_mode="MarkdownV2",
            reply_markup=menu_broker(),
        )

    elif data == "signal_xauusd":
        await query.edit_message_text(
            teks_signal(),
            parse_mode="MarkdownV2",
            reply_markup=menu_kembali(),
        )


# ══════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("✅ Bot Mie_Bot berjalan... Ctrl+C untuk berhenti.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
