"""Local approval service; deploy behind HTTPS. GET never changes decisions."""
import html
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from .approvals import get, decide
from .recommendations import blockers

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Approval tokens must not enter access logs.

    def respond(self, body, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        page = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Investment review</title><style>body{font:16px system-ui;max-width:850px;margin:40px auto;padding:20px;color:#173247}article{padding:16px;background:#f0f5f7;margin:10px 0}button{padding:14px 24px;margin:10px;font-size:16px}small{overflow-wrap:anywhere}</style>' + body
        self.wfile.write(page.encode())

    def token(self):
        return parse_qs(urlparse(self.path).query).get('token', [''])[0]

    def do_GET(self):
        try:
            token = self.token()
            card, status = get(token)
            esc = html.escape
            body = f'<h1>{esc(card["symbol"])} - {esc(card["action"])}</h1><p>{esc(card["thesis"])}</p><p>Status: {esc(status)}. Research mode: accepting cannot place a trade.</p>'
            for label in ('entry', 'stop', 'target', 'units', 'created_at', 'expires_at'):
                body += f'<p><b>{label.replace("_", " ").title()}:</b> {esc(str(card.get(label, "Missing")))}</p>'
            for key, value in card.get('evidence', {}).items():
                body += f'<article><b>{esc(key.replace("_", " ").title())}</b><p>{esc(value.get("summary", "Missing"))}</p><small>Source: {esc(value.get("source", "Missing"))} | Published: {esc(value.get("published_at", "Missing"))}</small></article>'
            reasons = blockers(card)
            if reasons:
                body += '<h2>Acceptance blocked</h2><ul>' + ''.join('<li>'+esc(r)+'</li>' for r in reasons) + '</ul>'
            if status == 'PENDING':
                disabled = 'disabled' if reasons else ''
                body += f'<form method="post"><input type="hidden" name="token" value="{esc(token)}"><p>Confirm your decision. The link is personal; do not forward it.</p><button name="decision" value="ACCEPT" {disabled}>Accept</button><button name="decision" value="REJECT">Not accepted</button></form>'
            self.respond(body)
        except (ValueError, KeyError):
            self.respond('Recommendation unavailable.', 404)

    def do_POST(self):
        expected = os.getenv('APPROVAL_BASE_URL', 'http://127.0.0.1:8080').rstrip('/')
        if self.headers.get('Origin') != expected:
            return self.respond('Invalid request origin.', 403)
        length = int(self.headers.get('Content-Length', '0'))
        if length < 1 or length > 4096:
            return self.respond('Invalid request size.', 400)
        fields = parse_qs(self.rfile.read(length).decode())
        try:
            token = fields['token'][0]
            if token != self.token():
                raise ValueError('Token mismatch')
            status = decide(token, fields['decision'][0])
            self.respond('<h1>Decision saved</h1><p>'+html.escape(status)+'</p><p>No trade has been placed.</p>')
        except (ValueError, KeyError) as exc:
            self.respond(html.escape(str(exc)), 400)

def serve():
    HTTPServer(('127.0.0.1', 8080), Handler).serve_forever()
