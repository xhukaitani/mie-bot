#!/usr/bin/env python3
"""
Signal Engine XAUUSD — Supply & Demand + UFO Otomatis
Berjalan setiap candle 15M close, kirim signal ke Telegram
"""

import time
import logging
import asyncio
from datetime import datetime, timezone

import yfinance as yf
import pandas as pd
import requests

# ─────────────────────────────────────────
#  KONFIGURASI — sesuaikan dengan milikmu
# ─────────────────────────────────────────
BOT_TOKEN   = "8973783812:AAE4iXqQ-hWnVpzToGjn2oOcwomfcY_K5hA"
CHAT_ID     = "8312672148"   # cara dapat: kirim pesan ke @userinfobot
SYMBOL      = "GC=F"                    # Gold Futures (XAUUSD di Yahoo Finance)
INTERVAL    = "15m"
PERIOD      = "5d"
CANDLE_SEC  = 15 * 60                   # 15 menit dalam detik

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════
#  FUNGSI AMBIL DATA
# ══════════════════════════════════════════

def ambil_data() -> pd.DataFrame:
    """Ambil data candle XAUUSD 15M dari Yahoo Finance."""
    df = yf.download(SYMBOL, interval=INTERVAL, period=PERIOD, progress=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


# ══════════════════════════════════════════
#  DETEKSI SUPPLY & DEMAND ZONE
# ══════════════════════════════════════════

def deteksi_supply_demand(df: pd.DataFrame) -> dict:
    """
    Logika Supply & Demand:
    - SUPPLY ZONE : candle bearish besar (body > rata-rata) diikuti drop
    - DEMAND ZONE : candle bullish besar (body > rata-rata) diikuti pump
    Cek 50 candle terakhir.
    """
    lookback = df.tail(50).copy()
    lookback["body"] = abs(lookback["Close"] - lookback["Open"])
    avg_body = lookback["body"].mean()

    supply_zones = []
    demand_zones = []

    for i in range(1, len(lookback) - 1):
        candle  = lookback.iloc[i]
        sebelum = lookback.iloc[i - 1]
        sesudah = lookback.iloc[i + 1]
        body    = candle["body"]

        # SUPPLY: candle bearish besar + candle berikutnya juga turun
        if (candle["Close"] < candle["Open"]
                and body > avg_body * 1.5
                and sesudah["Close"] < candle["Close"]):
            supply_zones.append({
                "top"   : round(candle["High"], 2),
                "bottom": round(candle["Open"], 2),
            })

        # DEMAND: candle bullish besar + candle berikutnya juga naik
        if (candle["Close"] > candle["Open"]
                and body > avg_body * 1.5
                and sesudah["Close"] > candle["Close"]):
            demand_zones.append({
                "top"   : round(candle["Close"], 2),
                "bottom": round(candle["Low"],   2),
            })

    # Ambil yang paling dekat harga saat ini
    harga_kini = float(df["Close"].iloc[-1])

    supply = sorted(
        [z for z in supply_zones if z["bottom"] > harga_kini],
        key=lambda z: z["bottom"]
    )
    demand = sorted(
        [z for z in demand_zones if z["top"] < harga_kini],
        key=lambda z: z["top"],
        reverse=True,
    )

    return {
        "harga"  : round(harga_kini, 2),
        "supply" : supply[0]  if supply  else None,
        "demand" : demand[0]  if demand  else None,
    }


# ══════════════════════════════════════════
#  DETEKSI UFO (Unfulfilled Order Block)
# ══════════════════════════════════════════

def deteksi_ufo(df: pd.DataFrame) -> list:
    """
    UFO = Order Block yang belum di-retest:
    - Candle impulsif besar (body > 2x rata-rata)
    - High/Low candle tersebut belum pernah disentuh harga setelahnya
    """
    lookback  = df.tail(100).copy()
    lookback["body"] = abs(lookback["Close"] - lookback["Open"])
    avg_body  = lookback["body"].mean()
    harga_kini = float(df["Close"].iloc[-1])
    ufo_list  = []

    for i in range(len(lookback) - 20):
        candle = lookback.iloc[i]
        sisa   = lookback.iloc[i + 1:]

        if candle["body"] < avg_body * 2:
            continue

        # UFO BEARISH (di atas harga sekarang — belum disentuh dari bawah)
        if candle["Close"] < candle["Open"]:
            level = round(candle["Open"], 2)
            if level > harga_kini:
                pernah_disentuh = (sisa["High"] >= level).any()
                if not pernah_disentuh:
                    ufo_list.append({
                        "tipe" : "BEARISH",
                        "level": level,
                        "zona" : f"{round(candle['Low'],2)} – {level}",
                    })

        # UFO BULLISH (di bawah harga sekarang — belum disentuh dari atas)
        if candle["Close"] > candle["Open"]:
            level = round(candle["Open"], 2)
            if level < harga_kini:
                pernah_disentuh = (sisa["Low"] <= level).any()
                if not pernah_disentuh:
                    ufo_list.append({
                        "tipe" : "BULLISH",
                        "level": level,
                        "zona" : f"{level} – {round(candle['High'],2)}",
                    })

    # Urutkan: UFO terdekat dengan harga saat ini di atas
    ufo_list = sorted(ufo_list, key=lambda u: abs(u["level"] - harga_kini))
    return ufo_list[:3]   # maks 3 UFO terdekat


# ══════════════════════════════════════════
#  TENTUKAN ARAH SIGNAL
# ══════════════════════════════════════════

def tentukan_signal(sd: dict, ufo_list: list) -> dict | None:
    """
    Logika signal:
    - SELL jika harga dekat/di dalam supply zone atau UFO bearish
    - BUY  jika harga dekat/di dalam demand zone atau UFO bullish
    """
    harga  = sd["harga"]
    supply = sd["supply"]
    demand = sd["demand"]

    # Jarak toleransi: 0.3% dari harga
    toleransi = harga * 0.003

    # --- CEK SELL ---
    if supply:
        jarak_supply = supply["bottom"] - harga
        if 0 <= jarak_supply <= toleransi * 10:
            entry = round((supply["top"] + supply["bottom"]) / 2, 2)
            sl    = round(supply["top"] + 5, 2)
            tp1   = round(harga - (sl - entry) * 1.5, 2)
            tp2   = round(harga - (sl - entry) * 2.5, 2)
            return {
                "arah"  : "SELL",
                "entry" : entry,
                "sl"    : sl,
                "tp1"   : tp1,
                "tp2"   : tp2,
                "alasan": f"Harga mendekati Supply Zone {supply['bottom']} – {supply['top']}",
            }

    # --- CEK UFO BEARISH ---
    for ufo in ufo_list:
        if ufo["tipe"] == "BEARISH":
            jarak = ufo["level"] - harga
            if 0 <= jarak <= toleransi * 8:
                sl  = round(ufo["level"] + 8, 2)
                tp1 = round(harga - (sl - harga) * 1.5, 2)
                tp2 = round(harga - (sl - harga) * 2.5, 2)
                return {
                    "arah"  : "SELL",
                    "entry" : harga,
                    "sl"    : sl,
                    "tp1"   : tp1,
                    "tp2"   : tp2,
                    "alasan": f"UFO Bearish terdeteksi di zona {ufo['zona']}",
                }

    # --- CEK BUY ---
    if demand:
        jarak_demand = harga - demand["top"]
        if 0 <= jarak_demand <= toleransi * 10:
            entry = round((demand["top"] + demand["bottom"]) / 2, 2)
            sl    = round(demand["bottom"] - 5, 2)
            tp1   = round(harga + (entry - sl) * 1.5, 2)
            tp2   = round(harga + (entry - sl) * 2.5, 2)
            return {
                "arah"  : "BUY",
                "entry" : entry,
                "sl"    : sl,
                "tp1"   : tp1,
                "tp2"   : tp2,
                "alasan": f"Harga mendekati Demand Zone {demand['bottom']} – {demand['top']}",
            }

    # --- CEK UFO BULLISH ---
    for ufo in ufo_list:
        if ufo["tipe"] == "BULLISH":
            jarak = harga - ufo["level"]
            if 0 <= jarak <= toleransi * 8:
                sl  = round(ufo["level"] - 8, 2)
                tp1 = round(harga + (harga - sl) * 1.5, 2)
                tp2 = round(harga + (harga - sl) * 2.5, 2)
                return {
                    "arah"  : "BUY",
                    "entry" : harga,
                    "sl"    : sl,
                    "tp1"   : tp1,
                    "tp2"   : tp2,
                    "alasan": f"UFO Bullish terdeteksi di zona {ufo['zona']}",
                }

    return None   # Tidak ada signal valid


# ══════════════════════════════════════════
#  KIRIM KE TELEGRAM
# ══════════════════════════════════════════

def kirim_telegram(pesan: str) -> bool:
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id"   : CHAT_ID,
        "text"      : pesan,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log.error(f"Gagal kirim Telegram: {e}")
        return False


def format_pesan(signal: dict, harga: float, ufo_list: list) -> str:
    waktu  = datetime.now().strftime("%Y-%m-%d %H:%M")
    emoji  = "✅ BUY" if signal["arah"] == "BUY" else "⭕ SELL"

    ufo_txt = ""
    for i, u in enumerate(ufo_list, 1):
        emo = "🔴" if u["tipe"] == "BEARISH" else "🟢"
        ufo_txt += f"   {emo} UFO #{i} ({u['tipe']}) : `{u['zona']}`\n"
    if not ufo_txt:
        ufo_txt = "   _Tidak ada UFO terdeteksi_\n"

    return (
        f"📊 *SIGNAL MARKET*       : `XAUUSD`\n"
        f"⏰ *Waktu Analisis*      : `{waktu}`\n"
        f"💰 *Harga Sekarang*      : `{harga}`\n"
        f"💰 *Harga Entry (15M)*   : `{signal['entry']}`\n"
        f"📈 *Rekomendasi*         : *{emoji}*\n"
        f"🛑 *Stop Loss*           : `{signal['sl']}`\n"
        f"🎯 *Take Profit 1*       : `{signal['tp1']}`\n"
        f"🎯 *Take Profit 2*       : `{signal['tp2']}`\n"
        f"\n"
        f"🗺️ *Area UFO Terdeteksi* :\n{ufo_txt}"
        f"\n"
        f"📌 *Alasan Signal* :\n"
        f"   _{signal['alasan']}_\n"
        f"\n"
        f"⚠️ _Gunakan manajemen risiko yang ketat\\!_"
    )


# ══════════════════════════════════════════
#  LOOP UTAMA — Jalan setiap candle close
# ══════════════════════════════════════════

def detik_ke_candle_berikutnya() -> int:
    """Hitung sisa detik sampai candle 15M berikutnya close."""
    sekarang = int(time.time())
    sisa     = CANDLE_SEC - (sekarang % CANDLE_SEC)
    return sisa


def main():
    log.info("🚀 Signal Engine XAUUSD aktif — Supply & Demand + UFO")
    log.info(f"   Simbol  : {SYMBOL}")
    log.info(f"   Interval: {INTERVAL}")
    log.info("   Menunggu candle 15M berikutnya...\n")

    signal_terakhir = None   # hindari duplikat signal berturutan

    while True:
        tunggu = detik_ke_candle_berikutnya()
        log.info(f"⏳ Candle berikutnya close dalam {tunggu} detik...")
        time.sleep(tunggu + 2)   # +2 detik buffer agar data sudah update

        try:
            log.info("📥 Mengambil data candle terbaru...")
            df      = ambil_data()
            sd      = deteksi_supply_demand(df)
            ufo_list= deteksi_ufo(df)
            signal  = tentukan_signal(sd, ufo_list)

            log.info(f"   Harga   : {sd['harga']}")
            log.info(f"   Supply  : {sd['supply']}")
            log.info(f"   Demand  : {sd['demand']}")
            log.info(f"   UFO     : {ufo_list}")

            if signal:
                # Hindari kirim signal yang sama berulang
                kunci = f"{signal['arah']}-{signal['entry']}"
                if kunci != signal_terakhir:
                    pesan = format_pesan(signal, sd["harga"], ufo_list)
                    log.info(f"📤 Mengirim signal {signal['arah']} ke Telegram...")
                    if kirim_telegram(pesan):
                        log.info("✅ Signal berhasil dikirim!")
                        signal_terakhir = kunci
                    else:
                        log.warning("⚠️ Gagal kirim ke Telegram.")
                else:
                    log.info("ℹ️  Signal sama dengan sebelumnya, tidak dikirim ulang.")
            else:
                log.info("💤 Tidak ada signal valid saat ini.")

        except Exception as e:
            log.error(f"❌ Error: {e}")

        time.sleep(5)


if __name__ == "__main__":
    main()
