"""Rendering a transcript to HTML."""

from datetime import datetime, timezone

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
