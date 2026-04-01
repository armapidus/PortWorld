# PortWorld

PortWorld is an open-source runtime for voice-and-vision assistants connected to the real world.
The supported public slice today is:

- a FastAPI backend for realtime sessions, memory, and provider routing
- the `portworld` CLI for local bootstrap, self-hosting, and managed deploy workflows
- an iOS app that connects a self-hosted PortWorld backend to Meta smart glasses

## Status

PortWorld is shipped as a stable public `v0.x` project.
The supported surfaces are usable today, but the repository is still under active improvement.

- Stable first-class surfaces: `backend/`, `portworld_cli/`, `portworld_shared/`, `IOS/`
- Supported but still hardening: managed cloud deploy defaults and public-facing operator docs
- Not part of the public supported surface: old experimental/internal materials that are no longer tracked in the repo

## Who This Repo Is For

- operators who want to run PortWorld locally or on managed cloud targets
- contributors working on the backend, CLI, or iOS app
- teams building a self-hosted assistant flow around PortWorld's runtime and provider integrations

## Minimum Requirements

### Backend and CLI

- macOS or Linux
- Python 3.11+
- Docker and Docker Compose for the default local operator path
- Node.js/npm/npx only when using Node-based MCP extensions outside the published/container path

### iOS

- iPhone-focused app targeting iOS 17.0+
- Xcode with iOS 17 support
- a reachable PortWorld backend for meaningful runtime validation

## Supported Workflows

### 1. Default public operator path

This is the fastest working path for someone who wants to run PortWorld locally without developing the repo itself.

```bash
curl -fsSL --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/portworld/PortWorld/main/install.sh | bash
portworld init
cd ~/.portworld/stacks/default
docker compose up -d
portworld doctor --target local
portworld status
```

### 2. Source-checkout contributor path

Use this when you are editing PortWorld itself.

```bash
git clone https://github.com/portworld/PortWorld.git
cd PortWorld
pipx install . --force
portworld init
```

### 3. Backend-only contributor path

This is the fastest working backend path from a repo checkout.

```bash
git clone https://github.com/portworld/PortWorld.git
cd PortWorld
cp backend/.env.example backend/.env
docker compose up --build
curl http://127.0.0.1:8080/livez
```

`backend/.env.example` is the canonical environment reference.
At minimum, set the provider credentials required for the runtime mode you choose.

### 4. iOS contributor path

```bash
git clone https://github.com/portworld/PortWorld.git
cd PortWorld
cp backend/.env.example backend/.env
docker compose up --build
open IOS/PortWorld.xcodeproj
```

Then:

1. Build the `PortWorld` scheme.
2. Configure the backend base URL in the app or local config template.
3. Validate backend setup in-app against the running local deployment.

### 5. Managed deploys

The public CLI supports these managed targets:

- `gcp-cloud-run`
- `aws-ecs-fargate`
- `azure-container-apps`

Readiness example:

```bash
portworld doctor --target gcp-cloud-run --gcp-project <project> --gcp-region <region>
portworld doctor --target aws-ecs-fargate --aws-region <region>
portworld doctor --target azure-container-apps --azure-subscription <subscription> --azure-resource-group <resource-group> --azure-region <region>
```

Managed deploys are part of the supported surface, but some production hardening remains the operator's responsibility.
Optional provider integrations are also part of the supported surface when configured through the documented provider IDs and required environment variables.

## Repository Layout

- `backend/`: active backend runtime, local self-hosting path, and provider/runtime configuration
- `portworld_cli/`: public CLI/operator workflow
- `portworld_shared/`: shared contracts used by the backend and CLI
- `IOS/`: active iOS client app
- `docs/operations/`: release and operator documentation
- `docs/open-source/`: repository opening and publication checklist
- `.github/`: CI, release automation, and contribution templates

## What Works Today

- local backend self-hosting with documented health/readiness checks
- published-workspace local operator flow through `portworld init`
- managed deploy flows for GCP Cloud Run, AWS ECS/Fargate, and Azure Container Apps
- optional provider integrations documented in `backend/README.md` and `portworld providers`
- iOS onboarding, backend validation, and active Meta/glasses runtime path
- released CLI installation through PyPI/TestPyPI, GitHub Releases, and the bootstrap installer

## Major Limitations

- provider credentials are required for meaningful runtime use; there is no no-key production path
- managed deploy defaults still need explicit operator review before internet-facing production rollout
- iOS runtime validation depends on a reachable backend and, for full product validation, supported Meta hardware/app setup
- the shared iOS schemes do not currently provide a meaningful maintained Xcode test action

## Security And Community

- Security policy: [SECURITY.md](SECURITY.md)
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Open-source readiness checklist: [docs/open-source/OPEN_SOURCE_READINESS_CHECKLIST.md](docs/open-source/OPEN_SOURCE_READINESS_CHECKLIST.md)

Do not post secrets, tokens, private URLs, or unredacted production logs in public issues.

## Releases

- Changelog: [CHANGELOG.md](CHANGELOG.md)
- GitHub Releases: <https://github.com/portworld/PortWorld/releases>
- CLI release process: [docs/operations/CLI_RELEASE_PROCESS.md](docs/operations/CLI_RELEASE_PROCESS.md)

## Additional Documentation

- Backend runtime: [backend/README.md](backend/README.md)
- CLI/operator workflow: [portworld_cli/README.md](portworld_cli/README.md)
- iOS app: [IOS/README.md](IOS/README.md)

## License

This repository is licensed under the MIT License.
See [LICENSE](LICENSE).
