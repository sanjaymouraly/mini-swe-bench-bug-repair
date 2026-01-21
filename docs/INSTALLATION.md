# Installation & Quick Start

> **Disclaimer:** This is an independent SWE-bench-inspired practice benchmark. It is not an official SWE-bench dataset, evaluation, or contribution, and its scores are not directly comparable with official SWE-bench results.

Two supported platforms: **Windows 10/11 (PowerShell)** and **Linux (Ubuntu/Debian/Fedora)**.

Docker is strongly recommended: it is the default, most secure execution backend.
Everything still works without it (the `subprocess` backend is used instead), but
isolation is weaker.

---

## Requirements

| Requirement | Version | Notes |
| :--- | :--- | :--- |
| Python | 3.12 or newer | 3.12 and 3.13 are tested |
| Git | 2.30 or newer | Needed for deterministic base revisions and `git apply` |
| Docker | 24.0 or newer | Docker Desktop on Windows/macOS, Docker Engine on Linux |
| RAM | 4 GB free | The dashboard plus a few parallel containers |
| Disk | 2 GB free | The runner image is ~330 MB |

Ollama is **optional** and only needed for local, free model inference.

---

## Linux (Ubuntu / Debian)

### 1. Install the system dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git
```

### 2. Install Docker Engine

```bash
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in (or run `newgrp docker`) so your user can talk to the daemon.

Verify:

```bash
docker info
```

### 3. Clone and set up the Python environment

```bash
git clone https://github.com/your-org/software-bug-repair-benchmark.git
cd software-bug-repair-benchmark

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### 4. Build the isolated runner image

```bash
docker build --target runner \
  -t software-bug-repair-benchmark-runner:latest -f Dockerfile .
```

### 5. Verify the installation

```bash
bugbench --help
bugbench list
bugbench reference --sandbox docker
```

The last command must report `Resolved: 12/12 (100.0%)`.

---

## Windows 10 / 11 (PowerShell)

### 1. Install the prerequisites

Install each of the following, then **restart PowerShell** so the `PATH` is
refreshed:

- **Python 3.12+** — <https://www.python.org/downloads/windows/> (tick
  *Add python.exe to PATH* during installation)
- **Git for Windows** — <https://git-scm.com/download/win>
- **Docker Desktop for Windows** — <https://www.docker.com/products/docker-desktop/>
  (enable WSL 2 backend)

Verify in PowerShell:

```powershell
python --version
git --version
docker version
```

> If `docker version` reports that the daemon is not running, start Docker
> Desktop and wait for the whale icon to report *Engine running*.

### 2. Allow the bundled scripts to run (one time)

If you hit `running scripts is disabled on this system`:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 3. Clone and set up the Python environment

```powershell
git clone https://github.com/your-org/software-bug-repair-benchmark.git
cd software-bug-repair-benchmark

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

> If activation fails with a policy error, run
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
> and reopen PowerShell.

### 4. Build the isolated runner image

```powershell
docker build --target runner -t software-bug-repair-benchmark-runner:latest -f Dockerfile .
```

### 5. Verify the installation

```powershell
bugbench --help
bugbench list
bugbench reference --sandbox docker
```

The last command must report `Resolved: 12/12 (100.0%)`.

---

## Docker Desktop file sharing (Windows)

Docker Desktop needs explicit permission to read the project directory. Open
**Settings → Resources → File sharing** and add the drive that contains the
repository (usually `C:\`). If you cloned to another drive, add that one too.

Symptom of a missing share: the container starts but the workspace mount is
empty, and every task fails with an environment error.

---

## Optional: local models with Ollama

Ollama gives you free, private, offline model inference.

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows: download the installer from https://ollama.com/download
```

Then pull a code-capable model and start the server:

```bash
ollama serve            # in a separate terminal if it is not already running
ollama pull qwen2.5:7b
ollama list
```

Point Mini SWE-Bench at it:

```bash
bugbench providers --test ollama
bugbench run-agent --provider ollama --model qwen2.5:7b
```

Ollama's OpenAI-compatible endpoint is `http://localhost:11434/v1` and needs no
API key.

---

## Optional: configure a paid or remote provider

```bash
cp .env.example .env
```

Edit `.env` and add only the provider you need:

```bash
# Example: any OpenAI-compatible gateway
CUSTOM_OPENAI_BASE_URL=https://your-gateway.example/v1
CUSTOM_OPENAI_API_KEY=sk-...
CUSTOM_OPENAI_MODEL=your-model-id
```

Then check the connection:

```bash
bugbench providers --test custom_openai
```

`.env` is git-ignored. Never commit real API keys.

---

## Fast start (works fully offline, no API key)

```bash
# 1. Prove the dataset is sound (8 quality gates x 12 tasks)
bugbench validate --sandbox docker

# 2. The reference oracle must resolve 12/12
bugbench reference --sandbox docker

# 3. The no-op baseline must resolve 0/12
bugbench baseline --mode noop --sandbox docker

# 4. Evaluate your own fix
bugbench evaluate-patch --patch examples/sample_patches/pagiflow-001.patch

# 5. Open the dashboard
bugbench serve
# then browse to http://localhost:8000
```

---

## Running the whole thing in Docker

```bash
docker compose up --build
# dashboard on http://localhost:8000
```

---

## Uninstalling

```bash
deactivate                       # leave the virtualenv
rm -rf .venv
docker rmi software-bug-repair-benchmark-runner:latest
```

Nothing outside the repository, the Docker image, and the virtualenv is
modified.

---

## Next steps

- [`docs/CLI_REFERENCE.md`](CLI_REFERENCE.md) — every command and option
- [`docs/API_REFERENCE.md`](API_REFERENCE.md) — the HTTP API
- [`docs/CONFIGURATION_AND_PROVIDERS.md`](CONFIGURATION_AND_PROVIDERS.md) — providers, pricing, and cost control
- [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — common problems and fixes
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — how the evaluation pipeline works
