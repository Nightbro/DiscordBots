"""Rendering a Transcript into documents.

Each format renders from the same model, independently — nothing here parses
another format's output. That is why there is no HTML-to-PDF step: converting
would mean carrying an HTML engine with native dependencies, and the PDF and
Word output only need the messages themselves.

No Discord types. Blocking work only, so callers run it off the event loop.
"""

from __future__ import annotations

import html

from utils.archive import Transcript
from utils.config import ARCHIVE_IMAGE_WIDTH

STYLE_CSS = """\
:root {
  --bg: #1e1f22;
  --panel: #2b2d31;
  --text: #dbdee1;
  --muted: #949ba4;
  --accent: #c0a080;
  --link: #94b3e0;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f7f7f8;
    --panel: #ffffff;
    --text: #2e3035;
    --muted: #6b7076;
    --accent: #7b241c;
    --link: #1a5fb4;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 24px 16px 64px;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.55 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 860px; margin: 0 auto; }
header {
  border-bottom: 1px solid var(--muted);
  padding-bottom: 16px;
  margin-bottom: 24px;
}
h1 { margin: 0 0 4px; font-size: 22px; color: var(--accent); }
.meta { color: var(--muted); font-size: 13px; }
.msg {
  background: var(--panel);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
}
.msg-head { display: flex; gap: 8px; align-items: baseline; margin-bottom: 4px; }
.author { font-weight: 600; }
.time { color: var(--muted); font-size: 12px; }
.edited { color: var(--muted); font-size: 12px; font-style: italic; }
.body { white-space: pre-wrap; overflow-wrap: anywhere; }
.att { margin-top: 8px; }
.att img {
  max-width: 100%;
  border-radius: 6px;
  display: block;
  margin: 6px 0;
}
.files { margin-top: 8px; font-size: 13px; }
.files a { color: var(--link); }
.empty { color: var(--muted); font-style: italic; }
footer { margin-top: 32px; color: var(--muted); font-size: 12px; }
"""


def _message_html(message, image_width: int) -> str:
    parts = ['<div class="msg">']
    head = [
        f'<span class="author">{html.escape(message.author_name)}</span>',
        f'<span class="time">{html.escape(message.timestamp)}</span>',
    ]
    if message.edited:
        head.append('<span class="edited">(edited)</span>')
    parts.append(f'<div class="msg-head">{"".join(head)}</div>')

    if message.content:
        parts.append(f'<div class="body">{html.escape(message.content)}</div>')
    elif not message.attachments:
        parts.append('<div class="body empty">[no text]</div>')

    if message.images:
        parts.append('<div class="att">')
        for att in message.images:
            # Images are stored at full size; width here is presentation only.
            parts.append(
                f'<img src="{html.escape(att.path_in_bundle)}" '
                f'alt="{html.escape(att.filename)}" width="{image_width}">'
            )
        parts.append('</div>')

    if message.files:
        parts.append('<div class="files">')
        for att in message.files:
            size_kb = max(1, att.size // 1024)
            parts.append(
                f'<div>📎 <a href="{html.escape(att.path_in_bundle)}">'
                f'{html.escape(att.filename)}</a> — {size_kb} KB</div>'
            )
        parts.append('</div>')

    parts.append('</div>')
    return ''.join(parts)


def render_html(transcript: Transcript, *, image_width: int = 0) -> str:
    """The full index.html for a bundle. Images are referenced relatively."""
    width = image_width or ARCHIVE_IMAGE_WIDTH
    title = f'#{transcript.channel_name} — {transcript.guild_name}'
    generated = transcript.generated_at.strftime('%Y-%m-%d %H:%M UTC')

    body = [
        '<!doctype html>',
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{html.escape(title)}</title>',
        '<link rel="stylesheet" href="style.css">',
        '</head><body><div class="wrap">',
        '<header>',
        f'<h1>#{html.escape(transcript.channel_name)}</h1>',
        f'<div class="meta">{html.escape(transcript.guild_name)} · '
        f'{len(transcript.messages)} messages · '
        f'{transcript.attachment_count} attachments · '
        f'exported {html.escape(generated)}</div>',
        '</header>',
    ]

    if not transcript.messages:
        body.append('<p class="empty">No messages in this range.</p>')
    else:
        body.extend(_message_html(m, width) for m in transcript.messages)

    body.append(
        '<footer>Images and files are stored alongside this page in '
        '<code>images/</code> and <code>files/</code>. '
        'Message ids are listed in <code>manifest.json</code>.</footer>'
    )
    body.append('</div></body></html>')
    return '\n'.join(body)
