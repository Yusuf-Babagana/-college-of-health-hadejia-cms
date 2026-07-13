"""
HTML-to-PDF rendering, shared by every report that needs a downloadable
document: invoices, registration slips, transcripts, broadsheets.

Templates are plain Django templates styled with inline-friendly CSS
(xhtml2pdf does not support the full modern CSS box model used by
Bootstrap, so PDF templates should stay simple rather than reusing
static/css/theme.css).
"""
import logging
from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa

logger = logging.getLogger('apps')


class PDFRenderError(Exception):
    pass


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
