import pytest
from mock import MagicMock, AsyncMock, call

from randovania.game_connection.connection_backend import MemoryOperation
from randovania.game_connection.connection_base import ConnectionStatus
from randovania.game_connection.nintendont_backend import NintendontBackend, SocketHolder


@pytest.fixture(name="backend")
def dolphin_backend():
    backend = NintendontBackend("localhost")
    return backend


@pytest.mark.asyncio
async def test_perform_memory_operations(backend):
    backend._socket = MagicMock()
    backend._socket.max_input = 120
    backend._socket.max_output = 100
    backend._socket.max_addresses = 8
    backend._socket.writer.drain = AsyncMock()
    backend._socket.reader.read = AsyncMock(side_effect=[
        b"\x03" + b"A" * 50 + b"B" * 30,
        b"\x01" + b"C" * 50,
    ])

    # Run
    result = await backend._perform_memory_operations([
        MemoryOperation(0x1000, read_byte_count=50),
        MemoryOperation(0x1000, offset=10, read_byte_count=30, write_bytes=b"1" * 30),
        MemoryOperation(0x1000, read_byte_count=50),
        MemoryOperation(0x2000, read_byte_count=10),
        MemoryOperation(0x2000, read_byte_count=10),
    ])

    # Assert
    backend._socket.writer.drain.assert_has_awaits([call(), call()])
    backend._socket.writer.write.assert_has_calls([
        call(b'\x00\x02\x01\x01\x00\x00\x10\x00' + b'\x80\x32' + b'\xd0\x1e\x00\n' + (b"1" * 30)),
        call(b'\x00\x03\x02\x01\x00\x00\x10\x00\x00\x00\x20\x00' + b'\x80\x32' + b'\x81\x0A' + b'\x81\x0A'),
    ])
    assert result == [b"A" * 50, b"B" * 30, b"C" * 50, None, None]
    backend._socket.reader.read.assert_has_awaits([call(1024), call(1024)])


@pytest.mark.asyncio
async def test_connect(backend, mocker):
    reader, writer = MagicMock(), MagicMock()
    writer.drain = AsyncMock()
    reader.read = AsyncMock(return_value=b'\x00\x00\x00\x02\x00\x00\x00x\x00\x00\x00\xfa\x00\x00\x00\x03')
    mock_open = mocker.patch("asyncio.open_connection", new_callable=AsyncMock, return_value=(reader, writer))

    # Run
    await backend._connect()

    # Assert
    mock_open.assert_awaited_once_with("localhost", backend._port)
    writer.drain.assert_awaited_once_with()

    socket: SocketHolder = backend._socket
    assert socket.reader is reader
    assert socket.writer is writer
    assert socket.api_version == 2
    assert socket.max_input == 120
    assert socket.max_output == 250
    assert socket.max_addresses == 3


def test_current_status_disconnected(backend):
    backend._socket = None
    assert backend.current_status == ConnectionStatus.Disconnected


def test_current_status_wrong_game(backend):
    backend._socket = True
    assert backend.current_status == ConnectionStatus.UnknownGame


def test_current_status_not_in_game(backend):
    backend._socket = True
    backend.patches = True
    assert backend.current_status == ConnectionStatus.TitleScreen


def test_current_status_tracker_only(backend):
    backend._socket = True
    backend.patches = True
    backend._world = True
    assert backend.current_status == ConnectionStatus.TrackerOnly


def test_current_status_in_game(backend):
    backend._socket = True
    backend.patches = True
    backend._world = True
    backend.checking_for_collected_index = True
    assert backend.current_status == ConnectionStatus.InGame
