async def send_webhook(data, media_path=None):
    if not N8N_WEBHOOK_URL:
        return
    try:
        async with UPLOAD_SEMAPHORE:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()

                # Se tem mídia real, manda ela
                if media_path:
                    form.add_field("file", open(media_path, "rb"), filename=os.path.basename(media_path))
                else:
                    # Se não tem mídia, gera um arquivo .txt com o texto
                    text_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
                    with open(text_file.name, "w", encoding="utf-8") as f:
                        f.write(data.get("text", ""))
                    form.add_field("file", open(text_file.name, "rb"), filename="message.txt")

                # Adiciona metadados
                for k, v in data.items():
                    form.add_field(k, str(v))

                async with session.post(N8N_WEBHOOK_URL, data=form, timeout=60) as resp:
                    print(f"[WEBHOOK] Status: {resp.status}")
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
    finally:
        if media_path and os.path.exists(media_path):
            os.remove(media_path)
