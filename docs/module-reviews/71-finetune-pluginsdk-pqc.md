# Module 10 — Fine-Tuning · Plugin SDK · PQC Vault

**Reviewed:** 2026-08-10
**Panes:** `finetune`, `pluginsdk`, `pqc`
**Frontend:** `frontend/js/03-features-a.js` (3,024 lines)
**Backend:** `backend/routers/finetune.py`, `pluginsdk.py`, `pqc.py`
**Endpoints:** 25
**Risk score:** 20 (joint highest unreviewed)

---

## Summary

Four defects. Two are the recurring **fabricated confidence** theme, one is a
missing gate on a publishing path, and one is the **12th "second door"**.

| # | Component | Defect | Severity |
|---|---|---|---|
| 1 | finetune | Wrote three hardcoded marketing sentences as "training examples" whenever no rows were supplied | High |
| 2 | finetune | `source_type` defaulted to `chat_history` and never read chat history | Medium |
| 3 | pluginsdk | `/publish` never ran the validator sitting in the same file — an invalid pack reached the marketplace *and* `installed.json` | High |
| 4 | pqc | `/kem/decapsulate` — the call that returns the shared secret — omitted the `simulated` flag its two sibling routes declare | High |

---

## 1–2. Fine-tuning invented the user's training data

`POST /finetune/datasets/create` with no `custom_rows`:

```python
else:
    # Generate default training pairs from local memory and context
    rows = [
        {"instruction": "What is the mission of Agentic OS?", ...},
        {"instruction": "How do multi-agent swarms work in Agentic OS?", ...},
        {"instruction": "How does the compounding Information Hierarchy work?", ...},
    ]
```

Three sentences of product marketing, written to disk as JSONL and reported as:

> `Dataset 'ds_759186cf' created with 3 training examples`

Nothing in the response, the dataset list, or the file distinguishes this from
a dataset built out of the user's own data. Anyone who then started a LoRA run
would be fine-tuning a model on invented copy about the product.

The comment says "from local memory and context". It reads neither. And
`source_type` defaults to `"chat_history"` — a source the endpoint never
consulted at any point.

**Fix:** `_rows_from_chat_history()` actually reads `chat_log` (column
`message`, not `content`) and pairs each user turn with the assistant reply
that followed. When there is genuinely nothing to build from, the endpoint
returns **422** rather than inventing rows — and writes no file.

A prior review had already fixed `/jobs/start`, which used to report
`step 150/150, train_loss 0.284, status "completed"` without a training
library installed. The dataset half of the same feature was left behind — the
same lesson, one endpoint over.

---

## 3. The Plugin SDK published packs it knew were invalid

`pluginsdk.py` contains a thorough validator: required fields, semantic
version, per-skill checks, and an allow-list of permissions so a typo cannot
silently broaden a pack's authority. `/publish/{pack_id}` **never called it.**

Demonstrated end to end:

```
POST /pluginsdk/packs        {"id":"brokenpack","version":"not-a-version",
                              "description":"","skills":[]}
POST /pluginsdk/validate     -> ok:false, score:40
                                ["Missing required field: description",
                                 "Missing required field: skills",
                                 "version must be semantic (e.g. 1.0.0)"]
POST /pluginsdk/publish/brokenpack   -> ok:true, published:true
GET  /pluginsdk/registry             -> ['brokenpack', 'm10pack']
plugins/installed.json               -> ['m10pack', 'brokenpack']
```

Publishing is what puts a pack in the marketplace *and* installs its skills for
every user of the instance. It was the one path with no gate.

The rules lived inline inside the `/validate` endpoint, which is precisely why
`/publish` could not reuse them. They are now `_validate_manifest()`, shared by
both, so the two cannot drift apart again.

---

## 4. The PQC route that hands back the secret didn't say it was fake

`backend/routers/pqc.py` is admirably blunt in its module docstring: the
primitives are SHA3 and an XOR mask, the KEM shared secret is derivable from
public values, and the vault "encryption" is recoverable from the public
`keypair_id` alone. `/keypair/generate` and `/kem/encapsulate` both return
`simulated: true` with a warning.

`/kem/decapsulate` returned:

```json
{"ok": true, "shared_secret_b64": "...", "algorithm": "ML-KEM-1024",
 "message": "Key decapsulation successful; shared secret recovered"}
```

No `simulated`, no `warning`, and a message asserting success. A caller
checking `simulated` on the operation that actually produces the secret would
have concluded the exchange was real. **12th "second door."**

### The pane made the strongest claim of all

A previous review fixed the algorithm badges to read `simulated`. It did not
touch the **top half** of the pane, which hardcoded:

- `ACTIVE · FIPS 203 COMPLIANT` and `ACTIVE · FIPS 204 COMPLIANT` in green
- `HARDENED STORAGE`
- "Real-time visual proof of Module-Lattice Key Encapsulation Mechanism"
- "⚡ Encapsulation engine live and monitoring all agentic vector transactions"
- card text asserting "FIPS 203 compliant zero-trust quantum resilience"

The most prominent copy on the page carried the least true claim, and the
"SIMULATED" badge lower down directly contradicted the paragraph beside it.

All of it is now conditional on the server's `simulated` flag, plus a banner at
the very top of the pane linking to the real Fernet AES-256 vault. Verified in
Chromium: banner renders at 928×121, `FIPS 203 COMPLIANT` no longer appears,
no page errors.

---

## Verified working (no change needed)

- `/finetune/hardware` honestly reports `training_available:false` with a clear
  notice, and `/jobs/start` refuses with 501 rather than faking a run.
- `/pqc/vault/encrypt` refuses with 501 unless `AGENTIC_PQC_DEMO=1`.
- pluginsdk CRUD, template, export/import, and registry all behave.
- `/pluginsdk/packs/{id}/skills/{id}/run` degrades to an honest 503.
- The permissions allow-list correctly rejects unknown capabilities.

---

## Cross-module impact

- **Plugin Marketplace** and the **Skills** system both consume what
  `/publish` writes (`plugins/installed.json`, `skills`). They now receive only
  validated packs. Existing invalid packs already published are unaffected —
  the gate applies at publish time.
- **Secrets Vault** is now linked directly from the PQC pane as the real
  alternative.
- `frontend/styles-redesign.css` gained `.pqc-sim-banner`, `.pqc-sim-link`,
  `.tech-badge.pqc-badge-sim`.
- Callers of `/finetune/datasets/create` must handle 422 where they previously
  always got a dataset. The only caller is this pane.

---

## Tests

`tests/unit/test_143_module10_finetune_sdk_pqc.py` — **17 tests.**

Revert-proof (caches cleared, all three routers reverted): **13 of 17 fail.**
The 4 survivors are deliberate: `test_publish_accepts_a_valid_pack` guards the
happy path the new gate could have broken, `test_pqc_vault_encrypt_still_refuses`
pins pre-existing protection, and two parametrised cases cover the PQC routes
that were *already* correct — which is the point of the parametrisation, since
it isolates the third door as the only one that was wrong.

Full suite: **3,568 unit + 655 regression/system/uat = 4,223 passing, 0 failures.**
