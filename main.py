# main.py
import asyncio
import logging
import sys
import time
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from deep_translator import GoogleTranslator
from config import config
from datetime import datetime, timedelta

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Stockage des données
message_mapping = {}  # source_id -> target_id
message_content_cache = {}  # source_id -> signature
stats = {
    'total_translated': 0,
    'total_edited': 0,
    'errors': 0,
    'start_time': datetime.now(),
    'last_message_time': None,
    'source_connected': False,
    'target_connected': False,
    'recent_messages': []  # Liste des 10 derniers messages pour debug
}

# Cache pour éviter les doublons de notifications
notification_cache = {
    'source_notified': False,
    'target_notified': False
}

# Initialisation du traducteur
translator = GoogleTranslator(source='auto', target=config.TARGET_LANGUAGE)

# Initialisation du client Pyrogram
app = Client(
    "translation_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True
)

def translate_text(text: str) -> str:
    """Traduit le texte en français."""
    if not text or not text.strip():
        return text
    try:
        return translator.translate(text)
    except Exception as e:
        logger.error(f"Erreur de traduction: {e}")
        stats['errors'] += 1
        return text

def format_gambling_message(text: str) -> str:
    """Formate spécifiquement les messages de jeux."""
    if not text:
        return text
        
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        if not line.strip():
            formatted_lines.append('')
            continue
            
        translated_line = translate_text(line)
        
        replacements = {
            'игрок': 'Joueur',
            'выигрыш': 'GAIN',
            'проигрыш': 'PERTE',
            'проигрышь': 'PERTE',
            'Догон': 'Suite',
            'игры': 'parties',
            'игра': 'partie'
        }
        
        for rus, fr in replacements.items():
            translated_line = translated_line.replace(rus, fr)
            
        formatted_lines.append(translated_line)
    
    return '\n'.join(formatted_lines)

def is_gambling_format(text: str) -> bool:
    """Détecte si le message est au format jeu."""
    if not text:
        return False
    indicators = ['♠️', '♥️', '♦️', '♣️', '₽', 'игрок', 'выигрыш', 'проигрыш', 'проигрышь', 'Догон']
    return any(ind in text for ind in indicators)

def get_message_signature(text: str, caption: str = None) -> str:
    """Crée une signature unique du contenu."""
    return f"{text or ''}|{caption or ''}"

async def notify_admin(client: Client, message: str, parse_mode: str = "markdown"):
    """Envoie une notification à l'admin."""
    try:
        await client.send_message(
            chat_id=config.ADMIN_ID,
            text=message,
            parse_mode=parse_mode
        )
        logger.info(f"Notification envoyée à l'admin: {config.ADMIN_ID}")
    except Exception as e:
        logger.error(f"Impossible de notifier l'admin {config.ADMIN_ID}: {e}")

# ==================== COMMANDES ====================

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Commande /start - Affiche toutes les commandes disponibles."""
    is_admin = message.from_user.id == config.ADMIN_ID
    
    welcome_text = f"""
🤖 **Bot de Traduction Automatique**

Bienvenue {message.from_user.mention} !

Je traduis automatiquement les messages du canal source vers le canal cible.

📋 **Commandes disponibles :**

🔹 `/start` - Affiche ce menu
🔹 `/status` - Voir l'état du bot et la connexion aux canaux
🔹 `/stats` - Voir les statistiques de traduction
🔹 `/test` - Tester la connexion et envoyer un message test
🔹 `/last` - Voir les 5 derniers messages traités
🔹 `/check` - Vérifier si les canaux sont accessibles
🔹 `/ping` - Vérifier que le bot est en ligne
🔹 `/info` - Informations sur la configuration
🔹 `/help` - Aide détaillée

{'🔹 `/reset` - Réinitialiser les statistiques *(admin)*' if is_admin else ''}

⚙️ **Fonctionnement :**
• **Canal Source** : `{config.SOURCE_CHANNEL_ID}`
• **Canal Cible** : `{config.TARGET_CHANNEL_ID}`
• Auto-détection des éditions
• Pas de doublons garanti
    """
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistiques", callback_data="stats"),
         InlineKeyboardButton("🔍 Status", callback_data="status")],
        [InlineKeyboardButton("🧪 Test", callback_data="test"),
         InlineKeyboardButton("❓ Aide", callback_data="help")]
    ])
    
    await message.reply(welcome_text, reply_markup=keyboard)

@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    """Commande /help - Aide détaillée."""
    help_text = """
📚 **AIDE DU BOT DE TRADUCTION**

**Comment ça marche ?**
1. Ajoute le bot aux deux canaux (source et cible)
2. Le bot détecte automatiquement les messages
3. Il traduit et envoie dans le canal cible
4. Si un message est édité, il met à jour la traduction

**Gestion des éditions :**
- Le bot garde une trace de chaque message
- Quand un message est modifié dans le canal source
- Il modifie automatiquement la traduction correspondante
- Pas de message en double !

**Format spécial Casino :**
Le bot détecte automatiquement les messages de jeu et traduit :
- `игрок` → **Joueur**
- `выигрыш` → **GAIN**
- `проигрыш` → **PERTE**
- `Догон` → **Suite**

**Problèmes courants :**
• Si le bot ne traduit pas → Vérifiez `/check`
• Si les éditions ne fonctionnent pas → Vérifiez les permissions d'édition
• Pour réinitialiser → `/reset` (admin uniquement)
    """
    await message.reply(help_text)

@app.on_message(filters.command("status") & filters.private)
async def status_command(client: Client, message: Message):
    """Commande /status - État de la connexion."""
    uptime = datetime.now() - stats['start_time']
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Vérification en temps réel
    try:
        await client.get_chat(config.SOURCE_CHANNEL_ID)
        source_status = "🟢 Connecté"
        stats['source_connected'] = True
    except:
        source_status = "🔴 Déconnecté"
        stats['source_connected'] = False
    
    try:
        await client.get_chat(config.TARGET_CHANNEL_ID)
        target_status = "🟢 Connecté"
        stats['target_connected'] = True
    except:
        target_status = "🔴 Déconnecté"
        stats['target_connected'] = False
    
    status_text = f"""
📊 **ÉTAT DU BOT**

🟢 **Bot :** En ligne
⏱ **Uptime :** {hours}h {minutes}m {seconds}s

📡 **Canaux :**
{source_status} **Source :** `{config.SOURCE_CHANNEL_ID}`
{target_status} **Cible :** `{config.TARGET_CHANNEL_ID}`

📨 **Activité récente :**
• Dernier message : {stats['last_message_time'].strftime('%H:%M:%S') if stats['last_message_time'] else 'Aucun'}
• Messages en cache : {len(message_mapping)}
• Messages en attente : {len([m for m in message_mapping if m not in message_content_cache])}
    """
    
    await message.reply(status_text)

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    """Commande /stats - Statistiques détaillées."""
    uptime = datetime.now() - stats['start_time']
    total_ops = stats['total_translated'] + stats['total_edited'] + stats['errors']
    success_rate = ((stats['total_translated'] / total_ops * 100) if total_ops > 0 else 100)
    
    stats_text = f"""
📈 **STATISTIQUES DE TRADUCTION**

✅ **Messages traduits :** `{stats['total_translated']}`
📝 **Messages édités :** `{stats['total_edited']}`
❌ **Erreurs :** `{stats['errors']}`
📊 **Taux de succès :** `{success_rate:.1f}%`

⏱ **Temps de fonctionnement :** `{str(uptime).split('.')[0]}`
🔄 **Messages en suivi :** `{len(message_mapping)}`

📉 **Activité :**
• Moyenne : `{stats['total_translated'] / (uptime.total_seconds() / 3600):.1f}` msg/heure
• Dernière activité : `{stats['last_message_time'].strftime('%H:%M:%S') if stats['last_message_time'] else 'N/A'}`
    """
    
    await message.reply(stats_text)

@app.on_message(filters.command("test") & filters.private)
async def test_command(client: Client, message: Message):
    """Commande /test - Teste la connexion aux canaux."""
    status_msg = await message.reply("🧪 **Test de connexion en cours...**\n\n1️⃣ Vérification canal source...")
    
    results = []
    all_ok = True
    
    # Test canal source
    try:
        chat = await client.get_chat(config.SOURCE_CHANNEL_ID)
        member = await client.get_chat_member(config.SOURCE_CHANNEL_ID, "me")
        perms = "Lecture ✓" if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER] else "⚠️ Limité"
        results.append(f"✅ Source : {chat.title}\n   Permissions : {perms}")
        stats['source_connected'] = True
        await status_msg.edit_text("🧪 **Test en cours...**\n\n✅ Canal source OK\n2️⃣ Vérification canal cible...")
    except Exception as e:
        results.append(f"❌ Source : {str(e)}")
        stats['source_connected'] = False
        all_ok = False
    
    # Test canal cible
    try:
        chat = await client.get_chat(config.TARGET_CHANNEL_ID)
        member = await client.get_chat_member(config.TARGET_CHANNEL_ID, "me")
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            can_post = "Envoi ✓" if member.privileges.can_post_messages else "❌"
            can_edit = "Édition ✓" if member.privileges.can_edit_messages else "❌"
            perms = f"{can_post} | {can_edit}"
        else:
            perms = "⚠️ Admin requis"
        results.append(f"✅ Cible : {chat.title}\n   Permissions : {perms}")
        stats['target_connected'] = True
        await status_msg.edit_text("🧪 **Test en cours...**\n\n✅ Canal source OK\n✅ Canal cible OK\n3️⃣ Test d'envoi...")
    except Exception as e:
        results.append(f"❌ Cible : {str(e)}")
        stats['target_connected'] = False
        all_ok = False
    
    # Envoi d'un message test si les deux sont OK
    if all_ok:
        try:
            test_msg = await client.send_message(
                config.TARGET_CHANNEL_ID,
                "🧪 **Test de connexion**\n✅ Le bot fonctionne correctement !\n🕒 Test effectué à : " + datetime.now().strftime('%H:%M:%S')
            )
            results.append(f"✅ Message test envoyé (ID: `{test_msg.id}`)")
            
            # Test d'édition
            await asyncio.sleep(2)
            await client.edit_message_text(
                config.TARGET_CHANNEL_ID,
                test_msg.id,
                "🧪 **Test de connexion**\n✅ Envoi OK\n✅ Édition OK\n🕒 " + datetime.now().strftime('%H:%M:%S')
            )
            results.append("✅ Édition testée avec succès")
            
            # Nettoyage
            await asyncio.sleep(3)
            await test_msg.delete()
            results.append("🗑 Message test nettoyé")
            
        except Exception as e:
            results.append(f"❌ Échec du test : {str(e)}")
    
    final_text = "📋 **RÉSULTATS DU TEST**\n\n" + "\n\n".join(results)
    await status_msg.edit_text(final_text)

@app.on_message(filters.command("last") & filters.private)
async def last_command(client: Client, message: Message):
    """Commande /last - Affiche les derniers messages traités."""
    if not stats['recent_messages']:
        await message.reply("📭 Aucun message n'a encore été traité.")
        return
    
    text = "📨 **10 DERNIERS MESSAGES TRAITÉS**\n\n"
    
    for i, msg in enumerate(reversed(stats['recent_messages'][-10:]), 1):
        preview = msg['content'][:40] + "..." if len(msg['content']) > 40 else msg['content']
        status_icon = "✅" if msg['translated'] else "❌"
        text += f"`{i}.` **ID {msg['id']}** - `{msg['time']}`\n"
        text += f"   {preview}\n"
        text += f"   {status_icon} Traduit | [Voir](https://t.me/c/{str(config.SOURCE_CHANNEL_ID)[4:]}/{msg['id']})\n\n"
    
    await message.reply(text, disable_web_page_preview=True)

@app.on_message(filters.command("check") & filters.private)
async def check_command(client: Client, message: Message):
    """Commande /check - Vérification complète des canaux."""
    check_msg = await message.reply("🔍 **Analyse des canaux...**")
    
    report = ["📋 **RAPPORT DE VÉRIFICATION**\n"]
    
    # Vérification canal source
    report.append("📥 **CANAL SOURCE**")
    try:
        chat = await client.get_chat(config.SOURCE_CHANNEL_ID)
        report.append(f"• Nom : {chat.title}")
        report.append(f"• Type : {chat.type}")
        report.append(f"• Membres : {chat.members_count if chat.members_count else 'N/A'}")
        
        member = await client.get_chat_member(config.SOURCE_CHANNEL_ID, "me")
        report.append(f"• Mon statut : {member.status.value}")
        
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
            report.append("• ✅ Accès confirmé")
            stats['source_connected'] = True
        else:
            report.append("• ⚠️ Accès limité")
            
    except Exception as e:
        report.append(f"• ❌ Erreur : {str(e)}")
        stats['source_connected'] = False
    
    report.append("")
    
    # Vérification canal cible
    report.append("📤 **CANAL CIBLE**")
    try:
        chat = await client.get_chat(config.TARGET_CHANNEL_ID)
        report.append(f"• Nom : {chat.title}")
        report.append(f"• Type : {chat.type}")
        
        member = await client.get_chat_member(config.TARGET_CHANNEL_ID, "me")
        report.append(f"• Mon statut : {member.status.value}")
        
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            privs = member.privileges
            can_post = "✅" if privs.can_post_messages else "❌"
            can_edit = "✅" if privs.can_edit_messages else "❌"
            can_delete = "✅" if privs.can_delete_messages else "❌"
            
            report.append(f"• Envoi : {can_post}")
            report.append(f"• Édition : {can_edit}")
            report.append(f"• Suppression : {can_delete}")
            
            if privs.can_post_messages and privs.can_edit_messages:
                report.append("• ✅ Configuration optimale")
                stats['target_connected'] = True
            else:
                report.append("• ⚠️ Droits insuffisants")
        else:
            report.append("• ❌ Admin requis pour édition")
            
    except Exception as e:
        report.append(f"• ❌ Erreur : {str(e)}")
        stats['target_connected'] = False
    
    await check_msg.edit_text("\n".join(report))

@app.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: Message):
    """Commande /ping - Vérification rapide."""
    start = time.time()
    msg = await message.reply("🏓 **Ping...**")
    end = time.time()
    latency = (end - start) * 1000
    
    await msg.edit_text(f"""
🏓 **Pong!**

⚡ **Latence :** `{latency:.1f}ms`
🤖 **Bot :** En ligne
⏱ **Uptime :** `{str(datetime.now() - stats['start_time']).split('.')[0]}`
    """)

@app.on_message(filters.command("reset") & filters.private)
async def reset_command(client: Client, message: Message):
    """Commande /reset - Réinitialise les stats (admin uniquement)."""
    if message.from_user.id != config.ADMIN_ID:
        await message.reply("⛔ **Accès refusé**\n\nCette commande est réservée à l'administrateur.")
        return
    
    old_stats = stats.copy()
    
    stats['total_translated'] = 0
    stats['total_edited'] = 0
    stats['errors'] = 0
    stats['start_time'] = datetime.now()
    message_mapping.clear()
    message_content_cache.clear()
    
    await message.reply(f"""
🗑 **Statistiques réinitialisées !**

📊 **Anciennes valeurs :**
• Messages traduits : `{old_stats['total_translated']}`
• Messages édités : `{old_stats['total_edited']}`
• Erreurs : `{old_stats['errors']}`

✅ Compteurs remis à zéro.
🕒 Nouveau départ : `{datetime.now().strftime('%H:%M:%S')}`
    """)

@app.on_message(filters.command("info") & filters.private)
async def info_command(client: Client, message: Message):
    """Commande /info - Informations de configuration."""
    is_admin = message.from_user.id == config.ADMIN_ID
    
    info_text = f"""
⚙️ **CONFIGURATION DU BOT**

🤖 **Bot :** @{((await client.get_me())).username}
👤 **Votre ID :** `{message.from_user.id}`
{'👑 **Admin :** Oui' if is_admin else '👤 **Admin :** Non'}

📡 **Canaux configurés :**
• **Source :** `{config.SOURCE_CHANNEL_ID}`
• **Cible :** `{config.TARGET_CHANNEL_ID}`

🔧 **Paramètres :**
• Langue : `{config.TARGET_LANGUAGE.upper()}`
• Mode : `{'Render.com' if config.RENDER_DEPLOYMENT else 'Local'}`
• Port : `{config.PORT}`
• Host : `{config.HOST}`

💾 **Mémoire :**
• Messages trackés : `{len(message_mapping)}`
• Cache : `{len(message_content_cache)} entrées`
    """
    
    if is_admin:
        info_text += f"\n\n🔐 **Admin ID :** `{config.ADMIN_ID}`"
    
    await message.reply(info_text)

# ==================== GESTION DES CANAUX ====================

@app.on_chat_member_updated()
async def handle_chat_member_update(client: Client, update):
    """Détecte quand le bot est ajouté à un canal."""
    if not update.new_chat_member:
        return
    
    new_member = update.new_chat_member
    me = await client.get_me()
    
    if new_member.user.id != me.id:
        return
    
    chat = update.chat
    chat_id = chat.id
    
    # Détermine si c'est le canal source ou cible
    if chat_id == config.SOURCE_CHANNEL_ID:
        stats['source_connected'] = True
        
        if not notification_cache['source_notified']:
            notif_text = f"""
🎯 **BOT PRÊT À TRADUIRE !**

✅ **Ajouté au canal SOURCE**

📋 **Informations :**
• Nom : {chat.title}
• ID : `{chat_id}`
• Type : {chat.type}

🔄 **Statut :** En attente de messages à traduire...
            """
            await notify_admin(client, notif_text)
            notification_cache['source_notified'] = True
            logger.info(f"Notification envoyée: ajout au canal source {chat_id}")
            
    elif chat_id == config.TARGET_CHANNEL_ID:
        stats['target_connected'] = True
        
        if not notification_cache['target_notified']:
            notif_text = f"""
🎯 **BOT CONFIGURÉ !**

✅ **Ajouté au canal CIBLE**

📋 **Informations :**
• Nom : {chat.title}
• ID : `{chat_id}`
• Type : {chat.type}

✉️ **Prêt à envoyer les traductions ici !**
            """
            await notify_admin(client, notif_text)
            notification_cache['target_notified'] = True
            logger.info(f"Notification envoyée: ajout au canal cible {chat_id}")

# ==================== TRADUCTION ====================

@app.on_message(filters.chat(config.SOURCE_CHANNEL_ID) & (filters.text | filters.media))
async def handle_source_message(client: Client, message: Message):
    """Traite les messages du canal source."""
    try:
        source_id = message.id
        
        # Récupère le contenu
        text = message.text or message.caption
        
        logger.info(f"Message reçu du canal source : {source_id}")
        stats['last_message_time'] = datetime.now()
        
        if not text and not message.media:
            return
        
        # Traduction
        if text:
            translated_text = format_gambling_message(text) if is_gambling_format(text) else translate_text(text)
        else:
            translated_text = None
        
        # Envoi vers canal cible
        if message.text:
            sent = await client.send_message(
                config.TARGET_CHANNEL_ID,
                translated_text or "..."
            )
        elif message.media:
            # Copie avec nouvelle légende traduite
            sent = await message.copy(
                config.TARGET_CHANNEL_ID,
                caption=translated_text
            )
        
        # Stockage
        message_mapping[source_id] = sent.id
        message_content_cache[source_id] = get_message_signature(text, message.caption)
        
        # Stats
        stats['total_translated'] += 1
        stats['recent_messages'].append({
            'id': source_id,
            'content': text or "[Média]",
            'time': datetime.now().strftime('%H:%M:%S'),
            'translated': True
        })
        
        # Garde seulement les 10 derniers
        if len(stats['recent_messages']) > 10:
            stats['recent_messages'].pop(0)
            
        logger.info(f"Traduit : {source_id} -> {sent.id}")
        
        # Notification pour l'admin si premier message
        if stats['total_translated'] == 1:
            await notify_admin(
                client,
                f"🎉 **Première traduction effectuée !**\n\n"
                f"Message ID source : `{source_id}`\n"
                f"Message ID cible : `{sent.id}`\n\n"
                f"Le bot fonctionne correctement ! ✅"
            )
        
    except Exception as e:
        logger.error(f"Erreur traduction : {e}")
        stats['errors'] += 1
        stats['recent_messages'].append({
            'id': source_id,
            'content': str(e),
            'time': datetime.now().strftime('%H:%M:%S'),
            'translated': False
        })

@app.on_edited_message(filters.chat(config.SOURCE_CHANNEL_ID))
async def handle_edited_source_message(client: Client, message: Message):
    """Gère les messages édités."""
    try:
        source_id = message.id
        
        if source_id not in message_mapping:
            logger.warning(f"Message édité inconnu : {source_id}, traitement comme nouveau")
            await handle_source_message(client, message)
            return
        
        target_id = message_mapping[source_id]
        new_text = message.text or message.caption
        
        # Vérifie changement réel
        new_sig = get_message_signature(new_text, message.caption)
        if message_content_cache.get(source_id) == new_sig:
            logger.info(f"Message {source_id} inchangé, ignoré")
            return
        
        logger.info(f"Message édité détecté : {source_id}, mise à jour de {target_id}")
        
        # Traduction
        if new_text:
            translated = format_gambling_message(new_text) if is_gambling_format(new_text) else translate_text(new_text)
        else:
            translated = None
        
        # Modification
        if message.text:
            await client.edit_message_text(config.TARGET_CHANNEL_ID, target_id, translated)
        elif message.caption:
            await client.edit_message_caption(config.TARGET_CHANNEL_ID, target_id, caption=translated)
        
        message_content_cache[source_id] = new_sig
        stats['total_edited'] += 1
        
        logger.info(f"Message modifié avec succès : {target_id}")
        
    except Exception as e:
        logger.error(f"Erreur modification : {e}")
        stats['errors'] += 1

# ==================== CALLBACKS ====================

@app.on_callback_query()
async def handle_callbacks(client: Client, callback_query):
    """Gère les boutons inline."""
    data = callback_query.data
    
    if data == "stats":
        await stats_command(client, callback_query.message)
    elif data == "status":
        await status_command(client, callback_query.message)
    elif data == "test":
        await test_command(client, callback_query.message)
    elif data == "help":
        await help_command(client, callback_query.message)
    
    await callback_query.answer()

# ==================== SERVEUR WEB ====================

async def health_check(request):
    return web.Response(text="Bot OK", status=200)

async def start_web_server():
    web_app = web.Application()
    web_app.router.add_get('/', health_check)
    web_app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()
    logger.info(f"Serveur web sur port {config.PORT}")

# ==================== DÉMARRAGE ====================

async def main():
    logger.info("Démarrage du bot...")
    
    if config.RENDER_DEPLOYMENT:
        await start_web_server()
    
    await app.start()
    
    # Message de démarrage
    me = await app.get_me()
    logger.info(f"Bot @{me.username} démarré!")
    
    # Notification démarrage à l'admin
    startup_msg = f"""
🚀 **BOT DÉMARRÉ !**

🤖 **@{me.username}** est en ligne et prêt !

📋 **Récapitulatif :**
• Canal Source : `{config.SOURCE_CHANNEL_ID}`
• Canal Cible : `{config.TARGET_CHANNEL_ID}`
• Admin : `{config.ADMIN_ID}`

✅ En attente d'être ajouté aux canaux...
    """
    
    await notify_admin(app, startup_msg)
    
    # Vérification initiale des canaux
    try:
        await app.get_chat(config.SOURCE_CHANNEL_ID)
        stats['source_connected'] = True
        logger.info("Canal source accessible")
    except Exception as e:
        logger.warning(f"Canal source non accessible: {e}")
    
    try:
        await app.get_chat(config.TARGET_CHANNEL_ID)
        stats['target_connected'] = True
        logger.info("Canal cible accessible")
    except Exception as e:
        logger.warning(f"Canal cible non accessible: {e}")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt...")
    except Exception as e:
        logger.error(f"Fatal : {e}")
        sys.exit(1)
