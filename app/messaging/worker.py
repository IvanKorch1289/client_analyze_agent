"""
FastStream worker (RabbitMQ listener).

Запуск (пример):
    python -m app.messaging.worker
"""

from __future__ import annotations

from faststream import FastStream

from app.messaging.broker import broker


app = FastStream(broker)


def main() -> None:
    # Важно: это long-lived процесс (воркер).
    app.run()


if __name__ == "__main__":
    main()

