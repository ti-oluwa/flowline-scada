"""
Application storage backends.
"""

import hashlib
import logging
from pathlib import Path
import typing

from nicegui import App
import orjson
import redis


logger = logging.getLogger(__name__)

__all__ = [
    "StorageBackend",
    "InMemoryStorage",
    "UserSessionStorage",
    "JSONFileStorage",
    "HybridBrowserStorage",
    "RedisStorage",
]


class StorageBackend:
    """Base storage backend interface"""

    def __init__(self, namespace: str):
        self.namespace = namespace

    def get_key(self, key: str, *args, **kwargs) -> str:
        base_key = f"{self.namespace}:{key}"
        if args or kwargs:
            hash_input = str(args) + str(sorted(kwargs.items()))
            hash_suffix = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
            return f"{base_key}:{hash_suffix}"
        return base_key

    def read(self, key: str) -> typing.Optional[dict]:
        raise NotImplementedError

    def update(self, key: str, data: dict, overwrite: bool = False) -> None:
        raise NotImplementedError

    def create(self, key: str, data: dict) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class InMemoryStorage(StorageBackend):
    """In-memory storage backend"""

    def __init__(
        self,
        namespace: str,
        *,
        defaults: typing.Optional[dict] = None,
    ):
        self._store: typing.Dict[str, dict] = defaults or {}
        super().__init__(namespace)

    def read(self, key: str) -> typing.Optional[dict]:
        """Read entry by key"""
        logger.debug(f"Reading entry for key: {key}")
        return self._store.get(key)

    def update(self, key: str, data: dict, overwrite: bool = False) -> None:
        """Update entry by key"""
        logger.debug(f"Updating entry for key: {key} with data: {data}")
        if key not in self._store:
            raise KeyError(f"Entry with key '{key}' does not exist.")
        if overwrite:
            self._store[key] = data
            return
        self._store[key].update(data)

    def create(self, key: str, data: dict) -> None:
        """Create new entry by key"""
        logger.debug(f"Creating entry for key: {key} with data: {data}")
        if key in self._store:
            raise KeyError(f"Entry with key '{key}' already exists.")
        self._store[key] = data

    def delete(self, key: str) -> None:
        """Delete entry by key"""

        logger.debug(f"Deleting entry for key: {key}")
        if key in self._store:
            del self._store[key]
            return
        raise KeyError(f"Entry with key '{key}' does not exist.")


class UserSessionStorage(StorageBackend):
    """Session storage backend using NiceGUI's `app.storage.user`"""

    def __init__(self, app: App, session_key: str, namespace: str):
        super().__init__(namespace)
        self.app = app
        self.session_key = session_key
        if not hasattr(app, "storage"):
            raise ValueError("App does not support storage backend.")
        self.app.storage.user[self.session_key] = {}
        logger.debug(
            f"Initialized {self.__class__.__name__} with session_key: {session_key}"
        )

    def read(self, key: str) -> typing.Optional[dict]:
        logger.debug(f"Reading entry for key: {key}")
        return self.app.storage.user[self.session_key].get(key, None)

    def update(self, key: str, data: dict, overwrite: bool = False) -> None:
        logger.debug(f"Updating entry for key: {key} with data: {data}")
        if key not in self.app.storage.user[self.session_key]:
            raise KeyError(f"Entry with key '{key}' does not exist.")

        if overwrite:
            self.app.storage.user[self.session_key][key] = data
            return
        self.app.storage.user[self.session_key][key].update(data)

    def create(self, key: str, data: dict) -> None:
        logger.debug(f"Creating entry for key: {key} with data: {data}")
        if key in self.app.storage.user[self.session_key]:
            raise KeyError(f"Entry with key '{key}' already exists.")
        self.app.storage.user[self.session_key][key] = data

    def delete(self, key: str) -> None:
        logger.debug(f"Deleting entry for key: {key}")
        if key in self.app.storage.user[self.session_key]:
            del self.app.storage.user[self.session_key][key]
            return
        raise KeyError(f"Entry with key '{key}' does not exist.")


class BrowserLocalStorage(StorageBackend):
    """Browser local storage backend using NiceGUI's `app.storage.browser`"""

    def __init__(self, app: App, storage_key: str, namespace: str):
        super().__init__(namespace)
        self.app = app
        self.storage_key = storage_key
        if not hasattr(app, "storage"):
            raise ValueError("App does not support storage backend.")
        self.app.storage.browser[self.storage_key] = {}
        logger.debug(
            f"Initialized {self.__class__.__name__} with storage_key: {storage_key}"
        )

    def read(self, key: str) -> typing.Optional[dict]:
        logger.debug(f"Reading entry for key: {key}")
        return self.app.storage.browser[self.storage_key].get(key, None)

    def update(self, key: str, data: dict, overwrite: bool = False) -> None:
        logger.debug(f"Updating entry for key: {key} with data: {data}")
        if key not in self.app.storage.browser[self.storage_key]:
            raise KeyError(f"Entry with key '{key}' does not exist.")

        if overwrite:
            self.app.storage.browser[self.storage_key][key] = data
            return
        self.app.storage.browser[self.storage_key][key].update(data)

    def create(self, key: str, data: dict) -> None:
        logger.debug(f"Creating entry for key: {key} with data: {data}")
        if key in self.app.storage.browser[self.storage_key]:
            raise KeyError(f"Entry with key '{key}' already exists.")
        self.app.storage.browser[self.storage_key][key] = data

    def delete(self, key: str) -> None:
        logger.debug(f"Deleting entry for key: {key}")
        if key in self.app.storage.browser[self.storage_key]:
            del self.app.storage.browser[self.storage_key][key]
            return
        raise KeyError(f"Entry with key '{key}' does not exist.")


class JSONFileStorage(StorageBackend):
    """JSON file storage backend"""

    def __init__(self, storage_dir: typing.Union[str, Path], namespace: str):
        super().__init__(namespace)
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(
            f"Initialized {self.__class__.__name__} with storage directory: {storage_dir}"
        )

    def _get_file_path(self, key: str) -> Path:
        return self.storage_dir / f"{key}.json"

    def read(self, key: str) -> typing.Optional[dict]:
        logger.debug(f"Reading entry for key: {key}")
        file_path = self._get_file_path(key)
        if not file_path.exists():
            return None

        with file_path.open("rb") as f:
            return orjson.loads(f.read())

    def update(self, key: str, data: dict, overwrite: bool = False) -> None:
        logger.debug(f"Updating entry for key: {key} with data: {data}")
        file_path = self._get_file_path(key)
        if not file_path.exists():
            raise KeyError(f"Entry with key '{key}' does not exist.")

        if overwrite:
            with file_path.open("wb") as f:
                f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        else:
            existing_data = self.read(key) or {}
            existing_data.update(data)
            with file_path.open("wb") as f:
                f.write(orjson.dumps(existing_data, option=orjson.OPT_INDENT_2))

    def create(self, key: str, data: dict) -> None:
        logger.debug(f"Creating entry for key: {key} with data: {data}")
        file_path = self._get_file_path(key)
        with file_path.open("wb") as f:
            f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

    def delete(self, key: str) -> None:
        logger.debug(f"Deleting entry for key: {key}")
        file_path = self._get_file_path(key)
        if not file_path.exists():
            raise KeyError(f"Entry with key '{key}' does not exist.")
        file_path.unlink()


class HybridBrowserStorage:
    """Hybrid storage backend combining browser local storage and another persistent storage."""

    def __init__(
        self,
        browser_storage: BrowserLocalStorage,
        persistent_storage: StorageBackend,
        dump_freq: int = 10,
    ):
        """
        Initialize the hybrid storage.

        :param browser_storage: Instance of `BrowserLocalStorage` for fast access.
        :param persistent_storage: Instance of another storage backend for persistence.
        :param dump_freq: Number of operations after which to dump data to persistent storage.
        """
        self.browser_storage = browser_storage
        self.persistent_storage = persistent_storage
        self.dump_freq = dump_freq
        self._operation_count = 0
        logger.debug(
            f"Initialized {self.__class__.__name__} with dump_freq: {dump_freq}"
        )

    def read(self, key: str) -> typing.Optional[dict]:
        logger.debug(f"Reading entry for key: {key}")
        data = self.browser_storage.read(key)
        if data is not None:
            return data

        data = self.persistent_storage.read(key)
        if data is not None:
            try:
                self.browser_storage.create(key, data)
            except KeyError:
                self.browser_storage.update(key, data, overwrite=True)
        return data

    def update(self, key: str, data: dict, overwrite: bool = False) -> None:
        logger.debug(f"Updating entry for key: {key} with data: {data}")
        self.browser_storage.update(key, data, overwrite)
        self._operation_count += 1
        if self._operation_count >= self.dump_freq:
            self.dump(key)
            self._operation_count = 0

    def create(self, key: str, data: dict) -> None:
        logger.debug(f"Creating entry for key: {key} with data: {data}")
        self.browser_storage.create(key, data)
        self._operation_count += 1
        if self._operation_count >= self.dump_freq:
            self.dump(key)
            self._operation_count = 0

    def delete(self, key: str) -> None:
        logger.debug(f"Deleting entry for key: {key}")
        self.browser_storage.delete(key)
        try:
            self.persistent_storage.delete(key)
        except KeyError:
            pass

    def dump(self, key: str) -> None:
        logger.debug(f"Dumping entry for key: {key} to persistent storage")
        data = self.browser_storage.read(key)
        if data is not None:
            try:
                self.persistent_storage.update(key, data, overwrite=True)
            except KeyError:
                self.persistent_storage.create(key, data)

    def flush(self) -> None:
        """Force dump all browser storage data to file storage"""
        logger.debug("Flushing all browser storage data to persistent storage")
        for key in self.browser_storage.app.storage.browser.get(
            self.browser_storage.storage_key, {}
        ):
            self.dump(key)
        self._operation_count = 0


class RedisStorage(StorageBackend):
    """Redis storage backend"""

    def __init__(self, client: redis.Redis, namespace: str):
        """
        Initialize Redis storage with a Redis client.

        :param client: An instance of `redis.Redis`
        """
        super().__init__(namespace)
        self.client = client
        logger.debug(f"Initialized {self.__class__.__name__} with Redis client")

    def read(self, key: str) -> typing.Optional[dict]:
        logger.debug(f"Reading entry for key: {key}")
        data = self.client.get(key)
        if data is None:
            return None
        return orjson.loads(data)

    def update(self, key: str, data: dict, overwrite: bool = False) -> None:
        logger.debug(f"Updating entry for key: {key} with data: {data}")
        if not self.client.exists(key):
            raise KeyError(f"Entry with key '{key}' does not exist.")
        if overwrite:
            self.client.set(key, orjson.dumps(data, option=orjson.OPT_INDENT_2))
            return
        existing_data = self.read(key) or {}
        existing_data.update(data)
        self.client.set(key, orjson.dumps(existing_data, option=orjson.OPT_INDENT_2))

    def create(self, key: str, data: dict) -> None:
        logger.debug(f"Creating entry for key: {key} with data: {data}")
        if self.client.exists(key):
            raise KeyError(f"Entry with key '{key}' already exists.")
        self.client.set(key, orjson.dumps(data, option=orjson.OPT_INDENT_2))

    def delete(self, key: str) -> None:
        logger.debug(f"Deleting entry for key: {key}")
        if not self.client.exists(key):
            raise KeyError(f"Entry with key '{key}' does not exist.")
        self.client.delete(key)
