from collections import deque
import logging
from os import PathLike
from pathlib import Path
import typing
import sys
from numcodecs import Blosc

import attrs
import orjson
import h5py
import zarr

from src.flow import Fluid
from src.pipeline.manage import PipelineManager
from src.types import FlowType, PipeConfig, converter
from src.units import Quantity


logger = logging.getLogger(__name__)

is_PYTHON_310_OR_LOWER = sys.version_info < (3, 11)


@attrs.frozen
class FlowStatus:
    fluid: Fluid
    flow_rate: Quantity
    mass_rate: Quantity
    pressure: Quantity
    temperature: Quantity


@attrs.frozen
class PipelineStatus:
    name: str
    flow_type: typing.Union[str, FlowType] = attrs.field(converter=FlowType)
    pipes: typing.List[PipeConfig]
    upstream: FlowStatus
    downstream: FlowStatus
    connector_length: Quantity
    is_leaking: bool
    leak_rate: Quantity
    pressure_drop: Quantity


StatusStreamer = typing.Callable[[PipelineStatus], None]
RateLimitter = typing.Callable[[PipelineManager], bool]
F = typing.TypeVar("F")
Formatter = typing.Callable[[PipelineStatus], F]


def monitor_pipeline(
    manager: PipelineManager,
    streamer: StatusStreamer,
    ratelimitter: typing.Optional[RateLimitter] = None,
) -> typing.Callable[[str, typing.Any], None]:
    """
    Creates a monitor for the pipeline that logs its status using the provided streamer.

    :param manager: The `PipelineManager` instance to monitor.
    :param streamer: A callable that takes a `PipelineStatus` object and writes/logs it to a stream or some sort of persistent storage.
    :param ratelimitter: An optional `RateLimitter` callable to control logging frequency.
    :return: A callable that can be subscribed to pipeline events.
    """

    def _monitor_pipeline(event: str, data: typing.Any) -> None:
        if ratelimitter is not None and not ratelimitter(manager):
            logger.info("Rate limited logging.")
            return

        pipeline = manager.get_pipeline()
        upstream_fluid = pipeline.upstream_fluid
        upstream_status = FlowStatus(
            fluid=upstream_fluid,
            flow_rate=pipeline.inlet_flow_rate,
            mass_rate=pipeline.inlet_mass_rate,
            pressure=pipeline.upstream_pressure,
            temperature=pipeline.upstream_temperature,
        )

        downstream_fluid = pipeline.downstream_fluid or upstream_fluid
        downstream_status = FlowStatus(
            fluid=downstream_fluid,
            flow_rate=pipeline.outlet_flow_rate,
            mass_rate=pipeline.outlet_mass_rate,
            pressure=pipeline.downstream_pressure,
            temperature=pipeline.downstream_temperature,
        )
        pipeline_status = PipelineStatus(
            name=pipeline.name,
            flow_type=pipeline.flow_type,
            pipes=manager.get_pipe_configs(),
            upstream=upstream_status,
            downstream=downstream_status,
            connector_length=pipeline.connector_length,
            is_leaking=pipeline.is_leaking,
            leak_rate=pipeline.leak_rate,
            pressure_drop=pipeline.pressure_drop,
        )
        logger.info("Logging pipeline status...")
        streamer(pipeline_status)

    manager.subscribe("*", _monitor_pipeline)
    return _monitor_pipeline


def interval_ratelimitter(interval: int) -> RateLimitter:
    """
    Creates a rate limiter that allows logging every `interval` calls.

    :param interval: The number of calls between allowed logs.
    :return: A `RateLimitter` callable.
    """
    counter = 0

    def _ratelimitter(manager: PipelineManager) -> bool:
        nonlocal counter
        counter += 1
        if counter >= interval:
            counter = 0
            return True
        return False

    return _ratelimitter


class BaseFileStreamer(typing.Generic[F]):
    """Base class for streaming pipeline status to a file."""

    def __init__(
        self,
        filepath: typing.Union[str, PathLike],
        formatter: typing.Optional[Formatter[F]] = None,
        batch_size: typing.Optional[int] = None,
    ) -> None:
        """
        Initializes the file streamer.

        :param filepath: The path to the file where the status will be streamed.
        :param formatter: An optional formatter to convert `PipelineStatus` to type `F`.
        :param batch_size: An optional batch size for buffering statuses before writing.
        """
        self.filepath = Path(filepath)
        base_path = self.filepath.parent
        base_path.mkdir(mode=0o777, parents=True, exist_ok=True)
        self.filepath.touch(mode=0o777, exist_ok=True)
        self.formatter = formatter
        self.batch_size = batch_size
        self._queue: typing.Deque[PipelineStatus] = deque()

    def __call__(self, status: PipelineStatus) -> None:
        """Streams the given pipeline status to the file."""
        if self.batch_size is not None:
            self._queue.append(status)
            if len(self._queue) >= self.batch_size:
                self._flush()

        elif self.formatter is not None:
            formatted = self.formatter(status)
            self.write([formatted])
        else:
            self.write([status])

    def read(self) -> bytes:
        """
        Reads the current contents of the file.

        :return: The contents of the file as bytes.
        """
        if not self.filepath.exists():
            return b""

        with self.filepath.open("rb") as f:
            f.seek(0)
            return f.read()

    def write(self, data: typing.Sequence[typing.Union[F, PipelineStatus]]) -> None:
        """Writes the given data to the file. Must be implemented by subclasses."""
        raise NotImplementedError

    def _flush(self) -> None:
        """Flushes the queued pipeline statuses to the file."""
        if not self._queue:
            return
        batch = list(self._queue)
        if self.formatter is not None:
            formatted = [self.formatter(status) for status in batch]
            self.write(formatted)
        else:
            self.write(batch)
        self._queue.clear()

    def shutdown(self) -> None:
        """Flushes any remaining data in the queue to the file."""
        # Flush any remaining data in the queue
        self._flush()


class JsonFileStreamer(BaseFileStreamer[typing.Dict[str, typing.Any]]):
    """Streams pipeline status as JSON to a file as an array of objects."""

    def write(
        self,
        data: typing.Sequence[
            typing.Union[typing.Dict[str, typing.Any], PipelineStatus]
        ],
    ) -> None:
        """
        Writes the given data to the file as JSON.

        :param data: A sequence of `PipelineStatus` objects or dictionaries to write.
        """
        serializable_data = []
        for item in data:
            if isinstance(item, PipelineStatus):
                item_dict = converter.unstructure(item)
                serializable_data.append(item_dict)
            else:
                serializable_data.append(item)

        existing_data = self.read()
        with self.filepath.open("wb") as f:
            if existing_data:
                loaded_existing = orjson.loads(existing_data)
                if isinstance(loaded_existing, list):
                    serializable_data = loaded_existing + serializable_data
                else:
                    raise ValueError(
                        f"Existing data in file {self.filepath} is not a JSON array."
                    )
            f.write(orjson.dumps(serializable_data, option=orjson.OPT_INDENT_2))


class ZarrV2Streamer(BaseFileStreamer[PipelineStatus]):
    """Streams pipeline status to a Zarr v2 directory store."""

    def __init__(
        self,
        filepath: typing.Union[str, PathLike],
        formatter: typing.Optional[Formatter[F]] = None,
        batch_size: typing.Optional[int] = None,
    ) -> None:
        """
        Initializes the Zarr v2 streamer.

        :param filepath: The path to the directory where the Zarr store will be created.
        :param formatter: An optional formatter to convert `PipelineStatus` to type `F`.
        :param batch_size: An optional batch size for buffering statuses before writing.
        """
        self.filepath = Path(filepath)
        if not self.filepath.is_dir():
            raise ValueError(f"Zarr v2 store must be a directory. Got: {self.filepath}")

        self.filepath.mkdir(mode=0o777, parents=True, exist_ok=True)
        self.formatter = formatter
        self.batch_size = batch_size
        self._queue: typing.Deque[PipelineStatus] = deque()

    def write(
        self,
        data: typing.Sequence[PipelineStatus],
    ) -> None:
        """
        Writes the given data to the Zarr file.

        :param data: A sequence of `PipelineStatus` objects to write.
        """
        root = zarr.open(store=self.filepath, mode="a", zarr_version=2)

        if "pipeline_status" not in root:
            if is_PYTHON_310_OR_LOWER:
                compressor = Blosc(cname="zstd", clevel=3, shuffle=Blosc.BITSHUFFLE)
            else:
                from zarr.codecs.blosc import BloscCodec, BloscShuffle

                compressor = BloscCodec(
                    cname="zstd", clevel=3, shuffle=BloscShuffle.bitshuffle
                )

            pipeline_status_array = root.create_group("pipeline_status")  # type: ignore
            pipeline_status_array.create_dataset(
                "data",
                shape=(0,),
                maxshape=(None,),
                dtype=h5py.special_dtype(vlen=str) if is_PYTHON_310_OR_LOWER else str,
                chunks=(1,),
                compressor=compressor,
            )
        else:
            pipeline_status_array = root["pipeline_status"]["data"]  # type: ignore

        if not isinstance(pipeline_status_array, zarr.Array):
            raise ValueError(
                f"Expected 'pipeline_status/data' to be a Zarr Array, got {type(pipeline_status_array)}"
            )

        for status in data:
            status_json = orjson.dumps(converter.unstructure(status)).decode("utf-8")
            current_size = pipeline_status_array.shape[0]
            pipeline_status_array.resize((current_size + 1,))
            pipeline_status_array[current_size] = status_json

    def read(self) -> bytes:
        """
        Reads the current contents of the Zarr file.

        :return: The contents of the Zarr file as bytes.
        """
        if not self.filepath.exists():
            return b""

        root = zarr.open(store=self.filepath, mode="r", zarr_version=2)
        if "pipeline_status" not in root:
            return b""

        pipeline_status_array = root["pipeline_status"]["data"]  # type: ignore
        if not isinstance(pipeline_status_array, zarr.Array):
            return b""

        all_data = []
        for i in range(pipeline_status_array.shape[0]):
            all_data.append(pipeline_status_array[i])

        return orjson.dumps(all_data)


class HDF5FileStreamer(BaseFileStreamer[PipelineStatus]):
    """Streams pipeline status to an HDF5 file."""

    def write(
        self,
        data: typing.Sequence[PipelineStatus],
    ) -> None:
        """
        Writes the given data to the HDF5 file.

        :param data: A sequence of `PipelineStatus` objects to write.
        """
        with h5py.File(self.filepath, "a") as hdf5_file:
            if "pipeline_status" not in hdf5_file:
                dt = h5py.special_dtype(vlen=str)
                pipeline_status_dataset = hdf5_file.create_dataset(
                    "pipeline_status",
                    shape=(0,),
                    maxshape=(None,),
                    dtype=dt,
                    chunks=True,
                    compression="gzip",
                    compression_opts=4,
                )
            else:
                pipeline_status_dataset = hdf5_file["pipeline_status"]

            for status in data:
                status_json = orjson.dumps(converter.unstructure(status)).decode(
                    "utf-8"
                )
                current_size = pipeline_status_dataset.shape[0]  # type: ignore
                pipeline_status_dataset.resize((current_size + 1,))  # type: ignore
                pipeline_status_dataset[current_size] = status_json  # type: ignore

            hdf5_file.flush()

    def read(self) -> bytes:
        """
        Reads the current contents of the HDF5 file.

        :return: The contents of the HDF5 file as bytes.
        """
        if not self.filepath.exists():
            return b""

        with h5py.File(self.filepath, "r") as hdf5_file:
            if "pipeline_status" not in hdf5_file:
                return b""

            pipeline_status_dataset = hdf5_file["pipeline_status"]
            all_data = []
            for i in range(pipeline_status_dataset.shape[0]):  # type: ignore
                all_data.append(pipeline_status_dataset[i])  # type: ignore

            return orjson.dumps(all_data)
