"""Security utilities including SSRF validation."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFValidationError(ValueError):
    """Raised when an external URL fails SSRF safety validation."""
    pass


def validate_external_url(url: str) -> str:
    """
    Validate that an external URL is safe to download from.
    Blocks private IP ranges, loopback, link-local addresses, and non-HTTP protocols.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("URL must be a non-empty string.")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise SSRFValidationError(f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL missing hostname.")

    # Check for localhost / loopback strings
    lowered = hostname.lower()
    if lowered in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise SSRFValidationError("Requests to localhost/loopback are prohibited.")

    # Resolve hostname to IP and check for private / internal IP ranges
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SSRFValidationError(f"Could not resolve hostname '{hostname}': {e}")

    for addr_info in resolved_ips:
        ip_str = addr_info[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
            ):
                raise SSRFValidationError(
                    f"Resolved IP {ip_str} is in a private or restricted network range."
                )
        except ValueError:
            continue

    return url
