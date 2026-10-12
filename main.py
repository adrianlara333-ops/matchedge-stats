import os
import re
import sqlite3
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# === CONFIGURACIÓN TELEGRAM ===
TOKEN = "8343705082:AAFiV6ZTR4y7WiA1uABk5DgnW1uiCuq2JpM"
CANAL_ID = -1004419997961
ADMIN_ID = 1582610498

# === SERVIDOR WEB PARA RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MatchEdge Bot is running!")

    def log_message(self, format, *args):
        pass

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# === BASE DE DATOS ===
conn = sqlite3.connect("matchedge_stats.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    """CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id INTEGER UNIQUE,
    fecha TEXT,
    evento TEXT,
    pick TEXT,
    cuota REAL,
    stake REAL DEFAULT 1.0,
    estado TEXT DEFAULT 'PENDIENTE'
)"""
)
conn.commit()

def procesar_texto_pick(texto: str):
    if not ("pick" in texto.lower() and "odds" in texto.lower()):
        return None

    evento_match = re.search(r"(?:⚽|\b)([A-Za-z0-9\s\.\-]+vs[A-Za-z0-9\s\.\-]+)", texto, re.IGNORECASE)
    pick_match = re.search(r"Pick:\s*([^\n\r]+)", texto, re.IGNORECASE)
    cuota_match = re.search(r"Odds:\s*([\d\.]+)", texto, re.IGNORECASE)
    stake_match = re.search(r"Stake:\s*([\d\.\/]+)", texto, re.IGNORECASE)

    evento = evento_match.group(1).strip() if evento_match else "Evento MatchEdge"
    pick = pick_match.group(1).strip() if pick_match else "Pronóstico"
    cuota = float(cuota_match.group(1).strip()) if cuota_match else 1.00

    stake_val = 1.0
    if stake_match:
        st_raw = stake_match.group(1).split("/")[0].strip()
        try:
            stake_val = float(st_raw)
        except ValueError:
            stake_val = 1.0

    return evento, pick, cuota, stake_val

# === COMANDO START ===
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *MatchEdge Stats Bot conectado.*\n\n"
        "Comandos disponibles:\n"
        "• `/stats` - Ver balance, yield y resumen histórico.\n"
        "• `/add <texto>` - Registrar un pick individual.\n"
        "• `/import <bloques>` - Importar varios picks juntos separados por `---`.\n\n"
        "Cualquier pick publicado en el canal oficial se detectará automáticamente.",
        parse_mode="Markdown",
    )

# === COMANDO STATS ===
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT estado, cuota, stake FROM picks")
    registros = cursor.fetchall()

    if not registros:
        await update.message.reply_text("📊 Aún no hay picks registrados en la base de datos.")
        return

    total = len(registros)
    ganadas = sum(1 for r in registros if r[0] == "GANADA")
    perdidas = sum(1 for r in registros if r[0] == "PERDIDA")
    nulas = sum(1 for r in registros if r[0] == "NULA")
    pendientes = sum(1 for r in registros if r[0] == "PENDIENTE")

    beneficio = 0.0
    stake_total = 0.0

    for estado, cuota, stake in registros:
        if estado == "GANADA":
            beneficio += (cuota - 1.0) * stake
            stake_total += stake
        elif estado == "PERDIDA":
            beneficio -= stake
            stake_total += stake
        elif estado == "NULA":
            stake_total += stake

    winrate = (ganadas / (ganadas + perdidas) * 100) if (ganadas + perdidas) > 0 else 0.0
    yield_val = (beneficio / stake_total * 100) if stake_total > 0 else 0.0

    msg = (
        f"📊 *ESTADÍSTICAS MATCHEDGE*\n\n"
        f"🔹 *Total picks:* {total}\n"
        f"✅ *Ganadas:* {ganadas}\n"
        f"❌ *Perdidas:* {perdidas}\n"
        f"⚪ *Nulas:* {nulas}\n"
        f"⏳ *Pendientes:* {pendientes}\n\n"
        f"🎯 *Winrate:* {winrate:.1f}%\n"
        f"📈 *Yield:* {yield_val:+.2f}%\n"
        f"💰 *Beneficio neto:* {beneficio:+.2f} uds"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# === REGISTRO MANUAL INDIVIDUAL ===
async def add_manual_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.replace("/add", "").strip()
    datos = procesar_texto_pick(texto)

    if not datos:
        await update.message.reply_text(
            "⚠️ Formato incorrecto. Debe incluir al menos `Pick:` y `Odds:`.\n\n"
            "Ejemplo:\n`/add Levante vs Sevilla\nPick: Ambos marcan\nOdds: 1.80`",
            parse_mode="Markdown",
        )
        return

    evento, pick, cuota, stake = datos
    fecha = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO picks (msg_id, fecha, evento, pick, cuota, stake, estado) VALUES (NULL, ?, ?, ?, ?, ?, 'PENDIENTE')",
        (fecha, evento, pick, cuota, stake),
    )
    pick_id = cursor.lastrowid
    conn.commit()

    keyboard = [
        [
            InlineKeyboardButton("✅ Ganada", callback_data=f"win_{pick_id}"),
            InlineKeyboardButton("❌ Perdida", callback_data=f"loss_{pick_id}"),
            InlineKeyboardButton("⚪ Nula", callback_data=f"void_{pick_id}"),
        ]
    ]
    await update.message.reply_text(
        f"📌 *Pick añadido manualmente (ID #{pick_id})*\n\n"
        f"⚽ *Evento:* {evento}\n"
        f"▫️ *Pick:* {pick}\n"
        f"▫️ *Cuota:* {cuota}\n"
        f"▫️ *Stake:* {stake}\n\n"
        f"Elige el resultado:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

# === REGISTRO MASIVO (/import) ===
async def import_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.replace("/import", "").strip()
    bloques = [b.strip() for b in texto.split("---") if b.strip()]

    fecha = datetime.now().strftime("%Y-%m-%d")
    contador = 0

    for b in bloques:
        evento_m = re.search(r"(?:⚽|\b)([A-Za-z0-9\s\.\-\&\(\)]+vs[A-Za-z0-9\s\.\-\&\(\)]+|[A-Za-z0-9\s\.\-]+)", b)
        pick_m = re.search(r"Pick:\s*([^\n\r]+)", b, re.IGNORECASE)
        cuota_m = re.search(r"Odds:\s*([\d\.]+)", b, re.IGNORECASE)
        estado_m = re.search(r"Status:\s*(GANADA|PERDIDA|NULA|PENDIENTE)", b, re.IGNORECASE)

        if pick_m and cuota_m:
            evento = evento_m.group(1).strip() if evento_m else "Pick Histórico"
            pick = pick_m.group(1).strip()
            cuota = float(cuota_m.group(1).strip())
            estado = estado_m.group(1).upper() if estado_m else "GANADA"

            cursor.execute(
                "INSERT INTO picks (msg_id, fecha, evento, pick, cuota, stake, estado) VALUES (NULL, ?, ?, ?, ?, 1.0, ?)",
                (fecha, evento, pick, cuota, estado),
            )
            contador += 1

    conn.commit()
    await update.message.reply_text(
        f"✅ Se han importado {contador} picks históricos correctamente.\nUsa `/stats` para consultar el balance acumulado.",
        parse_mode="Markdown",
    )

# === CAPTURA EN TIEMPO REAL DESDE EL CANAL ===
async def capturar_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post or update.edited_channel_post
    if not post or post.chat.id != CANAL_ID:
        return

    cursor.execute("SELECT id FROM picks WHERE msg_id = ?", (post.message_id,))
    if cursor.fetchone():
        return

    texto = post.text or post.caption or ""
    datos = procesar_texto_pick(texto)
    if not datos:
        return

    evento, pick, cuota, stake = datos
    fecha = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO picks (msg_id, fecha, evento, pick, cuota, stake, estado) VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE')",
        (post.message_id, fecha, evento, pick, cuota, stake),
    )
    pick_id = cursor.lastrowid
    conn.commit()

    keyboard = [
        [
            InlineKeyboardButton("✅ Ganada", callback_data=f"win_{pick_id}"),
            InlineKeyboardButton("❌ Perdida", callback_data=f"loss_{pick_id}"),
            InlineKeyboardButton("⚪ Nula", callback_data=f"void_{pick_id}"),
        ]
    ]

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🎯 *Nuevo pick detectado en el canal*\n\n"
            f"📌 *Evento:* {evento}\n"
            f"▫️ *Pick:* {pick}\n"
            f"▫️ *Cuota:* {cuota}\n"
            f"▫️ *Stake:* {stake}\n\n"
            f"Selecciona el resultado al finalizar:"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

# === BOTONES DE RESULTADO ===
async def boton_resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    accion, pick_id = query.data.split("_")
    estado = "GANADA" if accion == "win" else "PERDIDA" if accion == "loss" else "NULA"

    cursor.execute("UPDATE picks SET estado = ? WHERE id = ?", (estado, pick_id))
    conn.commit()

    emoji = "✅" if estado == "GANADA" else "❌" if estado == "PERDIDA" else "⚪"
    await query.edit_message_text(
        text=f"{query.message.text}\n\n*Resultado fijado:* {emoji} {estado}",
        parse_mode="Markdown",
    )

# === INICIALIZACIÓN ===
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("add", add_manual_cmd))
    app.add_handler(CommandHandler("import", import_cmd))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, capturar_canal))
    app.add_handler(CallbackQueryHandler(boton_resultado))

    print("MatchEdge Bot iniciado...")
    app.run_polling()
