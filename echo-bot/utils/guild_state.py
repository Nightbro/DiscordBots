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
    seek_to: float = 0.0            # seconds offset passed as -ss to FFmpeg on (re-)start


@dataclass
class GuildState:
    queue: deque[Track] = field(default_factory=deque)
    voice_client: discord.VoiceClient | None = None
    current_track: Track | None = None
    last_track: Track | None = None          # most recent track that started playing
    interrupted_track: Track | None = None
    tts_queue: deque[str] = field(default_factory=deque)
    tts_voice: str = field(default_factory=lambda: TTS_DEFAULT_VOICE)
    soundboard_panel_message: discord.Message | None = None
    # Playback-position tracking (used to resume from exact position after interrupt)
    track_play_start: float | None = None  # time.monotonic() when this play session began
    track_position_secs: float = 0.0       # absolute track position (s) at track_play_start
    # Last text channel that received a non-bot message (used for maintenance announcements)
    last_text_channel_id: int | None = None
