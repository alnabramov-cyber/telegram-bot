import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_http():
    server = HTTPServer(("0.0.0.0", 10000), Handler)
    server.serve_forever()

# HTTP-заглушка для Render
threading.Thread(target=run_http, daemon=True).start()

# Основной цикл (пока бот-заглушка)
while True:
    print("Bot is alive")
    time.sleep(60)
