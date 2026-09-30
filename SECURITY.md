# Security Policy

JARVIS runs on your own Mac with access to your files, browser, email, calendar and shell, so security reports are taken seriously.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **[private vulnerability reporting](https://github.com/bertrandmbanwi/Jarvis/security/advisories/new)**. Don't open a public issue.

Include what you found, how to reproduce it, and what an attacker could do with it. You'll get an acknowledgement within a few days, and credit in the release notes if you'd like it.

## Scope

Especially interesting:

- Ways for a web page, email, document or other untrusted content to make JARVIS run tools (prompt injection that bypasses the approval prompt, cross-origin requests to the local API or WebSockets).
- Authentication bypasses on the tunnel/PIN remote-access path.
- Secret leakage (API keys, OAuth tokens) through logs, the UI or the API.
- Path traversal, command injection or SSRF in the built-in tools.

## Supported versions

Security fixes land on `main`. Please make sure you can reproduce the issue on the latest commit.
