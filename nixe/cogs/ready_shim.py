import logging
from discord.ext import commands

log = logging.getLogger(__name__)

class ReadyShim(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._logged = False

    @commands.Cog.listener()
    async def on_ready(self):
        # Avoid spam on reconnects; log only once per process.
        if self._logged:
            return
        self._logged = True

        user = getattr(self.bot, "user", None)
        if user is None:
            log.info("[ready] Bot ready (bot.user is None)")
            return

        # str(user) yields "name#1234" on legacy accounts, or "name" on new usernames.
        log.info("[ready] Bot ready as %s (%s)", str(user), getattr(user, "id", "unknown"))

async def setup(bot: commands.Bot):
    await bot.add_cog(ReadyShim(bot))
