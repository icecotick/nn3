import discord
from discord.ext import commands
from config import ADMIN_ROLES, MUTE_ROLE_NAME

def is_admin(member):
    return any(role.name.lower() in [r.lower() for r in ADMIN_ROLES] for role in member.roles)

class Mod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="мут")
    async def mute(self, ctx, member: discord.Member, time: int, *, reason: str = "Не указана"):
        if not is_admin(ctx.author):
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
        if not is_admin(ctx.author):
            await ctx.send("❌ Эта команда доступна только для администраторов!")
            return
        
        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role)
            await ctx.send(f"✅ {member.mention} размьючен!")
        else:
            await ctx.send("❌ Пользователь не замьючен!")

async def setup(bot):
    await bot.add_cog(Mod(bot))
