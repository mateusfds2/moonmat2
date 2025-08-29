from pyrogram import Client, filters
from pymongo import MongoClient
import os
import requests
import mimetypes

# 🔹 Configs de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# 🔹 Conexão MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# 🔹 ID do bot oficial (ignorar mensagens dele)
BOT_OFICIAL_ID = 7436240400


@Client.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        me = await client.get_me()

        # 🚫 Ignora mensagens do próprio userbot
        if message.outgoing or (message.from_user and message.from_user.id == me.id):
            return

        # 🚫 Ignora mensagens do bot oficial
        if message.from_user and message.from_user.id == BOT_OFICIAL_ID:
            return

        # ✅ Pega texto ou legenda (pode ser vazio se for só mídia)
        text_content = message.text or message.caption or ""

        data = {
            "message_id": message.id,
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "user_id": getattr(message.from_user, "id", None) if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else None,
            "outgoing": message.outgoing,
            "text": text_content,
            "has_media": bool(message.media),
            "date": message.date.isoformat() if message.date else None,
        }

        # ✅ Evita duplicados no MongoDB
        if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
            collection.insert_one(data)
            print(f"[LOG] Mensagem salva no MongoDB: {data}")
        else:
            print(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

        # 🔥 Sempre dispara webhook para n8n
        if N8N_WEBHOOK_URL:
            files = None
            try:
                if message.media:  # 📸 Se tiver mídia, faz upload com MIME correto
                    media_path = await message.download(
                        file_name=f"downloads/{message.chat.id}_{message.id}"
                    )

                    # Pega extensão e MIME
                    ext = os.path.splitext(media_path)[1].lower()
                    mime_type, _ = mimetypes.guess_type(media_path)
                    if not mime_type:
                        mime_type = "application/octet-stream"

                    # Somente envia formatos suportados
                    if ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                        files = {
                            "file": (
                                f"{message.id}{ext}",
                                open(media_path, "rb"),
                                mime_type
                            )
                        }
                    else:
                        print(f"[WEBHOOK WARNING] Arquivo com formato não suportado: {ext}")
                        files = None  # não envia

                # Envia os dados e o arquivo
                requests.post(N8N_WEBHOOK_URL, data=data, files=files, timeout=10)
                print(f"[WEBHOOK] Mensagem enviada para n8n: {data}")

            except Exception as e:
                print(f"[WEBHOOK ERROR] {e}")

            finally:
                if files:
                    files["file"][1].close()  # fecha o arquivo corretamente

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")
