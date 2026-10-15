from unittest import IsolatedAsyncioTestCase

from app.bots.discord.bot import BudakDiscordBot, setup_slash_commands


class BotCommandTests(IsolatedAsyncioTestCase):
    async def test_discord_registers_on_and_off_as_prefix_and_slash_commands(self):
        bot = BudakDiscordBot()
        try:
            setup_slash_commands(bot)

            self.assertIsNotNone(bot.get_command("on"))
            self.assertIsNotNone(bot.get_command("off"))
            self.assertIsNotNone(bot.tree.get_command("on"))
            self.assertIsNotNone(bot.tree.get_command("off"))
        finally:
            await bot.close()


if __name__ == "__main__":
    import unittest

    unittest.main()
