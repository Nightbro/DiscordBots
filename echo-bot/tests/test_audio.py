import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from utils.audio import AudioFileManager, AUDIO_EXTS


# ---------------------------------------------------------------------------
# is_valid_audio
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('filename', [
    'song.mp3', 'effect.ogg', 'voice.wav', 'lossless.flac',
    'mobile.m4a', 'codec.opus', 'compressed.aac',
    'UPPER.MP3', 'Mixed.Ogg',
])
def test_valid_audio_extensions(filename):
    assert AudioFileManager.is_valid_audio(filename) is True


@pytest.mark.parametrize('filename', [
    'video.mp4', 'image.png', 'document.pdf', 'archive.zip',
    'noext', '.mp3hidden', 'file.txt',
])
def test_invalid_audio_extensions(filename):
    assert AudioFileManager.is_valid_audio(filename) is False


def test_audio_exts_is_frozenset():
    assert isinstance(AUDIO_EXTS, frozenset)


def test_audio_exts_all_lowercase():
    assert all(ext == ext.lower() for ext in AUDIO_EXTS)


def test_audio_exts_all_start_with_dot():
    assert all(ext.startswith('.') for ext in AUDIO_EXTS)


# ---------------------------------------------------------------------------
# receive_attachment
# ---------------------------------------------------------------------------

def _make_attachment(filename: str) -> MagicMock:
    att = MagicMock(spec=discord.Attachment)
    att.filename = filename
    att.save = AsyncMock()
    return att


async def test_receive_attachment_success(ctx, tmp_path):
    ctx.message = MagicMock()
    ctx.message.attachments = [_make_attachment('intro.mp3')]

    path = await AudioFileManager.receive_attachment(ctx, tmp_path, 'test_intro.mp3')

    assert path == tmp_path / 'test_intro.mp3'
    ctx.send.assert_not_awaited()


async def test_receive_attachment_no_attachment_sends_error(ctx, tmp_path):
    ctx.message = MagicMock()
    ctx.message.attachments = []

    path = await AudioFileManager.receive_attachment(ctx, tmp_path, 'test.mp3')

    assert path is None
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_receive_attachment_invalid_ext_sends_error(ctx, tmp_path):
    ctx.message = MagicMock()
    ctx.message.attachments = [_make_attachment('video.mp4')]

    path = await AudioFileManager.receive_attachment(ctx, tmp_path, 'test.mp3')

    assert path is None
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_receive_attachment_saves_to_dest(ctx, tmp_path):
    attachment = _make_attachment('sound.ogg')
    ctx.message = MagicMock()
    ctx.message.attachments = [attachment]

    await AudioFileManager.receive_attachment(ctx, tmp_path, 'out.ogg')

    attachment.save.assert_awaited_once_with(tmp_path / 'out.ogg')


async def test_receive_attachment_uses_first_attachment(ctx, tmp_path):
    first = _make_attachment('first.mp3')
    second = _make_attachment('second.mp3')
    ctx.message = MagicMock()
    ctx.message.attachments = [first, second]

    await AudioFileManager.receive_attachment(ctx, tmp_path, 'out.mp3')

    first.save.assert_awaited_once()
    second.save.assert_not_awaited()
