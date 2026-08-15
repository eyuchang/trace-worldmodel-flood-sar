# ADR: remote annotated-tag identity for Reference recovery v2

## Decision

Verify authorization-tag type and target through the GitHub Git-data API,
independently of the checkout-local tag ref.

For the fixed expected tag, the workflow reads the remote tag ref, requires an
object of type `tag`, reads that exact tag object, and requires it to target the
workflow's `GITHUB_SHA` as a commit. The returned JSON is stored only in the
runner's private temporary directory. The workflow also requires tag-push ref
identity, run attempt 1, and detached `HEAD == GITHUB_SHA`.

## Context

In recovery-v1, `actions/checkout` fetched the annotated tag and subsequently
updated the same local ref to its peeled commit while preparing the requested
checkout. A local `git cat-file -t <tag>` check therefore returned `commit` even
though the pushed remote object remained an annotated tag. The workflow stopped
before it inspected either predecessor lifecycle or any protected seed.

## Alternatives considered

- Increasing checkout depth does not prevent the local ref replacement.
- Trusting `GITHUB_REF_TYPE=tag` does not distinguish annotated from lightweight
  tags.
- Parsing `git ls-remote` can verify a peeled ref, but the Git-data API provides
  explicit object types and exact object identities for both verification and
  audit.
- Moving or retrying the v1 tag would erase the once-only lifecycle and is
  prohibited.

## Consequences

The v2 identity guard requires read-only repository API access, already present
in the workflow's permissions. A checkout implementation may normalize local
refs without invalidating remote authorization evidence. Failure to retrieve,
parse, type-check, or match either remote object stops before protected
derivation. The workflow records no protected values while performing this
check.
