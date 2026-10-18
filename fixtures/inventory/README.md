# Browser inventory fixture

`browser-source-order.zip` is a deterministic, uncompressed synthetic ZIP with
regular members dated 17 October 2026:

- `first.ini`: one static host (`first-host`, `192.0.2.81`).
- `second.ini`: one static host (`second-host`, `192.0.2.82`).
- `roles/ignored.py`: an unsupported extra whose contents must never execute.

The browser test explicitly chooses the two INI files, changes their read order,
checks the returned provenance and ignored filename, then commits two hosts with
no invented processes. There are no credentials, external references or target
connections in the fixture.
