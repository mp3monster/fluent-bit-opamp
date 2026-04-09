#!/usr/bin/env python3
"""Install dependencies and generate a self-signed TLS certificate + key.

This script is intended for local development only.
Use `--help` for usage details and see docs/self_signed_tls_setup.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import os
import pathlib
import subprocess
import sys
from typing import Iterable

SCRIPT_DOC_PATH = "docs/self_signed_tls_setup.md"
DEFAULT_CERT_FILE = "certs/provider-server.pem"
DEFAULT_KEY_FILE = "certs/provider-server-key.pem"
DEFAULT_COMMON_NAME = "localhost"
DEFAULT_VALIDITY_DAYS = 365
DEFAULT_DNS_NAMES = ("localhost",)
DEFAULT_IP_ADDRESSES = ("127.0.0.1",)
PIP_INSTALL_CMD = (sys.executable, "-m", "pip", "install", "--upgrade", "cryptography")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install cert-generation dependency and create a self-signed TLS cert/key.",
        epilog=(
            "For step-by-step usage and configuration values, see "
            f"{SCRIPT_DOC_PATH}"
        ),
    )
    parser.add_argument(
        "--cert-file",
        default=DEFAULT_CERT_FILE,
        help=f"Output certificate path (default: {DEFAULT_CERT_FILE})",
    )
    parser.add_argument(
        "--key-file",
        default=DEFAULT_KEY_FILE,
        help=f"Output private key path (default: {DEFAULT_KEY_FILE})",
    )
    parser.add_argument(
        "--common-name",
        default=DEFAULT_COMMON_NAME,
        help=f"Certificate common name (default: {DEFAULT_COMMON_NAME})",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_VALIDITY_DAYS,
        help=f"Validity period in days (default: {DEFAULT_VALIDITY_DAYS})",
    )
    parser.add_argument(
        "--dns-name",
        action="append",
        default=[],
        help=(
            "DNS SAN entry. Repeat for multiple values. "
            "Example: --dns-name localhost --dns-name provider.local"
        ),
    )
    parser.add_argument(
        "--ip-address",
        action="append",
        default=[],
        help=(
            "IP SAN entry. Repeat for multiple values. "
            "Example: --ip-address 127.0.0.1 --ip-address 10.0.0.5"
        ),
    )
    parser.add_argument(
        "--skip-dependency-install",
        action="store_true",
        help=(
            "Do not auto-install Python dependency when missing. "
            "If cryptography is unavailable, the script will fail."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output files if they already exist.",
    )
    return parser.parse_args()


def ensure_dependency(skip_install: bool) -> None:
    """Ensure the cryptography package is available, optionally installing it."""
    try:
        import cryptography  # noqa: F401
    except ImportError:
        if skip_install:
            raise RuntimeError(
                "Missing dependency: cryptography. "
                "Install it with: python -m pip install --upgrade cryptography"
            ) from None

        print("[INFO] Installing dependency: cryptography")
        subprocess.run(PIP_INSTALL_CMD, check=True)
        try:
            import cryptography  # noqa: F401
        except ImportError as err:
            raise RuntimeError(
                "Failed to import cryptography after install. "
                "Check your Python environment and pip configuration."
            ) from err


def _dedupe(items: Iterable[str]) -> list[str]:
    """Return items in input order with duplicates removed."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _prepare_output_path(path_str: str, *, force: bool) -> pathlib.Path:
    """Validate and prepare output path for writing."""
    path = pathlib.Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"Output already exists: {path}. Use --force to overwrite.")
    return path


def generate_self_signed_certificate(
    *,
    cert_path: pathlib.Path,
    key_path: pathlib.Path,
    common_name: str,
    validity_days: int,
    dns_names: list[str],
    ip_addresses: list[str],
) -> None:
    """Generate and write self-signed certificate + private key."""
    if validity_days <= 0:
        raise ValueError("--days must be a positive integer")

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    san_entries: list[x509.GeneralName] = []
    for dns_name in dns_names:
        if dns_name:
            san_entries.append(x509.DNSName(dns_name))

    for ip_text in ip_addresses:
        try:
            ip_value = ipaddress.ip_address(ip_text)
        except ValueError as err:
            raise ValueError(f"Invalid --ip-address value: {ip_text}") from err
        san_entries.append(x509.IPAddress(ip_value))

    if not san_entries:
        raise ValueError("At least one SAN entry is required. Provide --dns-name or --ip-address.")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "GB"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpAMP Local Development"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    utc_now = dt.datetime.now(dt.timezone.utc)

    cert_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(utc_now - dt.timedelta(minutes=5))
        .not_valid_after(utc_now + dt.timedelta(days=validity_days))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    )

    certificate = cert_builder.sign(private_key=private_key, algorithm=hashes.SHA256())

    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_bytes = certificate.public_bytes(encoding=serialization.Encoding.PEM)

    key_path.write_bytes(key_bytes)
    cert_path.write_bytes(cert_bytes)

    if os.name != "nt":
        os.chmod(key_path, 0o600)


def main() -> int:
    """Program entrypoint."""
    args = parse_args()

    cert_path = _prepare_output_path(args.cert_file, force=args.force)
    key_path = _prepare_output_path(args.key_file, force=args.force)

    dns_names = _dedupe(args.dns_name or list(DEFAULT_DNS_NAMES))
    ip_addresses = _dedupe(args.ip_address or list(DEFAULT_IP_ADDRESSES))

    ensure_dependency(skip_install=args.skip_dependency_install)

    generate_self_signed_certificate(
        cert_path=cert_path,
        key_path=key_path,
        common_name=str(args.common_name).strip() or DEFAULT_COMMON_NAME,
        validity_days=int(args.days),
        dns_names=dns_names,
        ip_addresses=ip_addresses,
    )

    print("[OK] Self-signed certificate created")
    print(f"      cert: {cert_path}")
    print(f"      key : {key_path}")
    print(f"[INFO] See {SCRIPT_DOC_PATH} for configuration updates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
