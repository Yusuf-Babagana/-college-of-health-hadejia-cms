"""
HTML-to-PDF rendering, shared by every report that needs a downloadable
document: invoices, registration slips, transcripts, broadsheets.

Templates are plain Django templates styled with inline-friendly CSS
(xhtml2pdf does not support the full modern CSS box model used by
Bootstrap, so PDF templates should stay simple rather than reusing
static/css/theme.css).
"""
import base64
import logging
from functools import lru_cache
from io import BytesIO

from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa

logger = logging.getLogger('apps')


class PDFRenderError(Exception):
    pass


def image_file_data_uri(path):
    """A local image file (e.g. an uploaded profile picture) as a base64
    data URI for embedding in a PDF. '' if it can't be read - callers
    show a placeholder instead of failing the whole document."""
    try:
        with open(path, 'rb') as handle:
            encoded = base64.b64encode(handle.read()).decode('ascii')
    except (OSError, ValueError, TypeError):
        return ''
    mime = 'image/png' if str(path).lower().endswith('.png') else 'image/jpeg'
    return f'data:{mime};base64,{encoded}'


@lru_cache(maxsize=16)
def static_image_data_uri(static_path):
    """A static image (e.g. 'img/brand/logo1.png') as a base64 data URI, so
    a PDF template can embed it without caring where static files live on
    the machine (dev, collectstatic'd, PythonAnywhere). '' if not found."""
    path = finders.find(static_path)
    if not path:
        logger.warning('PDF image %s not found', static_path)
        return ''
    with open(path, 'rb') as handle:
        encoded = base64.b64encode(handle.read()).decode('ascii')
    mime = 'image/png' if static_path.lower().endswith('.png') else 'image/jpeg'
    return f'data:{mime};base64,{encoded}'


def render_to_pdf_bytes(template_name, context=None):
    """Render a template to a PDF and return the raw bytes."""
    html = render_to_string(template_name, context or {})
    buffer = BytesIO()
    result = pisa.pisaDocument(BytesIO(html.encode('UTF-8')), buffer)
    if result.err:
        logger.error('PDF generation failed for template %s (%s errors)', template_name, result.err)
        raise PDFRenderError(f'Failed to render PDF from {template_name}')
    return buffer.getvalue()


def render_to_pdf_response(template_name, context=None, filename='document.pdf', inline=True):
    """Render a template to a PDF and return it as an HttpResponse, either
    displayed inline in the browser or forced as a download.
    """
    pdf_bytes = render_to_pdf_bytes(template_name, context)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    disposition = 'inline' if inline else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    return response
