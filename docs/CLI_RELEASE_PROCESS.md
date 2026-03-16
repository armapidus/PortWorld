# CLI Release Process

This documents the tagged release flow for the public `portworld` CLI.

## Version Source

- The packaged CLI version is sourced from `backend.__version__`.
- Git tags should use the format `vX.Y.Z`.
- The public installer resolves `latest` from GitHub Releases and installs the matching PyPI package version.

## Required External Setup

- Create matching `portworld` projects on PyPI and TestPyPI, or configure the chosen package name from `pyproject.toml`.
- Add a Trusted Publisher on both indexes for:
  - owner/repo: `armapidus/PortWorld`
  - workflow: `.github/workflows/cli-release.yml`
  - environment: `testpypi` on TestPyPI and `pypi` on PyPI
- Create GitHub Actions environments named `testpypi` and `pypi`.
- Use annotated tags so the GitHub Release can reuse the tag message via `gh release create --notes-from-tag`.

## Release Steps

1. Update `backend/__init__.py`
   - bump `__version__` to the intended release version, for example `0.2.0`
2. Verify local packaging and CLI smoke
   - `python -m py_compile $(find portworld_cli -name '*.py' | sort) backend/cli.py`
   - `python -m portworld_cli.main --help`
   - `python -m portworld_cli.main providers list`
   - `python -m portworld_cli.main update cli --json`
3. Verify installer syntax and non-interactive path
   - `bash -n install.sh`
   - if needed, use `PORTWORLD_INSTALL_SOURCE_URL=. PORTWORLD_NO_INIT=1 PORTWORLD_NON_INTERACTIVE=1 bash install.sh`
4. Commit the version bump and related release notes/docs
5. Create an annotated tag
   - `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
6. Push the branch and tag
   - `git push origin <branch>`
   - `git push origin vX.Y.Z`
7. Wait for the `CLI Release` workflow on the pushed tag
   - `validate`: assert `vX.Y.Z` matches `backend.__version__` and capture the package name from `pyproject.toml`
   - `build`: build sdist and wheel once, then upload them as the shared workflow artifact
   - `publish_testpypi`: publish the built artifacts to TestPyPI through trusted publishing
   - `smoke_testpypi`: install the exact version from TestPyPI with `uv tool install` in a clean job and run CLI smoke commands
   - `publish_pypi`: publish the same downloaded artifacts to PyPI through trusted publishing
   - `github_release`: attach the same artifacts to the GitHub Release for the tag
8. Verify the public install paths against the new release
   - installer: `curl -fsSL --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/armapidus/PortWorld/main/install.sh | bash`
   - pinned installer: `curl -fsSL --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/armapidus/PortWorld/main/install.sh | bash -s -- --version vX.Y.Z`
   - manual fallback: `uv tool install "portworld==X.Y.Z"`

## Post-Release Smoke

- `portworld --help`
- `portworld init --help`
- `portworld providers list`
- `portworld update cli --json`

## Notes

- Source-checkout developer installs remain `pipx install . --force`.
- `cli-smoke` continues to run on branch pushes and pull requests only; tag pushes are owned by `cli-release`.
- `publish_pypi` depends on a successful TestPyPI publish and TestPyPI smoke pass.
- The release workflow never rebuilds after validation; PyPI and GitHub Release both reuse the `build` job artifacts.
- The public bootstrap installs `uv` automatically and downloads Python 3.11+ when needed.
