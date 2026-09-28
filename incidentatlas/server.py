"""Zero-dependency reference transport. Local development only."""
from functools import partial
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote,urlparse
from .service import Service
MAX_BODY=5*1024*1024


def make_handler(service,web_root):
    root=Path(web_root).resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,format,*args):
            # No request payloads, API keys or telemetry content are logged.
            super().log_message(format,*args)
        def send(self,status,payload,content_type='application/json'):
            content=payload.encode() if isinstance(payload,str) else json.dumps(payload,allow_nan=False).encode()
            self.send_response(status); self.send_header('Content-Type',content_type+'; charset=utf-8')
            self.send_header('Content-Length',str(len(content)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(content)
        def handle_request(self):
            try:
                path=urlparse(self.path).path
                if path.startswith('/api/'):
                    body=None
                    if self.command in {'POST','PATCH'}:
                        size=int(self.headers.get('Content-Length','0'))
                        if size<0 or size>MAX_BODY: self.send(413,{'error':'body exceeds 5 MiB'});return
                        body=json.loads(self.rfile.read(size)) if size else {}
                    result=service.dispatch(self.command,self.path,body)
                    self.send(200,result,'text/markdown' if isinstance(result,str) else 'application/json')
                elif self.command=='GET':
                    requested=(root/(unquote(path).lstrip('/') or 'index.html')).resolve()
                    if not requested.is_relative_to(root) or not requested.is_file(): raise KeyError('file not found')
                    content=requested.read_bytes();self.send_response(200)
                    self.send_header('Content-Type',mimetypes.guess_type(str(requested))[0] or 'application/octet-stream')
                    self.send_header('Content-Length',str(len(content)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(content)
                else: self.send(405,{'error':'method not allowed'})
            except (ValueError,TypeError,json.JSONDecodeError) as exc: self.send(400,{'error':str(exc)})
            except KeyError as exc: self.send(404,{'error':str(exc).strip("'")})
        do_GET=handle_request
        do_POST=handle_request
        do_PATCH=handle_request
    return Handler


def serve(host='127.0.0.1',port=8100,db_path='.incidentatlas/state.sqlite3',web_root=None):
    root=web_root or Path(__file__).resolve().parent.parent/'web'
    service=Service(db_path)
    server=HTTPServer((host,port),make_handler(service,root))
    print(f'IncidentAtlas local server: http://{host}:{port} (SQLite; no production authentication)',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close();service.store.close()
