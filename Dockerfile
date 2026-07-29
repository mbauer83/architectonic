# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# Architectonic — multi-stage image
#   stage 1 (frontend) : build the Vue SPA  → /build/dist
#   stage 2 (builder)  : resolve Python deps with uv into /app/.venv + plantuml.jar
#   stage 3 (runtime)  : slim image with the diagram runtime, source tree, and venv
#
# The runtime stage deliberately preserves the /app source layout (src/, config/,
# pyproject.toml, plantuml.jar, tools/gui/dist) because the app discovers resources
# (plantuml.jar, settings, the SPA) by walking the source tree — not via packaged
# data. The Python project is installed editable into /app/.venv accordingly.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build the Vue SPA ───────────────────────────────────────────────
FROM node:20-alpine AS frontend

WORKDIR /build
# Cache deps on package manifests only.
COPY tools/gui/package*.json ./
RUN npm ci
# Build the SPA. `generate-types` self-skips when uv is absent and uses the
# committed tools/gui/src/domain/types.generated.ts.
COPY tools/gui/ ./
RUN npm run build


# ── Stage 2: Resolve Python dependencies with uv ─────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder

# uv tuning for reproducible, cache-friendly container builds.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Optional dependency extras baked into the image. Defaults to the full assurance
# storage matrix (S3 + Azure WORM archives). For a leaner image without cloud
# archive support, build with: --build-arg ARCH_PIP_EXTRAS=""
ARG ARCH_PIP_EXTRAS="--extra cloud-archive"

WORKDIR /app

# Java is needed so `get-plantuml` can verify the downloaded jar runs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Layer 1: dependencies only (cached unless lockfile/manifest change).
# --no-install-project installs just the third-party deps. Extras:
#   gui            → FastAPI + uvicorn (the served backend)
#   cloud-archive  → boto3 + azure-* so the full assurance storage matrix works
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --group gui ${ARCH_PIP_EXTRAS}

# Layer 2: the project source + editable install of the project itself.
COPY src/ src/
COPY config/ config/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group gui ${ARCH_PIP_EXTRAS}

# Fetch the pinned plantuml.jar (sibling of pyproject.toml, where the app looks).
RUN .venv/bin/get-plantuml


# ── Stage 3: Runtime ─────────────────────────────────────────────────────────
FROM python:3.13-slim-trixie AS runtime

# Diagram runtime (Java + Graphviz + fonts), git/ssh for repo sync, curl for health.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-jre-headless \
        graphviz \
        libfontconfig1 \
        libharfbuzz0b \
        fonts-dejavu-core \
        git \
        openssh-client \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user with a real, persistable HOME (the assurance Fernet vault
# lives at $HOME/.config/arch-assurance/vault.enc).
ARG ARCH_UID=10001
ARG ARCH_GID=10001
RUN groupadd --gid ${ARCH_GID} arch \
    && useradd --uid ${ARCH_UID} --gid ${ARCH_GID} --create-home --home-dir /home/arch arch

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    HOME=/home/arch \
    ARCH_BACKEND_STATE_DIR=/app/.arch

WORKDIR /app

# Source tree + resolved venv + diagram jar. The editable .pth in /app/.venv
# points at /app/src, so the path layout below must match the builder's.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/plantuml.jar /app/plantuml.jar
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
# License + third-party notices ride in the image adopters receive (I-L3).
COPY LICENSE THIRD-PARTY-NOTICES.md /app/
# Reference copies of the licenses governing what this build assembled. Not an obligation of
# this project (it conveys no binaries) — they are here for whoever publishes THIS image and
# does convey them; the apt packages also carry their own under /usr/share/doc/*/copyright.
COPY licenses/texts/ /app/licenses/texts/
COPY src/ /app/src/
COPY config/ /app/config/
# Activate the server-oriented settings as the live config. It lives in the
# image layer (owned by the runtime user) so the entrypoint and `arch-assurance`
# can mutate it without bind-mount permission conflicts. Operators override
# declarative values via .env, or by mounting a settings.yaml writable by the
# runtime uid (see docs/reference/docker-compose.md).
RUN cp /app/config/settings.server.yaml /app/config/settings.yaml
# Pre-built SPA, served by the backend at /.
COPY --from=frontend /build/dist/ /app/tools/gui/dist/

# Entrypoint orchestrates non-interactive init/unlock + backend start.
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Writable locations for state, cloned repos, the assurance store, and the vault.
# These are pre-created (and owned by the runtime user) so named volumes mounted
# over them inherit the correct ownership instead of defaulting to root.
RUN mkdir -p /app/.arch /app/.arch-assurance /data \
    && chown -R arch:arch /app /home/arch /data

USER arch
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
