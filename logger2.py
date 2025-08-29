from pyrogram import Client, filters
import requests
import os

# Configurações do ambiente
N8N_WEBHOOK_URL = os.getenv(https://webhook.renove.cloud/webhook/logger)  # Defina no .env
BOT_OFICIAL_ID = 7436240400  # mesmo parâmetro do arquivo pai

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

        # ✅ Texto ou legenda
        text_content = message.text or message.caption or ""

        # 📸 Se tiver mídia
        if message.media:
            media_path = await message.download(
                file_name=f"downloads/{message.chat.id}_{message.id}"
            )
            with open(media_path, "rb") as f:
                files = {"file": f}
                data = {
                    "text": text_content,
                    "chat_id": message.chat.id,
                    "chat_title": getattr(message.chat, "title", None),
                    "user_id": getattr(message.from_user, "id", None) if message.from_user else None,
                    "username": getattr(message.from_user, "username", None) if message.from_user else None,
                    "date": message.date.isoformat() if message.date else None,
                }
                resp = requests.post(N8N_WEBHOOK_URL, files=files, data=data)
                print(f"[N8N] Mensagem + mídia enviada: {resp.status_code}")
            return

        # 📝 Apenas texto
        if text_content:
            data = {
                "text": text_content,
                "chat_id": message.chat.id,
                "chat_title": getattr(message.chat, "title", None),
                "user_id": getattr(message.from_user, "id", None) if message.from_user else None,
                "username": getattr(message.from_user, "username", None) if message.from_user else None,
                "date": message.date.isoformat() if message.date else None,
            }
            resp = requests.post(N8N_WEBHOOK_URL, json=data)
            print(f"[N8N] Mensagem enviada sem mídia: {resp.status_code}")

    except Exception as e:
        print(f"[ERRO N8N] {e}")
