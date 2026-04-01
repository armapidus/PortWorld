# PortWorld CLI

`portworld` is the command-line interface for setting up PortWorld locally, validating environments, and deploying PortWorld to supported cloud targets.

It supports two workflows:

- published workspace: run PortWorld locally without cloning the repo
- source checkout: work from a PortWorld repository clone for development

Supported environments:

- macOS and Linux
- Python 3.11+
- Docker for local published-workspace runs

## Install

Recommended install:

```bash
uv tool install portworld
```

Alternative install with `pipx`:

```bash
pipx install portworld
```

Convenience bootstrap installer:

```bash
curl -fsSL --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/portworld/PortWorld/main/install.sh | bash
```

The bootstrap can install `uv`, provision Python 3.11+ when needed, and bootstrap Node.js tooling for MCP launchers.

## Quickstart

The default public flow is a published workspace backed by a released backend image:

```bash
portworld init
cd ~/.portworld/stacks/default
docker compose up -d
portworld doctor --target local
portworld status
```

`portworld init` supports two setup modes:

- `quickstart`: minimal prompts with safe defaults
- `manual`: full explicit setup flow

You can force either mode:

```bash
portworld init --setup-mode quickstart
portworld init --setup-mode manual
```

This flow creates a local workspace, pins a released backend image, and lets you run PortWorld without cloning the repository.

## Source Checkout Workflow

Use a repo checkout when you are developing PortWorld itself:

```bash
pipx install . --force
portworld init
```

Source-checkout installs are intended for contributors, local development, and repo-backed changes.

## Managed Cloud Deploys

Supported managed targets:

- `gcp-cloud-run`
- `aws-ecs-fargate`
- `azure-container-apps`

Typical readiness and deploy flow:

```bash
portworld doctor --target gcp-cloud-run --gcp-project <project> --gcp-region <region>
portworld deploy gcp-cloud-run --project <project> --region <region> --cors-origins https://app.example.com

portworld doctor --target aws-ecs-fargate --aws-region <region>
portworld deploy aws-ecs-fargate --region <region> --cors-origins https://app.example.com

portworld doctor --target azure-container-apps --azure-subscription <subscription> --azure-resource-group <resource-group> --azure-region <region>
portworld deploy azure-container-apps --subscription <subscription> --resource-group <resource-group> --region <region> --cors-origins https://app.example.com
```

Managed log examples:

```bash
portworld logs gcp-cloud-run --since 24h --limit 50
portworld logs aws-ecs-fargate --since 24h --limit 50
portworld logs azure-container-apps --since 24h --limit 50
```

`portworld update deploy` redeploys the currently active managed target from workspace state and config.

Current MVP hardening notes:

- AWS one-click deploy currently provisions RDS with public accessibility and broad ingress
- Azure one-click deploy currently provisions PostgreSQL with public access
- treat these defaults as validation-only until production hardening is complete

## Main Commands

- `portworld init`: initialize or refresh a published workspace or source checkout
- `portworld doctor`: validate local or managed readiness
- `portworld deploy`: deploy PortWorld to a managed target
- `portworld status`: inspect workspace and deploy state
- `portworld logs`: read managed deployment logs
- `portworld config`: inspect or edit project configuration
- `portworld providers`: list supported providers
- `portworld update`: upgrade the CLI or redeploy the active managed target
- `portworld ops`: run lower-level operator tasks

## Updating

Upgrade an installed CLI:

```bash
uv tool upgrade portworld
```

Install a pinned release:

```bash
uv tool install "portworld==<version>"
```

Run the bootstrap installer for a specific tag:

```bash
curl -fsSL --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/portworld/PortWorld/main/install.sh | bash -s -- --version v<version>
```

## TestPyPI

For TestPyPI validation, use one of these commands:

```bash
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "portworld==<version>"
```

```bash
uv tool install --default-index https://test.pypi.org/simple --index https://pypi.org/simple "portworld==<version>"
```

The bare install snippet shown on TestPyPI may be incomplete because not every transitive dependency is necessarily hosted there.

## More Documentation

- Backend runtime and self-hosting: [backend/README.md](https://github.com/portworld/PortWorld/blob/main/backend/README.md)
- Operator quickstart and self-hosting notes: [docs/operations/BACKEND_SELF_HOSTING.md](https://github.com/portworld/PortWorld/blob/main/docs/operations/BACKEND_SELF_HOSTING.md)
- CLI release process: [docs/operations/CLI_RELEASE_PROCESS.md](https://github.com/portworld/PortWorld/blob/main/docs/operations/CLI_RELEASE_PROCESS.md)
- Changelog: [CHANGELOG.md](https://github.com/portworld/PortWorld/blob/main/CHANGELOG.md)
