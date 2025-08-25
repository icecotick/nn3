import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
from discord import Embed, Colour
import random
import os
import asyncpg
import asyncio
import requests
import time
from threading import Thread
from flask import Flask

# Настройки
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ROLE_NAME = "Патриот"
ADMIN_ROLES = ["создатель", "главный модер"]
CUSTOM_ROLE_PRICE = 2000
CRIT_CHANCE = 10
SUCCESS_CHANCE = 40
CLAN_CREATION_PRICE = 5000
MUTE_ROLE_NAME = "Muted"

# Проверка переменных
if not TOKEN:
    print("❌ Ошибка: Не установлен DISCORD_TOKEN")
    exit(1)

if not DATABASE_URL:
    print("❌ Ошибка: Не установлен DATABASE_URL")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Функция автоудаления
async def delete_after_delay(message, delay=60):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass
      # Функции базы данных
async def create_db_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance INTEGER DEFAULT 0,
                    profile_description TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_roles (
                    user_id BIGINT PRIMARY KEY,
                    role_id BIGINT,
                    role_name TEXT,
                    role_color TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS clans (
                    name TEXT PRIMARY KEY,
                    owner_id BIGINT,
                    balance INTEGER DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_clans (
                    user_id BIGINT PRIMARY KEY,
                    clan_name TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS levels (
                    user_id BIGINT PRIMARY KEY,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1
                )
            """)
        return pool
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")
        exit(1)

async def get_balance(user_id: int):
    async with bot.db.acquire() as conn:
        result = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
        return result["balance"] if result else 0

async def update_balance(user_id: int, amount: int):
    async with bot.db.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, balance) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET balance = users.balance + $2
        """, user_id, amount)

async def get_custom_role(user_id: int):
    async with bot.db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM custom_roles WHERE user_id = $1", user_id)

async def create_custom_role(user_id: int, role_id: int, role_name: str, role_color: str):
    async with bot.db.acquire() as conn:
        await conn.execute("""
            INSERT INTO custom_roles (user_id, role_id, role_name, role_color)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET
            role_id = $2, role_name = $3, role_color = $4
        """, user_id, role_id, role_name, role_color)

async def get_user_clan(user_id: int):
    async with bot.db.acquire() as conn:
        return await conn.fetchval("SELECT clan_name FROM user_clans WHERE user_id = $1", user_id)

async def add_user_to_clan(user_id: int, clan_name: str):
    async with bot.db.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_clans (user_id, clan_name) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET clan_name = $2
        """, user_id, clan_name)

async def get_profile_description(user_id: int):
    async with bot.db.acquire() as conn:
        result = await conn.fetchrow("SELECT profile_description FROM users WHERE user_id = $1", user_id)
        return result["profile_description"] if result and result["profile_description"] else "Описание отсутствует"

async def update_profile_description(user_id: int, description: str):
    async with bot.db.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, profile_description) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET profile_description = $2
        """, user_id, description)

async def get_level_data(user_id: int):
    async with bot.db.acquire() as conn:
        result = await conn.fetchrow("SELECT xp, level FROM levels WHERE user_id = $1", user_id)
        return {"xp": result["xp"], "level": result["level"]} if result else {"xp": 0, "level": 1}

async def update_level(user_id: int, xp: int, level: int):
    async with bot.db.acquire() as conn:
        await conn.execute("""
            INSERT INTO levels (user_id, xp, level) VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET xp = $2, level = $3
        """, user_id, xp, level)
      class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_admin(self, member):
        return any(role.name.lower() in [r.lower() for r in ADMIN_ROLES] for role in member.roles)

    @commands.command(name="славанн")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def slav_party(self, ctx):
        user = ctx.author
        role = discord.utils.get(ctx.guild.roles, name=ROLE_NAME)

        if not role:
            await ctx.send('❌ Роль не найдена!')
            return

        if role in user.roles:
            await ctx.send(f'🟥 {user.mention}, ты уже Патриот!')
            return

        roll = random.randint(1, 100)
        balance = await get_balance(user.id)

        if roll <= CRIT_CHANCE:
            await user.add_roles(role)
            await update_balance(user.id, 1000)
            msg = await ctx.send(f'💥 **КРИТ!** {user.mention}, ты получил роль + 1000 социального рейтинга! (Баланс: {await get_balance(user.id)})')
            await delete_after_delay(msg, 60)

        elif roll <= SUCCESS_CHANCE:
            await user.add_roles(role)
            await update_balance(user.id, 100)
            msg = await ctx.send(f'🟥 {user.mention}, ты получил роль + 100 рейтинга! (Баланс: {await get_balance(user.id)})')
            await delete_after_delay(msg, 60)

        else:
            penalty = min(10, balance)
            await update_balance(user.id, -penalty)
            msg = await ctx.send(f'🕊 {user.mention}, -{penalty} рейтинга. Попробуй ещё! (Баланс: {await get_balance(user.id)})')
            await delete_after_delay(msg, 60)

    @commands.command(name="фарм")
    @commands.cooldown(1, 1200, commands.BucketType.user)
    async def farm(self, ctx):
        user = ctx.author
        role = discord.utils.get(ctx.guild.roles, name=ROLE_NAME)

        if not role or role not in user.roles:
            await ctx.send("⛔ Эта команда доступна только для Патриотов.")
            return

        reward = random.randint(5, 15)
        await update_balance(user.id, reward)
        msg = await ctx.send(f"🌾 {user.mention}, вы заработали {reward} соц. кредитов! (Баланс: {await get_balance(user.id)})")
        await delete_after_delay(msg, 60)

    @commands.command(name="баланс")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def balance(self, ctx):
        bal = await get_balance(ctx.author.id)
        await ctx.send(f'💰 {ctx.author.mention}, ваш баланс: {bal}')

    @commands.command(name="перевести")
    async def transfer(self, ctx, member: discord.Member, amount: int):
        if amount <= 0:
            await ctx.send("❌ Сумма должна быть положительной!")
            return
        if member == ctx.author:
            await ctx.send("❌ Нельзя переводить самому себе!")
            return

        sender_balance = await get_balance(ctx.author.id)
        if sender_balance < amount:
            await ctx.send("❌ Недостаточно средств!")
            return

        await update_balance(ctx.author.id, -amount)
        await update_balance(member.id, amount)
        msg = await ctx.send(f'✅ {ctx.author.mention} перевел {amount} рейтинга {member.mention}!')
        await delete_after_delay(msg, 60)

    @commands.command(name="топ")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def top(self, ctx):
        async with bot.db.acquire() as conn:
            top_users = await conn.fetch("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")

        if not top_users:
            await ctx.send("😔 Таблица пуста.")
            return

        leaderboard = []
        for i, record in enumerate(top_users, start=1):
            try:
                user = await bot.fetch_user(record['user_id'])
                leaderboard.append(f"{i}. {user.name} — {record['balance']} кредитов")
            except:
                leaderboard.append(f"{i}. [Неизвестный пользователь] — {record['balance']} кредитов")

        await ctx.send("🏆 **Топ 10 Патриотов:**\n" + "\n".join(leaderboard))

    @commands.command(name="допкредит")
    async def add_credits(self, ctx, member: discord.Member, amount: int):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        if amount <= 0:
            await ctx.send("❌ Сумма должна быть положительной!")
            return
        
        await update_balance(member.id, amount)
        new_balance = await get_balance(member.id)
        msg = await ctx.send(f"✅ Администратор {ctx.author.mention} добавил {amount} кредитов пользователю {member.mention}\n💰 Новый баланс: {new_balance} кредитов")
        await delete_after_delay(msg, 60)

    @commands.command(name="минускредит")
    async def remove_credits(self, ctx, member: discord.Member, amount: int):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        if amount <= 0:
            await ctx.send("❌ Сумма должна быть положительной!")
            return
        
        current_balance = await get_balance(member.id)
        if current_balance < amount:
            await ctx.send(f"❌ У пользователя только {current_balance} кредитов, нельзя снять {amount}!")
            return
        
        await update_balance(member.id, -amount)
        new_balance = await get_balance(member.id)
        msg = await ctx.send(f"✅ Администратор {ctx.author.mention} снял {amount} кредитов у пользователя {member.mention}\n💰 Новый баланс: {new_balance} кредитов")
        await delete_after_delay(msg, 60)

    @commands.command(name="магазин")
    async def shop(self, ctx):
        shop_text = f"""
🛍 **Магазин социального кредита:**

🎨 `!купитьроль "Название" #Цвет` - Купить кастомную роль ({CUSTOM_ROLE_PRICE} кредитов)
Пример: `!купитьроль "Богач" #ff0000`

💰 Ваш баланс: {await get_balance(ctx.author.id)} кредитов
"""
        await ctx.send(shop_text)

    @commands.command(name="купитьроль")
    async def buy_role(self, ctx, role_name: str, role_color: str):
        user = ctx.author
        balance = await get_balance(user.id)
        
        if balance < CUSTOM_ROLE_PRICE:
            await ctx.send(f"❌ Недостаточно средств! Нужно {CUSTOM_ROLE_PRICE} кредитов, у вас {balance}.")
            return
        
        existing_role = await get_custom_role(user.id)
        if existing_role:
            try:
                old_role = ctx.guild.get_role(existing_role['role_id'])
                if old_role:
                    await old_role.delete()
            except:
                pass
        
        try:
            color = discord.Color.from_str(role_color)
            new_role = await ctx.guild.create_role(
                name=role_name,
                color=color,
                reason=f"Кастомная роль для {user.name}"
            )
            
            await user.add_roles(new_role)
            await create_custom_role(user.id, new_role.id, role_name, role_color)
            await update_balance(user.id, -CUSTOM_ROLE_PRICE)
            
            msg = await ctx.send(f"✅ {user.mention}, вы успешно купили роль {new_role.mention} за {CUSTOM_ROLE_PRICE} кредитов!")
            await delete_after_delay(msg, 60)
        except ValueError:
            await ctx.send("❌ Неверный формат цвета! Используйте HEX формат, например: `#ff0000`")
        except Exception as e:
            print(f"Ошибка при создании роли: {e}")
            await ctx.send("❌ Произошла ошибка при создании роли. Попробуйте позже.")

    @commands.command(name="помощь")
    async def help_command(self, ctx):
        help_text = """
📜 **Команды бота:**

🔴 `!славанн` — попытка стать Патриотом (2ч кд)
🌾 `!фарм` — заработать кредиты (20м кд, только для Патриотов)
💰 `!баланс` — показать ваш баланс (5с кд)
💸 `!перевести @юзер сумма` — перевод кредитов
🏆 `!топ` — топ-10 по балансу (5с кд)
🎰 `!рулетка ставка` — игра в рулетку (30с кд)
🛍 `!магазин` — просмотреть доступные товары
🎨 `!купитьроль "Название" #Цвет` — купить кастомную роль (2000 кредитов)
➕ `!допкредит @юзер сумма` — добавить кредиты (только для админов)
➖ `!минускредит @юзер сумма` — снять кредиты (только для админов)
👥 `!создатьклан название` — создать клан
👥 `!войтивклан название` — вступить в клан
🏆 `!клантоп` — топ кланов
👤 `!профиль @юзер` — посмотреть профиль
📝 `!описание_профиль текст` — изменить описание профиля
🎁 `!ежедневный` — ежедневная награда (24ч кд)
⚔️ `!дуэль @игрок ставка` — PvP дуэль (5м кд)
ℹ️ `!помощь` — это сообщение

**Примеры:**
`!купитьроль "Богач" #ff0000`
`!допкредит @User 500`
`!рулетка 100`
`!профиль @Участник`
`!дуэль @Игрок 200`
"""
        await ctx.send(help_text)

class Clans(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="создатьклан")
    async def create_clan(self, ctx, clan_name: str):
        user = ctx.author
        balance = await get_balance(user.id)
        
        if balance < CLAN_CREATION_PRICE:
            await ctx.send(f"❌ Нужно {CLAN_CREATION_PRICE} кредитов для создания клана!")
            return
        
        current_clan = await get_user_clan(user.id)
        if current_clan:
            await ctx.send("❌ Вы уже состоите в клане!")
            return
        
        async with bot.db.acquire() as conn:
            clan_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM clans WHERE name = $1)",
                clan_name
            )
            if clan_exists:
                await ctx.send("❌ Клан с таким именем уже существует!")
                return
            
            await conn.execute(
                "INSERT INTO clans (name, owner_id, balance) VALUES ($1, $2, $3)",
                clan_name, user.id, 0
            )
            await conn.execute(
                "INSERT INTO user_clans (user_id, clan_name) VALUES ($1, $2)",
                user.id, clan_name
            )
        
        await update_balance(user.id, -CLAN_CREATION_PRICE)
        msg = await ctx.send(f"✅ Клан '{clan_name}' создан! Вы стали лидером.")
        await delete_after_delay(msg, 60)

    @commands.command(name="войтивклан")
    async def join_clan(self, ctx, clan_name: str):
        user = ctx.author
        
        current_clan = await get_user_clan(user.id)
        if current_clan:
            await ctx.send("❌ Вы уже состоите в клане!")
            return
        
        async with bot.db.acquire() as conn:
            clan_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM clans WHERE name = $1)",
                clan_name
            )
            
            if not clan_exists:
                await ctx.send("❌ Такого клана не существует!")
                return
            
            await conn.execute(
                "INSERT INTO user_clans (user_id, clan_name) VALUES ($1, $2)",
                user.id, clan_name
            )
        
        msg = await ctx.send(f"✅ Вы вступили в клан '{clan_name}'!")
        await delete_after_delay(msg, 60)

    @commands.command(name="клантоп")
    async def clan_top(self, ctx):
        async with bot.db.acquire() as conn:
            top_clans = await conn.fetch(
                "SELECT name, balance FROM clans ORDER BY balance DESC LIMIT 10"
            )
        
        if not top_clans:
            await ctx.send("😔 Кланов пока нет.")
            return
        
        leaderboard = []
        for i, clan in enumerate(top_clans, start=1):
            leaderboard.append(f"{i}. {clan['name']} — {clan['balance']} кредитов")
        
        await ctx.send("🏆 **Топ кланов:**\n" + "\n".join(leaderboard))

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="профиль")
    async def profile(self, ctx, member: discord.Member = None):
        if not member:
            member = ctx.author
        
        balance = await get_balance(member.id)
        clan = await get_user_clan(member.id)
        description = await get_profile_description(member.id)
        level_data = await get_level_data(member.id)
        
        embed = Embed(
            title=f"👤 Профиль {member.name}",
            color=member.color,
            description=description
        )
        
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(name="💰 Баланс", value=f"{balance} кредитов", inline=True)
        embed.add_field(name="👥 Клан", value=clan if clan else "Нет клана", inline=True)
        embed.add_field(name="📊 Уровень", value=f"{level_data['level']} ({level_data['xp']} XP)", inline=True)
        
        embed.set_footer(text=f"ID: {member.id}")
        
        await ctx.send(embed=embed)

    @commands.command(name="описание_профиль")
    async def set_profile_description(self, ctx, *, description: str):
        if len(description) > 200:
            await ctx.send("❌ Описание не должно превышать 200 символов!")
            return
        
        await update_profile_description(ctx.author.id, description)
        msg = await ctx.send("✅ Описание профиля обновлено!")
        await delete_after_delay(msg, 60)

  class Mod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_admin(self, member):
        return any(role.name.lower() in [r.lower() for r in ADMIN_ROLES] for role in member.roles)

    @commands.command(name="мут")
    async def mute(self, ctx, member: discord.Member, time: int, *, reason: str = "Не указана"):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
        if not mute_role:
            mute_role = await ctx.guild.create_role(
                name=MUTE_ROLE_NAME,
                reason="Создание роли для мьюта"
            )
            
            for channel in ctx.guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, speak=False)
        
        await member.add_roles(mute_role)
        msg = await ctx.send(f"✅ {member.mention} замьючен на {time} минут по причине: {reason}")
        await delete_after_delay(msg, 60)

    @commands.command(name="размут")
    async def unmute(self, ctx, member: discord.Member):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role)
            msg = await ctx.send(f"✅ {member.mention} размьючен!")
            await delete_after_delay(msg, 60)
        else:
            await ctx.send("❌ Пользователь не замьючен!")

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ежедневный")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx):
        reward = random.randint(100, 500)
        await update_balance(ctx.author.id, reward)
        msg = await ctx.send(f"🎁 {ctx.author.mention}, вы получили {reward} кредитов!")
        await delete_after_delay(msg, 60)

    @commands.command(name="рулетка")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def roulette(self, ctx, bet: int):
        if bet <= 0:
            await ctx.send("❌ Ставка должна быть положительной!")
            return

        balance = await get_balance(ctx.author.id)
        if balance < bet:
            await ctx.send("❌ Недостаточно кредитов!")
            return

        outcome = random.choice(["win", "lose", "refund"])

        if outcome == "win":
            await update_balance(ctx.author.id, bet)
            msg = await ctx.send(f"🎉 {ctx.author.mention} выиграл {bet} кредитов!")
        elif outcome == "lose":
            await update_balance(ctx.author.id, -bet)
            msg = await ctx.send(f"💀 {ctx.author.mention} проиграл {bet} кредитов...")
        else:
            msg = await ctx.send(f"🔄 {ctx.author.mention} вернул свои {bet} кредитов!")
        
        await delete_after_delay(msg, 60)

    @commands.command(name="дуэль")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def duel(self, ctx, member: discord.Member, bet: int):
        if member == ctx.author:
            await ctx.send("❌ Нельзя вызвать самого себя!")
            return
        if bet <= 0:
            await ctx.send("❌ Ставка должна быть положительной!")
            return
        
        # Проверка баланса
        challenger_balance = await get_balance(ctx.author.id)
        target_balance = await get_balance(member.id)
        
        if challenger_balance < bet:
            await ctx.send("❌ У вас недостаточно кредитов!")
            return
        if target_balance < bet:
            await ctx.send("❌ У соперника недостаточно кредитов!")
            return
        
        # Случайный исход 50/50
        winner = ctx.author if random.random() > 0.5 else member
        loser = member if winner == ctx.author else ctx.author
        
        # Перевод денег
        await update_balance(winner.id, bet)
        await update_balance(loser.id, -bet)

      
        
        embed = Embed(
            title="⚔️ Дуэль завершена!",
            description=f"{winner.mention} побеждает и забирает {bet} кредитов у {loser.mention}!",
            color=Colour.green()
        )
        msg = await ctx.send(embed=embed)
        await delete_after_delay(msg, 60)
      class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("✅ Таблицы в БД готовы!")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            seconds = int(error.retry_after)
            minutes = seconds // 60
            seconds = seconds % 60
            await ctx.send(f"⏳ Подождите {minutes}м {seconds}с, прежде чем использовать эту команду снова.")
        else:
            print(f"⚠ Ошибка команды: {error}")
            await ctx.send("❌ Произошла ошибка при выполнении команды")

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            # Даем XP за сообщение (раз в минуту)
            user_id = message.author.id
            current_data = await get_level_data(user_id)
            current_xp = current_data['xp']
            current_level = current_data['level']
            
            # Добавляем XP
            xp_gain = random.randint(5, 15)
            new_xp = current_xp + xp_gain
            
            # Проверяем уровень
            xp_needed = current_level * 100
            new_level = current_level
            
            if new_xp >= xp_needed:
                new_level += 1
                new_xp = 0  # Сбрасываем XP при повышении уровня
                # Отправляем сообщение о новом уровне с автоудалением
                level_msg = await message.channel.send(f"🎉 {message.author.mention} достиг {new_level} уровня!")
                await delete_after_delay(level_msg, 60)
            
            # Обновляем данные в БД
            await update_level(user_id, new_xp, new_level)
        
        await self.bot.process_commands(message)

# Простой HTTP-сервер для Render
app = Flask('')

@app.route('/')
def home():
    return "🤖 Discord Bot is Alive!"

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
  async def setup():
    await bot.add_cog(Economy(bot))
    await bot.add_cog(Clans(bot))
    await bot.add_cog(Profile(bot))
    await bot.add_cog(Mod(bot))
    await bot.add_cog(Fun(bot))
    await bot.add_cog(Events(bot))

@bot.event
async def on_ready():
    try:
        bot.db = await create_db_pool()
        await setup()
        
        # Запускаем Flask в отдельном потоке
        web_thread = Thread(target=run_web)
        web_thread.daemon = True
        web_thread.start()
        
        print(f"✅ Бот запущен как {bot.user}")
        print("✅ HTTP-сервер запущен на порту 8080")
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")
        await bot.close()

async def close_db():
    if hasattr(bot, 'db') and not bot.db.is_closed():
        await bot.db.close()
        print("✅ Соединение с базой данных закрыто")

@bot.event
async def on_disconnect():
    await close_db()

def run_bot():
    try:
        asyncio.run(bot.start(TOKEN))
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал прерывания, завершаю работу...")
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")

if __name__ == "__main__":
    run_bot()
