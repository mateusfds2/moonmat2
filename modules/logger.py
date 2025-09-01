import os
import json
import aiohttp
import asyncio
import tempfile
import logging
import traceback
from pyrogram import Client, filters
from pymongo import MongoClient, errors

# 🔹 Configuração de logs detalhados
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s"
)

# 🔹 Carregamento das configurações de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

# [MELHORIA] Validação de variáveis essenciais mais específica
missing_vars = []
if not API_ID:
    missing_vars.append("API_ID")
if not API_HASH:
    missing_vars.append("API_HASH")
if not SESSION_STRING:
    missing_vars.append("SESSION_STRING")

if missing_vars:
    # Este log agora vai dizer exatamente qual variável está faltando
    logging.error(f"[ERRO CRÍTICO] As seguintes variáveis de ambiente são obrigatórias, mas não foram encontradas: {', '.join(missing_vars)}")
    exit(1)

# Validação para garantir que o API_ID é um número antes de converter
try:
    API_ID = int(API_ID)
except (ValueError, TypeError):
    logging.error(f"[ERRO CRÍTICO] A variável de ambiente API_ID ('{API_ID}') não é um número inteiro válido.")
    exit(1)


# 🔹 Conexão com o MongoDB com tratamento de erros
mongo_client = None
db = None
collection = None

if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # O comando ping() força a conexão e valida as credenciais.
        mongo_client.admin.command('ping')
        db = mongo_client[MONGO_DB_NAME]
        collection = db["messages"]
        logging.info("[MONGODB] Conexão com o MongoDB estabelecida com sucesso.")
    except errors.ConnectionFailure as e:
        logging.error(f"[MONGODB ERRO] Falha ao conectar com o MongoDB: {e}")
        mongo_client = db = collection = None
    except Exception as e:
        logging.error(f"[MONGODB ERRO INESPERADO] {e}")
        mongo_client = db = collection = None
else:
    logging.warning("[MONGODB] MONGO_URI não definida. O logger não salvará no banco de dados.")

# 🔹 Limite de uploads simultâneos para o webhook
UPLOAD_SEMAPHORE = asyncio.Semaphore(5)

async def send_to_webhook(data, media_path=None):
    """
    [CORREÇÃO] Envia dados para o n8n de forma mais estruturada.
    - O 'data' (dicionário python) é enviado como um campo JSON chamado 'json_data'.
    - O arquivo de mídia é enviado como um campo binário chamado 'file'.
    Isso facilita muito o tratamento dos dados no n8n.
    """
    if not N8N_WEBHOOK_URL:
        return

    try:
        async with UPLOAD_SEMAPHORE:
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()

                # 1. Adiciona os metadados como um único campo JSON.
                form_data.add_field(
                    'json_data',
                    json.dumps(data, ensure_ascii=False),
                    content_type='application/json'
                )

                # 2. Adiciona o arquivo de mídia, se existir.
                if media_path and os.path.exists(media_path):
                    with open(media_path, "rb") as f:
                        form_data.add_field(
                            "file",
                            f,
                            filename=os.path.basename(media_path),
                            content_type="application/octet-stream"
                        )

                # 3. Envia a requisição
                async with session.post(N8N_WEBHOOK_URL, data=form_data, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status >= 400:
                        logging.error(f"[WEBHOOK] Erro ao enviar. Status: {resp.status} | Resposta: {await resp.text()}")
                    else:
                        logging.info(f"[WEBHOOK] Enviado com sucesso. Status: {resp.status}")

    except asyncio.TimeoutError:
        logging.error("[WEBHOOK ERRO] Timeout ao enviar para o n8n.")
    except Exception as e:
        logging.error(f"[WEBHOOK ERRO] {e}\n{traceback.format_exc()}")
    finally:
        # Garante que o arquivo temporário seja sempre removido
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
            except OSError as e:
                logging.error(f"Erro ao remover arquivo de mídia temporário: {e}")


# 🔹 Inicialização do Cliente Pyrogram
app = Client(
    "moon_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)


@app.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        # [MELHORIA] Simplificado: `message.outgoing` já cobre todas as mensagens enviadas por você.
        if message.outgoing:
            return

        text_content = message.text or message.caption or ""
        from_user = message.from_user or message.forward_from

        data = {
            "chat_id": message.chat.id,
            "chat_title": message.chat.title or message.chat.first_name,
            "message_id": message.id,
            "from_user_id": from_user.id if from_user else None,
            "username": from_user.username if from_user else None,
            "first_name": from_user.first_name if from_user else None,
            "text": text_content,
            "has_media": bool(message.media),
            "media_type": str(message.media) if message.media else None,
            "date": message.date.isoformat() if message.date else None,
        }

        # Salva no MongoDB, se configurado
        if collection is not None:
            collection.insert_one(data.copy()) # Usa .copy() para evitar alterações no dict original
            logging.info(f"[MONGODB] Mensagem do chat '{data['chat_title']}' salva.")

        # Download da mídia em um diretório temporário seguro
        media_path = None
        if message.media:
            try:
                # [MELHORIA] Usa um diretório temporário para evitar problemas de permissão
                temp_dir = tempfile.gettempdir()
                media_path = await message.download(file_name=os.path.join(temp_dir, f"{message.chat.id}_{message.id}"))
                logging.info(f"Mídia baixada para: {media_path}")
            except Exception as e:
                 logging.error(f"Falha ao baixar mídia: {e}")


        # Envia para o webhook em uma tarefa de fundo para não bloquear o bot
        asyncio.create_task(send_to_webhook(data, media_path))

    except Exception as e:
        # [MELHORIA] Log de erro muito mais detalhado com traceback
        logging.error(f"[LOGGER ERRO] Ocorreu uma exceção não tratada: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    logging.info("[START] Moon Userbot iniciando...")
    app.run()
    logging.info("[STOP] Moon Userbot finalizado.")



