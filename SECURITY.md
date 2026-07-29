# Security Policy

Report vulnerabilities privately via GitHub's **"Report a vulnerability"** (Security →
Advisories) on this repository — not as public issues.

Scope notes for reporters: the assurance store is an encrypted SQLCipher database whose
key lives in the OS keychain/credential vault; the public signals database is
deliberately restricted to TLP:WHITE content; the backend binds to localhost by default
and the compose deployment fronts it with a reverse proxy. Findings that break any of
those boundaries are exactly what this policy is for.

Supported versions: the latest tagged release and `main`.
