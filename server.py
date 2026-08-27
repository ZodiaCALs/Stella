#!/usr/bin/env python3
"""本地服务：RSS 代理 + AI 转发 + B站/YouTube 直连"""
import json, re, time, email.utils
import urllib.request, urllib.parse, html as H
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8000
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
RSSHUB_MIRRORS = ['https://rsshub.app', 'https://rsshub.rssforever.com',
                  'https://rsshub.ktachibana.party', 'https://hub.slarker.me',
                  'https://rsshub.pseudoyu.com']

def http_get(url, timeout=15, headers=None):
    h = {'User-Agent': UA}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def esc(s): return H.escape(str(s), quote=False)

# ---------- B站 ----------
def bili_to_rss(mid):
    # 1) 空间页 __INITIAL_STATE__ 解析
    try:
        page = http_get(f'https://space.bilibili.com/{mid}/video', timeout=12,
                        headers={'Referer': 'https://www.bilibili.com/'}).decode('utf-8', 'ignore')
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*\(function', page, re.S)
        if m:
            state = json.loads(m.group(1))
            vlist = state.get('video', {}).get('list', {}).get('vlist', [])
            if vlist:
                return _build_bili_rss(vlist, mid)
    except Exception:
        pass
    # 2) 官方 API
    try:
        data = json.loads(http_get(
            f'https://api.bilibili.com/x/space/wbi/arc/search?mid={mid}&ps=12&pn=1', timeout=10,
            headers={'Referer': f'https://space.bilibili.com/{mid}/video'}))
        vlist = (data.get('data') or {}).get('list', {}).get('vlist', [])
        if vlist:
            return _build_bili_rss(vlist, mid)
    except Exception:
        pass
    # 3) RSSHub 镜像轮询
    for base in RSSHUB_MIRRORS:
        try:
            data = http_get(f'{base}/bilibili/user/video/{mid}', timeout=9)
            if data.strip().startswith(b'<'):
                return data
        except Exception:
            continue
    raise RuntimeError('bilibili fetch failed')

def _build_bili_rss(vlist, mid):
    items = []
    for v in vlist[:12]:
        link = 'https://www.bilibili.com/video/' + str(v.get('bvid', ''))
        play = v.get('play', 0) or 0
        items.append(
            '<item><title>%s</title><link>%s</link><guid>%s</guid><pubDate>%s</pubDate>'
            '<description>%s 播放量: %s</description>'
            '<media:thumbnail url="%s"/><media:statistics views="%s"/></item>'
            % (esc(v.get('title', '')), link, link,
               email.utils.formatdate(v.get('created', time.time())),
               esc(v.get('description', ''))[:280], play, esc(v.get('pic', '')), play))
    author = esc(vlist[0].get('author', f'Bilibili {mid}')) if vlist else ''
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>'
            '<title>%s</title><link>https://space.bilibili.com/%s</link>%s'
            '</channel></rss>' % (author, mid, ''.join(items))).encode('utf-8')

# ---------- YouTube ----------
def yt_feed(handle, cid):
    if not cid:
        handle = handle.lstrip('@')
        page = http_get('https://www.youtube.com/@' + handle, timeout=15,
                        headers={'Cookie': 'CONSENT=YES+cb.20220301-11-p0.en+FX+700',
                                 'Accept-Language': 'en-US,en;q=0.9'}).decode('utf-8', 'ignore')
        m = re.search(r'"channelId":"(UC[\w-]{22})"', page) or re.search(r'channel_id=(UC[\w-]{22})', page)
        if not m:
            raise RuntimeError('channel id not found')
        cid = m.group(1)
    return http_get('https://www.youtube.com/feeds/videos.xml?channel_id=' + cid, timeout=15)

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        try:
            if u.path == '/proxy':
                url = qs.get('url', [''])[0]
                if not url:
                    self.send_response(400); self.end_headers(); return
                data = http_get(url, timeout=20)
            elif u.path == '/bili':
                data = bili_to_rss(qs.get('mid', [''])[0])
            elif u.path == '/yt':
                data = yt_feed(qs.get('handle', [''])[0], qs.get('cid', [''])[0])
            else:
                return super().do_GET()
            self.send_response(200); self._cors()
            self.send_header('Content-Type', 'text/xml; charset=utf-8')
            self.end_headers(); self.wfile.write(data)
        except Exception as e:
            self.send_response(502); self._cors(); self.end_headers()
            self.wfile.write(str(e).encode())

    def do_POST(self):
        if self.path == '/ai':
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                url = body['base'].rstrip('/') + '/chat/completions'
                req = urllib.request.Request(url, data=json.dumps({
                    'model': body['model'], 'messages': body['messages'], 'temperature': 0.7
                }).encode(), headers={'Content-Type': 'application/json',
                                      'Authorization': 'Bearer ' + body['key']})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                self.send_response(200); self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers(); self.wfile.write(data)
            except Exception as e:
                self.send_response(502); self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return
        self.send_response(404); self.end_headers()

if __name__ == '__main__':
    print(f'✅ 服务已启动: http://127.0.0.1:{PORT}  （Ctrl+C 退出）')
    HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()