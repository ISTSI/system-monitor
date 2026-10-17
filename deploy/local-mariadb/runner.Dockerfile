# Connected build only. At runtime this image uses the internal database network.
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    HOME=/tmp

COPY deploy/local-mariadb/runner-bootstrap.requirements.txt /tmp/bootstrap.requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/bootstrap.requirements.txt
COPY backend/pyproject.toml backend/uv.lock /build/backend/
RUN uv sync --project /build/backend --locked --no-install-project --no-managed-python \
    --python /usr/local/bin/python && uv cache clean

# Source/configuration and only the identity's own secrets are mounted by Compose.
ENV UV_OFFLINE=1 PYTHONPATH=/workspace/backend/src
WORKDIR /workspace/backend
RUN groupadd --gid 10001 inspector && useradd --uid 10001 --gid 10001 --no-create-home --no-log-init --shell /usr/sbin/nologin inspector
USER 10001:10001
CMD ["python", "-m", "pytest", "tests/integration", "-v", "-rs", "-p", "no:cacheprovider"]
