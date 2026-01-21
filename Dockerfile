# syntax=docker/dockerfile:1

# ==============================================================================
# Stage 1: Isolated Sandbox Evaluation Runner (target: runner)
# Used by SandboxExecutor to run untrusted candidate patches with:
#   --network none --read-only --cap-drop ALL --security-opt no-new-privileges
#   --user 1000:1000 --memory 512m --cpus 1.0 --pids-limit 64
# ==============================================================================
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 sandbox \
    && useradd -m -u 1000 -g 1000 -s /bin/sh sandbox

# Pinned test-runner dependencies (see docker/requirements-runner.txt).
# NOTE: requirement specifiers MUST stay quoted: an unquoted ">=x" is parsed by
# /bin/sh as a stdout redirection and silently installs the wrong packages.
COPY docker/requirements-runner.txt /tmp/requirements-runner.txt
RUN pip install --no-cache-dir --retries 10 -r /tmp/requirements-runner.txt \
    && rm -f /tmp/requirements-runner.txt

USER 1000:1000
WORKDIR /workspace
CMD ["pytest", "-q"]

# ==============================================================================
# Stage 2: Full Mini SWE-Bench Orchestrator & Web Dashboard (target: app)
# ==============================================================================
FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    bubblewrap \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 bugbench \
    && useradd -m -u 1000 -g 1000 -s /bin/bash bugbench

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY benchmarks ./benchmarks
COPY private_evaluations ./private_evaluations

RUN pip install --no-cache-dir --retries 10 -e . && chown -R bugbench:bugbench /app

USER 1000:1000
EXPOSE 8000
CMD ["bugbench", "serve", "--host", "0.0.0.0", "--port", "8000"]
