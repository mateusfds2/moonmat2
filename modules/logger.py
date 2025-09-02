from pyrogram import Client, filters
from pymongo import MongoClient
import os

# 🔹 Configs de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# 🔹 ID do seu bot oficial que não deve ser logado
BOT_OFICIAL_ID = 7436240400

# 🔹 Grupo de destino (onde o userbot encaminhará as mensagens)
FORWARD_CHAT_ID = int(os.getenv("FORWARD_CHAT_ID", "-1001234567890"))  # coloque o ID do grupo destino

@Client.on_message(filters.all & ~filters.service)
async def log_and_forward(client, message):
    try:
        me = await client.get_me()

        # 🚫 Ignora mensagens enviadas pelo próprio userbot
        if message.outgoing or (message.from_user and message.from_user.id == me.id):
            return

        # 🚫 Ignora mensagens enviadas pelo bot oficial
        if message.from_user and message.from_user.id == BOT_OFICIAL_ID:
            return

        # ✅ Pega texto ou legenda (pode ser vazio se for só mídia)
        text_content = message.text or message.caption or ""

        data = {
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "message_id": message.id,
            "from_user_id": getattr(message.from_user, "id", None) if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else None,
            "text": text_content,
            "has_media": bool(message.media),
            "date": message.date.isoformat() if message.date else None,
        }

        # ✅ Evita duplicados
        if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
            collection.insert_one(data)
            print(f"[LOG] Mensagem salva no MongoDB: {data}")
        else:
            print(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

        # 🔥 Encaminha todas as mensagens para o grupo de destino
        try:
            await message.forward(FORWARD_CHAT_ID)
            print(f"[FORWARD] Mensagem {message.id} encaminhada para {FORWARD_CHAT_ID}")
        except Exception as e:
            print(f"[FORWARD ERROR] {e}")

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")
