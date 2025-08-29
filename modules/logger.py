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

# 🔹 Extensões suportadas pelo OpenAI
OPENAI_IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]


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
                if message.media:
                    media_path = await message.download(file_name=f"downloads/{message.chat.id}_{message.id}")

                    # Detecta tipo de mídia do Telegram
                    if message.photo:
                        ext = ".jpg"
                        mime_type = "image/jpeg"
                    elif message.sticker:
                        ext = ".webp"
                        mime_type = "image/webp"
                    elif message.video:
                        ext = ".mp4"
                        mime_type = "video/mp4"
                    elif message.document:
                        ext = os.path.splitext(message.document.file_name)[1].lower()
                        mime_type, _ = mimetypes.guess_type(media_path)
                        if not mime_type:
                            mime_type = "application/octet-stream"
                    else:
                        ext = os.path.splitext(media_path)[1].lower()
                        mime_type, _ = mimetypes.guess_type(media_path)
                        if not mime_type:
                            mime_type = "application/octet-stream"

                    # Só envia imagens suportadas pelo OpenAI
                    if ext in OPENAI_IMAGE_EXTS:
                        files = {
                            "file": (f"{message.id}{ext}", open(media_path, "rb"), mime_type)
                        }
                    else:
                        print(f"[WEBHOOK WARNING] Arquivo com formato não suportado: {ext}")
                        files = None

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
