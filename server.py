#!/usr/bin/env python3
"""本地 RSS 代理 + AI 摘要转发服务器"""
import json, urllib.request, urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8000

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path.startswith('/proxy'):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            url = qs.get('url', [''])[0]
            if not url:
                self.send_response(400); self.end_headers(); return
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                self.send_response(200)
                self.send_header('Content-Type', r.headers.get('Content-Type', 'text/xml'))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(502)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(str(e).encode())
            return
        return super().do_GET()

    def do_POST(self):
        """转发 AI 请求到 OpenAI 兼容接口（规避浏览器 CORS）"""
        if self.path == '/ai':
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                url = body['base'].rstrip('/') + '/chat/completions'
                req = urllib.request.Request(url, data=json.dumps({
                    'model': body['model'], 'messages': body['messages'], 'temperature': 0.7
                }).encode(), headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + body['key']
                })
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(502)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return
        self.send_response(404); self.end_headers()

if __name__ == '__main__':
    print(f'✅ 服务已启动: http://127.0.0.1:{PORT}')
    HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()