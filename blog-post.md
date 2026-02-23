---
title: "I Built a Terminal Session Debugger with Rewind, Breakpoints, and Branching"
published: false
description: "devops-rewind records your terminal sessions and lets you rewind to any step, set breakpoints, and branch off a new path when deploys fail. Like git for your shell."
tags: devops, python, cli, opensource
cover_image: ""
canonical_url:
series: "Building Developer Tools in 2026"
---

## The Problem: Deploy Scripts Fail and You Start Over

You're running a 50-step deploy process. Step 47 fails. You've already provisioned infrastructure, pulled images, run migrations, seeded data. Now you have two options:

1. **Start over from step 1.** 45 minutes wasted.
2. **Try to manually re-run from where it failed.** Good luck remembering what you already ran.

Neither is great. What if you could **rewind to step 45 and try a different path**, like hitting Ctrl+Z in your terminal?

That's what `devops-rewind` does.

## 3 Lines to Get Started

```bash
pip install devops-rewind
devops-rewind record my-deploy
devops-rewind rewind my-deploy 45
```

## How It Works

```
Record a session:                  When it fails:
┌──────────────────────┐          ┌──────────────────────┐
│ [0] git pull      OK │          │ rewind to step 1     │
│ [1] make build    OK │──────────│ branch from step 1   │
│ [2] make test     OK │          │ try new commands      │
│ [3] make deploy FAIL │          │ diff original vs fix  │
└──────────────────────┘          └──────────────────────┘
```

devops-rewind records every command you run — the command itself, stdout/stderr, exit code, working directory, and timestamp. Each command is a numbered "step." When something fails, you rewind to any step and inspect the exact state, or branch off to try a different approach.

## Core Features

### Record

Start a recording session with a named identifier:

```bash
devops-rewind record my-deploy
```

This opens an interactive prompt where every command you run is captured:

```
[0] /app $ git pull
Already up to date.
[1] /app $ make build
Building...
[2] /app $ make deploy
Error: connection refused
[3] /app $ exit
Session saved: my-deploy (3 steps)
```

### Rewind

Jump to any step and see exactly what happened:

```bash
devops-rewind rewind my-deploy 2
```

This shows the command, its output, the working directory at that point, and a summary of any failures that occurred before or after.

### Breakpoints

Set breakpoints that pause replay at specific conditions:

```bash
# Break at step 47
devops-rewind breakpoint add my-deploy 47

# Break on any kubectl command
devops-rewind breakpoint add my-deploy --pattern "kubectl apply"

# Break on any non-zero exit code
devops-rewind breakpoint add my-deploy --on-error
```

### Branch

Fork a session from any step. The new branch inherits all history up to that point:

```bash
devops-rewind branch my-deploy 1 --exec
```

Now you're in a new recording session with steps 0 and 1 already in history. Run different commands from there.

### Diff

Compare two sessions side-by-side. The diff engine finds the exact step where they diverge:

```bash
devops-rewind diff my-deploy my-deploy-branch-1
```

### Export

Turn any session into a runnable script, markdown doc, or JSON:

```bash
devops-rewind export my-deploy --format sh > deploy.sh
```

## Why Not Just Use `script` or `asciinema`?

| Feature | `script` | `asciinema` | **devops-rewind** |
|---------|----------|-------------|-------------------|
| Records output | Yes | Yes | Yes |
| Captures exit codes | No | No | **Yes** |
| Step-by-step replay | No | No | **Yes** |
| Rewind to any step | No | No | **Yes** |
| Breakpoints | No | No | **Yes** |
| Branch / fork | No | No | **Yes** |
| Diff two sessions | No | No | **Yes** |
| Export to shell script | Partial | No | **Yes** |

`script` and `asciinema` record raw terminal output. They don't understand individual commands, exit codes, or state. devops-rewind records at the **command level**, which enables rewind, branching, and diffing.

## Architecture

```
src/devops_rewind/
├── cli.py           # Click CLI with 8 commands
├── recorder.py      # Command-by-command recording via subprocess
├── session.py       # Step + Session dataclasses
├── player.py        # Replay + rewind engine
├── breakpoints.py   # Step/pattern/error breakpoint types
├── branching.py     # Fork session from any step
├── differ.py        # Diverge-point detection + diff
├── storage.py       # SQLite at ~/.devops-rewind/sessions.db
└── display.py       # Rich panels, tables, side-by-side columns
```

### Recording Approach

I chose `subprocess.run()` per command instead of wrapping a PTY. This is less "realistic" (no interactive prompts inside recorded commands), but it's:

- **Safe** — each command is isolated, no shell injection risk
- **Testable** — easy to mock in unit tests
- **Portable** — works on macOS, Linux, and Windows
- **Structured** — you get clean stdout, stderr, and exit code per step

### Branching Implementation

The branching engine copies steps 0 through N from the parent session into a new Session object, then opens a new recorder from that point. The parent session is never modified.

```python
def branch_session(session, from_step, storage, name=None):
    steps = session.steps[: from_step + 1]
    branch = Session.new(name or f"{session.name}-branch-{from_step}")
    branch.steps = [step.copy() for step in steps]
    branch.parent_id = session.session_id
    branch.branch_point = from_step
    storage.save(branch)
    return branch
```

## Numbers

- **116 tests** passing
- **89% coverage**
- **Python 3.9-3.12** matrix CI
- **SQLite** for persistent, portable storage

## Real-World Use Case

Last week I was debugging a Kubernetes deployment. The sequence was:

1. Build Docker image
2. Push to registry
3. Apply ConfigMap
4. Apply Deployment
5. Wait for rollout
6. Run smoke test — **FAILED**

With devops-rewind, I recorded the whole thing, rewound to step 3, branched, and tried a different ConfigMap. The diff clearly showed that one environment variable was wrong. Fixed it, exported the successful branch as a shell script, and added it to CI.

Total time saved: about 30 minutes of re-running steps 1-5.

## Try It

```bash
pip install devops-rewind
devops-rewind record my-session
```

Star it on GitHub: [github.com/LakshmiSravyaVedantham/devops-rewind](https://github.com/LakshmiSravyaVedantham/devops-rewind)

---

*What's the longest deploy sequence you've had to debug? Drop it in the comments.*
