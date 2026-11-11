"""개발용 테스트 페이지: 브라우저에서 질문을 넣고 RagResponse를 그대로 확인한다.

정식 프론트엔드/API가 아니다. 표준 라이브러리 http.server로 로컬에서만 띄운다.
화면이 이전 질문들을 함께 보내므로 "케이스는요?" 같은 후속 질문도 시험할 수 있다.

사용법 (backend/ 에서, 처음 한 번은 인덱싱 먼저):
    uv run python -m rag.indexer --config configs/rag/default.yaml
    uv run python ../eval/playground.py --config configs/rag/default.yaml
    → http://127.0.0.1:8765
"""

import argparse
import asyncio
import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from common import close_impl, load_impl, load_run_info

from rag.schemas import RagSystem

HTML_PATH = Path(__file__).resolve().parent / "playground.html"
MAX_QUESTION_LEN = 500
MAX_HISTORY = 5  # 화면이 보내는 이전 질문 개수 상한 (실제로 몇 개를 쓸지는 설정 history_turns)

logger = logging.getLogger("playground")


def make_handler(
    system: RagSystem, loop: asyncio.AbstractEventLoop, info: dict
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, data: dict) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(HTTPStatus.OK, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/info":
                self._send_json(HTTPStatus.OK, info)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/api/ask":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                question = str(body["question"]).strip()
                history = [str(h)[:MAX_QUESTION_LEN] for h in body.get("history", [])][
                    -MAX_HISTORY:
                ]
            except (ValueError, KeyError, TypeError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "question 필드가 필요합니다"})
                return
            if not question or len(question) > MAX_QUESTION_LEN:
                self._send_json(
                    HTTPStatus.BAD_REQUEST, {"error": f"질문은 1~{MAX_QUESTION_LEN}자여야 합니다"}
                )
                return

            try:
                # 요청 스레드가 여러 개여도 RAG 호출은 전용 이벤트 루프 하나에서만 실행한다
                future = asyncio.run_coroutine_threadsafe(
                    system.aanswer(question, history=history), loop
                )
                response = future.result()
            except Exception as e:
                logger.exception("답변 생성 실패")
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})
                return
            logger.info("[%s] %s", response.mode, question)
            self._send_json(HTTPStatus.OK, response.model_dump())

        def log_message(self, format: str, *args: object) -> None:
            pass  # 요청마다 찍히는 기본 접근 로그 대신 위의 logger.info만 남긴다

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="개발용 테스트 페이지")
    parser.add_argument("--impl", default="rag.pipeline:create")
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    run_info = load_run_info(args.impl, args.config, "-")
    info = {k: run_info[k] for k in ("run", "config_path", "embedding_model", "llm_model")}
    info["config"] = run_info["config"]

    system = load_impl(args.impl, args.config)
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    # 브라우저가 미리 열어 두는 빈 연결에 막히지 않도록 요청마다 스레드를 쓴다.
    # 외부에서 접근하지 못하도록 로컬호스트에만 연다
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(system, loop, info))
    logger.info("[%s] http://127.0.0.1:%d (종료: Ctrl+C)", info["run"], args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join()
        close_impl(system)
        loop.close()


if __name__ == "__main__":
    main()
