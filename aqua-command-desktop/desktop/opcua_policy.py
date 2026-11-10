"""
OPC UA SecurityPolicy Definitions and Strict Allowlist Validator (SEC-04).
Adheres strictly to OPC UA Part 4 and Part 7 specifications.
"""

from typing import Any

# Canonical Policy Identifiers
POLICY_NONE = "None"
POLICY_BASIC256SHA256 = "Basic256Sha256"

# Standard OPC UA SecurityPolicy URIs
URI_POLICY_NONE = "http://opcfoundation.org/UA/SecurityPolicy#None"
URI_POLICY_BASIC256SHA256 = "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256"

# Strict Allowlist: Maps recognized string representations to canonical policy names
ALLOWED_SECURITY_POLICIES = {
    POLICY_NONE.lower(): POLICY_NONE,
    URI_POLICY_NONE.lower(): POLICY_NONE,
    POLICY_BASIC256SHA256.lower(): POLICY_BASIC256SHA256,
    URI_POLICY_BASIC256SHA256.lower(): POLICY_BASIC256SHA256,
}

# Explicitly forbidden / insecure policies that must be rejected with explicit error
DEPRECATED_OR_FORBIDDEN_POLICIES = {
    "basic128rsa15": "Basic128Rsa15 is cryptographically deprecated and forbidden by IEC 62541.",
    "http://opcfoundation.org/ua/securitypolicy#basic128rsa15": "Basic128Rsa15 is cryptographically deprecated and forbidden.",
    "basic256": "Basic256 (SHA-1) is cryptographically broken and forbidden by IEC 62541.",
    "http://opcfoundation.org/ua/securitypolicy#basic256": "Basic256 (SHA-1) is cryptographically broken and forbidden.",
}


def normalize_security_policy(policy_input: Any) -> str:
    """
    Validates and normalizes OPC UA SecurityPolicy input against the strict allowlist.
    Returns canonical policy name: 'None' or 'Basic256Sha256'.
    Raises ValueError on invalid, empty, unsupported, malformed, or deprecated policy.
    """
    if not policy_input or not isinstance(policy_input, str):
        raise ValueError(
            f"SEC-04: Invalid SecurityPolicy value: {repr(policy_input)}. "
            f"Allowed policies are 'None' and 'Basic256Sha256'."
        )

    cleaned = policy_input.strip()
    if not cleaned:
        raise ValueError(
            "SEC-04: SecurityPolicy cannot be empty or whitespace. "
            "Allowed policies are 'None' and 'Basic256Sha256'."
        )

    lowered = cleaned.lower()

    if lowered in DEPRECATED_OR_FORBIDDEN_POLICIES:
        raise ValueError(f"SEC-04: Insecure SecurityPolicy rejected: {DEPRECATED_OR_FORBIDDEN_POLICIES[lowered]}")

    if lowered in ALLOWED_SECURITY_POLICIES:
        return ALLOWED_SECURITY_POLICIES[lowered]

    raise ValueError(
        f"SEC-04: Unsupported or unrecognized OPC UA SecurityPolicy: '{policy_input}'. "
        f"Allowed policies: '{POLICY_NONE}' ({URI_POLICY_NONE}), "
        f"'{POLICY_BASIC256SHA256}' ({URI_POLICY_BASIC256SHA256})."
    )


def assert_secure_channel_for_auth(policy: str, auth_mode: str) -> None:
    """
    Enforces that Username/Password credentials are NEVER transmitted over an unencrypted channel.
    Raises PermissionError if auth_mode is Username but SecurityPolicy is None or unencrypted.
    """
    canonical_policy = normalize_security_policy(policy)
    auth_normalized = (auth_mode or "Anonymous").strip()

    if auth_normalized.lower() in ("username", "user_password"):
        if canonical_policy == POLICY_NONE:
            raise PermissionError(
                "SEC-04: Plaintext username/password is strictly forbidden when SecurityPolicy is None. "
                "Encrypted session (Basic256Sha256) is mandatory for credential transmission."
            )
