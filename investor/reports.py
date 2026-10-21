import html
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from .recommendations import blockers


def pdf(cards, destination, review_links=None):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    fontdir = Path(reportlab.__file__).parent / 'fonts'
    pdfmetrics.registerFont(TTFont('Brief', str(fontdir / 'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('BriefBold', str(fontdir / 'VeraBd.ttf')))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = 'Brief'
    for name in ('Title', 'Heading1', 'Heading3'):
        styles[name].fontName = 'BriefBold'
    styles['Heading3'].fontSize = 10
    styles['Heading3'].spaceBefore = 7
    styles['Heading3'].spaceAfter = 3
    styles['BodyText'].fontSize = 8
    styles['BodyText'].leading = 10
    styles['BodyText'].spaceBefore = 2
    story = []
    for index, card in enumerate(cards):
        if index:
            story.append(PageBreak())
        p = lambda text: Paragraph(html.escape(str(text)), styles['BodyText'])
        story += [Paragraph('INVESTMENT DECISION BRIEF', styles['Title']), p('RESEARCH ONLY - NO LIVE ORDERS'), Spacer(1, 12),
                  Paragraph(html.escape(card['symbol']+' | '+card['action']), styles['Heading1']), p(card['thesis']), Spacer(1, 12)]
        rows = [[p('Entry'), p('Stop'), p('Target'), p('Units'), p('Planned stop risk')],
                [p(f"${card['entry']:,.2f}" if card.get('entry') else 'N/A'), p(f"${card['stop']:,.2f}" if card.get('stop') else 'N/A'), p(f"${card['target']:,.2f}" if card.get('target') else 'N/A'), p(f"{card.get('units', 0):g}"), p('$%.2f' % (abs(card.get('entry', 0)-card.get('stop', 0))*card.get('units', 0)))]]
        table = Table(rows, colWidths=[1*inch, 1*inch, 1*inch, 1*inch, 2.2*inch])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dceaf0')), ('VALIGN',(0,0),(-1,-1),'TOP'), ('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        story += [table, Spacer(1, 8), p('Created: '+card['created_at']+' | Expires: '+card['expires_at']),
                  p('Stop risk excludes gaps and costs. Targets are scenarios, not forecasts.')]
        for name, evidence in card['evidence'].items():
            story += [Paragraph(html.escape(name.replace('_',' ').title()), styles['Heading3']), p(evidence.get('summary','Missing')),
                      p('Source: '+evidence.get('source','Missing')+' | '+evidence.get('published_at','Missing timestamp'))]
        reasons = blockers(card)
        story += [Spacer(1, 8), p('Acceptance: '+(('Blocked - illustrative sample, not a verified trade.' if card.get('sample') else '; '.join(reasons)) if reasons else 'Eligible for research approval; execution requires fresh broker and portfolio checks.'))]
        if review_links:
            link = html.escape(review_links[index], quote=True)
            story += [Spacer(1, 10), Paragraph(f'<a href="{link}" color="blue">Review evidence and choose Accept / Not accepted</a>', styles['BodyText'])]
    SimpleDocTemplate(str(path), topMargin=36, bottomMargin=36, leftMargin=36, rightMargin=36).build(story)
    return path


def send_report(path, links):
    required = ('REPORT_RECIPIENT','SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_FROM')
    if any(not os.getenv(k) for k in required):
        raise ValueError('Configure recipient and SMTP credentials before sending')
    message = EmailMessage()
    message['Subject'] = 'Research recommendations - review required'
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = os.environ['REPORT_RECIPIENT']
    message.set_content('No live trades will be placed. Review each proposal, then select Accept or Not accepted.\n\n'+'\n'.join(links)+'\n\nThe attached PDF contains the supporting evidence. Links are personal; do not forward.')
    message.add_attachment(Path(path).read_bytes(), maintype='application', subtype='pdf', filename='investment-review.pdf')
    with smtplib.SMTP_SSL(os.environ['SMTP_HOST'], int(os.getenv('SMTP_PORT','465')), context=ssl.create_default_context()) as smtp:
        smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(message)
