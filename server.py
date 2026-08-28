import os
import json
import httpx
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PORT = int(os.environ.get("PORT", "10000"))

API_BASE = "https://api.odirouter.ai/v1"


# Отдельный ключ для каждой модели
API_KEYS = {
    "gpt": os.environ.get("GPTMINI_KEY"),
    "gemini": os.environ.get("PROPREW_KEY"),
    "qwen": os.environ.get("QWEN_KEY"),
}


MODELS = {
    "gpt": "free-gpt-5.4-mini",
    "gemini": "free-gemini-3.1-pro-preview",
    "qwen": "free-qwen3.5-plus",
}


SYSTEM_PROMPT = """
Ты — ИИ-ассистент.

Отвечай на русском языке, если пользователь пишет на русском.

Отвечай понятно, точно и по существу.

Не выдумывай факты.

Если ты не уверен в информации, прямо сообщи об этом.

Старайся давать полезный и хорошо структурированный ответ.
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

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS"
        )

        self.end_headers()

        self.wfile.write(body)


    def do_OPTIONS(self):

        self.send_response(204)

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS"
        )

        self.end_headers()


    def do_GET(self):

        if self.path in ("/", "/index.html"):

            try:

                with open("index.html", "rb") as file:
                    body = file.read()

                self.send_response(200)

                self.send_header(
                    "Content-Type",
                    "text/html; charset=utf-8"
                )

                self.send_header(
                    "Content-Length",
                    str(len(body))
                )

                self.end_headers()

                self.wfile.write(body)

            except FileNotFoundError:

                self.send_json(
                    500,
                    {
                        "error":
                            "index.html не найден"
                    }
                )

            return


        if self.path == "/health":

            self.send_json(
                200,
                {
                    "status": "ok"
                }
            )

            return


        self.send_json(
            404,
            {
                "error": "Not found"
            }
        )


    def do_POST(self):

        if self.path != "/api/chat":

            self.send_json(
                404,
                {
                    "error": "Not found"
                }
            )

            return


        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    0
                )
            )

            raw = self.rfile.read(length)

            data = json.loads(
                raw.decode("utf-8")
            )

        except Exception:

            self.send_json(
                400,
                {
                    "error":
                        "Некорректный JSON"
                }
            )

            return


        user_text = str(
            data.get(
                "message",
                ""
            )
        ).strip()


        if not user_text:

            self.send_json(
                400,
                {
                    "error":
                        "Пустое сообщение"
                }
            )

            return


        model_key = data.get(
            "model",
            "gpt"
        )


        if model_key not in MODELS:

            self.send_json(
                400,
                {
                    "error":
                        "Неизвестная модель"
                }
            )

            return


        model = MODELS[model_key]

        api_key = API_KEYS.get(model_key)


        if not api_key:

            self.send_json(
                500,
                {
                    "error":
                        "API-ключ для выбранной модели не настроен"
                }
            )

            return


        history = data.get(
            "history",
            []
        )


        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]


        # Если история существует —
        # добавляем последние сообщения.
        if isinstance(history, list):

            for item in history[-20:]:

                if not isinstance(item, dict):
                    continue

                role = item.get("role")
                content = item.get("content")

                if role not in (
                    "user",
                    "assistant"
                ):
                    continue

                if not isinstance(content, str):
                    continue

                if not content.strip():
                    continue

                messages.append(
                    {
                        "role": role,
                        "content": content[:30000]
                    }
                )


        messages.append(
            {
                "role": "user",
                "content": user_text
            }
        )


        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }


        headers = {
            "Authorization":
                f"Bearer {api_key}",

            "Content-Type":
                "application/json",

            "Accept":
                "text/event-stream",

            "Cache-Control":
                "no-cache",

            "X-Request-Id":
                f"site-{os.urandom(8).hex()}"
        }


        try:

            with httpx.Client(
                timeout=httpx.Timeout(
                    connect=30,
                    read=180,
                    write=60,
                    pool=30
                )
            ) as client:

                with client.stream(
                    "POST",
                    f"{API_BASE}/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:

                    if response.status_code >= 400:

                        error_text = response.read().decode(
                            "utf-8",
                            errors="replace"
                        )

                        self.send_json(
                            502,
                            {
                                "error":
                                    f"OdiRouter HTTP {response.status_code}",
                                "details":
                                    error_text[:2000]
                            }
                        )

                        return


                    self.send_response(200)

                    self.send_header(
                        "Content-Type",
                        "text/event-stream; charset=utf-8"
                    )

                    self.send_header(
                        "Cache-Control",
                        "no-cache"
                    )

                    self.send_header(
                        "Connection",
                        "keep-alive"
                    )

                    self.send_header(
                        "Access-Control-Allow-Origin",
                        "*"
                    )

                    self.send_header(
                        "X-Accel-Buffering",
                        "no"
                    )

                    self.end_headers()


                    for line in response.iter_lines():

                        if not line:
                            continue

                        if not line.startswith("data: "):
                            continue

                        data_text = line[6:].strip()


                        if data_text == "[DONE]":

                            self.wfile.write(
                                b"data: [DONE]\n\n"
                            )

                            self.wfile.flush()

                            break


                        try:

                            chunk = json.loads(
                                data_text
                            )

                        except json.JSONDecodeError:

                            continue


                        choices = chunk.get(
                            "choices",
                            []
                        )


                        if choices:

                            delta = choices[0].get(
                                "delta",
                                {}
                            )

                            text = delta.get(
                                "content",
                                ""
                            )


                            if text:

                                event = {
                                    "type": "text",
                                    "text": text
                                }

                                self.wfile.write(
                                    (
                                        "data: " +
                                        json.dumps(
                                            event,
                                            ensure_ascii=False
                                        ) +
                                        "\n\n"
                                    ).encode("utf-8")
                                )

                                self.wfile.flush()


        except Exception as e:

            print(
                "STREAM ERROR:",
                repr(e)
            )

            try:

                self.wfile.write(
                    (
                        "data: " +
                        json.dumps(
                            {
                                "error":
                                    str(e)
                            },
                            ensure_ascii=False
                        ) +
                        "\n\n"
                    ).encode("utf-8")
                )

                self.wfile.flush()

            except Exception:
                pass


    def log_message(
        self,
        format,
        *args
    ):

        print(
            format % args
        )


server = ThreadingHTTPServer(
    ("0.0.0.0", PORT),
    Handler
)


print(
    f"Server started on port {PORT}"
)


server.serve_forever()
