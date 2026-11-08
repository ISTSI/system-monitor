#!/usr/bin/env python3
"""Create a private server key and CSR for an internal CA; no ACME/network use."""

import argparse
import ipaddress
import os
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--hostname", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if os.name != "posix" or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}", args.hostname):
    parser.error("Use a valid hostname/IP on the Linux deployment host")
try:
    ipaddress.ip_address(args.hostname)
    alternative = "IP:" + args.hostname
except ValueError:
    alternative = "DNS:" + args.hostname
if args.output.exists() or args.output.is_symlink():
    parser.error("Use a new directory; existing recovery material is never overwritten")
os.umask(0o077)
args.output.mkdir(mode=0o700)
subprocess.run(
    [
        "openssl",
        "genpkey",
        "-algorithm",
        "EC",
        "-pkeyopt",
        "ec_paramgen_curve:P-256",
        "-out",
        str(args.output / "server.key"),
    ],
    check=True,
)
subprocess.run(
    [
        "openssl",
        "req",
        "-new",
        "-sha256",
        "-key",
        str(args.output / "server.key"),
        "-out",
        str(args.output / "server.csr"),
        "-subj",
        "/CN=" + args.hostname,
        "-addext",
        "subjectAltName=" + alternative,
    ],
    check=True,
)
print("Private key and CSR created. Submit only server.csr through your internal CA process.")
