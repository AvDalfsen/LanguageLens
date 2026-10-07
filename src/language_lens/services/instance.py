"""Per-user local IPC: a second launch reopens the existing Lens window."""
import hashlib
from pathlib import Path

from filelock import FileLock, Timeout

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from language_lens.config import settings_path


class SingleInstance(QObject):
    reopen = Signal()

    def __init__(self, parent=None, *, root: Path | None = None):
        super().__init__(parent)
        root = (root or settings_path().parent).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.name = "LanguageLens-" + hashlib.sha256(str(root).casefold().encode()).hexdigest()[:24]
        self.notified = False
        # OS-owned file lock releases on process death, without PID probing or
        # deleting an endpoint another simultaneous launch has just claimed.
        self._lock = FileLock(str(root / "instance.lock"))
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)

    def _notify(self):
        socket = QLocalSocket(self)
        socket.connectToServer(self.name)
        connected = socket.waitForConnected(500)
        if connected:
            self.notified = True
            socket.write(b"show")
            socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        socket.deleteLater()
        return connected

    def claim(self):
        try:
            self._lock.acquire(timeout=0)
        except Timeout:
            self._notify()
            return False
        if self._notify():
            self._lock.release()
            return False
        if self.server.listen(self.name):
            return True
        # Only remove a stale endpoint after another connection probe; a new
        # concurrent instance may have won the race since the first probe.
        if self._notify():
            self._lock.release()
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self._lock.release()
            raise RuntimeError("Could not claim the local Language Lens instance.")
        return True

    def close(self):
        self.server.close()
        self._lock.release()

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            def read(socket=socket):
                socket.readAll()  # no commands beyond a request to reopen
                self.reopen.emit()
                socket.disconnectFromServer()
            socket.readyRead.connect(read)
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                read()
