# Self-Signed TLS Certificate Setup

This guide shows how to use `scripts/generate_self_signed_tls_cert.py` to:

1. install required Python dependency (`cryptography`), and
2. generate a self-signed TLS certificate and private key for local provider HTTPS testing.

## Script Location

- Script: `scripts/generate_self_signed_tls_cert.py`
- Help: `python scripts/generate_self_signed_tls_cert.py --help`

The script `--help` output points to this document.

## What The Script Generates

By default, the script writes:

- certificate: `certs/provider-server.pem`
- private key: `certs/provider-server-key.pem`

Default SAN values:

- DNS: `localhost`
- IP: `127.0.0.1`

## Usage

Linux/macOS:

```bash
python3 scripts/generate_self_signed_tls_cert.py
```

Windows (cmd or PowerShell):

```powershell
python scripts/generate_self_signed_tls_cert.py
```

## Common Options

```bash
python3 scripts/generate_self_signed_tls_cert.py \
  --cert-file certs/provider-server.pem \
  --key-file certs/provider-server-key.pem \
  --common-name localhost \
  --dns-name localhost \
  --dns-name provider.local \
  --ip-address 127.0.0.1 \
  --days 365 \
  --force
```

If dependency auto-install is not desired:

```bash
python3 scripts/generate_self_signed_tls_cert.py --skip-dependency-install
```

## Configuration Updates Required

Apply the following values where relevant.

## 1) Provider Config (`config/opamp.json`)

Add/update `provider.tls`:

```json
{
  "provider": {
    "tls": {
      "cert_file": "certs/provider-server.pem",
      "key_file": "certs/provider-server-key.pem",
      "trust_anchor_mode": "none"
    }
  }
}
```

If you start provider with `scripts/run_opamp_server.sh --https` or
`scripts\\run_opamp_server.cmd --https`, this block is generated/updated automatically.

Also ensure the consumer URL in the same file uses HTTPS:

```json
{
  "consumer": {
    "server_url": "https://localhost:8080"
  }
}
```

## 2) Fluentd Consumer Config (`consumer/opamp-fluentd.json`)

Set:

```json
{
  "consumer": {
    "server_url": "https://localhost:8080"
  }
}
```

## Self-Signed Certificate Impact: CA Validation

A self-signed server certificate is not chained to a public CA. If the consumer is doing strict CA validation, HTTPS validation will fail unless you disable verification or trust that cert/CA explicitly.

For the TLS model documented in `docs/tls_https_mtls_revision.md`, the impacted client setting is:

```json
{
  "consumer": {
    "tls": {
      "verify_server": false
    }
  }
}
```

Use `verify_server=false` for local development only.

## Recommended Development-Only Pattern

1. Generate the self-signed certificate/key with the script.
2. Enable provider TLS using the generated files.
3. Point consumer `server_url` to `https://...`.
4. Disable client CA verification for local self-signed usage (`consumer.tls.verify_server=false`).

## Troubleshooting

- `Missing dependency: cryptography`
  - Re-run without `--skip-dependency-install`, or install manually:
    - `python -m pip install --upgrade cryptography`
- Certificate hostname mismatch
  - Ensure the host in `server_url` is included in SAN entries (`--dns-name`, `--ip-address`).
- Existing output files
  - Use `--force` to overwrite existing cert/key files.
