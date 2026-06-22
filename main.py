#!/usr/bin/env python3
"""
Mie_Bot 1.0 — Main Entry Point
Menjalankan dua proses sekaligus:
  1. Bot Telegram (handler /start, menu tombol)
  2. Signal Engine (analisa XAUUSD otomatis tiap 15M)
"""

import time
import logging
import threading
from datetime import datetime

import pytz
import pandas as pd
import requests
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
BOT_TOKEN      = "8973783812:AAE4iXqQ-hWnVpzToGjn2oOcwomfcY_K5hA"
CHAT_ID        = "-1004410608338"
TOPIC_ID       = 4
TWELVE_API_KEY = "dbb5e1da912149f4ba5d518591d6ac47"
VALETAX_URL    = "https://ma.valetax.com/p/6826903"
SYMBOL         = "XAU/USD"
INTERVAL       = "15min"
CANDLE_SEC     = 15 * 60
JAM_MULAI      = 6
JAM_SELESAI    = 24
TIMEZONE       = pytz.timezone("Asia/Jakarta")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════
#  BAGIAN 1 — BOT TELEGRAM (Menu & /start)
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
        "✅ *Regulasi*       : FSC Mauritius\n"
        "✅ *Leverage*       : Hingga 1:1000\n"
        "✅ *Deposit Min*    : \\$10\n"
        "✅ *Spread*         : Mulai 0\\.1 pips\n"
        "✅ *Platform*       : MT4 / MT5\n"
        "✅ *Metode Deposit* : Bank Lokal / USDT\n\n"
        "📌 Klik tombol di bawah untuk mendaftar :"
    )

def ambil_signal_manual() -> str:
    """
    Ambil signal terkini untuk ditampilkan manual via tombol.
    Bisa diakses kapan saja — tidak terikat jam trading.
    """
    try:
        df       = ambil_data_twelvedata()
        sd       = deteksi_supply_demand(df)
        ufo_list = deteksi_ufo(df)
        signal   = tentukan_signal(sd, ufo_list)
        waktu    = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")

        if signal:
            return format_pesan(signal, sd["harga"], ufo_list, waktu)
        else:
            # Tampilkan info market meskipun tidak ada signal
            supply_txt = f"`{sd['supply']['bottom']} - {sd['supply']['top']}`" if sd["supply"] else "_Tidak terdeteksi_"
            demand_txt = f"`{sd['demand']['bottom']} - {sd['demand']['top']}`" if sd["demand"] else "_Tidak terdeteksi_"
            return (
                f"📊 *INFO MARKET XAUUSD*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ *Waktu*          : `{waktu}` WIB\n"
                f"💰 *Harga Sekarang* : `{sd['harga']}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔴 *Supply Zone* : {supply_txt}\n"
                f"🟢 *Demand Zone* : {demand_txt}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💤 _Belum ada setup entry valid saat ini_\n"
                f"_Harga belum menyentuh area Supply/Demand/UFO_"
            )
    except Exception as e:
        return f"❌ Gagal ambil data: `{e}`"

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

    if query.data == "menu_utama":
        nama = query.from_user.first_name or "Trader"
        await query.edit_message_text(
            teks_sambutan(nama),
            parse_mode="MarkdownV2",
            reply_markup=menu_utama(),
        )

    elif query.data == "daftar_broker":
        await query.edit_message_text(
            teks_broker(),
            parse_mode="MarkdownV2",
            reply_markup=menu_broker(),
        )

    elif query.data == "signal_xauusd":
        await query.edit_message_text(
            "⏳ Mengambil data signal terkini\\.\\.\\.",
            parse_mode="MarkdownV2",
        )
        pesan = ambil_signal_manual()
        await query.edit_message_text(
            pesan,
            parse_mode="MarkdownV2",
            reply_markup=menu_kembali(),
        )


# ══════════════════════════════════════════
#  BAGIAN 2 — SIGNAL ENGINE (Otomatis 15M)
# ══════════════════════════════════════════

def ambil_data_twelvedata() -> pd.DataFrame:
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol"    : SYMBOL,
        "interval"  : INTERVAL,
        "outputsize": 100,
        "apikey"    : TWELVE_API_KEY,
        "format"    : "JSON",
    }
    r    = requests.get(url, params=params, timeout=15)
    data = r.json()

    if "values" not in data:
        raise ValueError(f"Twelve Data error: {data.get('message', 'Unknown')}")

    rows = [{"Open": float(v["open"]), "High": float(v["high"]),
             "Low": float(v["low"]), "Close": float(v["close"])}
            for v in reversed(data["values"])]

    df = pd.DataFrame(rows)
    log.info(f"Data OK — harga terakhir: {df['Close'].iloc[-1]}")
    return df


def deteksi_supply_demand(df: pd.DataFrame) -> dict:
    lookback         = df.tail(50).copy()
    lookback["body"] = abs(lookback["Close"] - lookback["Open"])
    avg_body         = lookback["body"].mean()
    supply_zones, demand_zones = [], []

    for i in range(1, len(lookback) - 1):
        candle  = lookback.iloc[i]
        sesudah = lookback.iloc[i + 1]
        body    = candle["body"]

        if candle["Close"] < candle["Open"] and body > avg_body * 1.5 and sesudah["Close"] < candle["Close"]:
            supply_zones.append({"top": round(candle["High"], 2), "bottom": round(candle["Open"], 2)})

        if candle["Close"] > candle["Open"] and body > avg_body * 1.5 and sesudah["Close"] > candle["Close"]:
            demand_zones.append({"top": round(candle["Close"], 2), "bottom": round(candle["Low"], 2)})

    harga_kini = float(df["Close"].iloc[-1])
    supply = sorted([z for z in supply_zones if z["bottom"] > harga_kini], key=lambda z: z["bottom"])
    demand = sorted([z for z in demand_zones if z["top"] < harga_kini], key=lambda z: z["top"], reverse=True)

    return {"harga": round(harga_kini, 2), "supply": supply[0] if supply else None, "demand": demand[0] if demand else None}


def deteksi_ufo(df: pd.DataFrame) -> list:
    lookback         = df.tail(100).copy()
    lookback["body"] = abs(lookback["Close"] - lookback["Open"])
    avg_body         = lookback["body"].mean()
    harga_kini       = float(df["Close"].iloc[-1])
    ufo_list         = []

    for i in range(len(lookback) - 20):
        candle = lookback.iloc[i]
        sisa   = lookback.iloc[i + 1:]
        if candle["body"] < avg_body * 2:
            continue
        if candle["Close"] < candle["Open"]:
            level = round(candle["Open"], 2)
            if level > harga_kini and not (sisa["High"] >= level).any():
                ufo_list.append({"tipe": "BEARISH", "level": level, "zona": f"{round(candle['Low'],2)} - {level}"})
        if candle["Close"] > candle["Open"]:
            level = round(candle["Open"], 2)
            if level < harga_kini and not (sisa["Low"] <= level).any():
                ufo_list.append({"tipe": "BULLISH", "level": level, "zona": f"{level} - {round(candle['High'],2)}"})

    return sorted(ufo_list, key=lambda u: abs(u["level"] - harga_kini))[:3]


def tentukan_signal(sd: dict, ufo_list: list) -> dict | None:
    harga, supply, demand = sd["harga"], sd["supply"], sd["demand"]
    toleransi = harga * 0.003

    if supply and 0 <= supply["bottom"] - harga <= toleransi * 10:
        entry = round((supply["top"] + supply["bottom"]) / 2, 2)
        sl = round(supply["top"] + 5, 2)
        return {"arah": "SELL", "entry": entry, "sl": sl,
                "tp1": round(harga - (sl - entry) * 1.5, 2), "tp2": round(harga - (sl - entry) * 2.5, 2),
                "alasan": f"Harga mendekati Supply Zone {supply['bottom']} - {supply['top']}"}

    for ufo in ufo_list:
        if ufo["tipe"] == "BEARISH" and 0 <= ufo["level"] - harga <= toleransi * 8:
            sl = round(ufo["level"] + 8, 2)
            return {"arah": "SELL", "entry": harga, "sl": sl,
                    "tp1": round(harga - (sl - harga) * 1.5, 2), "tp2": round(harga - (sl - harga) * 2.5, 2),
                    "alasan": f"UFO Bearish di zona {ufo['zona']}"}

    if demand and 0 <= harga - demand["top"] <= toleransi * 10:
        entry = round((demand["top"] + demand["bottom"]) / 2, 2)
        sl = round(demand["bottom"] - 5, 2)
        return {"arah": "BUY", "entry": entry, "sl": sl,
                "tp1": round(harga + (entry - sl) * 1.5, 2), "tp2": round(harga + (entry - sl) * 2.5, 2),
                "alasan": f"Harga mendekati Demand Zone {demand['bottom']} - {demand['top']}"}

    for ufo in ufo_list:
        if ufo["tipe"] == "BULLISH" and 0 <= harga - ufo["level"] <= toleransi * 8:
            sl = round(ufo["level"] - 8, 2)
            return {"arah": "BUY", "entry": harga, "sl": sl,
                    "tp1": round(harga + (harga - sl) * 1.5, 2), "tp2": round(harga + (harga - sl) * 2.5, 2),
                    "alasan": f"UFO Bullish di zona {ufo['zona']}"}
    return None


def format_pesan(signal: dict, harga: float, ufo_list: list, waktu_wib: str) -> str:
    emoji = "✅ BUY" if signal["arah"] == "BUY" else "⭕ SELL"
    ufo_txt = ""
    for i, u in enumerate(ufo_list, 1):
        emo = "🔴" if u["tipe"] == "BEARISH" else "🟢"
        ufo_txt += f"   {emo} UFO \\#{i} \\({u['tipe']}\\) : {u['zona']}\n"
    if not ufo_txt:
        ufo_txt = "   Tidak ada UFO terdeteksi\n"

    return (
        f"📊 *SIGNAL MARKET*       : `XAUUSD`\n"
        f"⏰ *Waktu Analisis*      : `{waktu_wib}` WIB\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Harga Sekarang*      : `{harga}`\n"
        f"💰 *Harga Entry \\(15M\\)* : `{signal['entry']}`\n"
        f"📈 *Rekomendasi*         : *{emoji}*\n"
        f"🛑 *Stop Loss*           : `{signal['sl']}`\n"
        f"🎯 *Take Profit 1*       : `{signal['tp1']}`\n"
        f"🎯 *Take Profit 2*       : `{signal['tp2']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🗺️ *Area UFO Terdeteksi* :\n{ufo_txt}"
        f"📌 *Alasan Signal* :\n"
        f"   _{signal['alasan']}_\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _Gunakan manajemen risiko yang ketat_"
    )


def kirim_telegram(pesan: str) -> bool:
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "message_thread_id": TOPIC_ID,
            "text": pesan, "parse_mode": "MarkdownV2"}
    try:
        r = requests.post(url, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log.error(f"Gagal kirim: {e}")
        return False


def jalankan_signal_engine():
    """Thread terpisah untuk signal engine otomatis."""
    log.info("🔄 Signal Engine thread dimulai...")
    signal_terakhir = None

    while True:
        tunggu = CANDLE_SEC - (int(time.time()) % CANDLE_SEC)
        log.info(f"⏳ Candle berikutnya dalam {tunggu} detik...")
        time.sleep(tunggu + 2)

        sekarang_wib = datetime.now(TIMEZONE)
        jam_sekarang = sekarang_wib.hour
        waktu_str    = sekarang_wib.strftime("%Y-%m-%d %H:%M")

        if not (JAM_MULAI <= jam_sekarang < JAM_SELESAI):
            log.info(f"😴 Di luar jam trading ({sekarang_wib.strftime('%H:%M')} WIB).")
            continue

        try:
            df       = ambil_data_twelvedata()
            sd       = deteksi_supply_demand(df)
            ufo_list = deteksi_ufo(df)
            signal   = tentukan_signal(sd, ufo_list)

            if signal:
                kunci = f"{signal['arah']}-{signal['entry']}"
                if kunci != signal_terakhir:
                    pesan = format_pesan(signal, sd["harga"], ufo_list, waktu_str)
                    if kirim_telegram(pesan):
                        log.info(f"✅ Signal {signal['arah']} dikirim ke topik {TOPIC_ID}")
                        signal_terakhir = kunci
            else:
                log.info("💤 Tidak ada signal valid.")

        except Exception as e:
            log.error(f"❌ Error signal engine: {e}")

        time.sleep(5)


# ══════════════════════════════════════════
#  MAIN — Jalankan keduanya bersamaan
# ══════════════════════════════════════════

def main():
    log.info("🚀 Mie_Bot 1.0 starting...")

    # Jalankan signal engine di thread terpisah
    thread = threading.Thread(target=jalankan_signal_engine, daemon=True)
    thread.start()
    log.info("✅ Signal Engine berjalan di background")

    # Jalankan bot Telegram di thread utama
    log.info("✅ Bot Telegram aktif — siap terima /start")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
