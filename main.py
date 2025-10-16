import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
import random
import os
import asyncpg
import asyncio
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import signal
import sys

# ==================== КОНФИГУРАЦИЯ ====================
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Настройки бота
ROLE_NAME = "Патриот"
ADMIN_ROLES = ["создатель", "главный модер"]
CUSTOM_ROLE_PRICE = 2000
CRIT_CHANCE = 10
SUCCESS_CHANCE = 40
CLAN_CREATION_PRICE = 5000
MUTE_ROLE_NAME = "Muted"

# Проверка переменных окружения
if not TOKEN:
    print("❌ Ошибка: Не установлен DISCORD_TOKEN")
    sys.exit(1)

if not DATABASE_URL:
    print("❌ Ошибка: Не установлен DATABASE_URL")
    sys.exit(1)

# Настройки Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== FLASK СЕРВЕР ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот активен! 🤖"

@app.route('/health')
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

def run_flask():
    try:
        port = int(os.environ.get('PORT', 8080))
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"❌ Ошибка Flask: {e}")

def keep_alive():
    try:
        flask_thread = Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        print("✅ Веб-сервер запущен")
    except Exception as e:
        print(f"❌ Ошибка при запуске веб-сервера: {e}")

# ==================== БАЗА ДАННЫХ ====================
async def create_db_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance INTEGER DEFAULT 0,
                    profile_description TEXT,
                    daily_claimed TIMESTAMP,
                    farm_booster_until TIMESTAMP,
                    roulette_booster_until TIMESTAMP,
                    business_license TEXT,
                    business_income INTEGER DEFAULT 0,
                    last_business_claim TIMESTAMP
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
                    balance INTEGER DEFAULT 0,
                    member_slots INTEGER DEFAULT 10,
                    income_multiplier DECIMAL DEFAULT 1.0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_clans (
                    user_id BIGINT PRIMARY KEY,
                    clan_name TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS premium_roles (
                    user_id BIGINT PRIMARY KEY,
                    role_type TEXT,
                    purchased_at TIMESTAMP DEFAULT NOW()
                )
            """)
        return pool
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")
        sys.exit(1)

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

async def get_user_data(user_id: int):
    async with bot.db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def get_user_clan(user_id: int):
    async with bot.db.acquire() as conn:
        return await conn.fetchval("SELECT clan_name FROM user_clans WHERE user_id = $1", user_id)

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
    def init(self, bot):
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
            await ctx.send(f'💥 КРИТ! {user.mention}, ты получил роль + 1000 социального рейтинга! (Баланс: {await get_balance(user.id)})')

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
            await ctx.send("⛔️ Эта команда доступна только для Патриотов.")
            return

        user_data = await get_user_data(user.id)
        base_reward = random.randint(30, 70)
        
        if user_data and user_data['farm_booster_until'] and user_data['farm_booster_until'] > datetime.now():
            reward = int(base_reward * 1.5)
            booster_text = " 🚀 (с бустером)"
        else:
            reward = base_reward
            booster_text = ""

        await update_balance(user.id, reward)
        await ctx.send(f"🌾 {user.mention}, вы заработали {reward} соц. кредитов{booster_text}! (Баланс: {await get_balance(user.id)})")

    @commands.command(name="баланс")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def balance(self, ctx):
        bal = await get_balance(ctx.author.id)
        await ctx.send(f'💰 {ctx.author.mention}, ваш баланс: {bal} кредитов')

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
        await ctx.send(f'✅ {ctx.author.mention} перевел {amount} кредитов {member.mention}!')

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

        await ctx.send("🏆 Топ 10 Патриотов:**\n" + "\n".join(leaderboard))

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
        balance = await get_balance(ctx.author.id)
        
        shop_text = f"""
🛍 Магазин социального кредита:

🎨 Кастомные роли
!купитьроль "Название" #Цвет - Персональная роль ({CUSTOM_ROLE_PRICE} кредитов)

🏷 Премиум-роли (появляются в топе участников)
!купитьпремиум золотой - Золотая роль (5000 кредитов)
!купитьпремиум платиновый - Платиновая роль (10000 кредитов)

🎁 Бустеры доходов
!бустер фарма - +50% к фарму на 24 часа (1500 кредитов)
!бустер рулетки - +25% к шансу выигрыша на 12 часов (2000 кредитов)

💼 Бизнес-лицензии (пассивный доход)
!купитьлицензию малый - Малый бизнес (+100 кредитов/час, 8000 кредитов)
!купитьлицензию средний - Средний бизнес (+250 кредитов/час, 15000 кредитов)
!купитьлицензию крупный - Крупный бизнес (+500 кредитов/час, 30000 кредитов)

🎯 Особые возможности
!сменитьник "новый ник" - Смена ника на сервере (3000 кредитов)
!анонс текст - Отправить объявление в спец. канал (5000 кредитов)

💰 Ваш баланс: {balance} кредитов

Примеры:
!купитьроль "Богач" #ff0000
!бустер фарма
!купитьлицензию малый
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
            await ctx.send("❌ Неверный формат цвета! Используйте HEX формат, например: #ff0000")
        except Exception as e:
            print(f"Ошибка при создании роли: {e}")
            await ctx.send("❌ Произошла ошибка при создании роли. Попробуйте позже.")

    @commands.command(name="купитьпремиум")
    async def buy_premium_role(self, ctx, role_type: str):
        user = ctx.author
        balance = await get_balance(user.id)
        
        premium_roles = {
            "золотой": {"price": 5000, "color": discord.Color.gold()},
            "платиновый": {"price": 10000, "color": discord.Color.light_grey()}
        }
        
        role_type = role_type.lower()
        if role_type not in premium_roles:
            await ctx.send("❌ Доступные премиум-роли: 'золотой', 'платиновый'")
            return
        
        role_data = premium_roles[role_type]
        if balance < role_data["price"]:
            await ctx.send(f"❌ Недостаточно средств! Нужно {role_data['price']} кредитов.")
            return
        
        role_name = f"{role_type.capitalize()} Патриот"
        
        existing_role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not existing_role:
            existing_role = await ctx.guild.create_role(
                name=role_name,
                color=role_data["color"],
                hoist=True,
                reason="Премиум роль из магазина"
            )
        
        await user.add_roles(existing_role)
        await update_balance(user.id, -role_data["price"])
        
        async with bot.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO premium_roles (user_id, role_type) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET role_type = $2
            """, user.id, role_type)
        
        await ctx.send(f"✅ {user.mention}, вы купили премиум-роль {existing_role.mention}!")

    @commands.command(name="бустер")
    async def buy_booster(self, ctx, booster_type: str):
        user = ctx.author
        balance = await get_balance(user.id)
        
        boosters = {
            "фарма": {"price": 1500, "duration": 86400},
            "рулетки": {"price": 2000, "duration": 43200}
        }
        
        booster_type = booster_type.lower()
        if booster_type not in boosters:
            await ctx.send("❌ Доступные бустеры: 'фарма', 'рулетки'")
            return
        
        booster_data = boosters[booster_type]
        if balance < booster_data["price"]:
            await ctx.send(f"❌ Недостаточно средств! Нужно {booster_data['price']} кредитов.")
            return
        
        booster_until = datetime.now() + timedelta(seconds=booster_data["duration"])
        
        async with bot.db.acquire() as conn:
            if booster_type == "фарма":
                await conn.execute("""
                    INSERT INTO users (user_id, farm_booster_until) VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET farm_booster_until = $2
                """, user.id, booster_until)
            else:
                await conn.execute("""
                    INSERT INTO users (user_id, roulette_booster_until) VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET roulette_booster_until = $2
                """, user.id, booster_until)
        
        await update_balance(user.id, -booster_data["price"])
        hours = booster_data["duration"] // 3600
        await ctx.send(f"🚀 {user.mention}, вы активировали бустер {booster_type} на {hours} часов!")

    @commands.command(name="купитьлицензию")
    async def buy_license(self, ctx, license_type: str):
        user = ctx.author
        balance = await get_balance(user.id)
        
        licenses = {
            "малый": {"price": 8000, "income": 100},
            "средний": {"price": 15000, "income": 250},
            "крупный": {"price": 30000, "income": 500}
        }
        
        license_type = license_type.lower()
        if license_type not in licenses:
            await ctx.send("❌ Доступные лицензии: 'малый', 'средний', 'крупный'")
            return
        
        license_data = licenses[license_type]
        if balance < license_data["price"]:
            await ctx.send(f"❌ Недостаточно средств! Нужно {license_data['price']} кредитов.")
            return
        
        async with bot.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, business_license, business_income, last_business_claim) 
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE SET 
                business_license = $2, business_income = $3, last_business_claim = $4
            """, user.id, license_type, license_data["income"], datetime.now())
        
        await update_balance(user.id, -license_data["price"])
        await ctx.send(f"💼 {user.mention}, вы купили {license_type} бизнес! (+{license_data['income']} кредитов/час)")

    @commands.command(name="сменитьник")
    async def change_nickname(self, ctx, *, new_nickname: str):
        user = ctx.author
        balance = await get_balance(user.id)
        price = 3000
        
        if balance < price:
            await ctx.send(f"❌ Недостаточно средств! Нужно {price} кредитов.")
            return
        
        if len(new_nickname) > 32:
            await ctx.send("❌ Слишком длинный ник! Максимум 32 символа.")
            return
        
        try:
            await user.edit(nick=new_nickname)
            await update_balance(user.id, -price)
            await ctx.send(f"✅ {user.mention}, ваш ник изменен на '{new_nickname}'!")
        except discord.Forbidden:
            await ctx.send("❌ У бота нет прав для смены ника!")

    @commands.command(name="анонс")
    async def make_announcement(self, ctx, *, announcement: str):
        user = ctx.author
        balance = await get_balance(user.id)
        price = 5000
        
        if balance < price:
            await ctx.send(f"❌ Недостаточно средств! Нужно {price} кредитов.")
            return
        
        embed = discord.Embed(
            title="📢 Объявление от сообщества",
            description=announcement,
            color=0x00ff00,
            timestamp=datetime.now()
        )
        embed.set_author(name=user.display_name, icon_url=user.avatar.url if user.avatar else user.default_avatar.url)
        embed.set_footer(text="Купить размещение: !анонс текст")
        
        await ctx.send(embed=embed)
        await update_balance(user.id, -price)
        await ctx.send(f"✅ {user.mention}, ваше объявление опубликовано!")

    @commands.command(name="ежедневный")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx):
        reward = random.randint(100, 500)
        await update_balance(ctx.author.id, reward)
        
        async with bot.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, daily_claimed) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET daily_claimed = $2
            """, ctx.author.id, datetime.now())
        
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

        user_data = await get_user_data(ctx.author.id)
        has_roulette_booster = user_data and user_data['roulette_booster_until'] and user_data['roulette_booster_until'] > datetime.now()
        
        if has_roulette_booster:
            outcomes = ["win", "win", "lose", "jackpot", "refund"]
            weights = [30, 25, 20, 5, 20]
        else:
            outcomes = ["win", "lose", "refund"]
            weights = [40, 40, 20]

        outcome = random.choices(outcomes, weights=weights)[0]

        if outcome == "win":
            win_amount = bet * 2
            await update_balance(ctx.author.id, win_amount)
            await ctx.send(f"🎉 {ctx.author.mention} выиграл {win_amount} кредитов!{' 🚀' if has_roulette_booster else ''}")
        elif outcome == "jackpot":
            win_amount = bet * 5
            await update_balance(ctx.author.id, win_amount)
            await ctx.send(f"💰 ДЖЕКПОТ! {ctx.author.mention} выиграл {win_amount} кредитов! 🎰")
        elif outcome == "lose":
            await update_balance(ctx.author.id, -bet)
            await ctx.send(f"💀 {ctx.author.mention} проиграл {bet} кредитов...{' 🚀' if has_roulette_booster else ''}")
        else:
            await ctx.send(f"🔄 {ctx.author.mention} вернул свои {bet} кредитов.{' 🚀' if has_roulette_booster else ''}")
        
    @commands.command(name="помощь")
    async def help_command(self, ctx):
        try:
            help_text = """
📜 Команды бота:

🔰 Основные
🔴 !славанн — попытка стать Патриотом (2ч кд)
🌾 !фарм — заработать кредиты (20м кд, только для Патриотов)  
💰 !баланс — показать баланс (5с кд)
🎁 !ежедневный — ежедневная награда (24ч кд)

💸 Экономика
💸 !перевести @юзер сумма — перевод кредитов
🎰 !рулетка ставка — игра в рулетку (30с кд)
🏆 !топ — топ-10 по балансу (5с кд)

🛍 Магазин 
🛍 !магазин — просмотреть магазин
🎨 !купитьроль "Название" #Цвет — кастомная роль (2000к)
⭐️ !купитьпремиум тип — премиум-роль (5000-10000к)
🚀 !бустер тип — бустеры доходов (1500-2000к)
💼 !купитьлицензию тип — бизнес-лицензии (8000-30000к)
📝 !сменитьник "ник" — сменить ник (3000к)
📢 !анонс текст — отправить объявление (5000к)

👥 Кланы
👥 !создатьклан название — создать клан (5000к)
👥 !войтивклан название — вступить в клан
👥 !покинутьклан — покинуть клан
👥 !клан [название] — информация о клане
🏆 !клантоп — топ кланов
💵 !внести_клан сумма — внести в казну
💸 !снять_клан сумма — снять из казны (владелец)

👤 Профиль
👤 !профиль [@юзер] — посмотреть профиль
📝 !описание_профиль текст — изменить описание
🔄 !сбросить_описание — сбросить описание

🎮 Развлечения
🎲 !рандом [min] [max] — случайное число
🎯 !орёл — подбросить монетку
🤔 !выбор вариант1, вариант2 — случайный выбор
🎱 !шар вопрос — магический шар
🎰 !слоты [ставка] — игровые автоматы
📚 !викторина — случайная викторина
🎭 !кто вопрос — случайный участник

🛡 Модерация
🔇 !мут @участник [время] [причина] — замутить
🔊 !размут @участник — размутить
🧹 !очистить [кол-во] — очистить чат
👢 !кик @участник [причина] — кикнуть
🔨 !бан @участник [причина] — забанить

⚙️ Админ-команды
➕ !допкредит @юзер сумма — добавить кредиты
➖ !минускредит @юзер сумма — снять кредиты

ℹ️ !помощь — это сообщение
"""
            await ctx.send(help_text)
        except Exception as e:
            print(f"Ошибка в команде помощь: {e}")
            await ctx.send("Произошла ошибка при выполнении команды")

# ==================== КЛАНЫ ====================
class Clans(commands.Cog):
    def init(self, bot):
        self.bot = bot

    async def get_clan_members(self, clan_name: str):
        async with bot.db.acquire() as conn:
            return await conn.fetch("SELECT user_id FROM user_clans WHERE clan_name = $1", clan_name)

    async def get_clan_member_count(self, clan_name: str):
        async with bot.db.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM user_clans WHERE clan_name = $1", clan_name)

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
        
        if len(clan_name) > 20:
            await ctx.send("❌ Название клана не должно превышать 20 символов!")
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
            clan = await conn.fetchrow("SELECT * FROM clans WHERE name = $1", clan_name)
            if not clan:
                await ctx.send("❌ Такого клана не существует!")
                return
            
            member_count = await self.get_clan_member_count(clan_name)
            if member_count >= clan['member_slots']:
                await ctx.send("❌ В клане нет свободных мест!")
                return
            
            await conn.execute(
                "INSERT INTO user_clans (user_id, clan_name) VALUES ($1, $2)",
                user.id, clan_name
            )
        
        await ctx.send(f"✅ Вы вступили в клан '{clan_name}'!")

    @commands.command(name="покинутьклан")
    async def leave_clan(self, ctx):
        user = ctx.author
        current_clan = await get_user_clan(user.id)
        
        if not current_clan:
            await ctx.send("❌ Вы не состоите в клане!")
            return
        
        async with bot.db.acquire() as conn:
            clan_owner = await conn.fetchval("SELECT owner_id FROM clans WHERE name = $1", current_clan)
            if clan_owner == user.id:
                await ctx.send("❌ Владелец клана не может его покинуть! Сначала передайте ownership.")
                return
            
            await conn.execute("DELETE FROM user_clans WHERE user_id = $1", user.id)
        
        await ctx.send(f"✅ Вы покинули клан '{current_clan}'!")

    @commands.command(name="клан")
    async def clan_info(self, ctx, clan_name: str = None):
        if not clan_name:
            user_clan = await get_user_clan(ctx.author.id)
            if not user_clan:
                await ctx.send("❌ Вы не состоите в клане! Укажите название клана.")
                return
            clan_name = user_clan
        
        async with bot.db.acquire() as conn:
            clan = await conn.fetchrow("SELECT * FROM clans WHERE name = $1", clan_name)
            if not clan:
                await ctx.send("❌ Клан не найден!")
                return
            
            members = await self.get_clan_members(clan_name)
            member_count = len(members)
            
            try:
                owner = await bot.fetch_user(clan['owner_id'])
                owner_name = owner.name
            except:
                owner_name = "Неизвестный пользователь"
        
        embed = discord.Embed(
            title=f"🏰 Клан: {clan_name}",
            color=0x00ff00
        )
        
        embed.add_field(name="👑 Владелец", value=owner_name, inline=True)
        embed.add_field(name="💰 Казна", value=f"{clan['balance']} кредитов", inline=True)
        embed.add_field(name="👥 Участники", value=f"{member_count}/{clan['member_slots']}", inline=True)
        embed.add_field(name="📈 Множитель дохода", value=f"x{clan['income_multiplier']}", inline=True)
        
        member_list = []
        for i, member in enumerate(members[:10], 1):
            try:
                member_user = await bot.fetch_user(member['user_id'])
                member_list.append(f"{i}. {member_user.name}")
            except:
                member_list.append(f"{i}. Неизвестный")
        
        if member_list:
            embed.add_field(name="🎯 Участники", value="\n".join(member_list), inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(name="клантоп")
    async def clan_top(self, ctx):
        async with bot.db.acquire() as conn:
            top_clans = await conn.fetch(
                "SELECT name, balance, member_slots FROM clans ORDER BY balance DESC LIMIT 10"
            )
        
        if not top_clans:
            await ctx.send("😔 Кланов пока нет.")
            return
        
        leaderboard = []
        for i, clan in enumerate(top_clans, start=1):
            member_count = await self.get_clan_member_count(clan['name'])
            leaderboard.append(f"{i}. {clan['name']} — {clan['balance']}к | {member_count}/{clan['member_slots']} чел.")
        
        embed = discord.Embed(
            title="🏆 Топ кланов по казне",
            description="\n".join(leaderboard),
            color=0xffd700
        )
        await ctx.send(embed=embed)

    @commands.command(name="внести_клан")
    async def clan_deposit(self, ctx, amount: int):
        user = ctx.author
        clan_name = await get_user_clan(user.id)
        
        if not clan_name:
            await ctx.send("❌ Вы не состоите в клане!")
            return
        
        if amount <= 0:
            await ctx.send("❌ Сумма должна быть положительной!")
            return
        
        user_balance = await get_balance(user.id)
        if user_balance < amount:
            await ctx.send("❌ Недостаточно средств!")
            return
        
        await update_balance(user.id, -amount)
        async with bot.db.acquire() as conn:
            await conn.execute(
                "UPDATE clans SET balance = balance + $1 WHERE name = $2",
                amount, clan_name
            )
        
        await ctx.send(f"✅ {user.mention} внес {amount} кредитов в казну клана '{clan_name}'!")

    @commands.command(name="снять_клан")
    async def clan_withdraw(self, ctx, amount: int):
        user = ctx.author
        clan_name = await get_user_clan(user.id)
        
        if not clan_name:
            await ctx.send("❌ Вы не состоите в клане!")
            return
        
        async with bot.db.acquire() as conn:
            clan_owner = await conn.fetchval("SELECT owner_id FROM clans WHERE name = $1", clan_name)
            if clan_owner != user.id:
                await ctx.send("❌ Только владелец клана может снимать средства!")
                return
            
            clan_balance = await conn.fetchval("SELECT balance FROM clans WHERE name = $1", clan_name)
            if clan_balance < amount:
                await ctx.send("❌ В казне клана недостаточно средств!")
                return
            
            await conn.execute(
                "UPDATE clans SET balance = balance - $1 WHERE name = $2",
                amount, clan_name
            )
        
        await update_balance(user.id, amount)
        await ctx.send(f"✅ {user.mention} снял {amount} кредитов из казны клана!")

# ==================== ПРОФИЛЬ ====================
class Profile(commands.Cog):
    def init(self, bot):
        self.bot = bot

    @commands.command(name="профиль")
    async def profile(self, ctx, member: discord.Member = None):
        if not member:
            member = ctx.author
        
        balance = await get_balance(member.id)
        clan = await get_user_clan(member.id)
        description = await get_profile_description(member.id)
        user_data = await get_user_data(member.id)
        
        embed = discord.Embed(
            title=f"📊 Профиль {member.display_name}",
            color=member.color
        )
        
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(name="💰 Баланс", value=f"{balance} кредитов", inline=True)
        embed.add_field(name="👥 Клан", value=clan if clan else "Нет клана", inline=True)
        
        if user_data and user_data['business_license']:
            business_info = f"{user_data['business_license'].capitalize()} бизнес\n+{user_data['business_income']}/час"
            embed.add_field(name="💼 Бизнес", value=business_info, inline=True)
        
        boosters = []
        if user_data and user_data['farm_booster_until'] and user_data['farm_booster_until'] > datetime.now():
            time_left = user_data['farm_booster_until'] - datetime.now()
            hours_left = int(time_left.total_seconds() // 3600)
            boosters.append(f"🌾 Фарм ({hours_left}ч)")
        
        if user_data and user_data['roulette_booster_until'] and user_data['roulette_booster_until'] > datetime.now():
            time_left = user_data['roulette_booster_until'] - datetime.now()
            hours_left = int(time_left.total_seconds() // 3600)
            boosters.append(f"🎰 Рулетка ({hours_left}ч)")
        
        if boosters:
            embed.add_field(name="🚀 Бустеры", value="\n".join(boosters), inline=True)
        
        embed.add_field(name="📝 Описание", value=description, inline=False)
        
        join_date = member.joined_at.strftime("%d.%m.%Y") if member.joined_at else "Неизвестно"
        embed.add_field(name="📅 На сервере с", value=join_date, inline=True)
        embed.add_field(name="🆔 ID", value=member.id, inline=True)
        
        embed.set_footer(text=f"Запросил: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)

    @commands.command(name="описание_профиль")
    async def set_profile_description(self, ctx, *, description: str):
        if len(description) > 200:
            await ctx.send("❌ Описание не должно превышать 200 символов!")
            return
        
        await update_profile_description(ctx.author.id, description)
        await ctx.send("✅ Описание профиля обновлено!")

    @commands.command(name="сбросить_описание")
    async def reset_profile_description(self, ctx):
        await update_profile_description(ctx.author.id, "")
        await ctx.send("✅ Описание профиля сброшено!")

# ==================== РАЗВЛЕЧЕНИЯ ====================
class Fun(commands.Cog):
    def init(self, bot):
        self.bot = bot

    @commands.command(name="рандом")
    async def random_num(self, ctx, min_num: int = 1, max_num: int = 100):
        if min_num > max_num:
            min_num, max_num = max_num, min_num
        
        result = random.randint(min_num, max_num)
        await ctx.send(f"🎲 {ctx.author.mention}, случайное число: {result} (от {min_num} до {max_num})")

    @commands.command(name="орёл")
    async def coin_flip(self, ctx):
        result = random.choice(["Орёл 🦅", "Решка 🪙"])
        await ctx.send(f"🎯 {ctx.author.mention}, результат: {result}!")

    @commands.command(name="выбор")
    async def choose(self, ctx, *, options: str):
        options_list = [opt.strip() for opt in options.split(",") if opt.strip()]
        
        if len(options_list) < 2:
            await ctx.send("❌ Укажите хотя бы 2 варианта через запятую!")
            return
        
        chosen = random.choice(options_list)
        await ctx.send(f"🤔 {ctx.author.mention}, я выбираю: {chosen}!")

    @commands.command(name="шар")
    async def magic_ball(self, ctx, *, question: str):
        answers = [
            "Бесспорно! ✅", "Предрешено! ✅", "Никаких сомнений! ✅", "Определённо да! ✅",
            "Можешь быть уверен в этом! ✅", "Мне кажется — «да»! 🤔", "Вероятнее всего! 👍",
            "Хорошие перспективы! 👍", "Знаки говорят — «да»! 🔮", "Да! ✅",
            "Пока не ясно, попробуй снова! 🔄", "Спроси позже! ⏰", "Лучше не рассказывать! 🤫",
            "Сейчас нельзя предсказать! 🔮", "Сконцентрируйся и спроси опять! 🧘",
            "Даже не думай! ❌", "Мой ответ — «нет»! ❌", "По моим данным — «нет»! ❌",
            "Перспективы не очень хорошие! 👎", "Весьма сомнительно! 🤨"
        ]
        
        answer = random.choice(answers)
        embed = discord.Embed(
            title="🎱 Магический шар",
            color=0x7289da
        )
        embed.add_field(name="❓ Вопрос", value=question, inline=False)
        embed.add_field(name="📜 Ответ", value=answer, inline=False)
        embed.set_footer(text=f"Запросил: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)

@commands.command(name="слоты")
@commands.cooldown(1, 10, commands.BucketType.user)
async def slots(self, ctx, bet: int = 10):
    if bet <= 0:
        await ctx.send("❌ Ставка должна быть положительной!")
        return

    # ИСПРАВЛЕННЫЕ СТРОКИ:
    balance = await get_balance_from_db(ctx.author.id)
    if balance < bet:
        await ctx.send("❌ Недостаточно кредитов!")
        return

    symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    
    if result[0] == result[1] == result[2]:
        if result[0] == "💎":
            multiplier = 10
        elif result[0] == "7️⃣":
            multiplier = 5
        else:
            multiplier = 3
    elif result[0] == result[1] or result[1] == result[2]:
        multiplier = 1.5
    else:
        multiplier = 0
    
    win_amount = int(bet * multiplier)
    
    if win_amount > 0:
        # ИСПРАВЛЕННАЯ СТРОКА:
        await update_balance_in_db(ctx.author.id, win_amount)
    else:
        # ИСПРАВЛЕННАЯ СТРОКА:
        await update_balance_in_db(ctx.author.id, -bet)
    
    embed = discord.Embed(
        title="🎰 Игровые автоматы",
        color=0xffd700 if win_amount > 0 else 0xff0000
    )
    
    embed.add_field(
        name="Результат",
        value=f"| {result[0]} | {result[1]} | {result[2]} |",
        inline=False
    )
    
    if win_amount > 0:
        if multiplier == 10:
            embed.add_field(name="🎉 ДЖЕКПОТ!", value=f"Вы выиграли {win_amount} кредитов!", inline=False)
        else:
            embed.add_field(name="✅ Выигрыш", value=f"+{win_amount} кредитов (x{multiplier})", inline=False)
    else:
        embed.add_field(name="❌ Проигрыш", value=f"-{bet} кредитов", inline=False)
    
    # ИСПРАВЛЕННАЯ СТРОКА:
    embed.add_field(name="💰 Баланс", value=f"{await get_balance_from_db(ctx.author.id)} кредитов", inline=True)
    embed.set_footer(text=f"Игрок: {ctx.author.display_name}")
    
    await ctx.send(embed=embed)
    
    @commands.command(name="викторина")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def quiz(self, ctx):
        questions = [
            {
                "question": "Сколько планет в Солнечной системе?",
                "options": ["8", "9", "10", "7"],
                "answer": 0
            },
            {
                "question": "Какая самая длинная река в мире?",
                "options": ["Амазонка", "Нил", "Янцзы", "Миссисипи"],
                "answer": 0
            },
            {
                "question": "В каком году началась Вторая мировая война?",
                "options": ["1939", "1941", "1937", "1945"],
                "answer": 0
            }
        ]
        
        q = random.choice(questions)
        
        embed = discord.Embed(
            title="📚 Викторина",
            description=q["question"],
            color=0x0099ff
        )
        
        options_text = ""
        for i, option in enumerate(q["options"]):
            options_text += f"{i+1}. {option}\n"
        
        embed.add_field(name="Варианты:", value=options_text, inline=False)
        embed.set_footer(text="У вас 15 секунд чтобы ответить цифрой!")
        
        message = await ctx.send(embed=embed)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
        
        try:
            response = await self.bot.wait_for('message', timeout=15.0, check=check)
            user_answer = int(response.content) - 1
            
            if user_answer == q["answer"]:
                reward = random.randint(50, 150)
                await update_balance(ctx.author.id, reward)
                await ctx.send(f"✅ Правильно! {ctx.author.mention} получает {reward} кредитов!")
            else:
                correct_answer = q["options"][q["answer"]]
                await ctx.send(f"❌ Неправильно! Правильный ответ: {correct_answer}")
                
        except asyncio.TimeoutError:
            await ctx.send("⏰ Время вышло!")

    @commands.command(name="кто")
    async def who_is(self, ctx, *, question: str):
        members = [member for member in ctx.guild.members if not member.bot]
        
        if not members:
            await ctx.send("❌ На сервере нет участников!")
            return
        
        chosen = random.choice(members)
        
        embed = discord.Embed(
            title="🎭 Случайный выбор",
            color=chosen.color
        )
        embed.add_field(name="❓ Вопрос", value=question, inline=False)
        embed.add_field(name="👤 Выбран", value=chosen.mention, inline=False)
        embed.set_thumbnail(url=chosen.avatar.url if chosen.avatar else chosen.default_avatar.url)
        
        await ctx.send(embed=embed)

# ==================== МОДЕРАЦИЯ ====================
class Mod(commands.Cog):
    def init(self, bot):
        self.bot = bot

    def is_admin(self, member):
        return any(role.name.lower() in [r.lower() for r in ADMIN_ROLES] for role in member.roles)

    async def create_mute_role(self, guild):
        mute_role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
        if not mute_role:
            mute_role = await guild.create_role(
                name=MUTE_ROLE_NAME,
                reason="Создание роли для мьюта"
            )
            
            for channel in guild.channels:
                try:
                    if isinstance(channel, discord.TextChannel):
                        await channel.set_permissions(mute_role, 
                            send_messages=False,
                            add_reactions=False
                        )
                    elif isinstance(channel, discord.VoiceChannel):
                        await channel.set_permissions(mute_role,
                            speak=False,
                            connect=False
                        )
                except discord.Forbidden:
                    continue
        
        return mute_role

    @commands.command(name="мут")
    async def mute(self, ctx, member: discord.Member, time: int = 60, *, reason: str = "Не указана"):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        if member == ctx.author:
            await ctx.send("❌ Нельзя замутить самого себя!")
            return
        
        if self.is_admin(member):
            await ctx.send("❌ Нельзя замутить администратора!")
            return
        
        mute_role = await self.create_mute_role(ctx.guild)
        await member.add_roles(mute_role, reason=f"Мут от {ctx.author.name}: {reason}")
        
        embed = discord.Embed(
            title="🔇 Пользователь замьючен",
            color=0xff0000,
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Пользователь", value=member.mention, inline=True)
        embed.add_field(name="⏰ Время", value=f"{time} минут", inline=True)
        embed.add_field(name="🛡 Модератор", value=ctx.author.mention, inline=True)
        embed.add_field(name="📝 Причина", value=reason, inline=False)
        
        await ctx.send(embed=embed)
        
        if time > 0:
            await asyncio.sleep(time * 60)
            try:
                if mute_role in member.roles:
                    await member.remove_roles(mute_role)
                    await ctx.send(f"✅ {member.mention} автоматически размьючен!")
            except:
                pass

    @commands.command(name="размут")
    async def unmute(self, ctx, member: discord.Member):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role)
            
            embed = discord.Embed(
                title="🔊 Пользователь размьючен",
                color=0x00ff00,
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Пользователь", value=member.mention, inline=True)
            embed.add_field(name="🛡 Модератор", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Пользователь не замьючен!")

    @commands.command(name="очистить")
    async def clear(self, ctx, amount: int = 10):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        if amount > 100:
            await ctx.send("❌ Нельзя удалить больше 100 сообщений за раз!")
            return
        
        deleted = await ctx.channel.purge(limit=amount + 1)
        
        embed = discord.Embed(
            title="🧹 Очистка сообщений",
            description=f"Удалено {len(deleted) - 1} сообщений",
            color=0xffff00
        )
        embed.add_field(name="🛡 Модератор", value=ctx.author.mention, inline=True)
        
        message = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        await message.delete()

    @commands.command(name="кик")
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Не указана"):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        if member == ctx.author:
            await ctx.send("❌ Нельзя кикнуть самого себя!")
            return
        
        if self.is_admin(member):
            await ctx.send("❌ Нельзя кикнуть администратора!")
            return
        
        try:
            await member.kick(reason=f"Кик от {ctx.author.name}: {reason}")
            
            embed = discord.Embed(
                title="👢 Пользователь кикнут",
                color=0xffa500,
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Пользователь", value=member.name, inline=True)
            embed.add_field(name="🛡 Модератор", value=ctx.author.mention, inline=True)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ У бота нет прав для кика!")

    @commands.command(name="бан")
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Не указана"):
        if not self.is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        if member == ctx.author:
            await ctx.send("❌ Нельзя забанить самого себя!")
            return
        
        if self.is_admin(member):
            await ctx.send("❌ Нельзя забанить администратора!")
            return
        
        try:
            await member.ban(reason=f"Бан от {ctx.author.name}: {reason}")
            
            embed = discord.Embed(
                title="🔨 Пользователь забанен",
                color=0xff0000,
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Пользователь", value=member.name, inline=True)
            embed.add_field(name="🛡 Модератор", value=ctx.author.mention, inline=True)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ У бота нет прав для бана!")

# ==================== СОБЫТИЯ ====================
class Events(commands.Cog):
    def init(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("=" * 50)
        print(f"🤖 Бот: {self.bot.user.name}")
        print(f"🆔 ID: {self.bot.user.id}")
        print(f"📡 Серверов: {len(self.bot.guilds)}")
        print("=" * 50)

    @commands.Cog.listener()
    async def on_disconnect(self):
        print("🔌 Бот отключен от Discord")

    @commands.Cog.listener()
    async def on_resumed(self):
        print("🔁 Соединение с Discord восстановлено")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            seconds = int(error.retry_after)
            if seconds > 3600:
                time_str = f"{seconds // 3600}ч {(seconds % 3600) // 60}м"
            elif seconds > 60:
                time_str = f"{seconds // 60}м {seconds % 60}с"
            else:
                time_str = f"{seconds}с"
            
            await ctx.send(f"⏳ Подождите {time_str} перед использованием команды.")
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ У бота недостаточно прав для выполнения этой команды!")
        else:
            print(f"⚠️ Ошибка в команде {ctx.command}: {error}")

# ==================== ЗАПУСК БОТА ====================
async def setup_bot():
    try:
        bot.db = await create_db_pool()
        await bot.add_cog(Economy(bot))
        await bot.add_cog(Clans(bot))
        await bot.add_cog(Profile(bot))
        await bot.add_cog(Fun(bot))
        await bot.add_cog(Mod(bot))
        await bot.add_cog(Events(bot))
        print("✅ Все коги загружены")
        return True
    except Exception as e:
        print(f"❌ Ошибка при настройке бота: {e}")
        return False

async def close_bot():
    """Корректное закрытие бота"""
    print("🔄 Завершаем работу бота...")
    try:
        if hasattr(bot, 'db') and bot.db:
            await bot.db.close()
            print("✅ Пул соединений с БД закрыт")
        await bot.close()
        print("✅ Соединение с Discord закрыто")
    except Exception as e:
        print(f"⚠️ Ошибка при закрытии: {e}")

def run_discord_bot():
    """Запуск Discord бота в отдельном потоке"""
    async def start_bot():
        try:
            setup_ok = await setup_bot()
            if not setup_ok:
                print("❌ Не удалось настроить бота")
                return
            
            print("🚀 Запускаем Discord бота...")
            await bot.start(TOKEN)
        except KeyboardInterrupt:
            print("⏹ Остановка по запросу пользователя...")
        except Exception as e:
            print(f"❌ Ошибка при запуске бота: {e}")
        finally:
            await close_bot()
    
    # Запускаем асинхронную функцию в отдельном потоке
    asyncio.run(start_bot())

if name == 'main':
    print("🔧 Инициализация приложения...")
    
    # Запускаем Flask в главном потоке
    keep_alive()
    
    # Даем Flask время запуститься
    import time
    time.sleep(2)
    
    # Запускаем Discord бота
    try:
        run_discord_bot()
    except Exception as e:
        print(f"❌ Фатальная ошибка: {e}")
