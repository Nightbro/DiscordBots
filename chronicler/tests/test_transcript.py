"""Rendering a transcript to HTML, PDF and Word."""

from datetime import datetime, timezone
from io import BytesIO

import pytest

from utils import transcript as render
from utils.archive import ArchivedAttachment, ArchivedMessage, Transcript
from utils.config import ARCHIVE_IMAGE_WIDTH

WHEN = datetime(2026, 11, 19, 14, 30, tzinfo=timezone.utc)


def _att(filename, size=2048):
    return ArchivedAttachment(filename=filename, stored_as=f'1-0-{filename}', size=size)


def _message(content='hello there', attachments=None, author='Ivan', edited=False, mid=1):
    return ArchivedMessage(
        id=mid,
        author_id=42,
        author_name=author,
        created_at=WHEN,
        content=content,
        edited=edited,
        attachments=attachments or [],
    )


def _html(messages=None, **kwargs):
    transcript = Transcript(
        guild_name='The Table',
        channel_name='general',
        messages=messages if messages is not None else [_message()],
        generated_at=WHEN,
    )
    return render.render_html(transcript, **kwargs)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_html_is_a_complete_document():
    out = _html()
    assert out.startswith('<!doctype html>')
    assert out.rstrip().endswith('</html>')
    assert '<meta charset="utf-8">' in out


def test_html_links_the_stylesheet_rather_than_inlining_it():
    assert '<link rel="stylesheet" href="style.css">' in _html()


def test_header_carries_channel_guild_and_counts():
    out = _html([_message(), _message(mid=2)])
    assert '#general' in out
    assert 'The Table' in out
    assert '2 messages' in out
    assert '2026-11-19' in out


def test_message_shows_author_timestamp_and_text():
    out = _html([_message(content='roll for initiative', author='Mira')])
    assert 'Mira' in out
    assert '2026-11-19 14:30' in out
    assert 'roll for initiative' in out


def test_edited_messages_are_marked():
    assert '(edited)' in _html([_message(edited=True)])
    assert '(edited)' not in _html([_message(edited=False)])


def test_empty_transcript_says_so():
    out = _html([])
    assert 'No messages in this range' in out


def test_message_with_neither_text_nor_attachments_is_still_rendered():
    out = _html([_message(content='')])
    assert '[no text]' in out


# ---------------------------------------------------------------------------
# Attachments — references must be relative, because CDN links expire
# ---------------------------------------------------------------------------

def test_images_are_referenced_relatively_not_from_discord():
    """Discord CDN links are signed and expire, so an export must not use them."""
    out = _html([_message(attachments=[_att('shot.png')])])
    assert 'src="images/1-0-shot.png"' in out
    assert 'discordapp' not in out
    assert 'src="http' not in out
    assert 'href="http' not in out


def test_images_are_displayed_at_the_configured_width():
    out = _html([_message(attachments=[_att('shot.png')])])
    assert f'width="{ARCHIVE_IMAGE_WIDTH}"' in out


def test_image_width_can_be_overridden():
    out = _html([_message(attachments=[_att('shot.png')])], image_width=123)
    assert 'width="123"' in out


def test_non_image_files_are_linked_with_their_size():
    out = _html([_message(attachments=[_att('notes.pdf', size=4096)])])
    assert 'href="files/1-0-notes.pdf"' in out
    assert '4 KB' in out


def test_a_tiny_file_still_reports_at_least_one_kb():
    out = _html([_message(attachments=[_att('tiny.txt', size=5)])])
    assert '1 KB' in out


def test_images_and_files_both_appear():
    out = _html([_message(attachments=[_att('a.png'), _att('b.zip')])])
    assert 'images/1-0-a.png' in out
    assert 'files/1-0-b.zip' in out


def test_footer_explains_where_the_files_are():
    out = _html()
    assert 'images/' in out
    assert 'manifest.json' in out


# ---------------------------------------------------------------------------
# Escaping — message text is untrusted input
# ---------------------------------------------------------------------------

def test_message_text_is_escaped():
    out = _html([_message(content='<script>alert(1)</script>')])
    assert '<script>' not in out
    assert '&lt;script&gt;' in out


def test_author_name_is_escaped():
    out = _html([_message(author='<b>bold</b>')])
    assert '<b>bold</b>' not in out
    assert '&lt;b&gt;' in out


def test_attachment_filename_is_escaped():
    out = _html([_message(attachments=[_att('a"onerror=x.png')])])
    assert 'onerror=x' not in out.replace('&quot;onerror=x', '')


def test_channel_and_guild_names_are_escaped():
    transcript = Transcript(
        guild_name='<guild>',
        channel_name='<chan>',
        messages=[_message()],
        generated_at=WHEN,
    )
    out = render.render_html(transcript)
    assert '<guild>' not in out
    assert '&lt;guild&gt;' in out
    assert '&lt;chan&gt;' in out


def test_newlines_survive_as_preformatted_text():
    """White-space is preserved by CSS, so the text itself needs no <br>."""
    out = _html([_message(content='line one\nline two')])
    assert 'line one\nline two' in out
    assert 'white-space: pre-wrap' in render.STYLE_CSS


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

def test_stylesheet_defines_colours_for_both_schemes():
    assert ':root' in render.STYLE_CSS
    assert 'prefers-color-scheme: light' in render.STYLE_CSS


def test_stylesheet_keeps_images_inside_the_page():
    assert 'max-width: 100%' in render.STYLE_CSS


# ---------------------------------------------------------------------------
# Shared fixtures for the document formats
# ---------------------------------------------------------------------------

def _transcript(messages=None, guild='The Table', channel='general'):
    return Transcript(
        guild_name=guild,
        channel_name=channel,
        messages=messages if messages is not None else [_message()],
        generated_at=WHEN,
    )


@pytest.fixture
def staged(tmp_path):
    """A staging tree with one real image in it, as an export would produce."""
    from PIL import Image

    images = tmp_path / 'images'
    images.mkdir()
    Image.new('RGB', (1600, 900), (30, 40, 50)).save(images / '1-0-shot.png')
    return tmp_path


def _docx_text(data: bytes) -> str:
    from docx import Document

    return '\n'.join(p.text for p in Document(BytesIO(data)).paragraphs)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def test_pdf_is_a_pdf():
    data = render.render_pdf(_transcript())
    assert data.startswith(b'%PDF')
    assert len(data) > 500


def test_pdf_of_an_empty_range_still_renders():
    assert render.render_pdf(_transcript([])).startswith(b'%PDF')


def test_pdf_embeds_an_image_when_the_files_are_there(staged):
    """A JPEG stream in the PDF shows as a DCTDecode filter — assert that,
    rather than a size delta, which a flat test image barely moves."""
    plain = render.render_pdf(_transcript([_message(content='look')]))
    withimg = render.render_pdf(
        _transcript([_message(content='look', attachments=[_att('shot.png')])]),
        root=staged,
    )
    assert b'DCTDecode' in withimg
    assert b'DCTDecode' not in plain


def test_pdf_notes_an_image_it_cannot_reach(tmp_path):
    """A missing file must leave a trace in the document, not vanish silently."""
    data = render.render_pdf(
        _transcript([_message(attachments=[_att('gone.png')])]), root=tmp_path
    )
    assert data.startswith(b'%PDF')


def test_pdf_survives_a_corrupt_image(tmp_path):
    images = tmp_path / 'images'
    images.mkdir()
    (images / '1-0-shot.png').write_bytes(b'not an image at all')
    data = render.render_pdf(
        _transcript([_message(attachments=[_att('shot.png')])]), root=tmp_path
    )
    assert data.startswith(b'%PDF')


def test_pdf_handles_non_latin_text():
    """A Serbian or Cyrillic transcript must not blow up the renderer."""
    data = render.render_pdf(_transcript([
        _message(content='Мршави Вук каже здраво', author='Мира'),
        _message(content='Šta ćeš raditi večeras?', author='Miloš'),
    ]))
    assert data.startswith(b'%PDF')


def test_pdf_falls_back_when_no_truetype_font_exists(monkeypatch):
    """With no system font, output degrades to Latin-1 rather than failing."""
    monkeypatch.setattr(render, '_FONT_CANDIDATES', ())
    monkeypatch.setattr(render, 'ARCHIVE_PDF_FONT', '')
    assert render.unicode_font() is None
    data = render.render_pdf(_transcript([_message(content='Мршави Вук')]))
    assert data.startswith(b'%PDF')


def test_configured_font_is_preferred(monkeypatch, tmp_path):
    font = tmp_path / 'custom.ttf'
    font.write_bytes(b'stub')
    monkeypatch.setattr(render, 'ARCHIVE_PDF_FONT', str(font))
    assert render.unicode_font() == font


def test_a_missing_configured_font_falls_back_to_a_system_one(monkeypatch, tmp_path):
    monkeypatch.setattr(render, 'ARCHIVE_PDF_FONT', str(tmp_path / 'nope.ttf'))
    monkeypatch.setattr(render, '_FONT_CANDIDATES', ())
    assert render.unicode_font() is None


def test_pdf_notes_non_image_attachments():
    data = render.render_pdf(_transcript([_message(attachments=[_att('notes.pdf')])]))
    assert data.startswith(b'%PDF')


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

def test_docx_opens_and_carries_the_messages():
    data = render.render_docx(_transcript([
        _message(content='roll for initiative', author='Mira'),
    ]))
    text = _docx_text(data)
    assert 'roll for initiative' in text
    assert 'Mira' in text
    assert '#general' in text


def test_docx_header_carries_the_counts():
    data = render.render_docx(_transcript([_message(), _message(mid=2)]))
    assert '2 messages' in _docx_text(data)


def test_docx_of_an_empty_range_says_so():
    assert 'No messages in this range' in _docx_text(render.render_docx(_transcript([])))


def test_docx_marks_edited_messages():
    data = render.render_docx(_transcript([_message(edited=True)]))
    assert '(edited)' in _docx_text(data)


def test_docx_keeps_non_latin_text_intact():
    """Unlike the PDF fallback, Word has no Latin-1 limitation to work around."""
    data = render.render_docx(_transcript([_message(content='Мршави Вук', author='Мира')]))
    text = _docx_text(data)
    assert 'Мршави Вук' in text
    assert 'Мира' in text


def test_docx_embeds_an_image(staged):
    """A .docx is a zip — an embedded picture lands under word/media/."""
    import zipfile

    withimg = render.render_docx(
        _transcript([_message(attachments=[_att('shot.png')])]), root=staged
    )
    with zipfile.ZipFile(BytesIO(withimg)) as zf:
        media = [n for n in zf.namelist() if n.startswith('word/media/')]
    assert media, 'no image was embedded'

    plain = render.render_docx(_transcript([_message()]))
    with zipfile.ZipFile(BytesIO(plain)) as zf:
        assert not [n for n in zf.namelist() if n.startswith('word/media/')]


def test_docx_notes_an_image_it_cannot_reach(tmp_path):
    data = render.render_docx(
        _transcript([_message(attachments=[_att('gone.png')])]), root=tmp_path
    )
    assert '[image: gone.png]' in _docx_text(data)


def test_docx_notes_non_image_attachments():
    data = render.render_docx(_transcript([_message(attachments=[_att('notes.pdf')])]))
    assert '[file: notes.pdf]' in _docx_text(data)


def test_docx_template_is_optional(monkeypatch):
    monkeypatch.setattr(render, 'ARCHIVE_DOCX_TEMPLATE', '')
    assert render.docx_template() is None


def test_a_missing_docx_template_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(render, 'ARCHIVE_DOCX_TEMPLATE', str(tmp_path / 'nope.docx'))
    assert render.docx_template() is None
    assert render.render_docx(_transcript()).startswith(b'PK')


def test_docx_template_supplies_styles_and_not_content(monkeypatch, tmp_path):
    """A template is a source of styles — its own text must not leak through."""
    from docx import Document

    template = tmp_path / 'template.docx'
    doc = Document()
    doc.add_paragraph('PLACEHOLDER TEXT FROM THE TEMPLATE')
    doc.save(template)

    monkeypatch.setattr(render, 'ARCHIVE_DOCX_TEMPLATE', str(template))
    assert render.docx_template() == template
    text = _docx_text(render.render_docx(_transcript([_message(content='real content')])))
    assert 'PLACEHOLDER' not in text
    assert 'real content' in text


# ---------------------------------------------------------------------------
# Image downscaling
# ---------------------------------------------------------------------------

def test_large_images_are_downscaled_for_embedding(staged):
    from PIL import Image

    buffer = render._embeddable(staged / 'images' / '1-0-shot.png', 120)
    assert buffer is not None
    with Image.open(buffer) as embedded:
        assert embedded.width < 1600


def test_a_small_image_is_left_alone(tmp_path):
    from PIL import Image

    images = tmp_path / 'images'
    images.mkdir()
    Image.new('RGB', (50, 40)).save(images / 'tiny.png')
    buffer = render._embeddable(images / 'tiny.png', 120)
    with Image.open(buffer) as embedded:
        assert embedded.size == (50, 40)


def test_an_unreadable_image_returns_nothing(tmp_path):
    (tmp_path / 'broken.png').write_bytes(b'nope')
    assert render._embeddable(tmp_path / 'broken.png', 120) is None


def test_a_missing_image_returns_nothing(tmp_path):
    assert render._embeddable(tmp_path / 'absent.png', 120) is None
