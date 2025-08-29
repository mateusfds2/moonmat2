from pyrogram import Client, filters
import requests
import os

# Configuração do ambiente (Heroku ou .env)
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
BOT_OFICIAL_ID = 7436240400  # id do seu bot oficial

@Client.on_message(filters.all & ~filters.service)
async def log_message_n8n(client, message):
    try:
        me = await client.get_me()

        # 🚫 Ignora mensagens do próprio userbot
        if message.outgoing or (message.from_user and message.from_user.id == me.id):
            return

        # 🚫 Ignora mensagens do bot oficial
        if message.from_user and message.from_user.id == BOT_OFICIAL_ID:
            return

        # ✅ Pega texto/legenda (pode ser vazio)
        text_content = message.text or message.caption or ""

        # Monta payload
        data = {
            "text": text_content,
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "user_id": getattr(message.from_user, "id", None) if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else None,
            "date": message.date.isoformat() if message.date else None,
        }

        files = None
        if message.media:  # 📸 Se tiver mídia, faz upload
            media_path = await message.download(
                file_name=f"downloads/{message.chat.id}_{message.id}"
            )
            files = {"file": open(media_path, "rb")}

        # 🔥 Dispara webhook SEMPRE
        if N8N_WEBHOOK_URL:
            requests.post(N8N_WEBHOOK_URL, data=data, files=files)

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")
