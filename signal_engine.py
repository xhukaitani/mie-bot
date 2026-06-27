#!/usr/bin/env python3
"""
Signal Engine XAUUSD — Supply & Demand + UFO Otomatis
Sumber data : Twelve Data API (realtime, sesuai TradingView)
Tujuan      : Grup Telegram topik tertentu
Update      : Setiap 5 menit
Jam aktif   : 06:00 - 02:00 WIB (Senin - Jumat)
OFF         : Sabtu & Minggu
"""

import time
import logging
from datetime import datetime
import pytz
import pandas as pd
import requests

# ─────────────────────────────────────────
#  KONFIGURASI
# ─────────────────────────────────────────
BOT_TOKEN      = "8973783812:AAE4iXqQ-hWnVpzToGjn2oOcwomfcY_K5hA"
CHAT_ID        = "-1004410608338"
TOPIC_ID       = 4
TWELVE_API_KEY = "dbb5e1da912149f4ba5d518591d6ac47"
SYMBOL         = "XAU/USD"
INTERVAL       = "15min"
INTERVAL_CEK   = 5 * 60        # cek setiap 5 menit
JAM_MULAI      = 6             # 06:00 WIB
JAM_SELESAI    = 2             # 02:00 WIB (dini hari)
TIMEZONE       = pytz.timezone("Asia/Jakarta")

HARI_NAMA = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════
#  CEK JAM AKTIF
# ══════════════════════════════════════════

def jam_aktif() -> bool:
    """
    Aktif dari jam 06:00 sampai 02:00 WIB (melewati tengah malam).
    OFF penuh pada hari Sabtu (5) dan Minggu (6).
    """
    sekarang = datetime.now(TIMEZONE)
    hari     = sekarang.weekday()  # 0=Senin, 1=Selasa, ..., 5=Sabtu, 6=Minggu
    jam      = sekarang.hour

    # ── Sabtu & Minggu → selalu OFF ──
    if hari >= 5:
        return False

    # ── Senin–Jumat → cek rentang jam aktif ──
    return jam >= JAM_MULAI or jam < JAM_SELESAI


# ══════════════════════════════════════════
#  AMBIL DATA DARI TWELVE DATA
# ══════════════════════════════════════════

def ambil_data() -> pd.DataFrame:
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
        raise ValueError(f"Twelve Data error: {data.get('message', 'Unknown error')}")

    rows = []
    for v in reversed(data["values"]):
        rows.append({
            "Open" : float(v["open"]),
            "High" : float(v["high"]),
            "Low"  : float(v["low"]),
            "Close": float(v["close"]),
        })

    df = pd.DataFrame(rows)
    log.info(f"Data OK — {len(df)} candle, harga terakhir: {df['Close'].iloc[-1]}")
    return df


# ══════════════════════════════════════════
#  DETEKSI SUPPLY & DEMAND ZONE
# ══════════════════════════════════════════

def deteksi_supply_demand(df: pd.DataFrame) -> dict:
    lookback         = df.tail(50).copy()
    lookback["body"] = abs(lookback["Close"] - lookback["Open"])
    avg_body         = lookback["body"].mean()
    supply_zones     = []
    demand_zones     = []

    for i in range(1, len(lookback) - 1):
        candle  = lookback.iloc[i]
        sesudah = lookback.iloc[i + 1]
        body    = candle["body"]

        if (candle["Close"] < candle["Open"]
                and body > avg_body * 1.5
                and sesudah["Close"] < candle["Close"]):
            supply_zones.append({
                "top"   : round(candle["High"], 2),
                "bottom": round(candle["Open"], 2),
            })

        if (candle["Close"] > candle["Open"]
                and body > avg_body * 1.5
                and sesudah["Close"] > candle["Close"]):
            demand_zones.append({
                "top"   : round(candle["Close"], 2),
                "bottom": round(candle["Low"],   2),
            })

    harga_kini = float(df["Close"].iloc[-1])
    supply = sorted([z for z in supply_zones if z["bottom"] > harga_kini], key=lambda z: z["bottom"])
    demand = sorted([z for z in demand_zones if z["top"] < harga_kini], key=lambda z: z["top"], reverse=True)

    return {
        "harga" : round(harga_kini, 2),
        "supply": supply[0] if supply else None,
        "demand": demand[0] if demand else None,
    }


# ══════════════════════════════════════════
#  DETEKSI UFO (Unfulfilled Order Block)
# ══════════════════════════════════════════

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
                ufo_list.append({
                    "tipe" : "BEARISH",
                    "level": level,
                    "zona" : f"{round(candle['Low'],2)} - {level}",
                })

        if candle["Close"] > candle["Open"]:
            level = round(candle["Open"], 2)
            if level < harga_kini and not (sisa["Low"] <= level).any():
                ufo_list.append({
                    "tipe" : "BULLISH",
                    "level": level,
                    "zona" : f"{level} - {round(candle['High'],2)}",
                })

    return sorted(ufo_list, key=lambda u: abs(u["level"] - harga_kini))[:3]


# ══════════════════════════════════════════
#  TENTUKAN ARAH SIGNAL
# ══════════════════════════════════════════

def tentukan_signal(sd: dict, ufo_list: list) -> dict | None:
    harga     = sd["harga"]
    supply    = sd["supply"]
    demand    = sd["demand"]
    toleransi = harga * 0.003

    if supply and 0 <= supply["bottom"] - harga <= toleransi * 10:
        entry = round((supply["top"] + supply["bottom"]) / 2, 2)
        sl    = round(supply["top"] + 5, 2)
        return {"arah": "SELL", "entry": entry, "sl": sl,
                "tp1": round(harga - (sl - entry) * 1.5, 2),
                "tp2": round(harga - (sl - entry) * 2.5, 2),
                "alasan": f"Harga mendekati Supply Zone {supply['bottom']} - {supply['top']}"}

    for ufo in ufo_list:
        if ufo["tipe"] == "BEARISH" and 0 <= ufo["level"] - harga <= toleransi * 8:
            sl = round(ufo["level"] + 8, 2)
            return {"arah": "SELL", "entry": harga, "sl": sl,
                    "tp1": round(harga - (sl - harga) * 1.5, 2),
                    "tp2": round(harga - (sl - harga) * 2.5, 2),
                    "alasan": f"UFO Bearish di zona {ufo['zona']}"}

    if demand and 0 <= harga - demand["top"] <= toleransi * 10:
        entry = round((demand["top"] + demand["bottom"]) / 2, 2)
        sl    = round(demand["bottom"] - 5, 2)
        return {"arah": "BUY", "entry": entry, "sl": sl,
                "tp1": round(harga + (entry - sl) * 1.5, 2),
                "tp2": round(harga + (entry - sl) * 2.5, 2),
                "alasan": f"Harga mendekati Demand Zone {demand['bottom']} - {demand['top']}"}

    for ufo in ufo_list:
        if ufo["tipe"] == "BULLISH" and 0 <= harga - ufo["level"] <= toleransi * 8:
            sl = round(ufo["level"] - 8, 2)
            return {"arah": "BUY", "entry": harga, "sl": sl,
                    "tp1": round(harga + (harga - sl) * 1.5, 2),
                    "tp2": round(harga + (harga - sl) * 2.5, 2),
                    "alasan": f"UFO Bullish di zona {ufo['zona']}"}

    return None


# ══════════════════════════════════════════
#  FORMAT PESAN
# ══════════════════════════════════════════

def format_pesan_signal(signal: dict, harga: float, ufo_list: list) -> str:
    waktu = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    emoji = "✅ BUY" if signal["arah"] == "BUY" else "⭕ SELL"

    ufo_txt = ""
    for i, u in enumerate(ufo_list, 1):
        emo = "🔴" if u["tipe"] == "BEARISH" else "🟢"
        ufo_txt += f"   {emo} UFO #{i} ({u['tipe']}) : {u['zona']}\n"
    if not ufo_txt:
        ufo_txt = "   Tidak ada UFO terdeteksi\n"

    return (
        f"📊 SIGNAL MARKET       : XAUUSD\n"
        f"⏰ Waktu Analisis      : {waktu} WIB\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Harga Sekarang      : {harga}\n"
        f"💰 Harga Entry (15M)   : {signal['entry']}\n"
        f"📈 Rekomendasi         : {emoji}\n"
        f"🛑 Stop Loss           : {signal['sl']}\n"
        f"🎯 Take Profit 1       : {signal['tp1']}\n"
        f"🎯 Take Profit 2       : {signal['tp2']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🗺️ Area UFO Terdeteksi :\n{ufo_txt}"
        f"📌 Alasan Signal :\n"
        f"   {signal['alasan']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Gunakan manajemen risiko yang ketat!"
    )


def format_pesan_sama(signal: dict, harga: float) -> str:
    waktu = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    emoji = "✅ BUY" if signal["arah"] == "BUY" else "⭕ SELL"

    return (
        f"🔁 KONFIRMASI SIGNAL   : XAUUSD\n"
        f"⏰ Update              : {waktu} WIB\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Harga Sekarang      : {harga}\n"
        f"📈 Rekomendasi         : {emoji}\n"
        f"💰 Entry               : {signal['entry']}\n"
        f"🛑 Stop Loss           : {signal['sl']}\n"
        f"🎯 Take Profit 1       : {signal['tp1']}\n"
        f"🎯 Take Profit 2       : {signal['tp2']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Signal masih berlaku — tidak ada perubahan setup.\n"
        f"   Tetap ikuti rencana trading sebelumnya."
    )


# ══════════════════════════════════════════
#  KIRIM KE TELEGRAM
# ══════════════════════════════════════════

def kirim_telegram(pesan: str) -> bool:
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id"           : CHAT_ID,
        "message_thread_id" : TOPIC_ID,
        "text"              : pesan,
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            return True
        log.error(f"Telegram error: {r.text}")
        return False
    except Exception as e:
        log.error(f"Gagal kirim: {e}")
        return False


# ══════════════════════════════════════════
#  LOOP UTAMA
# ══════════════════════════════════════════

def main():
    log.info("🚀 Mie_Bot Signal Engine aktif!")
    log.info(f"   Sumber data : Twelve Data API (realtime)")
    log.info(f"   Simbol      : {SYMBOL}")
    log.info(f"   Grup ID     : {CHAT_ID}")
    log.info(f"   Topik ID    : {TOPIC_ID}")
    log.info(f"   Update      : Setiap 5 menit")
    log.info(f"   Jam aktif   : 06:00 - 02:00 WIB (Senin - Jumat)")
    log.info(f"   OFF         : Sabtu & Minggu (seharian)")

    signal_terakhir = None  # simpan signal terakhir untuk perbandingan

    while True:
        sekarang_wib = datetime.now(TIMEZONE)
        waktu_str    = sekarang_wib.strftime("%H:%M")
        hari_str     = HARI_NAMA[sekarang_wib.weekday()]

        # ── CEK JAM AKTIF ──
        if not jam_aktif():
            log.info(f"😴 Di luar jam aktif — {hari_str} {waktu_str} WIB. Bot istirahat.")
            time.sleep(INTERVAL_CEK)
            continue

        log.info(f"🔍 Mulai analisa — {hari_str} {waktu_str} WIB")

        try:
            df       = ambil_data()
            sd       = deteksi_supply_demand(df)
            ufo_list = deteksi_ufo(df)
            signal   = tentukan_signal(sd, ufo_list)

            log.info(f"   Harga  : {sd['harga']}")
            log.info(f"   Supply : {sd['supply']}")
            log.info(f"   Demand : {sd['demand']}")

            if signal:
                kunci = f"{signal['arah']}-{signal['entry']}"

                if kunci != signal_terakhir:
                    # ── SIGNAL BARU ──
                    pesan = format_pesan_signal(signal, sd["harga"], ufo_list)
                    if kirim_telegram(pesan):
                        log.info(f"✅ Signal BARU {signal['arah']} dikirim!")
                        signal_terakhir = kunci

                else:
                    # ── SIGNAL SAMA — tetap kirim konfirmasi ──
                    pesan = format_pesan_sama(signal, sd["harga"])
                    if kirim_telegram(pesan):
                        log.info(f"🔁 Konfirmasi signal {signal['arah']} dikirim (sama seperti sebelumnya).")

            else:
                log.info("💤 Tidak ada signal valid saat ini.")
                signal_terakhir = None  # reset jika tidak ada signal

        except Exception as e:
            log.error(f"❌ Error: {e}")

        log.info(f"⏳ Menunggu 5 menit untuk analisa berikutnya...\n")
        time.sleep(INTERVAL_CEK)


if __name__ == "__main__":
    main()
