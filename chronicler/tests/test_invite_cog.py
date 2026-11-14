import pytest

from cogs.invite import InviteCog, is_invite_request


# ---------------------------------------------------------------------------
# is_invite_request
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text', ['join', 'JOIN', ' Join ', '!join', 'invite', 'add'])
def test_recognises_invite_requests(text):
    assert is_invite_request(text) is True


@pytest.mark.parametrize('text', ['', 'joining', 'join the party', 'roll', '!roll 2d6', 'jo in'])
def test_ignores_everything_else(text):
    assert is_invite_request(text) is False


# ---------------------------------------------------------------------------
# on_message listener
# ---------------------------------------------------------------------------

def _embed_of(message):
    return message.channel.send.call_args.kwargs['embed']


async def test_dm_join_replies_with_the_url_when_configured(mock_bot, dm_message, monkeypatch):
    monkeypatch.setattr('utils.message.INVITE_URL', 'https://example.invalid/oauth')
    cog = InviteCog(mock_bot)
    await cog.on_message(dm_message)
    dm_message.channel.send.assert_awaited_once()
    description = _embed_of(dm_message).description
    assert 'https://example.invalid/oauth' in description
    assert 'To add me to your server use this url:' in description


async def test_dm_join_explains_when_no_url_is_configured(mock_bot, dm_message, monkeypatch):
    """Chronicler ships with no application yet — say so, do not send a blank link."""
    monkeypatch.setattr('utils.message.INVITE_URL', '')
    cog = InviteCog(mock_bot)
    await cog.on_message(dm_message)
    dm_message.channel.send.assert_awaited_once()
    assert 'no invite link yet' in _embed_of(dm_message).title


async def test_dm_is_case_insensitive(mock_bot, dm_message):
    dm_message.content = 'JOIN'
    cog = InviteCog(mock_bot)
    await cog.on_message(dm_message)
    dm_message.channel.send.assert_awaited_once()


async def test_guild_message_is_ignored(mock_bot, dm_message, guild_message):
    cog = InviteCog(mock_bot)
    await cog.on_message(guild_message)
    guild_message.channel.send.assert_not_awaited()


async def test_bot_own_message_is_ignored(mock_bot, dm_message):
    dm_message.author.bot = True
    cog = InviteCog(mock_bot)
    await cog.on_message(dm_message)
    dm_message.channel.send.assert_not_awaited()


async def test_unrelated_dm_is_ignored(mock_bot, dm_message):
    dm_message.content = 'what dice should I bring'
    cog = InviteCog(mock_bot)
    await cog.on_message(dm_message)
    dm_message.channel.send.assert_not_awaited()


async def test_roll_in_dm_is_not_swallowed(mock_bot, dm_message):
    """The listener must leave !roll alone so commands still work in DMs."""
    dm_message.content = '!roll 2d6'
    cog = InviteCog(mock_bot)
    await cog.on_message(dm_message)
    dm_message.channel.send.assert_not_awaited()
