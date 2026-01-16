# Flowline SCADA

Flowline SCADA is a small simulation and visualization tool for pipeline flowlines. It provides a web-based UI (via NiceGUI) to build simple pipeline models, simulate steady-state single-phase flow using known correlations, and monitor pipeline state. The project can run locally as a web server or be packaged as a native desktop app on Windows and macOS (native packaging is not supported on Linux by default).

This repository contains the simulator core, a NiceGUI-based frontend, pluggable storage backends (JSON files or Redis), and utilities for units and monitoring.

## Key features

- Single-phase, steady-state pipeline flow simulation using standard flow correlations.
- Interactive web UI for building and inspecting pipelines, adding flow stations (meters/regulators), and viewing pipeline configuration.
- Session-scoped configuration and state storage. Supports local JSON file storage and Redis.
- Monitor pipeline status to JSON files for later analysis.
- Can run:
  - Locally as a web application (default)
  - As a native desktop application on Windows and macOS (not Linux)

## Requirements

- Python 3.11 or newer
- The project dependencies are listed in `pyproject.toml`. Major dependencies include:
  - attrs
  - cattrs
  - CoolProp (for fluid properties)
  - nicegui (web UI)
  - orjson
  - pint (units)
  - python-dotenv
  - redis (optional)
  - scipy
  - pywebview[qt] (only for native packaging on non-Linux platforms)

Install deps using your preferred tool (uv, pip, poetry, etc.). Example with `pip` and `uv`:

```bash
uv sync

# Or with pip:
pip install -e .
```

> Note: `pywebview[qt]` only required for creating native desktop builds on macOS/Windows.

## Running locally (web)

1. Clone the repository.
2. Create and activate a virtual environment and install dependencies.
3. (Optional) Create a `.env` file at the project root to configure environment variables like `REDIS_URL`, `LOG_FILE`, and `LOG_LEVEL`.
4. Run the application:

```bash
python main.py
```

By default, the NiceGUI app will start and open on an available port (it tries 8008). The app serves the interactive UI where you can create and run pipeline simulations.

## Running as a native desktop app (Windows / macOS)

When you run `python main.py`, it opens a native application window if you are on Windows or Mac.

If you need a distributable executable file, this project also includes a helper script `build.sh` that wraps `nicegui-pack` to create a one-file native executable (Windows `.exe` or macOS bundle).

Simple steps to build the executable (For Linux / Mac):

1. Make `build.sh` executable (on Linux / WSL or macOS):

    ```bash
    chmod +x build.sh
    ```

2. Run the build script:

    ```bash
    bash ./build.sh
    ```

3. After the script completes, look for `FlowlineSCADA.exe` or the produced native bundle in the repository root or `dist`/`build` output (depending on the packer). Grant the produced file execute permissions if needed and run it as you would any desktop app.

For Windows users, a PowerShell helper `build.ps1` is provided which runs `nicegui-pack` from PowerShell and prints helpful messages. Use PowerShell when building on Windows if you prefer a native experience:

```powershell
# From the repository root in PowerShell (with your venv activated):
./build.ps1
```

## Storage and logs

- Config and session state are stored either in Redis (when `REDIS_URL` is set and reachable) or as JSON files under `.flowline-scada/configs` and `.flowline-scada/states`.
- Pipeline monitor output is written to `.flowline-scada/logs/pipeline_status_<session>.json`.
- Default log file: `.flowline-scada/logs/flowlinescada.log` (configurable via `LOG_FILE`).
- You can go into `main.py` and swap out the storage backend or modify logging settings as needed.

## Configuration

- Environment variables (via `.env` or system env):
  - `REDIS_URL` - URL for Redis storage (optional). If not set or unreachable, the app falls back to file storage.
  - `LOG_FILE` - path to write logs (default: `.flowline-scada/logs/flowlinescada.log`).
  - `LOG_LEVEL` - logging level (e.g. `INFO`, `DEBUG`).
  - `NICEGUI_STORAGE_SECRET` - secret used by NiceGUI for local browser storage encryption.
  - `DEBUG` - when truthy, the NiceGUI FastAPI app will be created with debug enabled.

## Code structure

- `main.py` - application entrypoint and NiceGUI pages.
- `src/` - library modules:
  - `config/` - Pipeline and UI configuration
  - `flow.py` - flow and fluid models
  - `pipeline/` - pipeline core, manager, solver, monitor, and UI helpers
  - `storages.py` - JSONFileStorage and RedisStorage implementations
  - `units.py` - unit system helpers (pint wrappers)
  - `logging.py` - logging setup

## Limitations and notes

- Simulation focuses on single-phase steady-state flow. It does not currently support transient multiphase simulations.
- The build scripts (`build.sh`) uses `nicegui-pack` and may require additional tooling (PyInstaller, Qt libs for pywebview) to be installed and available in PATH.

## Contributing

Contributions are welcome. For code changes, open a PR against `main`.

## License

This project is licensed under the terms in the `LICENSE` file in the repository root.
