import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
import random
import os
import asyncpg
import asyncio

# ==================== КОНФИГ ====================
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

# ==================== БАЗА ДАННЫХ ====================
async def create_db_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance INTEGER DEFAULT 0,
                    profile_description TEXT
                )
            """)
            # Таблица кастомных ролей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_roles (
                    user_id BIGINT PRIMARY KEY,
                    role_id BIGINT,
                    role_name TEXT,
                    role_color TEXT
                )
            """)
            # Таблица кланов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS clans (
                    name TEXT PRIMARY KEY,
                    owner_id BIGINT,
                    balance INTEGER DEFAULT 0
                )
            """)
            # Таблица связи пользователей и кланов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_clans (
                    user_id BIGINT PRIMARY KEY,
                    clan_name TEXT
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

# ==================== ЭКОНОМИКА ====================
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
            await ctx.send(f'💥 **КРИТ!** {user.mention}, ты получил роль + 1000 социального рейтинга! (Баланс: {await get_balance(user.id)})')

        elif roll <= SUCCESS_CHANCE:
            await user.add_roles(role)
            await update_balance(user.id, 100)
            await ctx.send(f'🟥 {user.mention}, ты получил роль + 100 рейтинга! (Баланс: {await get_balance(user.id)})')

        else:
            penalty = min(10, balance)
            await update_balance(user.id, -penalty)
            await ctx.send(f'🕊 {user.mention}, -{penalty} рейтинга. Попробуй ещё! (Баланс: {await get_balance(user.id)})')

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
        await ctx.send(f"🌾 {user.mention}, вы заработали {reward} соц. кредитов! (Баланс: {await get_balance(user.id)})")

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
        await ctx.send(f'✅ {ctx.author.mention} перевел {amount} рейтинга {member.mention}!')

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
        await ctx.send(f"✅ Администратор {ctx.author.mention} добавил {amount} кредитов пользователю {member.mention}\n💰 Новый баланс: {new_balance} кредитов")

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
        await ctx.send(f"✅ Администратор {ctx.author.mention} снял {amount} кредитов у пользователя {member.mention}\n💰 Новый баланс: {new_balance} кредитов")

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
            
            await ctx.send(f"✅ {user.mention}, вы успешно купили роль {new_role.mention} за {CUSTOM_ROLE_PRICE} кредитов!")
        except ValueError:
            await ctx.send("❌ Неверный формат цвета! Используйте HEX формат, например: `#ff0000`")
        except Exception as e:
            print(f"Ошибка при создании роли: {e}")
            await ctx.send("❌ Произошла ошибка при создании роли. Попробуйте позже.")

    @commands.command(name="помощь")
    async def help_command(self, ctx):
        help_text = f"""
📜 **Команды бота:**

🔴 `!славанн` — попытка стать Патриотом (2ч кд)
🌾 `!фарм` — заработать кредиты (20м кд, только для Патриотов)
💰 `!баланс` — показать ваш баланс (5с кд)
💸 `!перевести @юзер сумма` — перевод кредитов
🏆 `!топ` — топ-10 по балансу (5с кд)
🛍 `!магазин` — просмотреть доступные товары
🎨 `!купитьроль "Название" #Цвет` — купить кастомную роль ({CUSTOM_ROLE_PRICE} кредитов)
➕ `!допкредит @юзер сумма` — добавить кредиты (только для админов)
➖ `!минускредит @юзер сумма` — снять кредиты (только для админов)
👥 `!создатьклан название` — создать клан
👥 `!войтивклан название` — вступить в клан
🏆 `!клантоп` — топ кланов
👤 `!профиль @юзер` — посмотреть профиль
📝 `!описание_профиль текст` — изменить описание профиля
ℹ️ `!помощь` — это сообщение

Примеры:
`!купитьроль "Богач" #ff0000`
`!допкредит @Пользователь 500`
`!профиль @Участник`
"""
        await ctx.send(help_text)

# ==================== КЛАНЫ ====================
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
        await ctx.send(f"✅ Клан '{clan_name}' создан! Вы стали лидером.")

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
        
        await ctx.send(f"✅ Вы вступили в клан '{clan_name}'!")

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

# ==================== ПРОФИЛЬ ====================
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
        
        embed = discord.Embed(
            title=f"Профиль {member.name}",
            color=member.color
        )
        
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(name="💰 Баланс", value=f"{balance} кредитов", inline=True)
        embed.add_field(name="👥 Клан", value=clan if clan else "Нет клана", inline=True)
        embed.add_field(name="📝 Описание", value=description, inline=False)
        embed.set_footer(text=f"ID: {member.id}")
        
        await ctx.send(embed=embed)

    @commands.command(name="описание_профиль")
    async def set_profile_description(self, ctx, *, description: str):
        if len(description) > 200:
            await ctx.send("❌ Описание не должно превышать 200 символов!")
            return
        
        await update_profile_description(ctx.author.id, description)
        await ctx.send("✅ Описание профиля обновлено!")

# ==================== МОДЕРАЦИЯ ====================
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
        await ctx.send(f"✅ {member.mention} замьючен на {time} минут по причине: {reason}")

    @commands.command(name="размут")
    async def unmute(self, ctx, member: discord.Member):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role)
            await ctx.send(f"✅ {member.mention} размьючен!")
        else:
            await ctx.send("❌ Пользователь не замьючен!")

# ==================== РАЗВЛЕЧЕНИЯ ====================
class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ежедневный")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx):
        reward = random.randint(100, 500)
        await update_balance(ctx.author.id, reward)
        await ctx.send(f"🎁 {ctx.author.mention}, вы получили {reward} кредитов!")

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
            await ctx.send(f"🎉 {ctx.author.mention} выиграл {bet} кредитов!")
        elif outcome == "lose":
            await update_balance(ctx.author.id, -bet)
            await ctx.send(f"💀 {ctx.author.mention} проиграл {bet} кредитов...")
        else:
            await ctx.send(f"🔄 {ctx.author.mention} вернул свои {bet} кредитов.")

# ==================== СОБЫТИЯ ====================
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

# ==================== ЗАПУСК БОТА ====================
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
        print(f"✅ Бот запущен как {bot.user}")
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
