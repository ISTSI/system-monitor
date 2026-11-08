# Offline runtime assets

These files are copied to a built release's `runtime/` directory. Use
[`docs/OFFLINE_OPERATIONS.md`](../../docs/OFFLINE_OPERATIONS.md) in the repository,
or the packaged operator guide, for the complete installation/recovery process.
Native Ubuntu/Rocky qualification is reported separately from Linux-container
verification. Templates alone do not qualify a target platform.

`manage.py --help` exposes private Linux initialization, exact image load,
managed/external startup, interactive Administrator bootstrap and coordinated
backup/fresh managed-volume restore. It uses only Python 3.9+ stdlib, the host's
OpenSSL and Docker Compose v2.24+ or rootless Podman 4.4+. No container gets a
host runtime socket. Docker serving uses the supplied Compose recipes; Podman
uses explicit pull-disabled commands and the packaged systemd fallback.

Archive/loaded content identities come from the **actual built release manifest**;
there are no guessed app/proxy image IDs in these templates. MariaDB and proxy
upstream pins are recorded by connected preparation; artifacts never pull on
start. The proxy listens unprivileged on 8443, runs UID/GID 10001 and uses only
the supplied certificate/key. Its access log is disabled.

Run the delivered recovery security tests without network access:

```sh
python3 -B -m unittest discover -s deploy/offline -p test_runtime.py -v
```

The Linux tests cover corrupt/extra/duplicated/traversal/symlink/hardlink members,
actual byte limits, exact binary restoration, ownership and overwrite refusal.
Database lifecycle and actual-served browser evidence belong in the release
test report, not this test suite.
