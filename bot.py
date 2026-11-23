import os
import sqlite3
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

ARCHIVE_CHANNEL_ID = 1574345296350154752 # Заміни на ID свого закритого каналу
TOKEN = os.getenv("DISCORD_TOKEN", "MTU3NDM1MDQ2MDUyODM2NTcwOQ.GH_pqr.kTezdNmzXIw2DqAR5fQ8nBWS61yCC1Jwy_X67I")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

conn = sqlite3.connect("evidence_db.sqlite")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        violator_nick TEXT NOT NULL,
        proof_url TEXT NOT NULL,
        added_by_id INTEGER NOT NULL,
        added_by_name TEXT NOT NULL,
        date_added TEXT NOT NULL
    )
""")
conn.commit()


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Бот {bot.user} запущений!")


@bot.tree.command(name="cuff", description="Занести порушника та доказ (відео/фото) в базу")
@app_commands.describe(
    нікнейм="Нікнейм порушника",
    доказ="Прикріпіть фото або відео",
    посилання="Або вкажіть посилання"
)
async def cuff(
    interaction: discord.Interaction,
    нікнейм: str,
    доказ: discord.Attachment = None,
    посилання: str = None
):
    if not доказ and not посилання:
        await interaction.response.send_message(
            "❌ Потрібно прикріпити фото/відео або вказати посилання!",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    proof_link = посилання.strip() if посилання else None
    archive_channel = bot.get_channel(ARCHIVE_CHANNEL_ID)

    if доказ:
        if archive_channel is None:
            await interaction.followup.send("❌ Не знайдено канал-архів. Перевір ID каналу.", ephemeral=True)
            return
        file_data = await доказ.to_file()
        archive_msg = await archive_channel.send(
            content=f"📁 Архів | Порушник: {нікнейм.strip()} | Вніс: {interaction.user.mention} ({interaction.user.id})",
            file=file_data
        )
        proof_link = archive_msg.attachments[0].url if archive_msg.attachments else archive_msg.jump_url

    date_now = datetime.now().strftime("%d.%m.%Y %H:%M")
    clean_nick = нікнейм.strip()

    cursor.execute(
        "INSERT INTO evidence (violator_nick, proof_url, added_by_id, added_by_name, date_added) VALUES (?, ?, ?, ?, ?)",
        (clean_nick, proof_link, interaction.user.id, str(interaction.user), date_now)
    )
    conn.commit()
    record_id = cursor.lastrowid

    embed = discord.Embed(title="🔒 Порушника занесено в базу", color=discord.Color.red())
    embed.add_field(name="ID доказу", value=f"#{record_id}", inline=True)
    embed.add_field(name="Порушник", value=f"{clean_nick}", inline=True)
    embed.add_field(name="Адмін", value=interaction.user.mention, inline=True)
    embed.add_field(name="Доказ", value=f"[Відкрити матеріал]({proof_link})", inline=False)
    embed.set_footer(text=f"Дата: {date_now} | Видалити свій запис: /unjail {record_id}")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="spec", description="Знайти докази на гравця та отримати їх у ПП")
@app_commands.describe(нікнейм="Нікнейм гравця для пошуку")
async def spec(interaction: discord.Interaction, нікнейм: str):
    clean_nick = нікнейм.strip().lower()
    cursor.execute(
        "SELECT id, violator_nick, proof_url, added_by_id, added_by_name, date_added FROM evidence WHERE LOWER(violator_nick) LIKE ?",
        (f"%{clean_nick}%",)
    )
    rows = cursor.fetchall()

    if not rows:
        await interaction.response.send_message(f"🔍 Доказів на **{нікнейм}** не знайдено.", ephemeral=True)
        return

    try:
        for row in rows:
            record_id, nick, proof_url, added_by_id, added_by_name, date_added = row

dm_embed = discord.Embed(title=f"📂 Доказ #{record_id} | Порушник: {nick}", color=discord.Color.orange())
            dm_embed.add_field(name="Посилання на доказ", value=f"[Переглянути матеріал]({proof_url})", inline=False)
            dm_embed.add_field(name="Вніс доказ", value=f"{added_by_name} ({added_by_id})", inline=True)
            dm_embed.add_field(name="Дата", value=date_added, inline=True)
            await interaction.user.send(embed=dm_embed)
            await interaction.user.send(content=f"📎 Доказ #{record_id}: {proof_url}")

        await interaction.response.send_message(
            f"✅ Знайдено записів: {len(rows)}. Докази на **{нікнейм}** надіслано тобі в особисті повідомлення (ПП)!",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Бот не може написати тобі в ПП. Відкрий особисті повідомлення в налаштуваннях Discord.",
            ephemeral=True
        )


@bot.tree.command(name="unjail", description="Видалити свій доказ із бази за його ID")
@app_commands.describe(id_доказу="Номер ID доказу")
async def unjail(interaction: discord.Interaction, id_доказу: int):
    cursor.execute("SELECT id, violator_nick, added_by_id FROM evidence WHERE id = ?", (id_доказу,))
    row = cursor.fetchone()

    if not row:
        await interaction.response.send_message(f"❌ Доказ з ID **#{id_доказу}** не знайдено.", ephemeral=True)
        return

    record_id, nick, added_by_id = row
    if added_by_id != interaction.user.id:
        await interaction.response.send_message(
            f"⛔ Ти не можеш видалити чужий доказ (#{record_id} на {nick}). Дозволено видаляти лише власні докази!",
            ephemeral=True
        )
        return

    cursor.execute("DELETE FROM evidence WHERE id = ?", (id_доказу,))
    conn.commit()
    await interaction.response.send_message(f"🗑️ Твій доказ **#{record_id} на гравця {nick}** видалено з бази.", ephemeral=True)


bot.run(TOKEN)
