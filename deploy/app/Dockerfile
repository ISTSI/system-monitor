# Build on a connected preparation host after scripts/build_stage1.py succeeds.
# This digest is the recorded official linux/amd64 image in local-mariadb/images.lock.json.
FROM docker.io/library/python:3.13.16-slim@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024 AS build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
COPY deploy/local-mariadb/runner-bootstrap.requirements.txt /tmp/bootstrap.requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/bootstrap.requirements.txt
COPY backend/pyproject.toml backend/uv.lock /build/backend/
RUN uv sync --project /build/backend --locked --no-dev --no-install-project --no-managed-python --python /usr/local/bin/python
COPY backend/dist/system_inspector-0.1.0-py3-none-any.whl /tmp/system_inspector-0.1.0-py3-none-any.whl
RUN uv pip install --python /opt/venv/bin/python --no-deps /tmp/system_inspector-0.1.0-py3-none-any.whl

FROM docker.io/library/python:3.13.16-slim@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024
COPY --from=build /opt/venv /opt/venv
COPY third_party/backend /opt/notices/backend
COPY third_party/frontend /opt/notices/frontend
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_OFFLINE=1 HOME=/tmp
RUN mkdir -p /var/lib/system-inspector /var/cache/system-inspector && chown 10001:10001 /var/lib/system-inspector /var/cache/system-inspector
USER 10001:10001
WORKDIR /var/lib/system-inspector
EXPOSE 8000
CMD ["python", "-m", "inspector"]
