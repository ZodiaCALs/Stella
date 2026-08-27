#!/usr/bin/env python3
"""GameDev Pulse 本地服务器：提供静态页面 + /proxy 反代（绕过浏览器 CORS）
用法：python server.py  →  浏览器打开 http://127.0.0.1:8000
"""
import http.server, socketserver, urllib.request, urllib.parse

PORT = 8000

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/proxy':
            url = urllib.parse.parse_qs(parsed.query).get('url', [''])[0]
            if not url.startswith(('http://', 'https://')):
                self.send_error(400, 'bad url'); return
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (GameDevPulse/1.0)'})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = r.read()
                    ctype = r.headers.get('Content-Type', 'application/xml')
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(502, str(e))
            return
        super().do_GET()

    def log_message(self, fmt, *args): pass  # 静默日志

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('127.0.0.1', PORT), Handler) as httpd:
        print(f'🎮 GameDev Pulse 已启动 → http://127.0.0.1:{PORT}')
        httpd.serve_forever()