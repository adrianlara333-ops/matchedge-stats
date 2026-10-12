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
    ContextTypes,
    MessageHandler,
    filters,
)

# === CONFIGURACIÓN TELEGRAM ===
TOKEN = "8343705082:AAFiV6ZTR4y7WiA1uABk5DgnW1uiCuq2JpM"
CANAL_ID = -1004419997961
ADMIN_ID = 1582610498

# === SERVIDOR WEB PARA EVITAR EL TIMEOUT EN RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MatchEdge Bot is running!")

    def log_message(self, format, *args):
        # Silenciar logs continuos del servidor web
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
    fecha TEXT,
    evento TEXT,
    pick TEXT,
    cuota REAL,
    stake REAL DEFAULT 1.0,
    estado TEXT DEFAULT 'PENDIENTE'
)"""
)
conn.commit()

# === CAPTURA DE PICKS DESDE EL CANAL ===
async def capturar_pick_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post or update.channel_post.chat.id != CANAL_ID:
        return

    texto = update.channel_post.text or update.channel_post.caption or ""

    if "Odds:" in texto and "Pick:" in texto:
        evento_match = re.search(r"⚽\s*(.+)", texto) or re.search(
            r"([A-Za-z0-9\s]+vs[A-Za-z0-9\s]+)", texto
        )
        pick_match = re.search(r"Pick:\s*(.+)", texto)
        cuota_match = re.search(r"Odds:\s*([\d\.]+)", texto)

        evento = evento_match.group(1).strip() if evento_match else "Evento"
        pick = pick_match.group(1).strip() if pick_match else "Pick"
        cuota = float(cuota_match.group(1).strip()) if cuota_match else 1.00
        fecha = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            "INSERT INTO picks (fecha, evento, pick, cuota, estado) VALUES (?, ?, ?, ?, 'PENDIENTE')",
            (fecha, evento, pick, cuota),
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
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🎯 *Nuevo pick registrado en MatchEdge*\n\n"
                f"📌 *Evento:* {evento}\n"
                f"▫️ *Pick:* {pick}\n"
                f"▫️ *Cuota:* {cuota}\n\n"
                f"Selecciona el resultado al finalizar:"
            ),
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

# === BOTONES DE RESULTADO ===
async def boton_resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    accion, pick_id = query.data.split("_")
    estado = (
        "GANADA" if accion == "win" else "PERDIDA" if accion == "loss" else "NULA"
    )

    cursor.execute("UPDATE picks SET estado = ? WHERE id = ?", (estado, pick_id))
    conn.commit()

    emoji = "✅" if estado == "GANADA" else "❌" if estado == "PERDIDA" else "⚪"
    await query.edit_message_text(
        text=f"{query.message.text}\n\n*Resultado fijado:* {emoji} {estado}",
        parse_mode="Markdown",
    )

# === INICIALIZACIÓN ===
if __name__ == "__main__":
    # Inicia el micro servidor web para que Render detecte el puerto
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    # Inicia el bot de Telegram
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, capturar_pick_canal))
    app.add_handler(CallbackQueryHandler(boton_resultado))
    print("MatchEdge Bot iniciado...")
    app.run_polling()

