"""Command and listener tests for ReactionsCog (cogs/reactions.py)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import discord

from cogs.reactions import ReactionsCog


@pytest.fixture
def cog(mock_bot):
    return ReactionsCog(mock_bot)


def _mock_message(message_id=111, reactions=None):
    msg = MagicMock(spec=discord.Message)
    msg.id = message_id
    msg.reactions = reactions or []
    msg.add_reaction = AsyncMock()
    msg.remove_reaction = AsyncMock()
    return msg


# ---------------------------------------------------------------------------
# !react add
# ---------------------------------------------------------------------------

class TestReactAdd:
    async def test_adds_reaction(self, cog, ctx):
        msg = _mock_message()
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        await cog.react_add.callback(cog, ctx, 111, "👍")
        msg.add_reaction.assert_called_once_with("👍")
        assert any("Added" in str(c) for c in ctx.send.call_args_list)

    async def test_message_not_found(self, cog, ctx):
        ctx.channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "nope"))
        await cog.react_add.callback(cog, ctx, 999, "👍")
        assert any("not found" in str(c) for c in ctx.send.call_args_list)

    async def test_http_error(self, cog, ctx):
        msg = _mock_message()
        msg.add_reaction = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "bad emoji"))
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        await cog.react_add.callback(cog, ctx, 111, "notanemoji")
        assert any("Could not add" in str(c) for c in ctx.send.call_args_list)


# ---------------------------------------------------------------------------
# !react count
# ---------------------------------------------------------------------------

class TestReactCount:
    async def test_counts_all_reactions(self, cog, ctx):
        r1 = MagicMock(); r1.emoji = "👍"; r1.count = 3
        r2 = MagicMock(); r2.emoji = "❤️"; r2.count = 1
        msg = _mock_message(reactions=[r1, r2])
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        await cog.react_count.callback(cog, ctx, 111)
        text = ctx.send.call_args[0][0]
        assert "👍" in text and "3" in text
        assert "❤️" in text and "1" in text

    async def test_counts_specific_emoji(self, cog, ctx):
        r1 = MagicMock(); r1.emoji = "👍"; r1.count = 5
        msg = _mock_message(reactions=[r1])
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        with patch("cogs.reactions.discord.utils.get", return_value=r1):
            await cog.react_count.callback(cog, ctx, 111, "👍")
        text = ctx.send.call_args[0][0]
        assert "5" in text

    async def test_no_reactions(self, cog, ctx):
        msg = _mock_message(reactions=[])
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        await cog.react_count.callback(cog, ctx, 111)
        ctx.send.assert_called_with("No reactions on that message.")

    async def test_emoji_not_found(self, cog, ctx):
        msg = _mock_message(reactions=[])
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        with patch("cogs.reactions.discord.utils.get", return_value=None):
            await cog.react_count.callback(cog, ctx, 111, "👍")
        assert any("No" in str(c) and "reactions" in str(c) for c in ctx.send.call_args_list)

    async def test_message_not_found(self, cog, ctx):
        ctx.channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "nope"))
        await cog.react_count.callback(cog, ctx, 999)
        assert any("not found" in str(c) for c in ctx.send.call_args_list)


# ---------------------------------------------------------------------------
# !react remove
# ---------------------------------------------------------------------------

class TestReactRemove:
    async def test_removes_bots_own_reaction_by_default(self, cog, ctx):
        msg = _mock_message()
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        ctx.me = MagicMock()
        await cog.react_remove.callback(cog, ctx, 111, "👍")
        msg.remove_reaction.assert_called_once_with("👍", ctx.me)
        assert any("Removed" in str(c) for c in ctx.send.call_args_list)

    async def test_removes_specified_member_reaction(self, cog, ctx):
        msg = _mock_message()
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        member = MagicMock(spec=discord.Member)
        member.display_name = "Alice"
        await cog.react_remove.callback(cog, ctx, 111, "👍", member)
        msg.remove_reaction.assert_called_once_with("👍", member)
        assert any("Alice" in str(c) for c in ctx.send.call_args_list)

    async def test_forbidden_sends_permission_error(self, cog, ctx):
        msg = _mock_message()
        msg.remove_reaction = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perm"))
        ctx.channel.fetch_message = AsyncMock(return_value=msg)
        ctx.me = MagicMock()
        await cog.react_remove.callback(cog, ctx, 111, "👍")
        assert any("permission" in str(c) for c in ctx.send.call_args_list)

    async def test_message_not_found(self, cog, ctx):
        ctx.channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "nope"))
        ctx.me = MagicMock()
        await cog.react_remove.callback(cog, ctx, 999, "👍")
        assert any("not found" in str(c) for c in ctx.send.call_args_list)


# ---------------------------------------------------------------------------
# !react watch / unwatch / watches
# ---------------------------------------------------------------------------

class TestReactWatch:
    async def test_adds_watch_without_response(self, cog, ctx):
        with patch("cogs.reactions.add_watch") as mock_add:
            await cog.react_watch.callback(cog, ctx, 111, "👍")
        mock_add.assert_called_once_with(ctx.guild.id, 111, "👍", ctx.channel.id, None)
        assert any("Watching" in str(c) for c in ctx.send.call_args_list)

    async def test_adds_watch_with_custom_response(self, cog, ctx):
        with patch("cogs.reactions.add_watch") as mock_add:
            await cog.react_watch.callback(cog, ctx, 111, "👍", response="Nice {user}!")
        mock_add.assert_called_once_with(ctx.guild.id, 111, "👍", ctx.channel.id, "Nice {user}!")
        assert any("Nice {user}!" in str(c) for c in ctx.send.call_args_list)


class TestReactUnwatch:
    async def test_removes_existing_watch(self, cog, ctx):
        with patch("cogs.reactions.remove_watch", return_value=True):
            await cog.react_unwatch.callback(cog, ctx, 111, "👍")
        assert any("No longer watching" in str(c) for c in ctx.send.call_args_list)

    async def test_watch_not_found(self, cog, ctx):
        with patch("cogs.reactions.remove_watch", return_value=False):
            await cog.react_unwatch.callback(cog, ctx, 111, "👍")
        assert any("No watch found" in str(c) for c in ctx.send.call_args_list)


class TestReactWatches:
    async def test_no_watches(self, cog, ctx):
        with patch("cogs.reactions.get_watches", return_value={}):
            await cog.react_watches.callback(cog, ctx)
        ctx.send.assert_called_with("No reaction watches configured.")

    async def test_lists_watches(self, cog, ctx):
        watches = {
            "111:👍": {"channel_id": 1, "response": "hello {user}"},
            "222:❤️": {"channel_id": 1},
        }
        with patch("cogs.reactions.get_watches", return_value=watches):
            await cog.react_watches.callback(cog, ctx)
        text = ctx.send.call_args[0][0]
        assert "👍" in text and "111" in text
        assert "❤️" in text and "222" in text
        assert "hello {user}" in text


# ---------------------------------------------------------------------------
# on_reaction_add listener
# ---------------------------------------------------------------------------

class TestOnReactionAdd:
    def _make_reaction(self, message_id=111, emoji="👍", guild_id=999):
        guild = MagicMock(spec=discord.Guild)
        guild.id = guild_id
        msg = MagicMock(spec=discord.Message)
        msg.id = message_id
        msg.guild = guild
        msg.channel = MagicMock()
        reaction = MagicMock(spec=discord.Reaction)
        reaction.message = msg
        reaction.emoji = emoji
        return reaction

    def _make_user(self, is_bot=False):
        user = MagicMock(spec=discord.User)
        user.bot = is_bot
        user.mention = "<@123>"
        return user

    async def test_ignores_bot_reactions(self, cog):
        reaction = self._make_reaction()
        user = self._make_user(is_bot=True)
        with patch("cogs.reactions.get_watches", return_value={}) as mock_w:
            await cog.on_reaction_add(reaction, user)
        mock_w.assert_not_called()

    async def test_ignores_dm_reactions(self, cog):
        reaction = self._make_reaction()
        reaction.message.guild = None
        user = self._make_user()
        with patch("cogs.reactions.get_watches", return_value={}) as mock_w:
            await cog.on_reaction_add(reaction, user)
        mock_w.assert_not_called()

    async def test_fires_watch_with_default_response(self, cog):
        reaction = self._make_reaction(message_id=111, emoji="👍", guild_id=999)
        user = self._make_user()
        channel = MagicMock()
        channel.send = AsyncMock()
        reaction.message.guild.get_channel = MagicMock(return_value=channel)

        watches = {"111:👍": {"channel_id": 42}}
        with patch("cogs.reactions.get_watches", return_value=watches):
            await cog.on_reaction_add(reaction, user)

        channel.send.assert_called_once()
        text = channel.send.call_args[0][0]
        assert user.mention in text
        assert "👍" in text

    async def test_fires_watch_with_custom_response(self, cog):
        reaction = self._make_reaction(message_id=111, emoji="👍", guild_id=999)
        user = self._make_user()
        channel = MagicMock()
        channel.send = AsyncMock()
        reaction.message.guild.get_channel = MagicMock(return_value=channel)

        watches = {"111:👍": {"channel_id": 42, "response": "Thumbs up from {user}!"}}
        with patch("cogs.reactions.get_watches", return_value=watches):
            await cog.on_reaction_add(reaction, user)

        text = channel.send.call_args[0][0]
        assert "Thumbs up from" in text
        assert user.mention in text

    async def test_no_watch_match_does_nothing(self, cog):
        reaction = self._make_reaction(message_id=111, emoji="👍")
        user = self._make_user()
        channel = MagicMock()
        channel.send = AsyncMock()
        reaction.message.guild.get_channel = MagicMock(return_value=channel)

        with patch("cogs.reactions.get_watches", return_value={"999:❤️": {"channel_id": 1}}):
            await cog.on_reaction_add(reaction, user)

        channel.send.assert_not_called()

    async def test_falls_back_to_message_channel_when_channel_not_found(self, cog):
        reaction = self._make_reaction(message_id=111, emoji="👍", guild_id=999)
        user = self._make_user()
        reaction.message.channel.send = AsyncMock()
        reaction.message.guild.get_channel = MagicMock(return_value=None)

        watches = {"111:👍": {"channel_id": 42}}
        with patch("cogs.reactions.get_watches", return_value=watches):
            await cog.on_reaction_add(reaction, user)

        reaction.message.channel.send.assert_called_once()
