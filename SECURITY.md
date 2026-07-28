# Security Policy

## Supported Versions

Security fixes are accepted for the active development branch until the project
publishes versioned releases.

## Reporting a Vulnerability

Report suspected vulnerabilities privately through the repository security
advisory flow or by contacting the maintainers through the project's approved
private channel.

Do not publish exploit details, credentials, private keys, tokens, account
identifiers, or raw sensitive payloads in public issues, pull requests, logs, or
fixtures.

## Secret Handling

Secrets must not be committed. This includes exchange credentials, bearer
tokens, private keys, signing secrets, database passwords, live account
identifiers, and captured authorization headers.

If a secret is suspected to have been committed:

1. Treat it as compromised.
2. Revoke or rotate it outside the repository.
3. Notify maintainers through the private reporting channel.
4. Preserve enough audit context for remediation without republishing the
   secret value.

## Disclosure

Maintainers will coordinate validation, remediation, and disclosure timing based
on severity, exposure, and operational risk.
