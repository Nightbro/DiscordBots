from pathlib import Path

import discord
from discord.ext import commands

from utils.message import MessageWriter

AUDIO_EXTS: frozenset[str] = frozenset({
    '.mp3', '.ogg', '.wav', '.flac', '.m4a', '.opus', '.aac',
})


class AudioFileManager:
    @staticmethod
    def is_valid_audio(filename: str) -> bool:
        return Path(filename).suffix.lower() in AUDIO_EXTS

    @staticmethod
    async def receive_attachment(
        ctx: commands.Context,
        dest_dir: Path,
        filename: str,
    ) -> Path | None:
        """Validate and save the first attachment from ctx to dest_dir/filename.

        Sends an error embed and returns None if validation fails.
        """
        if not ctx.message.attachments:
            await ctx.send(embed=MessageWriter.error(
                'No attachment',
                'Please attach an audio file to your message.',
            ))
            return None

        attachment: discord.Attachment = ctx.message.attachments[0]

        if not AudioFileManager.is_valid_audio(attachment.filename):
            supported = ', '.join(sorted(AUDIO_EXTS))
            await ctx.send(embed=MessageWriter.error(
                'Unsupported file type',
                f'Supported formats: {supported}',
            ))
            return None

        dest = dest_dir / filename
        await attachment.save(dest)
        return dest
