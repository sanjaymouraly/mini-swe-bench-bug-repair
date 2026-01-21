# Mini SWE-Bench: Automated Software Bug Repair Evaluation

[![CI](https://github.com/sanjaymouraly/mini-swe-bench-bug-repair/actions/workflows/ci.yml/badge.svg)](https://github.com/sanjaymouraly/mini-swe-bench-bug-repair/actions/workflows/ci.yml)

A mini SWE-bench-style benchmark for evaluating automated software bug repair.

## Features

- Strict separation between agent and grading workspaces.
- Fresh grading checkout with external tests mounted read-only.
- Multi-dimensional grading distinguishes issue fixed from true resolution.
- Rejects unauthorized file changes, test tampering, symlink escapes, and shortcut hacks.
- Three-tier sandbox isolation with Docker, resource limits, and no network.
- Benchmark tasks with reproducible bug-repair scenarios and hidden tests.

## Stack

Python, FastAPI, HTTPX, Pydantic, PyYAML, Typer, Uvicorn, Docker

## Clone

```bash
git clone https://github.com/sanjaymouraly/mini-swe-bench-bug-repair.git
cd mini-swe-bench-bug-repair
```

## Setup

```bash
# The project ships a Docker Compose setup.
docker compose up --build
```

See `docs/` or the compose file for environment variables and ports.

## Run

```bash
docker compose up --build
```

## Tests

```bash
pytest -q
```

## Notes

- Sample data, when included, is synthetic.

## License

MIT © 2026 [Sanjay Mouraly](https://github.com/sanjaymouraly)
