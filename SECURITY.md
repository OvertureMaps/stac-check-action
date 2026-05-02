# Security Policy

## Supported versions

Only the latest released version on the current major receives security updates. Older majors and older patch releases within the current major do not receive backports. Pin to a SHA in production (see [README](./README.md#pinning)).

| Version | Supported |
|---------|-----------|
| Latest release on the current major (e.g. newest `v1.y.z`) | Yes |
| Older `v1.y.z` releases | No |
| Older majors (e.g. `v0.x`) | No |

## Reporting a vulnerability

Do not open a public issue for security vulnerabilities.

Use GitHub's [private vulnerability reporting](https://github.com/lowlydba/stac-check-action/security/advisories/new). Acknowledgement target: 72 hours.

Include:

- Affected version (tag or SHA).
- Reproduction steps or proof-of-concept.
- Impact assessment (confidentiality / integrity / availability).
- Suggested fix, if any.

## Scope

This action is a thin composite wrapper around the upstream [`stac-check`](https://github.com/stac-utils/stac-check) CLI. Vulnerabilities in `stac-check` itself should be reported to the [stac-utils](https://github.com/stac-utils/stac-check/security) project.

In scope here:

- Shell argument construction and injection vectors.
- Permission escalation paths.
- Secret exposure.
- Supply chain (action SHA pinning, dependency declarations).

## Disclosure

Coordinated disclosure preferred. Embargo period negotiable based on severity.
