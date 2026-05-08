# GitHub Actions CI/CD — Design Proposal

## Repository Overview

Monorepo with 4 independent packages under `packages/`:

| Package | PyPI Name | Tests | Key Deps |
|---------|-----------|-------|----------|
| `sdk` | `agent-builder-sdk-aws-transform` | 87 test files | boto3, fastapi, mcp, strands-agents, uvicorn |
| `mcp-server` | `agent-builder-mcp-aws-transform` | 9 test files | mcp, anyio, rank-bm25, boto3 |
| `mcp-client` | `agent-builder-mcp-client-aws-transform` | 2 test files | mcp, anyio, trio |
| `types` | `agent-builder-types` | 0 tests | boto3 |

Build system: setuptools + wheel. Python >=3.10. Tests: pytest + pytest-asyncio. License: Apache-2.0.

## Current Gaps

- No CI/CD at all (no `.github/` directory)
- No linting/formatting config (no ruff, mypy, flake8)
- No inter-package dependency declarations (SDK uses types at runtime but doesn't declare it)
- No type-checking setup despite `py.typed` markers

---

## Option A: Single Workflow, Matrix Over Packages

```
.github/workflows/ci.yml
```

One workflow with a job matrix iterating over packages. Each matrix entry installs deps and runs tests. Publish job triggers on tags.

```yaml
# Conceptual structure
jobs:
  test:
    strategy:
      matrix:
        package: [sdk, mcp-server, mcp-client, types]
    steps:
      - install packages/${{ matrix.package }}
      - run pytest
  publish:
    if: startsWith(github.ref, 'refs/tags/')
    needs: test
```

### Pros
- Dead simple — one file to maintain
- Easy to understand for new contributors
- Low operational overhead

### Cons
- All packages run on every push (no path filtering)
- If one package's tests are flaky, it blocks the entire CI
- Publishing logic gets complex for independent versioning

### Ratings
| Dimension | Score |
|-----------|-------|
| Simplicity | 9/10 |
| CI Speed | 5/10 |
| Correctness | 7/10 |
| Developer Experience | 6/10 |
| Scalability | 4/10 |

---

## Option B: Per-Package Workflows with Path Filters

```
.github/workflows/ci-sdk.yml
.github/workflows/ci-mcp-server.yml
.github/workflows/ci-mcp-client.yml
.github/workflows/ci-types.yml
.github/workflows/publish.yml
```

Each package gets its own workflow triggered only when its files change. Separate publish workflow handles PyPI releases.

```yaml
# ci-sdk.yml conceptual structure
on:
  push:
    paths: ["packages/sdk/**"]
  pull_request:
    paths: ["packages/sdk/**"]
jobs:
  test:
    steps:
      - install packages/sdk
      - run pytest
```

### Pros
- Fast — only affected packages run
- Clear ownership per package
- Independent failure isolation

### Cons
- 5 workflow files with duplicated boilerplate
- Doesn't catch cross-package breakage (changing types won't re-test SDK)
- Path filter maintenance overhead as files move

### Ratings
| Dimension | Score |
|-----------|-------|
| Simplicity | 6/10 |
| CI Speed | 9/10 |
| Correctness | 5/10 |
| Developer Experience | 7/10 |
| Scalability | 6/10 |

---

## Option C: Reusable Workflow + Per-Package Callers

```
.github/workflows/_test-package.yml    — reusable (called)
.github/workflows/ci.yml               — orchestrator
.github/workflows/publish.yml          — release to PyPI
```

A reusable workflow defines test/lint/build steps parameterized by package path. The orchestrator calls it once per package. An integration job installs all packages together and verifies cross-package imports. Publish uses `workflow_dispatch` with a package selector.

```yaml
# _test-package.yml (reusable)
on:
  workflow_call:
    inputs:
      package-path:
        type: string
      python-versions:
        type: string
        default: '["3.10", "3.11", "3.12"]'
jobs:
  test:
    strategy:
      matrix:
        python-version: ${{ fromJson(inputs.python-versions) }}
    steps:
      - install ${{ inputs.package-path }}
      - lint with ruff
      - run pytest

# ci.yml (orchestrator)
jobs:
  sdk:
    uses: ./.github/workflows/_test-package.yml
    with:
      package-path: packages/sdk
  mcp-server:
    uses: ./.github/workflows/_test-package.yml
    with:
      package-path: packages/mcp-server
  integration:
    needs: [sdk, mcp-server, mcp-client, types]
    steps:
      - install all packages
      - verify cross-package imports
```

### Pros
- DRY — test logic defined once, called N times
- Integration job catches cross-package issues
- Clean separation: CI vs publishing
- Easy to add new packages (one caller block)

### Cons
- Reusable workflow syntax has learning curve
- Slightly more complex than Option A
- GitHub's `paths` + reusable workflows interaction can be unintuitive

### Ratings
| Dimension | Score |
|-----------|-------|
| Simplicity | 7/10 |
| CI Speed | 8/10 |
| Correctness | 9/10 |
| Developer Experience | 8/10 |
| Scalability | 9/10 |

---

## Option D: Change Detection Script + Dynamic Matrix

```
.github/workflows/ci.yml
.github/workflows/publish.yml
scripts/detect-changes.py
```

A single CI workflow runs a detection script that outputs affected packages (via `git diff`), then dynamically generates the job matrix. Only affected packages + their dependents run.

```yaml
jobs:
  detect:
    outputs:
      matrix: ${{ steps.detect.outputs.packages }}
    steps:
      - run: python scripts/detect-changes.py >> $GITHUB_OUTPUT
  test:
    needs: detect
    strategy:
      matrix:
        package: ${{ fromJson(needs.detect.outputs.matrix) }}
    steps:
      - install packages/${{ matrix.package }}
      - run pytest
```

```python
# scripts/detect-changes.py (conceptual)
DEPENDENCY_GRAPH = {
    "types": [],
    "sdk": ["types"],
    "mcp-server": [],
    "mcp-client": [],
}
# Outputs affected packages + transitive dependents
```

### Pros
- Most efficient — truly minimal CI runs
- Handles dependency graph (changing types triggers SDK tests too)
- Single workflow file

### Cons
- Most complex to implement and debug
- Custom script becomes load-bearing infrastructure
- Dynamic matrices are harder to reason about in PR checks
- Overkill for 4 packages

### Ratings
| Dimension | Score |
|-----------|-------|
| Simplicity | 4/10 |
| CI Speed | 10/10 |
| Correctness | 10/10 |
| Developer Experience | 6/10 |
| Scalability | 10/10 |

---

## Summary Comparison

| Dimension | A (Single) | B (Per-Pkg) | C (Reusable) | D (Dynamic) |
|-----------|:---:|:---:|:---:|:---:|
| Simplicity | 9 | 6 | 7 | 4 |
| CI Speed | 5 | 9 | 8 | 10 |
| Correctness | 7 | 5 | 9 | 10 |
| Dev Experience | 6 | 7 | 8 | 6 |
| Scalability | 4 | 6 | 9 | 10 |
| **Total** | **31** | **33** | **41** | **40** |

## Recommendation

**Option C** — best balance of correctness, maintainability, and developer experience for a 4-package open-source monorepo at this stage.

## Additional CI Considerations

Regardless of option chosen:

1. **Linting**: Add `ruff` (replaces flake8 + black + isort in one fast tool)
2. **Type checking**: Consider `pyright` or `mypy` — especially since `types` package exists
3. **Python matrix**: 3.10, 3.11, 3.12
4. **PyPI publishing**: Use trusted publishers (OIDC) — no API tokens stored in secrets
5. **Dependency note**: `strands-agents>=1.30.0` may not be on public PyPI — need to verify before CI can install it
6. **Inter-package deps**: SDK should declare dependency on `agent-builder-types` in its pyproject.toml
