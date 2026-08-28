import os
import json
import httpx
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "10000"))

CVC_API_KEY = os.environ.get("CVC_API_KEY")

API_BASE = os.environ.get(
    "CVC_BASE_URL",
    "https://ai.starimg.ru/v1"
).rstrip("/")

MODEL = os.environ.get(
    "AI_MODEL",
    "cheapvibecode/claude-sonnet-5"
)

SYSTEM_PROMPT = """
Ты — ИИ-ассистент.

Отвечай преимущественно на русском языке.
Отвечай понятно, конкретно и по существу.
Если информации недостаточно, прямо скажи об этом.
"""

class Handler(BaseHTTPRequestHandler):

    def send_json(self, status, data):
        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )
        self.end_headers()

        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_POST(self):

        if self.path != "/api/chat":
            self.send_json(404, {"error": "Not found"})
            return

        if not CVC_API_KEY:
            self.send_json(
                500,
                {"error": "CVC_API_KEY не настроен на Render"}
            )
            return

        try:
            length = int(
                self.headers.get("Content-Length", 0)
            )

            raw = self.rfile.read(length)

            data = json.loads(
                raw.decode("utf-8")
            )

            user_text = str(
                data.get("message", "")
            ).strip()

            history = data.get("history", [])

            if not user_text:
                self.send_json(
                    400,
                    {"error": "Пустое сообщение"}
                )
                return

            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                }
            ]

            # История диалога
            if isinstance(history, list):
                for item in history[-20:]:

                    if not isinstance(item, dict):
                        continue

                    role = item.get("role")
                    content = item.get("content")

                    if role not in ("user", "assistant"):
                        continue

                    if not isinstance(content, str):
                        continue

                    messages.append({
                        "role": role,
                        "content": content[:30000]
                    })

            messages.append({
                "role": "user",
                "content": user_text
            })

            payload = {
                "model": MODEL,
                "messages": messages,
                "max_tokens": 4096
            }

            headers = {
                "Authorization":
                    f"Bearer {CVC_API_KEY}",
                "Content-Type":
                    "application/json",
                "Accept":
                    "application/json"
            }

            with httpx.Client(
                timeout=httpx.Timeout(
                    connect=30,
                    read=180,
                    write=60,
                    pool=30
                )
            ) as client:

                response = client.post(
                    f"{API_BASE}/chat/completions",
                    headers=headers,
                    json=payload
                )

            if response.status_code >= 400:
                self.send_json(
                    502,
                    {
                        "error":
                            f"AI API HTTP {response.status_code}",
                        "details":
                            response.text[:1000]
                    }
                )
                return

            result = response.json()

            choices = result.get("choices", [])

            if not choices:
                self.send_json(
                    502,
                    {
                        "error":
                            "AI API не вернул ответ",
                        "details": result
                    }
                )
                return

            message = choices[0].get(
                "message",
                {}
            )

            answer = message.get(
                "content",
                ""
            )

            if isinstance(answer, list):

                parts = []

                for item in answer:

                    if (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                    ):
                        parts.append(
                            item.get("text", "")
                        )

                answer = "\n".join(parts)

            usage = result.get(
                "usage",
                {}
            )

            self.send_json(
                200,
                {
                    "answer": str(answer),
                    "model": MODEL,
                    "usage": usage
                }
            )

        except Exception as e:

            print(
                "API ERROR:",
                repr(e)
            )

            self.send_json(
                500,
                {
                    "error":
                        "Ошибка сервера",
                    "details":
                        str(e)
                }
            )

    def do_GET(self):

        if self.path == "/health":
            self.send_json(
                200,
                {"status": "ok"}
            )
            return

        self.send_json(
            404,
            {"error": "Not found"}
        )

    def log_message(self, format, *args):
        print(format % args)


server = ThreadingHTTPServer(
    ("0.0.0.0", PORT),
    Handler
)

print(
    f"Server started on port {PORT}"
)

server.serve_forever()
