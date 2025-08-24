import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ROLE_NAME = "Патриот"
ADMIN_ROLES = ["создатель", "главный модер"]
CUSTOM_ROLE_PRICE = 2000
UPGRADE_ROLE_PRICE = 1000

CRIT_CHANCE = 10
SUCCESS_CHANCE = 40

MUTE_ROLE_NAME = "Muted"
CLAN_CREATION_PRICE = 5000
