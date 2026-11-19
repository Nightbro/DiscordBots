"""Rendering a Transcript into documents.

Each format renders from the same model, independently — nothing here parses
another format's output. That is why there is no HTML-to-PDF step: converting
would mean carrying an HTML engine with native dependencies, and the PDF and
Word output only need the messages themselves.

No Discord types. Blocking work only, so callers run it off the event loop.
"""

from __future__ import annotations

import html
import logging
from io import BytesIO
from pathlib import Path

from utils.archive import Transcript
from utils.config import (
    ARCHIVE_DOCX_TEMPLATE,
    ARCHIVE_IMAGE_WIDTH,
    ARCHIVE_PDF_FONT,
    ARCHIVE_PDF_FONT_SIZE,
    ARCHIVE_PDF_IMAGE_WIDTH_MM,
    ASSETS_DIR,
)

log = logging.getLogger(__name__)

# fpdf2's built-in fonts are Latin-1 only, so a transcript containing Cyrillic,
# Greek or anything else outside that range needs a real TrueType font. None is
# vendored — a font binary in the repo for one feature is a poor trade — so a
# system one is used when present, in this order.
_FONT_CANDIDATES = (
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/TTF/DejaVuSans.ttf',
    '/Library/Fonts/Arial Unicode.ttf',
    'C:/Windows/Fonts/segoeui.ttf',
    'C:/Windows/Fonts/arial.ttf',
)

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


# ---------------------------------------------------------------------------
# Shared helpers for the document formats
# ---------------------------------------------------------------------------

# Images are embedded at print resolution rather than at whatever the camera
# produced, so a transcript of holiday photos does not become a 200 MB PDF.
_IMAGE_DPI = 150


def unicode_font() -> Path | None:
    """A TrueType font able to render the whole transcript, if one is around."""
    if ARCHIVE_PDF_FONT:
        configured = Path(ARCHIVE_PDF_FONT)
        if not configured.is_absolute():
            configured = ASSETS_DIR / configured
        if configured.exists():
            return configured
        log.warning('Configured PDF font %s does not exist — looking for a system one', configured)
    for candidate in _FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def _latin1(text: str) -> str:
    """Last resort when no TrueType font exists: keep what Latin-1 can hold."""
    return text.encode('latin-1', 'replace').decode('latin-1')


def _embeddable(path: Path, width_mm: int) -> BytesIO | None:
    """One image, downscaled in memory. None if it cannot be read."""
    try:
        from PIL import Image

        max_px = max(1, round(width_mm / 25.4 * _IMAGE_DPI))
        with Image.open(path) as img:
            frame = img.convert('RGB')
            if frame.width > max_px:
                ratio = max_px / frame.width
                frame = frame.resize((max_px, max(1, round(frame.height * ratio))))
            buffer = BytesIO()
            frame.save(buffer, format='JPEG', quality=85)
        buffer.seek(0)
        return buffer
    except Exception as exc:
        # A corrupt or exotic upload must not cost the whole transcript.
        log.warning('Image %s could not be embedded: %s', path.name, exc)
        return None


def _header_lines(transcript: Transcript) -> tuple[str, str]:
    generated = transcript.generated_at.strftime('%Y-%m-%d %H:%M UTC')
    return (
        f'#{transcript.channel_name}',
        f'{transcript.guild_name} · {len(transcript.messages)} messages · '
        f'{transcript.attachment_count} attachments · exported {generated}',
    )


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def render_pdf(transcript: Transcript, *, root: Path | None = None) -> bytes:
    """The transcript as a PDF: messages, timestamps and inline images.

    Rendered from the model, not from the HTML — see the module docstring.
    """
    from fpdf import FPDF

    font = unicode_font()
    pdf = FPDF(unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if font is not None:
        pdf.add_font('body', '', str(font))
        family = 'body'

        def clean(text: str) -> str:
            return text
    else:
        family = 'helvetica'
        clean = _latin1
        log.warning(
            'No TrueType font found — the PDF uses a Latin-1 font and other '
            'characters will be replaced. Set archive.pdf_font in config.yaml.'
        )

    size = ARCHIVE_PDF_FONT_SIZE
    title, meta = _header_lines(transcript)

    pdf.set_font(family, size=size + 6)
    pdf.multi_cell(0, 9, clean(title), new_x='LMARGIN', new_y='NEXT')
    pdf.set_font(family, size=size - 2)
    pdf.set_text_color(110)
    pdf.multi_cell(0, 5, clean(meta), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    if not transcript.messages:
        pdf.set_font(family, size=size)
        pdf.multi_cell(0, 5, clean('No messages in this range.'),
                       new_x='LMARGIN', new_y='NEXT')
        return bytes(pdf.output())

    for message in transcript.messages:
        pdf.set_text_color(90)
        pdf.set_font(family, size=size - 2)
        stamp = f'{message.author_name} · {message.timestamp}'
        if message.edited:
            stamp += ' (edited)'
        pdf.multi_cell(0, 5, clean(stamp), new_x='LMARGIN', new_y='NEXT')

        pdf.set_text_color(0)
        pdf.set_font(family, size=size)
        if message.content:
            pdf.multi_cell(0, 5, clean(message.content), new_x='LMARGIN', new_y='NEXT')

        for attachment in message.images:
            buffer = None
            if root is not None:
                buffer = _embeddable(root / attachment.path_in_bundle,
                                     ARCHIVE_PDF_IMAGE_WIDTH_MM)
            if buffer is None:
                pdf.multi_cell(0, 5, clean(f'[image: {attachment.filename}]'),
                               new_x='LMARGIN', new_y='NEXT')
                continue
            try:
                pdf.image(buffer, w=ARCHIVE_PDF_IMAGE_WIDTH_MM)
            except Exception as exc:
                log.warning('Image %s rejected by the PDF writer: %s',
                            attachment.filename, exc)
                pdf.multi_cell(0, 5, clean(f'[image: {attachment.filename}]'),
                               new_x='LMARGIN', new_y='NEXT')

        for attachment in message.files:
            pdf.set_text_color(110)
            pdf.multi_cell(0, 5, clean(f'[file: {attachment.filename}]'),
                           new_x='LMARGIN', new_y='NEXT')
            pdf.set_text_color(0)

        pdf.ln(3)

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

def docx_template() -> Path | None:
    """The .docx whose styles the Word transcript should borrow, if configured."""
    if not ARCHIVE_DOCX_TEMPLATE:
        return None
    path = Path(ARCHIVE_DOCX_TEMPLATE)
    if not path.is_absolute():
        path = ASSETS_DIR / path
    if path.exists():
        return path
    log.warning('Configured Word template %s does not exist — using defaults', path)
    return None


def _paragraph(doc, text: str, style: str | None = None):
    """Add a paragraph, falling back when a template lacks the named style."""
    if style:
        try:
            return doc.add_paragraph(text, style=style)
        except KeyError:
            log.warning('Word template has no %s style — using the default', style)
    return doc.add_paragraph(text)


def render_docx(transcript: Transcript, *, root: Path | None = None) -> bytes:
    """The transcript as a .docx, styled by an optional template."""
    from docx import Document
    from docx.shared import Mm

    template = docx_template()
    doc = Document(str(template)) if template is not None else Document()

    # A template is a source of styles, not of content — drop anything it holds
    # so the transcript does not inherit somebody's placeholder text.
    for paragraph in list(doc.paragraphs):
        element = paragraph._element
        element.getparent().remove(element)

    title, meta = _header_lines(transcript)
    _paragraph(doc, title, 'Title')
    _paragraph(doc, meta, 'Subtitle')

    if not transcript.messages:
        _paragraph(doc, 'No messages in this range.')
    for message in transcript.messages:
        stamp = f'{message.author_name} · {message.timestamp}'
        if message.edited:
            stamp += ' (edited)'
        _paragraph(doc, stamp, 'Heading 2')

        if message.content:
            _paragraph(doc, message.content)

        for attachment in message.images:
            buffer = None
            if root is not None:
                buffer = _embeddable(root / attachment.path_in_bundle,
                                     ARCHIVE_PDF_IMAGE_WIDTH_MM)
            if buffer is None:
                _paragraph(doc, f'[image: {attachment.filename}]')
                continue
            try:
                doc.add_picture(buffer, width=Mm(ARCHIVE_PDF_IMAGE_WIDTH_MM))
            except Exception as exc:
                log.warning('Image %s rejected by the Word writer: %s',
                            attachment.filename, exc)
                _paragraph(doc, f'[image: {attachment.filename}]')

        for attachment in message.files:
            _paragraph(doc, f'[file: {attachment.filename}]')

    out = BytesIO()
    doc.save(out)
    return out.getvalue()
