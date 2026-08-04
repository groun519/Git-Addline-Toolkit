from __future__ import annotations

import re

from line_tracker import encode_author_patterns


AUTHOR_IDENTITY_RE = re.compile(r"^(?P<name>.+?)\s*<(?P<email>[^<>]+)>$")
AUTHOR_HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
GITHUB_NOREPLY_DOMAIN = "users.noreply.github.com"


def parse_author_identity(identity: str) -> tuple[str | None, str | None]:
    match = AUTHOR_IDENTITY_RE.fullmatch(identity.strip())
    if not match:
        cleaned = identity.strip()
        return (cleaned or None), None
    name = match.group("name").strip() or None
    email = match.group("email").strip() or None
    return name, email


def parse_shortlog_identities(output: str) -> list[str]:
    identities: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line:
            _, identity = line.split("\t", 1)
        else:
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            identity = parts[1]
        identity = identity.strip()
        if identity:
            identities.append(identity)
    return identities


def build_author_option_entries(
    identities: list[str],
    auto_label: str,
    all_label: str,
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    options = [auto_label, all_label]
    mapping = {auto_label: "auto", all_label: ""}
    aliases = {"auto": auto_label, "": all_label}

    parsed_identities: list[dict[str, object]] = []
    key_to_indices: dict[str, list[int]] = {}

    for raw_identity in identities:
        identity = raw_identity.strip()
        if not identity:
            continue

        name, email = parse_author_identity(identity)
        merge_keys = _extract_author_merge_keys(identity, name, email)
        item = {
            "identity": identity,
            "name": name,
            "email": email,
            "merge_keys": merge_keys,
        }
        index = len(parsed_identities)
        parsed_identities.append(item)
        for key in merge_keys:
            key_to_indices.setdefault(key, []).append(index)

    groups: list[dict[str, object]] = []
    visited: set[int] = set()
    for start_index in range(len(parsed_identities)):
        if start_index in visited:
            continue

        stack = [start_index]
        component_indices: list[int] = []
        while stack:
            index = stack.pop()
            if index in visited:
                continue
            visited.add(index)
            component_indices.append(index)
            for merge_key in parsed_identities[index]["merge_keys"]:
                for linked_index in key_to_indices.get(str(merge_key), []):
                    if linked_index not in visited:
                        stack.append(linked_index)

        component_indices.sort()
        component = [parsed_identities[index] for index in component_indices]
        display_item = max(
            component,
            key=lambda candidate: _author_display_priority(
                _as_optional_string(candidate.get("name")),
                _as_optional_string(candidate.get("email")),
            ),
        )

        identities_in_group: list[str] = []
        emails_in_group: list[str] = []
        for candidate in component:
            identity = str(candidate["identity"])
            email = _as_optional_string(candidate.get("email"))
            if identity not in identities_in_group:
                identities_in_group.append(identity)
            if email and email not in emails_in_group:
                emails_in_group.append(email)
        groups.append(
            {
                "display": str(display_item["identity"]),
                "identities": identities_in_group,
                "emails": emails_in_group,
            }
        )

    for group in groups:
        display = str(group["display"])
        if display in mapping:
            continue

        emails = [str(value) for value in group["emails"] if value]
        group_identities = [str(value) for value in group["identities"] if value]
        identities_for_filter = emails or group_identities
        if not identities_for_filter:
            continue

        escaped_patterns = [re.escape(value) for value in identities_for_filter]
        filter_value = encode_author_patterns(escaped_patterns)
        mapping[display] = filter_value
        options.append(display)
        aliases[filter_value] = display

        legacy_filter_value = "|".join(escaped_patterns)
        if legacy_filter_value:
            aliases[legacy_filter_value] = display
        for alias_source in group_identities:
            aliases[re.escape(alias_source)] = display
        for alias_source in emails:
            aliases[re.escape(alias_source)] = display

    return options, mapping, aliases


def _parse_email_parts(email: str | None) -> tuple[str | None, str | None]:
    if not email:
        return None, None
    if "@" not in email:
        return email.strip() or None, None
    local_part, domain = email.rsplit("@", 1)
    return local_part.strip() or None, domain.strip().casefold() or None


def _normalize_author_handle(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned or not AUTHOR_HANDLE_RE.fullmatch(cleaned):
        return None
    return cleaned.casefold()


def _extract_author_merge_keys(identity: str, name: str | None, email: str | None) -> list[str]:
    merge_keys: list[str] = []
    if email:
        merge_keys.append(f"email:{email.casefold()}")

    normalized_name = _normalize_author_handle(name)
    email_local, email_domain = _parse_email_parts(email)
    normalized_local = _normalize_author_handle(email_local)
    if normalized_name and normalized_local and normalized_name == normalized_local:
        merge_keys.append(f"handle:{normalized_name}")

    if email_domain == GITHUB_NOREPLY_DOMAIN and email_local:
        github_handle = _normalize_author_handle(email_local.rsplit("+", 1)[-1])
        if github_handle and (normalized_name is None or normalized_name == github_handle):
            merge_keys.append(f"handle:{github_handle}")

    if not email and normalized_name:
        merge_keys.append(f"name:{normalized_name}")
    if not merge_keys:
        merge_keys.append(f"identity:{identity.casefold()}")
    return list(dict.fromkeys(merge_keys))


def _author_display_priority(name: str | None, email: str | None) -> tuple[int, int]:
    email_local, email_domain = _parse_email_parts(email)
    normalized_name = _normalize_author_handle(name)
    normalized_local = _normalize_author_handle(email_local)

    priority = 0
    if email:
        priority = 3
        if email_domain == GITHUB_NOREPLY_DOMAIN:
            priority = 1
        elif normalized_name and normalized_local and normalized_name == normalized_local:
            priority = 4
    elif normalized_name:
        priority = 2
    return priority, -len((name or "") + (email or ""))


def _as_optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
