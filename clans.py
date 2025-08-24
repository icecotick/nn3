import discord
from discord.ext import commands
from utils.database import get_balance, update_balance, get_user_clan
from config import CLAN_CREATION_PRICE

class Clans(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="создатьклан")
    async def create_clan(self, ctx, clan_name: str):
        user = ctx.author
        balance = await get_balance(user.id, self.bot.db)
        
        if balance < CLAN_CREATION_PRICE:
            await ctx.send(f"❌ Нужно {CLAN_CREATION_PRICE} кредитов для создания клана!")
            return
        
        current_clan = await get_user_clan(user.id, self.bot.db)
        if current_clan:
            await ctx.send("❌ Вы уже состоите в клане!")
            return
        
        async with self.bot.db.acquire() as conn:
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
        
        await update_balance(user.id, -CLAN_CREATION_PRICE, self.bot.db)
        await ctx.send(f"✅ Клан '{clan_name}' создан! Вы стали лидером.")

    @commands.command(name="войтивклан")
    async def join_clan(self, ctx, clan_name: str):
        user = ctx.author
        
        current_clan = await get_user_clan(user.id, self.bot.db)
        if current_clan:
            await ctx.send("❌ Вы уже состоите в клане!")
            return
        
        async with self.bot.db.acquire() as conn:
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
        async with self.bot.db.acquire() as conn:
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

async def setup(bot):
    await bot.add_cog(Clans(bot))
