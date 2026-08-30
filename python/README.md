# PiCode Python Runtime

PiCode requires Python 3.11 or newer. Python 3.12 is recommended.

From the repository root on Windows, create the isolated environment and install all Runtime and development dependencies:

```powershell
py -3.12 -m venv python/.venv
python/.venv/Scripts/python.exe -m pip install -e "python[dev]"
```

Validate the Runtime:

```powershell
python/.venv/Scripts/python.exe -m ruff check python/src python/tests
python/.venv/Scripts/python.exe -m pyright --project python/pyproject.toml
python/.venv/Scripts/python.exe -m pytest python
```

The TypeScript Host looks for an explicitly configured interpreter first, then `python/.venv`, then a compatible system Python. It requires Pydantic to be installed and reports this setup command if no compatible Runtime is found.

## DeepSeek Router model

To use DeepSeek V4 Flash for model-backed routing, copy the repository-root `.env.example` to `.env`, then set `DEEPSEEK_API_KEY`. Keep `PICODE_MODEL=deepseek-v4-flash`; the optional base URL defaults to `https://api.deepseek.com`.

`PICODE_MODEL` without `DEEPSEEK_API_KEY` prevents Runtime startup with a clear error. `.env` is ignored by Git and must not be committed.
