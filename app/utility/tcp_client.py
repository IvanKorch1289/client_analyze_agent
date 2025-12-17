import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.utility.logging_client import logger


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class TCPClientConfig:
    host: str = "localhost"
    port: int = 9000
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    reconnect_attempts: int = -1
    connection_timeout: float = 10.0
    read_timeout: float = 30.0
    heartbeat_interval: float = 30.0
    buffer_size: int = 65536


@dataclass
class MessageMetrics:
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    failed_sends: int = 0
    reconnections: int = 0
    last_sent_time: Optional[float] = None
    last_received_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "failed_sends": self.failed_sends,
            "reconnections": self.reconnections,
            "last_sent_time": self.last_sent_time,
            "last_received_time": self.last_received_time,
        }


class TCPMessageClient:
    def __init__(self, config: Optional[TCPClientConfig] = None):
        self.config = config or TCPClientConfig()
        self._state = ConnectionState.DISCONNECTED
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._response_handlers: Dict[str, Callable] = {}
        self._metrics = MessageMetrics()
        self._lock = asyncio.Lock()
        self._send_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._current_reconnect_delay = self.config.reconnect_delay

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def metrics(self) -> MessageMetrics:
        return self._metrics

    async def connect(self) -> bool:
        if self._state == ConnectionState.CONNECTED:
            return True

        async with self._lock:
            self._state = ConnectionState.CONNECTING
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.config.host, self.config.port),
                    timeout=self.config.connection_timeout,
                )
                self._state = ConnectionState.CONNECTED
                self._current_reconnect_delay = self.config.reconnect_delay
                logger.info(
                    f"[TCP] Connected to {self.config.host}:{self.config.port}",
                    component="tcp_client",
                )
                
                if not self._running:
                    self._running = True
                    self._send_task = asyncio.create_task(self._send_loop())
                    self._receive_task = asyncio.create_task(self._receive_loop())
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
                return True
            except asyncio.TimeoutError:
                logger.error(
                    f"[TCP] Connection timeout to {self.config.host}:{self.config.port}",
                    component="tcp_client",
                )
                self._state = ConnectionState.DISCONNECTED
                return False
            except ConnectionRefusedError:
                logger.error(
                    f"[TCP] Connection refused to {self.config.host}:{self.config.port}",
                    component="tcp_client",
                )
                self._state = ConnectionState.DISCONNECTED
                return False
            except Exception as e:
                logger.error(
                    f"[TCP] Connection error: {e}",
                    component="tcp_client",
                )
                self._state = ConnectionState.DISCONNECTED
                return False

    async def disconnect(self):
        async with self._lock:
            self._running = False
            
            if self._send_task:
                self._send_task.cancel()
                try:
                    await self._send_task
                except asyncio.CancelledError:
                    pass

            if self._receive_task:
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass

            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

            if self._writer:
                self._writer.close()
                try:
                    await self._writer.wait_closed()
                except Exception:
                    pass

            self._reader = None
            self._writer = None
            self._state = ConnectionState.DISCONNECTED
            logger.info("[TCP] Disconnected", component="tcp_client")

    async def _reconnect(self):
        if self._state == ConnectionState.RECONNECTING:
            return

        self._state = ConnectionState.RECONNECTING
        attempts = 0

        while self._running:
            if self.config.reconnect_attempts > 0 and attempts >= self.config.reconnect_attempts:
                logger.error(
                    f"[TCP] Max reconnection attempts ({self.config.reconnect_attempts}) reached",
                    component="tcp_client",
                )
                self._state = ConnectionState.DISCONNECTED
                return

            attempts += 1
            self._metrics.reconnections += 1

            logger.info(
                f"[TCP] Reconnecting... attempt {attempts}",
                component="tcp_client",
            )

            if await self.connect():
                return

            await asyncio.sleep(self._current_reconnect_delay)
            self._current_reconnect_delay = min(
                self._current_reconnect_delay * 2,
                self.config.max_reconnect_delay,
            )

    async def send_message(self, message: Dict[str, Any], wait_response: bool = False) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            logger.warning("[TCP] Not connected, message queued", component="tcp_client")
            await self._message_queue.put(message)
            return None

        try:
            message_bytes = (json.dumps(message) + "\n").encode("utf-8")
            self._writer.write(message_bytes)
            await self._writer.drain()

            self._metrics.messages_sent += 1
            self._metrics.bytes_sent += len(message_bytes)
            self._metrics.last_sent_time = time.time()

            logger.debug(
                f"[TCP] Message sent: {len(message_bytes)} bytes",
                component="tcp_client",
            )

            if wait_response:
                try:
                    response_data = await asyncio.wait_for(
                        self._reader.readline(),
                        timeout=self.config.read_timeout,
                    )
                    if response_data:
                        self._metrics.messages_received += 1
                        self._metrics.bytes_received += len(response_data)
                        self._metrics.last_received_time = time.time()
                        return json.loads(response_data.decode("utf-8"))
                except asyncio.TimeoutError:
                    logger.warning("[TCP] Response timeout", component="tcp_client")
                    return None

            return {"status": "sent"}

        except (ConnectionResetError, BrokenPipeError) as e:
            logger.error(f"[TCP] Connection lost: {e}", component="tcp_client")
            self._metrics.failed_sends += 1
            self._state = ConnectionState.DISCONNECTED
            await self._message_queue.put(message)
            if self._running:
                asyncio.create_task(self._reconnect())
            return None
        except Exception as e:
            logger.error(f"[TCP] Send error: {e}", component="tcp_client")
            self._metrics.failed_sends += 1
            return None

    async def send_message_async(self, message: Dict[str, Any]):
        await self._message_queue.put(message)

    async def _send_loop(self):
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0,
                )
                if self.is_connected:
                    await self.send_message(message)
                else:
                    await self._message_queue.put(message)
                    await asyncio.sleep(0.5)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TCP] Send loop error: {e}", component="tcp_client")

    async def _receive_loop(self):
        while self._running:
            if not self.is_connected or not self._reader:
                await asyncio.sleep(0.5)
                continue

            try:
                data = await asyncio.wait_for(
                    self._reader.readline(),
                    timeout=self.config.heartbeat_interval + 10,
                )
                if not data:
                    logger.warning("[TCP] Connection closed by server", component="tcp_client")
                    self._state = ConnectionState.DISCONNECTED
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    continue

                self._metrics.messages_received += 1
                self._metrics.bytes_received += len(data)
                self._metrics.last_received_time = time.time()

                try:
                    message = json.loads(data.decode("utf-8"))
                    msg_type = message.get("type", "unknown")
                    if msg_type in self._response_handlers:
                        await self._response_handlers[msg_type](message)
                except json.JSONDecodeError:
                    logger.warning(
                        f"[TCP] Invalid JSON received: {data[:100]}",
                        component="tcp_client",
                    )

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TCP] Receive loop error: {e}", component="tcp_client")
                self._state = ConnectionState.DISCONNECTED
                if self._running:
                    asyncio.create_task(self._reconnect())

    async def _heartbeat_loop(self):
        while self._running:
            await asyncio.sleep(self.config.heartbeat_interval)
            if self.is_connected:
                await self.send_message({"type": "heartbeat", "timestamp": time.time()})

    async def start(self):
        if self._running:
            return

        self._running = True
        await self.connect()

        self._send_task = asyncio.create_task(self._send_loop())
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info("[TCP] Client started", component="tcp_client")

    async def stop(self):
        self._running = False
        await self.disconnect()
        logger.info("[TCP] Client stopped", component="tcp_client")

    def register_handler(self, message_type: str, handler: Callable):
        self._response_handlers[message_type] = handler

    def unregister_handler(self, message_type: str):
        self._response_handlers.pop(message_type, None)


_tcp_client: Optional[TCPMessageClient] = None


async def get_tcp_client(config: Optional[TCPClientConfig] = None) -> TCPMessageClient:
    global _tcp_client
    if _tcp_client is None:
        _tcp_client = TCPMessageClient(config)
    return _tcp_client


async def send_async_message(message: Dict[str, Any], wait_response: bool = False) -> Optional[Dict[str, Any]]:
    client = await get_tcp_client()
    if not client.is_connected:
        await client.connect()
    return await client.send_message(message, wait_response=wait_response)
