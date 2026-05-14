from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import discord

from utils.config import TTS_DEFAULT_VOICE


@dataclass
class Track:
    title: str
    url: str
    file_path: Path | None = None
    duration: int | None = None
    requester: discord.Member | None = None
    source_id: str | None = None  # yt-dlp video ID used for cache lookup
    cleanup_path: Path | None = None  # deleted after playback (used by TTS temp files)


@dataclass
class GuildState:
    queue: deque[Track] = field(default_factory=deque)
    voice_client: discord.VoiceClient | None = None
    current_track: Track | None = None
    interrupted_track: Track | None = None
    tts_queue: deque[str] = field(default_factory=deque)
    tts_voice: str = field(default_factory=lambda: TTS_DEFAULT_VOICE)
    soundboard_panel_message: discord.Message | None = None
