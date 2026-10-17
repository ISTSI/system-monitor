# Stage 01 application image

The application wheel includes the built local React assets. The image uses
the recorded official Python 3.13.16 Linux amd64 digest, locked production
dependencies and UID/GID 10001. It contains no configuration, passwords,
development certificates or database migration credentials. It starts one ASGI
worker on port 8000, behind the deployment's same-origin HTTPS proxy. Node/npm
are build tools only. No runtime dependency install or Internet access occurs.

From the repository root on an approved connected Linux Docker build host:

```sh
python scripts/build_stage1.py
docker build --platform linux/amd64 -f deploy/app/Dockerfile -t system-inspector:0.1.0 .
```

The Dockerfile-specific context allowlist excludes private/local files. Supply
the runtime configuration and runtime password as read-only mounts, with writable
state/cache volumes owned by 10001. Do not mount migration/root secrets into the
serving service. Migrations are separate explicit jobs; `python -m inspector`
does not invoke them. Use the prepared MariaDB service and HTTPS proxy contract
in `examples/deployment/`, adapting its documented operator commands to the
actual CLI in `backend/README.md`.

The temporary Windows VM tunnel is a host-side development route. Its
`127.0.0.1:13306` must not be copied into a Linux container as a database address.
No route, tunnel binding or VM infrastructure is changed by this image.

Stage 01 built and ran this image using the signed-in account's local Linux
Docker engine. Image ID:
`sha256:327fdc96ee1dcecd8683e80a1ee41bd3670f006e0336b3ae81958a90988b072f`.
Both roles, local assets, runtime-only secret mounts, DML restrictions, database
outage/fail-closed recovery, retained-volume restart and local image save/load
were verified. The acceptance app container is stopped; its DB volume and images
are retained. The primary VM development app remains at `https://localhost:8443`.
See [exact evidence](../../verification/stage-1/docker/) and
[status](../../progress/STATUS.md). Linux container validation is distinct from
Ubuntu/Rocky host installation and full Stage 08 release assembly.
