from pyrogram import Client, filters
from pymongo import MongoClient
import os

# Pega as variáveis de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")

# Conecta no MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# Captura todas as mensagens (inclusive suas), exceto mensagens de serviço
@Client.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        data = {
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "user_id": getattr(message.from_user, "id", None) if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else None,
            "outgoing": message.outgoing,  # True = você enviou, False = outra pessoa
            "text": message.text if message.text else None,
            "date": message.date.isoformat() if message.date else None,
        }  # ✅ fechando o dicionário certinho

        collection.insert_one(data)
        print(f"[LOG] Mensagem salva no MongoDB: {data}")

    except Exception as e:
        print(f"Erro ao salvar no MongoDB: {e}")
