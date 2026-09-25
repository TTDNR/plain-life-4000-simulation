# Plain Life 4000 Simulation Project Rules

## Git requirements

- This directory is an independent Git repository.
- The primary branch is `main`.
- Start work with `git status --short --branch`.
- Commit completed documentation, source, assets, and configuration as the project evolves.
- Keep a project-specific `.gitignore` covering local secrets, generated outputs, caches, and
  large temporary artifacts.
- Do not commit `.env`, tokens, credentials, private keys, generated caches, model weights,
  datasets, recordings, or large temporary outputs.
- Do not create a GitHub remote or push changes unless the user explicitly requests it.
- Before committing, run:

```powershell
git diff --check
```

When a technology stack is selected, update `docs/GIT_WORKFLOW.md` with its exact build, test, and
validation commands before committing implementation changes.

Detailed commands and commit conventions are in
[`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md).

## Shared cache

- Load the workspace cache configuration before running auxiliary tools:

```powershell
. D:\AiProject\workspace-env.ps1
```

- Downloaded models, datasets, package caches, and tools must remain under `D:\AiProject\.cache`.
- Do not store model weights, datasets, package caches, or downloaded tools inside this repository.
- Do not pass a project-local `local_dir`, `cache_dir`, or `--local-dir` to a downloader unless the
  user explicitly requests a project-local copy.

## Technology-neutral boundary

- Do not select an engine, language, framework, dependency manager, or data format without a
  project requirement that justifies it.
- Record material technical decisions and their tradeoffs in `docs/TECHNOLOGY_DECISIONS.md`.
- Keep the repository usable as a blank project until the simulation requirements are defined.
