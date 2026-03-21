# Backend Tools And MCP Extension Plan

Date: 2026-03-21

## Summary

- Build the feature on the active packaged surfaces, `portworld_cli/` and `backend/`, not on the older `framework/` hooks.
- Add a workspace-scoped extension system that lets developers discover, install, enable, validate, and expose custom tools and MCP servers through a dedicated `.portworld/extensions.json`.
- Unify backend execution so built-in tools, Python extension tools, and MCP-discovered tools all feed the same `RealtimeToolRegistry`.
- Ship a curated CLI catalog for official extensions, plus local manifest entries and optional Python package entry points for custom ones.

## Key Changes

### Workspace manifest

- Add `.portworld/extensions.json` with schema version, installed entries, local custom definitions, enabled state, install metadata, and per-extension env bindings.
- Keep `.portworld/project.json` focused on core runtime/deploy settings; the CLI writes `PORTWORLD_EXTENSIONS_MANIFEST` into `backend/.env` or workspace `.env` so the backend can load the manifest at startup.

### CLI surface

- Add `portworld extensions list`, `show`, `add`, `remove`, `enable`, `disable`, and `doctor`.
- `add` supports official registry IDs and local scaffolds; default behavior installs the dependency, writes the manifest, validates command/module presence, and rolls back manifest changes on install failure.
- Package a built-in catalog in `portworld_cli` with metadata per extension: id, kind (`tool_package` or `mcp_server`), summary, install strategy, launch spec, required env keys, and default exposure rules.

### Developer framework

- For custom Python tools, support entry points such as `portworld.tool_contributors` that return backend `ToolCatalogContributor`s.
- For custom MCP servers, support manifest-defined stdio/http specs and optional package hooks for validation/setup helpers.
- Add one example tool package, one example MCP manifest, and one "create your own extension" doc with templates.

### Backend runtime

- Add `backend/extensions/` to load the manifest from settings, resolve enabled extensions, and merge them into startup and health checks.
- Keep built-in memory/profile/search tools as core contributors, then append Python extension contributors and MCP-discovered contributors.
- Add an MCP bridge/client layer that connects to enabled MCP servers at startup, discovers their tools, and registers proxy `ToolDefinition`s into `RealtimeToolRegistry`. Reject name collisions unless explicitly namespaced by server id.
- Extend `portworld doctor` and backend readiness to validate enabled extensions, installed executables/modules, required env keys, and MCP connectivity.

### Public interfaces and types

- Add typed models for `ExtensionManifest`, `ExtensionCatalogEntry`, `InstalledExtension`, `MCPServerSpec`, `ToolPackageSpec`, and extension validation results.
- Add a read-only reporting surface in CLI and backend that shows active extensions and discovered MCP tools.

## Test Plan

### CLI tests

- Add/list/show/remove/enable/disable flows for official and local extensions.
- Install failure, duplicate id, bad manifest, and missing required env key cases.
- Source workspace vs published workspace manifest resolution.

### Backend and runtime tests

- Built-in contributors still load with no manifest.
- Python entry-point tool contributor registers tools and executes successfully.
- MCP stdio server is discovered, proxied into the registry, and called through the existing tool execution flow.
- Disabled extensions are ignored; duplicate tool names fail clearly; unreachable MCP servers fail readiness.

### Acceptance scenarios

- `portworld extensions add <official-mcp>` installs/configures it, `portworld extensions doctor` passes, and the backend exposes the MCP tool through the active tool registry.
- A developer follows the docs, creates a local custom tool package, adds it via manifest/CLI, and gets it loaded without editing core repo files.

## Assumptions

- The active implementation targets `portworld_cli/` and `backend/`; `framework/` stays reference-only for this feature.
- V1 supports local workspace manifests plus packaged Python hooks; remote third-party registries are deferred.
- Official installers cover Python/`uv` and Node/`npx`/`npm` first; docker-backed launchers can be added after the core model is stable.
- MCP servers are made useful immediately by proxying discovered MCP tools into the existing backend tool-calling path, not by storing server URLs only.
