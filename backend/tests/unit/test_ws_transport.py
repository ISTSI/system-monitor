"""Real loopback TCP proves the serving WebSocket size and receive-queue bounds."""

import asyncio
import socket
from collections import deque
from contextlib import asynccontextmanager

import uvicorn
from wsproto import ConnectionState, ConnectionType, WSConnection
from wsproto.events import AcceptConnection, CloseConnection, Ping, Request, TextMessage


class Application:
    def __init__(self, *, held=False):
        self.release = asyncio.Event()
        if not held:
            self.release.set()
        self.messages = []
        self.finished = asyncio.Event()

    async def __call__(self, scope, receive, send):
        assert scope["type"] == "websocket"
        assert (await receive())["type"] == "websocket.connect"
        await send({"type": "websocket.accept"})
        try:
            await self.release.wait()
            while True:
                event = await receive()
                if event["type"] == "websocket.disconnect":
                    return
                assert event["type"] == "websocket.receive"
                self.messages.append(event["text"])
                await send({"type": "websocket.send", "text": event["text"]})
        finally:
            self.finished.set()


async def until(predicate):
    async with asyncio.timeout(5):
        while not predicate():  # noqa: ASYNC110 -- The transport exposes state, not an Event.
            await asyncio.sleep(0.005)


class Client:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.connection = WSConnection(ConnectionType.CLIENT)
        self.pending = deque()

    async def send(self, *events):
        self.writer.write(b"".join(self.connection.send(event) for event in events))
        await self.writer.drain()

    async def event(self):
        async with asyncio.timeout(5):
            while not self.pending:
                data = await self.reader.read(65_536)
                self.connection.receive_data(data or None)
                self.pending.extend(self.connection.events())
                if not data and not self.pending:
                    raise AssertionError("The loopback WebSocket closed without a close frame.")
            event = self.pending.popleft()
            if isinstance(event, Ping):
                await self.send(event.response())
                return await self.event()
            if (
                isinstance(event, CloseConnection)
                and self.connection.state == ConnectionState.REMOTE_CLOSING
            ):
                await self.send(event.response())
            return event

    async def text(self):
        parts = []
        while True:
            event = await self.event()
            assert isinstance(event, TextMessage), event
            parts.append(event.data)
            if event.message_finished:
                return "".join(parts)

    async def close(self):
        try:
            if self.connection.state == ConnectionState.OPEN:
                await self.send(CloseConnection(code=1000))
            if self.connection.state == ConnectionState.LOCAL_CLOSING:
                async with asyncio.timeout(2):
                    while not isinstance(await self.event(), CloseConnection):
                        pass
        finally:
            self.writer.close()
            await self.writer.wait_closed()


@asynccontextmanager
async def serving(*, held=False):
    app = Application(held=held)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    listener.setblocking(False)
    address = listener.getsockname()
    # These transport and limit arguments intentionally match inspector.__main__.
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            ws="websockets",
            ws_max_size=16_384,
            ws_max_queue=16,
            access_log=False,
            log_config=None,
            lifespan="off",
            timeout_graceful_shutdown=2,
        )
    )
    running = asyncio.create_task(server.serve(sockets=[listener]))
    protocols = []
    try:
        await until(lambda: server.started or running.done())
        assert server.started
        yield app, server, address, protocols
    finally:
        app.release.set()
        server.should_exit = True
        try:
            async with asyncio.timeout(5):
                await running
        finally:
            listener.close()
            if not running.done():
                running.cancel()
                await asyncio.gather(running, return_exceptions=True)
        assert not server.server_state.connections
        assert not server.server_state.tasks
        for protocol in protocols:
            assert protocol.transfer_data_task.done()
            assert protocol.keepalive_ping_task.done()
            assert protocol.close_connection_task.done()


@asynccontextmanager
async def connected(server, address, protocols):
    reader, writer = await asyncio.open_connection(*address)
    client = Client(reader, writer)
    try:
        await client.send(Request(host=f"{address[0]}:{address[1]}", target="/stream"))
        assert isinstance(await client.event(), AcceptConnection)
        await until(
            lambda: any(hasattr(item, "messages") for item in server.server_state.connections)
        )
        protocol = next(
            item for item in server.server_state.connections if hasattr(item, "messages")
        )
        protocols.append(protocol)
        assert protocol.max_size == 16_384 and protocol.max_queue == 16
        yield client, protocol
    finally:
        await client.close()


async def test_serving_transport_accepts_valid_small_utf8_text_and_cleans_up():
    async with serving() as (app, server, address, protocols):
        async with connected(server, address, protocols) as (client, _):
            await client.send(TextMessage(data="valid Stra\u00dfe"))
            assert await client.text() == "valid Stra\u00dfe"
            assert app.messages == ["valid Stra\u00dfe"]
        await until(app.finished.is_set)


async def test_fragmented_utf8_message_exceeding_cumulative_byte_limit_closes_1009():
    async with serving() as (app, server, address, protocols):
        async with connected(server, address, protocols) as (client, _):
            # Every frame fits; 8,193 Unicode characters total still exceed the
            # 16 KiB message byte budget when their UTF-8 fragments are joined.
            await client.send(
                TextMessage(data="\u00e9" * 4096, message_finished=False),
                TextMessage(data="\u00e9" * 4096, message_finished=False),
                TextMessage(data="\u00e9", message_finished=True),
            )
            closing = await client.event()
            assert isinstance(closing, CloseConnection) and closing.code == 1009
            assert app.messages == []
        await until(app.finished.is_set)
        assert app.messages == []


async def test_coalesced_receive_burst_stops_at_sixteen_and_resumes_after_application_release():
    async with serving(held=True) as (app, server, address, protocols):
        async with connected(server, address, protocols) as (client, protocol):
            expected = [f"bounded-{index:02}" for index in range(64)]
            # One TCP write contains more complete frames than the queue limit.
            await client.send(*(TextMessage(data=text) for text in expected))
            await until(lambda: len(protocol.messages) == 16)
            await until(lambda: protocol._put_message_waiter is not None)
            assert not protocol._put_message_waiter.done()
            assert not protocol.transfer_data_task.done()
            for _ in range(10):
                assert len(protocol.messages) <= 16
                assert not app.messages
                await asyncio.sleep(0.005)
            app.release.set()
            assert [await client.text() for _ in expected] == expected
            await client.send(TextMessage(data="valid-after-release"))
            assert await client.text() == "valid-after-release"
            assert app.messages == [*expected, "valid-after-release"]
            assert len(protocol.messages) <= 16
        await until(app.finished.is_set)
