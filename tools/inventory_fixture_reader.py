"""Bounded non-executing reader of package inventory examples, NOT app code.

Implements a deliberately smaller, conservative fixture subset of document 10.
No uploads, authentication, filesystem discovery, Ansible, subprocesses, networks,
DB commits or production error UI. Requires locally installed PyYAML for YAML.
Never import this module as the application's production importer.
"""
from __future__ import annotations
from collections import defaultdict
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
import shlex
import stat
from typing import Any
import zipfile

MAX_UPLOAD = 10 * 1024 * 1024
MAX_EXPANDED = 20 * 1024 * 1024
MAX_FILES = 200
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
SENSITIVE = re.compile(r"password|(?:^|_)pass(?:$|_)|private_key|(?:^|_)token(?:$|_)", re.I)
RELEVANT = {"ansible_host", "ansible_port", "ansible_user", "ansible_connection", "inspector_subsystem", "inspector_processes"}


class InventoryError(ValueError):
    """Sanitized code only; never include a source value in diagnostics."""


def _duplicate_safe(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise InventoryError("DUPLICATE_KEY")
        result[k] = v
    return result


def safe_data(raw: bytes, *, json_input: bool = False) -> Any:
    if len(raw) > MAX_UPLOAD:
        raise InventoryError("INPUT_LIMIT")
    try:
        text = raw.decode("utf-8")
        if "$ANSIBLE_VAULT" in text:
            raise InventoryError("VAULT_UNSUPPORTED")
        if json_input:
            data = json.loads(text, object_pairs_hook=_duplicate_safe)
        else:
            import yaml
            class Loader(yaml.SafeLoader):
                pass
            def construct_mapping(loader, node, deep=False):
                return _duplicate_safe((loader.construct_object(k, deep=deep), loader.construct_object(v, deep=deep)) for k, v in node.value)
            Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
            for count, token in enumerate(yaml.scan(text)):
                if count > 100000:
                    raise InventoryError("PARSE_LIMIT")
                if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken)):
                    raise InventoryError("YAML_CONSTRUCT_UNSUPPORTED")
            data = yaml.load(text, Loader=Loader)
    except InventoryError:
        raise
    except ImportError:
        raise
    except Exception:
        raise InventoryError("INVALID_DATA") from None
    # Bound structure and reject non-JSON scalar types from YAML without reflecting values.
    count = 0
    def check(value, depth):
        nonlocal count
        count += 1
        if depth > 32 or count > 100000:
            raise InventoryError("PARSE_LIMIT")
        if isinstance(value, dict):
            if not all(isinstance(k, str) for k in value):
                raise InventoryError("NON_STRING_KEY")
            for child in value.values(): check(child, depth + 1)
        elif isinstance(value, list):
            for child in value: check(child, depth + 1)
        elif value is not None and type(value) not in (str, int, float, bool):
            raise InventoryError("UNSUPPORTED_SCALAR")
    check(data, 0)
    return data


def scrub(value: Any, omitted: set[str]) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if SENSITIVE.search(key):
                omitted.add(key)
                continue
            if key in {"ansible_ssh_common_args", "ansible_ssh_extra_args", "ansible_ssh_private_key_file", "ansible_become_password"}:
                omitted.add(key)
                continue
            result[key] = scrub(child, omitted)
        return result
    if isinstance(value, list): return [scrub(x, omitted) for x in value]
    return value


def bundle_files(raw: bytes) -> dict[str, bytes]:
    if len(raw) > MAX_UPLOAD: raise InventoryError("INPUT_LIMIT")
    result, names, total = {}, set(), 0
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            if len(archive.infolist()) > MAX_FILES: raise InventoryError("FILE_LIMIT")
            for info in archive.infolist():
                # ZipInfo normalizes Windows separators and truncates NULs in
                # filename. Validate the original archive name before either
                # transformation can conceal an unsafe member.
                name = info.orig_filename.rstrip("/") if info.is_dir() else info.orig_filename
                parts = name.split("/")
                if not name or "\\" in name or any(p in {"", ".", ".."} for p in parts) or ":" in name or len(parts) > 8:
                    raise InventoryError("UNSAFE_MEMBER")
                if PurePosixPath(name).is_absolute() or any(ord(c) < 32 for c in name): raise InventoryError("UNSAFE_MEMBER")
                if name.casefold() in names: raise InventoryError("DUPLICATE_MEMBER")
                names.add(name.casefold())
                kind = stat.S_IFMT(info.external_attr >> 16)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR): raise InventoryError("NON_REGULAR_MEMBER")
                if info.flag_bits & 1: raise InventoryError("ENCRYPTED_ARCHIVE")
                if info.is_dir(): continue
                if name.endswith((".zip", ".tar.gz", ".tgz")): raise InventoryError("NESTED_ARCHIVE")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}: raise InventoryError("UNSUPPORTED_COMPRESSION")
                with archive.open(info) as stream:
                    data = stream.read(MAX_EXPANDED - total + 1)
                total += len(data)
                if total > MAX_EXPANDED: raise InventoryError("EXPANDED_LIMIT")
                result[name] = data
    except InventoryError: raise
    except Exception: raise InventoryError("INVALID_ARCHIVE") from None
    return result


def read_inventory(raw: bytes, format: str, companions: dict[str, bytes] | None = None) -> dict[str, Any]:
    if len(raw) > MAX_UPLOAD: raise InventoryError("INPUT_LIMIT")
    if format not in {"ini", "yaml", "canonical_json"}: raise InventoryError("FORMAT_UNSUPPORTED")
    groups: dict[str, dict[str, Any]] = {}
    hostvars: dict[str, dict[str, Any]] = {}
    omitted: set[str] = set()
    ignored: list[str] = []
    def group(name):
        if not isinstance(name, str) or not NAME.fullmatch(name): raise InventoryError("INVALID_GROUP")
        return groups.setdefault(name, {"hosts": set(), "children": set(), "vars": {}})
    def merge_unique(dest, src):
        if not isinstance(src, dict): raise InventoryError("INVALID_VARIABLES")
        for key, value in src.items():
            if key in dest and dest[key] != value: raise InventoryError("STATIC_VARIABLE_CONFLICT")
            dest[key] = value
    def host(name, values, parent):
        if not isinstance(name, str) or not NAME.fullmatch(name) or "[" in name: raise InventoryError("HOST_PATTERN_UNSUPPORTED")
        group(parent)["hosts"].add(name)
        merge_unique(hostvars.setdefault(name, {}), values or {})
    group("all")
    if format == "ini":
        try: text = raw.decode("utf-8")
        except UnicodeError: raise InventoryError("INVALID_ENCODING") from None
        current, mode = "ungrouped", "hosts"
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith(("#", ";")): continue
            if s.startswith("[") and s.endswith("]"):
                section = s[1:-1]
                current, _, suffix = section.partition(":")
                mode = suffix or "hosts"
                if mode not in {"hosts", "children", "vars"}: raise InventoryError("INI_SECTION_UNSUPPORTED")
                group(current); continue
            try: tokens = shlex.split(s, comments=True, posix=True)
            except ValueError: raise InventoryError("INVALID_INI_QUOTING") from None
            if not tokens: continue
            if mode == "children":
                if len(tokens) != 1: raise InventoryError("INVALID_CHILD_GROUP")
                group(current)["children"].add(tokens[0]);group(tokens[0]);continue
            if mode == "vars":
                if len(tokens) != 1 or "=" not in tokens[0]: raise InventoryError("INI_VARS_SUBSET_LIMIT")
                key, value = tokens[0].split("=", 1)
                merge_unique(group(current)["vars"], {key: value});continue
            name, *rest = tokens
            values = {}
            for token in rest:
                if "=" not in token: raise InventoryError("INVALID_INI_VARIABLE")
                key, value = token.split("=", 1)
                merge_unique(values, {key: value})
            host(name, values, current)
    else:
        document = safe_data(raw, json_input=format == "canonical_json")
        if not isinstance(document, dict) or "plugin" in document: raise InventoryError("DYNAMIC_OR_INVALID_INVENTORY")
        if format == "canonical_json":
            meta = document.get("_meta", {})
            if not isinstance(meta, dict) or not isinstance(meta.get("hostvars", {}), dict): raise InventoryError("INVALID_CANONICAL_META")
            for name, values in meta.get("hostvars", {}).items(): host(name, values, "all")
            for name, value in document.items():
                if name == "_meta": continue
                if not isinstance(value, dict): raise InventoryError("INVALID_GROUP")
                g = group(name)
                g["vars"] = value.get("vars", {})
                for item in value.get("hosts", []): host(item, {}, name)
                for child in value.get("children", []): g["children"].add(child);group(child)
        else:
            def visit(name, value, depth=0):
                if depth > 20: raise InventoryError("GROUP_DEPTH_LIMIT")
                value = value or {}
                if not isinstance(value, dict) or set(value) - {"hosts", "vars", "children"}: raise InventoryError("YAML_GROUP_UNSUPPORTED")
                g=group(name)
                merge_unique(g["vars"], value.get("vars", {}) or {})
                for alias, variables in (value.get("hosts", {}) or {}).items(): host(alias, variables, name)
                for child, childvalue in (value.get("children", {}) or {}).items():
                    g["children"].add(child); visit(child, childvalue, depth+1)
            for name, value in document.items(): visit(name, value)
    for path, data in sorted((companions or {}).items()):
        parts = PurePosixPath(path).parts
        if len(parts) not in (2, 3) or parts[0] not in {"group_vars", "host_vars"}:
            ignored.append(path); continue
        entity = parts[1]
        if len(parts) == 2:
            for suffix in (".yaml", ".yml", ".json"):
                if entity.endswith(suffix): entity = entity[:-len(suffix)];break
        variables = safe_data(data, json_input=path.endswith(".json"))
        if not isinstance(variables, dict): raise InventoryError("INVALID_VARIABLES")
        if parts[0] == "group_vars" and entity in groups: groups[entity]["vars"].update(variables)
        elif parts[0] == "host_vars" and entity in hostvars: hostvars[entity].update(variables)
        else: ignored.append(path)
    # The sample reader expects validated companion paths; ZIP workflow provides them.
    parents: dict[str, set[str]] = defaultdict(set)
    for name, value in groups.items():
        if "ansible_group_priority" in value["vars"]: raise InventoryError("GROUP_PRIORITY_UNSUPPORTED")
        for child in value["children"]: parents[child].add(name)
    def ancestors(name, seen=frozenset()):
        if name in seen: raise InventoryError("GROUP_CYCLE")
        result = set()
        for parent in parents[name]: result.add(parent);result.update(ancestors(parent, seen | {name}))
        return result
    ancestry = {name: ancestors(name) for name in groups}
    output=[]
    for alias in sorted(hostvars):
        memberships = {g for g, data in groups.items() if alias in data["hosts"]}
        memberships |= set().union(*(ancestry[g] for g in memberships)) if memberships else set()
        memberships.add("all")
        candidates: dict[str, list[tuple[str, Any]]] = defaultdict(list)
        for name in memberships:
            variables = scrub(groups[name]["vars"], omitted)
            for key, value in variables.items():
                if key in RELEVANT: candidates[key].append((name, value))
        effective={}
        for key, options in candidates.items():
            # Canonical _meta.hostvars is already expanded; no need to guess its precedence.
            if format == "canonical_json" and key in hostvars[alias]: continue
            for first, fv in options:
                for second, sv in options:
                    if first != second and first != "all" and second != "all" and first not in ancestry[second] and second not in ancestry[first] and fv != sv:
                        raise InventoryError("STATIC_VARIABLE_CONFLICT")
            options.sort(key=lambda pair: (-1 if pair[0]=="all" else len(ancestry[pair[0]]), pair[0]))
            effective[key]=options[-1][1]
        effective.update({k:v for k,v in scrub(hostvars[alias], omitted).items() if k in RELEVANT})
        def check_template(value):
            if isinstance(value,str) and any(x in value for x in ("{{", "{%", "lookup(", "$(", "${")): raise InventoryError("UNRESOLVED_TEMPLATE")
            if isinstance(value,dict):
                for child in value.values(): check_template(child)
            if isinstance(value,list):
                for child in value: check_template(child)
        check_template(effective)
        if effective.get("ansible_connection", "ssh") not in {"ssh", "paramiko"}: raise InventoryError("NON_SSH_CONNECTION")
        try:
            raw_port=effective.get("ansible_port",22)
            if type(raw_port) not in (int,str): raise ValueError
            port=int(raw_port)
            if not 1<=port<=65535: raise ValueError
        except (TypeError,ValueError): raise InventoryError("INVALID_PORT") from None
        address=effective.get("ansible_host",alias)
        username=effective.get("ansible_user")
        if not isinstance(address,str) or not address or any(c.isspace() for c in address): raise InventoryError("INVALID_ADDRESS")
        if username is not None and (not isinstance(username,str) or not username): raise InventoryError("INVALID_USERNAME")
        processes=effective.get("inspector_processes",[])
        if not isinstance(processes,list): raise InventoryError("PROCESS_EXTENSION_UNSUPPORTED")
        output.append({"inventory_hostname":alias,"host":address,"port":port,"username":username,
                       "groups":sorted(memberships-{"all","ungrouped"}),"inspector_subsystem":effective.get("inspector_subsystem"),
                       "inspector_processes":processes})
    return {"hosts":output,"omitted_fields":sorted(omitted),"ignored_files":sorted(ignored)}
