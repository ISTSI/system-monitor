# Synthetic fixtures

Every hostname, path, process label, message and correlation identifier here is fictional demonstration data. The provided image is the user's visual reference; all logs were created for this package. No credential can be used to authenticate anywhere.

`source-manifest.json` maps 21 source objects to process IDs, synthetic remote paths and local fixture paths. `expected/events.json` contains 38 expected normalised physical-line events with exact byte offsets and hashes. `expected/labels.json` gives readable names to those event IDs. `expected/query-cases.json` contains 17 independently specified expected result sequences. One invalid-timestamp line belongs in the diagnostic lane. `expected/correlation-exact.json` distinguishes exact request-id matching from a substring that also matches REQ-00420.

Each of five process sources has a current file, a plain rotation, a ZIP and a TAR.GZ archive. The ingestion source additionally has a deliberately misleading archive filename whose content timestamp is current. Do not choose candidates exclusively from filenames. The two identical retry messages are separate physical events and must not be deduplicated by text/time.

Standalone samples cover fixed-width timestamps, CRLF and an unfinished live line. `live-scenarios.json` describes append/rotation/reconnect/refilter behaviours to implement against a real test transport; these descriptions are not an executed replay harness.

`rejected/traversal.zip`, `rejected/symlink.tar.gz` and `rejected/corrupt.zip` are small, harmless negative test inputs. They contain no executable payload. They must be rejected by safe readers; **do not extract them into a working directory**. The package checker opens them only to inspect/reject their metadata.

Use `tools/generate_load_fixture.py --output-dir /a/new/empty/path --size-mib 20` to generate a larger synthetic local benchmark input. It creates new files only, does not access SSH/network, and does not alter this small golden dataset.
