"""
Moon-Userbot Module: Group Members Cataloguer
Cataloga User IDs de todos os membros de um grupo específico no Telegram
"""

from pyrogram import Client, filters
from pyrogram.types import Message
from utils.misc import modules_help, prefix
from utils.db import db
import json
from datetime import datetime

# ID do grupo padrão (pode ser alterado via comando)
DEFAULT_GROUP_ID = -1003042756853


@Client.on_message(filters.command("catalog", prefix) & filters.me)
async def catalog_members(client: Client, message: Message):
    """Cataloga todos os User IDs do grupo especificado"""
    
    # Permite especificar outro grupo: .catalog -1001234567890
    if len(message.command) > 1:
        try:
            target_group = int(message.command[1])
        except ValueError:
            return await message.edit("❌ <b>ID de grupo inválido!</b>\n\nUso: <code>.catalog -1001234567890</code>")
    else:
        target_group = DEFAULT_GROUP_ID
    
    await message.edit("🔍 <b>Iniciando catalogação de User IDs...</b>")
    
    try:
        # Verifica se o grupo existe e se temos acesso
        chat = await client.get_chat(target_group)
        
        await message.edit(
            f"📊 <b>Catalogando User IDs do grupo:</b>\n"
            f"<b>Nome:</b> {chat.title}\n"
            f"<b>ID:</b> <code>{target_group}</code>\n\n"
            f"⏳ <i>Por favor, aguarde...</i>"
        )
        
        user_ids = []
        total_count = 0
        
        # Itera sobre todos os membros do grupo
        async for member in client.get_chat_members(target_group):
            total_count += 1
            user_ids.append(member.user.id)
            
            # Atualiza o status a cada 100 membros
            if total_count % 100 == 0:
                await message.edit(
                    f"📊 <b>Catalogando User IDs...</b>\n"
                    f"<b>Grupo:</b> {chat.title}\n"
                    f"<b>Progresso:</b> {total_count} IDs coletados\n"
                    f"⏳ <i>Aguarde...</i>"
                )
        
        # Salva os dados no banco de dados
        catalog_data = {
            "group_id": target_group,
            "group_title": chat.title,
            "total_members": total_count,
            "catalog_date": datetime.now().isoformat(),
            "user_ids": user_ids
        }
        
        db.set("group.catalog", f"group_{target_group}", catalog_data)
        
        # Mensagem final com resumo
        summary = (
            f"✅ <b>Catalogação concluída!</b>\n\n"
            f"📊 <b>Resumo:</b>\n"
            f"<b>Grupo:</b> {chat.title}\n"
            f"<b>ID do Grupo:</b> <code>{target_group}</code>\n"
            f"<b>Total de User IDs:</b> {total_count}\n"
            f"<b>Data:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"💾 <i>Dados salvos no banco de dados</i>\n"
            f"Use <code>{prefix}cataloginfo</code> para ver informações\n"
            f"Use <code>{prefix}exportcat</code> para baixar a lista"
        )
        
        await message.edit(summary)
        
    except Exception as e:
        await message.edit(f"❌ <b>Erro ao catalogar User IDs:</b>\n<code>{str(e)}</code>")


@Client.on_message(filters.command("cataloginfo", prefix) & filters.me)
async def catalog_info(client: Client, message: Message):
    """Mostra informações do último catálogo salvo"""
    
    # Permite especificar grupo: .cataloginfo -1001234567890
    if len(message.command) > 1:
        try:
            target_group = int(message.command[1])
        except ValueError:
            return await message.edit("❌ <b>ID de grupo inválido!</b>")
    else:
        target_group = DEFAULT_GROUP_ID
    
    catalog_data = db.get("group.catalog", f"group_{target_group}")
    
    if not catalog_data:
        return await message.edit(
            f"❌ <b>Nenhum catálogo encontrado</b>\n\n"
            f"Use <code>{prefix}catalog</code> para criar um novo catálogo"
        )
    
    total = catalog_data["total_members"]
    
    response = (
        f"📊 <b>Informações do Catálogo</b>\n\n"
        f"<b>Grupo:</b> {catalog_data['group_title']}\n"
        f"<b>ID do Grupo:</b> <code>{catalog_data['group_id']}</code>\n"
        f"<b>Data da catalogação:</b> {catalog_data['catalog_date'][:19]}\n"
        f"<b>Total de User IDs:</b> {total}\n\n"
        f"💡 <b>Comandos disponíveis:</b>\n"
        f"<code>{prefix}exportcat</code> - Exportar lista completa\n"
        f"<code>{prefix}searchcat [user_id]</code> - Verificar se ID existe\n"
        f"<code>{prefix}delcat</code> - Deletar este catálogo"
    )
    
    await message.edit(response)


@Client.on_message(filters.command("exportcat", prefix) & filters.me)
async def export_catalog(client: Client, message: Message):
    """Exporta o catálogo com todos os User IDs"""
    
    # Permite especificar grupo: .exportcat -1001234567890
    if len(message.command) > 1:
        try:
            target_group = int(message.command[1])
        except ValueError:
            return await message.edit("❌ <b>ID de grupo inválido!</b>")
    else:
        target_group = DEFAULT_GROUP_ID
    
    catalog_data = db.get("group.catalog", f"group_{target_group}")
    
    if not catalog_data:
        return await message.edit(f"❌ <b>Nenhum catálogo encontrado</b>")
    
    await message.edit("📤 <b>Gerando arquivo...</b>")
    
    # Cria arquivo de texto simples com os User IDs
    filename = f"userids_{target_group}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"USER IDS - {catalog_data['group_title']}\n")
            f.write(f"Group ID: {catalog_data['group_id']}\n")
            f.write(f"Total: {catalog_data['total_members']} membros\n")
            f.write(f"Data: {catalog_data['catalog_date'][:19]}\n")
            f.write("="*50 + "\n\n")
            
            for user_id in catalog_data['user_ids']:
                f.write(f"{user_id}\n")
        
        # Envia o arquivo
        await client.send_document(
            message.chat.id,
            filename,
            caption=(
                f"📊 <b>Lista de User IDs</b>\n\n"
                f"<b>Grupo:</b> {catalog_data['group_title']}\n"
                f"<b>Total:</b> {catalog_data['total_members']} IDs"
            )
        )
        await message.delete()
        
    except Exception as e:
        await message.edit(f"❌ <b>Erro ao enviar arquivo:</b>\n<code>{str(e)}</code>")
    finally:
        # Remove o arquivo temporário
        import os
        if os.path.exists(filename):
            os.remove(filename)


@Client.on_message(filters.command("searchcat", prefix) & filters.me)
async def search_catalog(client: Client, message: Message):
    """Verifica se um User ID existe no catálogo"""
    
    if len(message.command) < 2:
        return await message.edit(
            f"ℹ️ <b>Uso:</b> <code>{prefix}searchcat [user_id]</code>\n"
            f"ou <code>{prefix}searchcat -1001234567890 [user_id]</code>"
        )
    
    # Verifica se o primeiro argumento é um ID de grupo
    try:
        target_group = int(message.command[1])
        if len(message.command) < 3:
            return await message.edit(f"ℹ️ <b>Uso:</b> <code>{prefix}searchcat {target_group} [user_id]</code>")
        search_id = int(message.command[2])
    except ValueError:
        target_group = DEFAULT_GROUP_ID
        try:
            search_id = int(message.command[1])
        except ValueError:
            return await message.edit("❌ <b>User ID inválido! Deve ser um número.</b>")
    
    catalog_data = db.get("group.catalog", f"group_{target_group}")
    
    if not catalog_data:
        return await message.edit(f"❌ <b>Nenhum catálogo encontrado para este grupo</b>")
    
    # Busca o User ID na lista
    if search_id in catalog_data['user_ids']:
        position = catalog_data['user_ids'].index(search_id) + 1
        await message.edit(
            f"✅ <b>User ID encontrado!</b>\n\n"
            f"<b>User ID:</b> <code>{search_id}</code>\n"
            f"<b>Grupo:</b> {catalog_data['group_title']}\n"
            f"<b>Posição:</b> {position} de {catalog_data['total_members']}"
        )
    else:
        await message.edit(
            f"❌ <b>User ID não encontrado</b>\n\n"
            f"<b>User ID buscado:</b> <code>{search_id}</code>\n"
            f"<b>Grupo:</b> {catalog_data['group_title']}\n"
            f"<i>Este usuário não está no catálogo deste grupo</i>"
        )


@Client.on_message(filters.command("delcat", prefix) & filters.me)
async def delete_catalog(client: Client, message: Message):
    """Deleta o catálogo de um grupo específico"""
    
    # Permite especificar grupo: .delcat -1001234567890
    if len(message.command) > 1:
        try:
            target_group = int(message.command[1])
        except ValueError:
            return await message.edit("❌ <b>ID de grupo inválido!</b>")
    else:
        target_group = DEFAULT_GROUP_ID
    
    catalog_data = db.get("group.catalog", f"group_{target_group}")
    
    if not catalog_data:
        return await message.edit(
            f"❌ <b>Nenhum catálogo encontrado para o grupo:</b> <code>{target_group}</code>"
        )
    
    group_name = catalog_data.get("group_title", "Desconhecido")
    total_members = catalog_data.get("total_members", 0)
    
    # Remove o catálogo do banco de dados
    db.remove("group.catalog", f"group_{target_group}")
    
    await message.edit(
        f"🗑️ <b>Catálogo deletado com sucesso!</b>\n\n"
        f"<b>Grupo:</b> {group_name}\n"
        f"<b>ID:</b> <code>{target_group}</code>\n"
        f"<b>User IDs removidos:</b> {total_members}\n\n"
        f"✅ <i>Dados removidos do banco de dados</i>"
    )


@Client.on_message(filters.command("listcat", prefix) & filters.me)
async def list_catalogs(client: Client, message: Message):
    """Lista todos os catálogos salvos no banco de dados"""
    
    # Pega todos os catálogos salvos
    all_data = db.get("group.catalog")
    
    if not all_data or not isinstance(all_data, dict):
        return await message.edit(
            f"❌ <b>Nenhum catálogo encontrado</b>\n\n"
            f"Use <code>{prefix}catalog</code> para criar um novo catálogo"
        )
    
    # Filtra apenas os catálogos de grupos
    catalogs = {k: v for k, v in all_data.items() if k.startswith("group_")}
    
    if not catalogs:
        return await message.edit(
            f"❌ <b>Nenhum catálogo encontrado</b>\n\n"
            f"Use <code>{prefix}catalog</code> para criar um novo catálogo"
        )
    
    response = f"📚 <b>Catálogos salvos:</b> {len(catalogs)}\n\n"
    
    for key, catalog in catalogs.items():
        group_id = catalog.get("group_id", "Desconhecido")
        group_name = catalog.get("group_title", "Sem nome")
        total = catalog.get("total_members", 0)
        date = catalog.get("catalog_date", "")[:10]  # Apenas a data
        
        response += (
            f"📊 <b>{group_name}</b>\n"
            f"   ID: <code>{group_id}</code>\n"
            f"   User IDs: {total} | Data: {date}\n\n"
        )
    
    response += (
        f"💡 <b>Comandos:</b>\n"
        f"<code>{prefix}cataloginfo [id]</code> - Ver detalhes\n"
        f"<code>{prefix}exportcat [id]</code> - Baixar lista\n"
        f"<code>{prefix}delcat [id]</code> - Deletar catálogo"
    )
    
    await message.edit(response)


modules_help["catalog"] = {
    "catalog [group_id]": "Cataloga todos os User IDs do grupo (padrão: -1003042756853)",
    "cataloginfo [group_id]": "Mostra informações do catálogo salvo",
    "exportcat [group_id]": "Exporta lista de User IDs em arquivo .txt",
    "searchcat [group_id] [user_id]": "Verifica se um User ID está no catálogo",
    "delcat [group_id]": "Deleta o catálogo de um grupo específico",
    "listcat": "Lista todos os catálogos salvos",
}
