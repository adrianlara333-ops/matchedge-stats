import logging
import re
import sqlite3
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# === CONFIGURACIÓN ===
TOKEN = "8343705082:AAFiV6ZTR4y7WiA1uABk5DgnW1uiCuq2JpM"
CANAL_ID = -1004419997961
ADMIN_ID = 1582610498

# === BASE DE DATOS ===
conn = sqlite3.connect("matchedge_stats.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT,
    evento TEXT,
    pick TEXT,
    cuota REAL,
    stake REAL DEFAULT 1.0,
    estado TEXT DEFAULT 'PENDIENTE'
)''')
conn.commit()

# === 1. CAPTURAR PICKS DEL CANAL ===
async def capturar_pick_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post or update.channel_post.chat.id != CANAL_ID:
        return
    
    texto = update.channel_post.text or update.channel_post.caption or ""
    
    if "Odds:" in texto and "Pick:" in texto:
        evento_match = re.search(r"⚽\s*(.+)", texto) or re.search(r"([A-Za-z0-9\s]+vs[A-Za-z0-9\s]+)", texto)
        pick_match = re.search(r"Pick:\s*(.+)", texto)
        cuota_match = re.search(r"Odds:\s*([\d\.]+)", texto)
        
        evento = evento_match.group(1).strip() if evento_match else "Evento"
        pick = pick_match.group(1).strip() if pick_match else "Pick"
        cuota = float(cuota_match.group(1).strip()) if cuota_match else 1.00
        fecha = datetime.now().strftime("%Y-%m-%d")
        
        cursor.execute("INSERT INTO picks (fecha, evento, pick, cuota, estado) VALUES (?, ?, ?, ?, 'PENDIENTE')",
                       (fecha, evento, pick, cuota))
        pick_id = cursor.lastrowid
        conn.commit()
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Ganada", callback_data=f"win_{pick_id}"),
                InlineKeyboardButton("❌ Perdida", callback_data=f"loss_{pick_id}"),
                InlineKeyboardButton("⚪ Nula", callback_data=f"void_{pick_id}")
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
            parse_mode="Markdown"
        )

# === 2. GESTIONAR BOTONES DE RESULTADO ===
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
        parse_mode="Markdown"
    )

# === INICIALIZACIÓN ===
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, capturar_pick_canal))
    app.add_handler(CallbackQueryHandler(boton_resultado))
    print("MatchEdge Bot iniciado...")
    app.run_polling()
  
