# upgrade-python

Adds support for a new Python version by building all packages, identifying failures, and marking them with `python_versions` restrictions.

## Usage

```
/upgrade-python <full-version>
```

Example: `/upgrade-python 3.14.3`

The argument is the full Python version (e.g., `3.14.3`). Derive the major.minor (`3.14`) and cpython tag (`cp314`) from it.

## Step 1: Modify files for single-version build mode

Edit these files to build ONLY the new Python version (this speeds up CI dramatically):

### `build.py` line 35
Change `PYTHONS` to only the new version:
```python
PYTHONS = ((3, 14),)  # temporarily building only new version
```

### `validate.py` line 19
Same change:
```python
PYTHONS = ((3, 14),)  # temporarily building only new version
```

### `docker/install-pythons` line 9
Change `VERSIONS` to only the new full version:
```python
VERSIONS = ("3.14.3",)  # temporarily building only new version
```

### `.github/workflows/build.yml`

**Lines 60-63** — keep only the new cpython PATH entry:
```yaml
    - run: |
        echo "$PWD/pythons/cp314-cp314/bin" >> "$GITHUB_PATH"
        echo "$PWD/venv/bin" >> "$GITHUB_PATH"
```

**Line 44** — add `--upgrade-python` flag to linux build command:
```yaml
    - run: python3 -um build --pypi-url https://pypi.devinfra.sentry.io --upgrade-python
```

**Line 66** — add `--upgrade-python` flag to macos build command:
```yaml
    - run: python3 -um build --pypi-url https://pypi.devinfra.sentry.io --upgrade-python
```

## Step 2: Commit and push

Commit all changes with a message like "build: single-version mode for Python 3.14 upgrade" and push.

## Step 3: Wait for CI, then download and parse logs

Wait for CI to complete (it will likely fail — that's expected).

Download logs from each build job using the GitHub CLI:

```bash
# Get the workflow run
gh run list --branch <current-branch> --limit 1

# Get job IDs from the run
gh run view <run-id> --json jobs --jq '.jobs[] | {name: .name, id: .databaseId, conclusion: .conclusion}'

# Download logs for each job
gh api repos/getsentry/pypi/actions/jobs/<job-id>/logs > job-<name>.log
```

Parse the logs to identify:
- **Succeeded packages**: lines matching `=== <name>==<version>@<python>` that are NOT followed by `!!! FAILED:`
- **Failed packages**: lines matching `!!! FAILED: <name>==<version>: <error message>`

A package is considered failed if it failed on ANY platform (linux-amd64, linux-arm64, macos).

## Step 4: Update `packages.ini`

In one pass:

1. **Comment out** all packages that **succeeded on all platforms** by prepending `# ` to their section header and all their settings lines. These don't need to rebuild.

2. **Add `python_versions = <MAJOR.MINOR`** to each **failed** package's section. Also add a comment above the `python_versions` line (max ~80 chars) summarizing why the build failed — extract this from the error in the logs (e.g., `# pyo3 0.22.2 only supports up to Python 3.13`).

3. **Do NOT modify** packages that already have a `python_versions` restriction that is stricter than or equal to the new version (e.g., if a package already has `python_versions = <3.13`, leave it alone).

## Step 5: Commit, push, repeat

Commit with a message like "mark python 3.14 build failures in packages.ini" and push.

Wait for CI again. If there are still failures, repeat steps 3-5 until CI is green.


## Important notes

- The `--upgrade-python` flag in `build.py` enables continue-on-failure mode with a 10-minute timeout per package. Without it, builds fail on first error (normal behavior).
- The `=== name==version@python` and `!!! FAILED: name==version: error` log lines are the markers used to parse results.
- When commenting out succeeded packages, comment out the entire section (`[name==version]` header + all config lines).
- Keep the ordering of sections in `packages.ini` the same.
