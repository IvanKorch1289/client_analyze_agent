"""
FastStream worker (RabbitMQ listener).

Запуск (пример):
    python -m app.messaging.worker
"""

from __future__ import annotations

import asyncio
import pathlib

from faststream import FastStream

from app.messaging.broker import broker

app = FastStream(broker)

_HEARTBEAT_PATH = pathlib.Path("/tmp/worker_heartbeat")


async def _heartbeat_loop() -> None:
    """Периодически обновляет heartbeat-файл для Docker healthcheck."""
    while True:
        try:
            _HEARTBEAT_PATH.touch()
        except OSError:
            pass
        await asyncio.sleep(10)


@app.on_startup
async def _start_heartbeat() -> None:
    asyncio.create_task(_heartbeat_loop())


def main() -> None:
    # Важно: это long-lived процесс (воркер).
    # app.run() внутри обрабатывает event loop, warning можно игнорировать
    _ = app.run()  # type: ignore


if __name__ == "__main__":
    main()
