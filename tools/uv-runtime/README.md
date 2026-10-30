# ARIS helper runtime

This directory is the isolated `uv` project for ARIS Python helper scripts.
It is intentionally separate from every research project's Python environment.
The wrapper also defaults `UV_CACHE_DIR` to this directory's ignored
`.uv-cache/`; an explicitly supplied `UV_CACHE_DIR` still takes precedence.

Run a helper through the canonical wrapper:

```bash
bash ../uv_run_helper.sh ../semantic_scholar_fetch.py --help
```

Dependency changes must be made in `pyproject.toml`, followed by:

```bash
uv lock --project .
uv sync --project . --frozen
```

Do not install helper dependencies into an Idea's `code/` project unless that
dependency is also required by the scientific implementation itself.
