# Module 12 — Terminal

**Commit:** `200b9bc` · **Suite:** 2688 passed / 17 skipped / 0 failed · ruff clean
**Surface:** `backend/routers/terminal.py` (412 lines, 7 endpoints) ·
`frontend/js/16-terminal.js` (395 lines)

This module executes real shell commands, so its filter is a **security
boundary**, not a convenience. Every finding was reproduced against a live
server before the fix and re-verified after.

---

## 🔴 1. The allowlist was bypassable by design

The path filter correctly refused this:

```
cat /etc/passwd   →  blocked: access to '/etc/' not permitted
```

But this was permitted, and **printed the file**:

```
python3 -c "print(open(chr(47)+chr(101)+chr(116)+chr(99)+...).read())"
→ root:x:0:0:root:/root:/bin/bash
  daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
```

Allowlisting a command *name* is meaningless when the command is a
general-purpose interpreter. `python`, `python3`, `node` and `npx` were all on
the safe list, and each one trivially reads any file, opens any socket, or
spawns anything else. Every path rule above it was decorative.

### The fix, and what it deliberately does *not* do

The interpreters **stay allowed** — running project scripts is the entire point
of an integrated terminal, and banning them would have been the lazy fix. What's
refused is the inline-code and stdin-program forms (`-c`, `-e`, `--eval`, `-p`,
`--print`, bare `-`), which exist only to smuggle a payload past the filter.

| Still works | Now refused |
|---|---|
| `python3 manage.py migrate` | `python3 -c "..."` |
| `python3 -m pytest` | `node -e "..."` |
| `node server.js` | `python3 -` |
| `npm run build`, `npx prettier --write .` | `npx -e "..."` |

There are tests for every row.

---

## 🔴 2. Output redirection escaped the sandbox

```
echo pwned > /tmp/terminal_pwn.txt   →  file created
```

The cwd sandbox constrains where the shell *starts*, not where it can write.
`>` and `>>` are now refused **outside quotes**, so `grep '>' notes.txt` still
works.

---

## 🔴 3. cwd containment used a string prefix

```python
if str(resolved).startswith(str(PREVIEW_DIR.resolve())):
```

```
_get_work_dir('../preview_ESCAPED')  →  /home/user/repo/preview_ESCAPED
```

A prefix test on a **string**, so any sibling directory whose name merely begins
with `preview` passed. This is the identical defect I fixed in
`imagegen._safe_preview_path` during Module 10 — but here the value becomes the
**working directory of a real subprocess**, so the blast radius is much larger.

Now uses `Path.relative_to()`, and requires the directory to exist so the
subprocess can't die on a confusing `OSError`.

---

## 🔴 4. No timeout, no output cap

`sleep 12` ran the full 12 seconds. Nothing stopped a command running forever
while holding a subprocess and an SSE connection open — one `while true` and the
server leaks a process permanently. Output was equally unbounded.

Added `MAX_RUNTIME_S` (300s) and `MAX_OUTPUT_BYTES` (2 MB), both env-configurable.
Timeout reports **exit code 124** (the conventional value) with `timed_out: true`;
truncation is announced in-stream rather than silently dropping output.

Verified with a 5s / 4KB override:

```
60-second script  →  terminated at 5.001s, exit_code 124
200,000 lines     →  5 KB delivered + "[output truncated at 4096 bytes]"
```

---

## 🔴 5. Killing a command killed only the shell

This one surfaced *because* of the timeout fix, which is the useful part: the
timeout fired exactly on schedule, and `ps` showed the program still running.

```
  PID  PPID  CMD
 6102     1  python3 sleeper.py     ← re-parented to init, still going
```

`create_subprocess_shell` spawns `sh -c <command>`, so `proc.kill()` terminates
the **shell** and orphans its child. Every termination path was affected: the
timeout, client cancellation, cleanup, and — most visibly — **the user-facing
Kill button, which never actually stopped the program.**

Fixed with `start_new_session=True` plus `_terminate_tree()`, signalling the
whole process group (SIGTERM → SIGKILL after 5s) with a fallback to the direct
child if the group is already gone.

### A verification mistake worth recording

I twice read this as "still leaking" after it was fixed. My check was
`pgrep -af "sleeper.py"` — which **matched its own bash command line**
containing that string, and on another run matched the `curl` process. The real
count was zero. I only caught it by dumping `ps -eo pid,ppid,pgid,cmd` and
reading the actual rows. A grep pattern that can match the harness is not
evidence.

---

## 🟡 Also fixed

| Issue | Detail |
|---|---|
| **200-on-refusal** | Validation failures returned HTTP 200 with the refusal inside an SSE frame — indistinguishable from success to any non-SSE client. Now 400 / 403 / 404. |
| **Unbalanced quotes** | Were analysed with a broken token list; now refused outright. |
| **Allowlist too narrow** | `printf`, `false`, `sed`, `awk`, `make`, `cargo`, `jq` and ~14 others were rejected as "not permitted" — confusing for a terminal advertising real shell use. Added. `env`/`printenv` remain deliberately blocked. |
| **Quadratic rendering** | `innerHTML +=` per output line re-serialises and re-parses the whole buffer every time, locking the tab on a chatty command. Now `insertAdjacentHTML` with a 5000-line DOM cap. |
| **Bare status numbers** | The frontend now surfaces the server's explanation. |

---

## Verified working (no change needed)

- **Environment sandboxing is genuinely good.** `_sandboxed_env()` passes only a
  curated allowlist, and I confirmed live that a subprocess sees just
  `PATH, HOME, USER, SHELL, LANG, TERM…` — no `OPENROUTER_API_KEY`, no
  `GITHUB_TOKEN`. Whoever wrote that comment thought about it properly.
- Shell metacharacters (`&&`, `||`, `` ` ``, `$(`, `;`) are correctly blocked
  outside quotes.
- Sensitive-path prefixes are blocked for file-reading commands, including
  quoted and traversal forms.
- Terminal output is escaped before rendering — it is attacker-influenced text
  going into HTML.
- Per-session history isolation works; one session can't read another's.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Studio / Preview** | Shares `PREVIEW_DIR`; the cwd fix stops the terminal reaching outside it |
| **Secrets Vault** | Injects keys into `os.environ` — the env allowlist is what keeps them out of the shell |
| **Workspaces** | `activate` rmtree's `PREVIEW_DIR`; the terminal now falls back cleanly if cwd vanishes |
| **Composer / Builder** | Users run build commands here against generated projects |

---

## Tests

`tests/unit/test_63_terminal_module_review.py` — **65 contracts**, including the
exact `/etc/passwd` payload that worked before, and a `TestExistingProtectionsStillHold`
class asserting the path filter, injection blocking and secret-stripped env
haven't regressed while I widened the allowlist.

**Proven to catch the bugs: 31 of 65 fail against the pre-fix code.**

Two integration tests used `python3 -c` as a convenient way to produce a known
exit code — the very form now blocked. Rewritten to run a real script file and to
use `false`; one gained a new assertion that the inline form is refused, turning
a broken test into extra coverage.

---

## Follow-ups ✅ *all four done in `ff0008d`*

### 1. Authorisation gate

There was none — anyone who could reach the API had a shell as the server user.
Defensible on `127.0.0.1`, not once the server is reachable from the network, so
the gate is tied to the bind address rather than switched on globally:

| Condition | Behaviour |
|---|---|
| Bound to loopback | Allowed, exactly as before |
| Bound to `0.0.0.0` / a real IP | API key **required** |
| `TERMINAL_REQUIRE_AUTH=1` | Always required |
| `TERMINAL_DISABLED=1` | Refused outright (403) |

**A real fail-open found while verifying this:** `require_api_key()` returns
`None` when *no users are registered*, treating "auth not configured yet" as
"auth not needed". Sensible first-run convenience for most endpoints; a hole for
a network-reachable shell. Verified live — `TERMINAL_REQUIRE_AUTH=1` with an
empty user table ran `echo hi` and returned **200**. Now 401 with instructions.
The gate also fails **closed** (503) if the auth backend itself errors.

### 2. Kernel-enforced resource limits

The filter can only enumerate badness; it cannot bound what an *allowed* command
does. Added RLIMITs via `preexec_fn` — CPU 60s, address space 2 GB, file size
512 MB, 256 processes, no core dumps. Verified live with tight caps:

```
600 MB allocation →  MemoryError in 37ms          (cap 256 MB)
infinite loop     →  killed at 3.02s, exit 152    (SIGXCPU, cap 3s)
50 MB write       →  OSError [Errno 27]; file stopped at exactly 1048576 bytes
```

Soft limits are clamped to the inherited hard limit so `setrlimit` can't fail on
a restricted host, and every failure is swallowed — an exception in a forked
child before `exec` would be far worse than a missing cap.

### 3. Interactive commands fail fast, with the fix in the message

`stdin` is `DEVNULL`, so `npm init` blocked until the runtime cap killed it and
the user saw a bare timeout. Now detected up front:

```
npm init    →  "Try: npm init -y"
git commit  →  "Try: git commit -m \"message\""
git merge   →  "Try: git merge --no-edit"
```

Detection is **per-invocation, not per-command**, which is the part that matters:
`git commit` is refused but `git commit -m x` runs; `git add -p` is refused but
`git add .` runs; `git rebase -i` is refused but `git rebase --onto main` runs.
A blanket ban on `git commit` would have been worse than the hang.

### 4. `/env` caching

Four blocking subprocesses per call at 2s each — up to 8s of blocked event loop,
on an endpoint the UI hits every render. Cached for 5 minutes, with an explicit
`POST /env/refresh` for after installing a tool (a permanent cache would never
notice one).

**60 new contracts**; 35 fail against the pre-change code. One forks a child,
applies the limits and reads them back rather than trusting the source text.

---

## Module status

All four follow-ups complete. The one thing I could not do here remains the
honest long-term answer for arbitrary shell execution: **OS-level isolation**
(a container or `nsjail`). The RLIMITs bound resource consumption, and the filter
bounds obvious misuse, but neither is a substitute for a real sandbox. That is an
infrastructure decision rather than a code fix, and it needs a host this
environment cannot provide.
