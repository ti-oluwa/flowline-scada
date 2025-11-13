import logging as py_logging
import os
import typing
import sys
import traceback
from typing import TextIO, Optional

from src.types import LoggerLike


def setup_logging(
    log_file: Optional[str] = None,
    console: Optional[TextIO] = sys.stdout,
    base_level: int | str = py_logging.INFO,
    format: Optional[str] = None,
    datefmt: Optional[str] = "%d/%b/%Y %H:%M:%S",
    handlers: Optional[typing.Sequence[py_logging.Handler]] = None,
) -> None:
    """
    Simple interface to set up logging to a file and/or console stream.

    :param log_file: Path to the log file. File will be created if it does not exist.
    :param console: Console stream to log to. Set to None to disable console logging.
    :param base_level: Base log level.
    :param format: Log message format.
    :param datefmt: Date format for log messages.
    :param handlers: Additional logging handlers to add.
    """
    handlers = list(handlers or [])
    if console:
        handlers.append(py_logging.StreamHandler(sys.stdout))

    if log_file:
        if not os.path.exists(log_file):
            os.makedirs(os.path.dirname(log_file), exist_ok=True, mode=0o755)
        handlers.append(py_logging.FileHandler(log_file))

    py_logging.basicConfig(
        level=base_level,
        format=format or "[%(asctime)s] %(message)s",
        datefmt=datefmt,
        handlers=handlers,
    )


def modify_log_level(logger_name: str, level: int | str) -> None:
    """
    Modify the log level of a logger.

    :param logger_name: Name of the logger.
    :param level: Log level to set.
    """
    logger = py_logging.getLogger(logger_name)
    logger.setLevel(level)


def log_message(
    message: str,
    level: typing.Union[int, str] = py_logging.INFO,
    logger: typing.Optional[LoggerLike] = None,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> None:
    """
    Log a message with the specified log level.

    :param message: Message to log.
    :param level: Log level to use.
    :param logger: Optional logger to use. If None, the root logger is used.
    :param args: Additional positional arguments for the log message.
    :param kwargs: Additional keyword arguments for the log message.
    """
    if not isinstance(level, int):
        level = getattr(py_logging, level.upper(), py_logging.INFO)

    logger = logger or py_logging.getLogger(__name__)
    logger.log(int(level), message, *args, **kwargs)


def get_module_name(exc: BaseException) -> str:
    """
    Get the name of the module in which an exception occurred.

    :param exc: Exception object.
    :return: Name of the module.
    """
    return traceback.extract_tb(exc.__traceback__)[-1].filename


def get_function_name(exc: BaseException) -> str:
    """
    Get the name of the function in which an exception occurred.

    :param exc: Exception object.
    :return: Name of the function.
    """
    return traceback.extract_tb(exc.__traceback__)[-1].name


def log_exception(
    exc: BaseException,
    message: typing.Optional[str] = None,
    name: typing.Optional[str] = None,
    logger: typing.Optional[LoggerLike] = None,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> None:
    """
    Log an exception with optional custom message and traceback.

    :param exc: Exception object.
    :param message: Optional custom message to log.
    :param logger: Optional logger to use. If None, a logger with the given name is used.
    :param name: Optional name for the logger. If None, the default logger is used.
    :param args: Additional positional arguments for the log message.
    :param kwargs: Additional keyword arguments for the log message.
    """
    logger = logger or py_logging.getLogger(name or __name__)
    # Compose the log message
    if message:
        log_message = f"{message}: {exc}"
    else:
        log_message = f"An error occurred: {exc}"

    # Log the exception with traceback
    kwargs.pop(
        "exc_info", None
    )  # Ensure exc_info is not set to avoid issues with double kwargs
    try:
        logger.exception(log_message, exc_info=True, *args, **kwargs)

        # Log additional environment/context information
        logger.error(f"Exception type: {type(exc).__name__}")
        logger.error(f"Exception args: {exc.args}")
        logger.error(f"Environment: {os.getenv('ENVIRONMENT', 'not-set')}")
        logger.error(
            f"Function: {get_function_name(exc)} (module: {get_module_name(exc)})"
        )
    except Exception as log_exc:
        # Handle any exceptions that occur during logging
        logger.critical(
            f"Failed to log exception: {log_exc}", exc_info=True, *args, **kwargs
        )
    return
