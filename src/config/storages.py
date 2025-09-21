import typing
import orjson
import logging
import redis
from pathlib import Path
from nicegui import App

logger = logging.getLogger(__name__)

__all__ = ["InMemoryStorage", "UserSessionStorage", "JSONFileStorage"]


class InMemoryStorage:
    """In-memory storage backend for configurations"""

    def __init__(self, defaults: typing.Optional[dict] = None):
        self._store: typing.Dict[str, dict] = defaults or {}

    def read(self, id: str) -> typing.Optional[dict]:
        """Read configuration by id"""
        return self._store.get(id)

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        if id not in self._store:
            raise KeyError(f"Configuration with id '{id}' does not exist.")
        if overwrite:
            self._store[id] = data
        else:
            self._store[id].update(data)

    def create(self, id: str, data: dict) -> None:
        if id in self._store:
            raise KeyError(f"Configuration with id '{id}' already exists.")
        self._store[id] = data

    def delete(self, id: str) -> None:
        if id in self._store:
            del self._store[id]
        else:
            raise KeyError(f"Configuration with id '{id}' does not exist.")


class UserSessionStorage:
    """Session storage backend for configurations using NiceGUI's app storage"""

    def __init__(self, app: App, session_key: str = "pipeline-scada"):
        self.app = app
        self.session_key = session_key
        if not hasattr(app, "storage"):
            raise ValueError("App does not support storage backend.")
        self.app.storage.user[self.session_key] = {}

    def read(self, id: str) -> typing.Optional[dict]:
        try:
            return self.app.storage.user[self.session_key].get(id)
        except Exception as e:
            logger.error(f"Failed to read session storage for id '{id}': {e}")
            return None

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        try:
            if id not in self.app.storage.user[self.session_key]:
                raise KeyError(f"Configuration with id '{id}' does not exist.")
            if overwrite:
                self.app.storage.user[self.session_key][id] = data
            else:
                self.app.storage.user[self.session_key][id].update(data)
        except Exception as e:
            logger.error(f"Failed to update session storage for id '{id}': {e}")
            raise

    def create(self, id: str, data: dict) -> None:
        try:
            if id in self.app.storage.user[self.session_key]:
                raise KeyError(f"Configuration with id '{id}' already exists.")
            self.app.storage.user[self.session_key][id] = data
        except Exception as e:
            logger.error(f"Failed to create session storage for id '{id}': {e}")
            raise

    def delete(self, id: str) -> None:
        try:
            if id in self.app.storage.user[self.session_key]:
                del self.app.storage.user[self.session_key][id]
            else:
                raise KeyError(f"Configuration with id '{id}' does not exist.")
        except Exception as e:
            logger.error(f"Failed to delete session storage for id '{id}': {e}")
            raise


class BrowserLocalStorage:
    """Browser local storage backend for configurations using NiceGUI's app storage"""

    def __init__(self, app: App, storage_key: str = "pipeline-scada"):
        self.app = app
        self.storage_key = storage_key
        if not hasattr(app, "storage"):
            raise ValueError("App does not support storage backend.")
        self.app.storage.browser[self.storage_key] = {}

    def read(self, id: str) -> typing.Optional[dict]:
        try:
            return self.app.storage.browser[self.storage_key].get(id)
        except Exception as e:
            logger.error(f"Failed to read local storage for id '{id}': {e}")
            return None

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        try:
            if id not in self.app.storage.browser[self.storage_key]:
                raise KeyError(f"Configuration with id '{id}' does not exist.")
            if overwrite:
                self.app.storage.browser[self.storage_key][id] = data
            else:
                self.app.storage.browser[self.storage_key][id].update(data)
        except Exception as e:
            logger.error(f"Failed to update local storage for id '{id}': {e}")
            raise

    def create(self, id: str, data: dict) -> None:
        try:
            if id in self.app.storage.browser[self.storage_key]:
                raise KeyError(f"Configuration with id '{id}' already exists.")
            self.app.storage.browser[self.storage_key][id] = data
        except Exception as e:
            logger.error(f"Failed to create local storage for id '{id}': {e}")
            raise

    def delete(self, id: str) -> None:
        try:
            if id in self.app.storage.browser[self.storage_key]:
                del self.app.storage.browser[self.storage_key][id]
            else:
                raise KeyError(f"Configuration with id '{id}' does not exist.")
        except Exception as e:
            logger.error(f"Failed to delete local storage for id '{id}': {e}")
            raise


class JSONFileStorage:
    """JSON file storage backend for configurations"""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, id: str) -> Path:
        return self.config_dir / f"{id}_config.json"

    def read(self, id: str) -> typing.Optional[dict]:
        file_path = self._get_file_path(id)
        if not file_path.exists():
            return None
        try:
            with open(file_path, "rb") as f:
                return orjson.loads(f.read())
        except Exception as e:
            logger.error(f"Failed to read configuration file '{file_path}': {e}")
            return None

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        file_path = self._get_file_path(id)
        if not file_path.exists():
            raise KeyError(f"Configuration with id '{id}' does not exist.")
        try:
            if overwrite:
                with open(file_path, "wb") as f:
                    f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
            else:
                existing_data = self.read(id) or {}
                existing_data.update(data)
                with open(file_path, "wb") as f:
                    f.write(orjson.dumps(existing_data, option=orjson.OPT_INDENT_2))
        except Exception as e:
            logger.error(f"Failed to update configuration file '{file_path}': {e}")
            raise

    def create(self, id: str, data: dict) -> None:
        file_path = self._get_file_path(id)
        try:
            with open(file_path, "wb") as f:
                f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        except Exception as e:
            logger.error(f"Failed to create configuration file '{file_path}': {e}")
            raise

    def delete(self, id: str) -> None:
        file_path = self._get_file_path(id)
        if not file_path.exists():
            raise KeyError(f"Configuration with id '{id}' does not exist.")
        try:
            file_path.unlink()
        except Exception as e:
            logger.error(f"Failed to delete configuration file '{file_path}': {e}")
            raise


class HybridStorage:
    """Hybrid storage backend combining JSON file storage and browser local storage."""

    def __init__(
        self,
        json_storage: JSONFileStorage,
        browser_storage: BrowserLocalStorage,
        dump_freq: int = 10,
    ):
        self.json_storage = json_storage
        self.browser_storage = browser_storage
        self.dump_freq = dump_freq
        self._operation_count = 0

    def read(self, id: str) -> typing.Optional[dict]:
        data = self.browser_storage.read(id)
        if data is not None:
            return data

        data = self.json_storage.read(id)
        if data is not None:
            try:
                self.browser_storage.create(id, data)
            except KeyError:
                self.browser_storage.update(id, data, overwrite=True)
        return data

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        self.browser_storage.update(id, data, overwrite)
        self._operation_count += 1
        if self._operation_count >= self.dump_freq:
            self.dump(id)
            self._operation_count = 0

    def create(self, id: str, data: dict) -> None:
        self.browser_storage.create(id, data)
        self._operation_count += 1
        if self._operation_count >= self.dump_freq:
            self.dump(id)
            self._operation_count = 0

    def delete(self, id: str) -> None:
        self.browser_storage.delete(id)
        try:
            self.json_storage.delete(id)
        except KeyError:
            pass

    def dump(self, id: str) -> None:
        data = self.browser_storage.read(id)
        if data is not None:
            try:
                self.json_storage.update(id, data, overwrite=True)
            except KeyError:
                self.json_storage.create(id, data)

    def flush(self) -> None:
        """Force dump all browser storage data to file storage"""
        for id in self.browser_storage.app.storage.browser.get(
            self.browser_storage.storage_key, {}
        ):
            self.dump(id)
        self._operation_count = 0


class RedisStorage:
    """Redis storage backend for configurations"""

    def __init__(self, client: redis.Redis):
        self.client = client

    def read(self, id: str) -> typing.Optional[dict]:
        data = self.client.get(id)
        if data is None:
            return None
        return orjson.loads(data)

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        if not self.client.exists(id):
            raise KeyError(f"Configuration with id '{id}' does not exist.")
        if overwrite:
            self.client.set(id, orjson.dumps(data, option=orjson.OPT_INDENT_2))
            return
        existing_data = self.read(id) or {}
        existing_data.update(data)
        self.client.set(id, orjson.dumps(existing_data, option=orjson.OPT_INDENT_2))

    def create(self, id: str, data: dict) -> None:
        if self.client.exists(id):
            raise KeyError(f"Configuration with id '{id}' already exists.")
        self.client.set(id, orjson.dumps(data, option=orjson.OPT_INDENT_2))

    def delete(self, id: str) -> None:
        if not self.client.exists(id):
            raise KeyError(f"Configuration with id '{id}' does not exist.")
        self.client.delete(id)
