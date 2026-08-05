# 31 — Panes that invented data when the server had none

Autonomous hunt, batch 21. One pattern, three instances: the UI fell back to a
hardcoded literal whenever the real value was missing, and presented the
invention with the same confidence as a measurement. In every case **the server
was telling the truth and the frontend overrode it.**

---

## 1. Fine-tuning showed two datasets that do not exist

`03-features-a.js` rendered the dataset list as:

```js
(ds.datasets && ds.datasets.length ? ds.datasets : [
  {id:'ds_chat_v1',  name:'Active Chat History & System Memory Delta', rows:42, status:'ready'},
  {id:'ds_evals_v1', name:'Eval Framework Gold Standard Seed Suite',   rows:18, status:'ready'},
])
```

Verified against the running server:

```
GET  /api/finetune/datasets                      -> {"ok":true,"count":0,"datasets":[]}
POST /api/finetune/jobs/start {"dataset_id":"ds_chat_v1"}
                                                 -> "Dataset 'ds_chat_v1' not found"
```

So on a fresh install a user saw **two datasets badged READY**, pressed
"Train Adapter", and the only possible outcome was an error. The row counts
(42, 18) were fiction rendered as measurements.

The **"⚡ Start LoRA Training Loop Now"** button had the same problem from the
other direction — hardcoded to `finetuneStartJob('default_dataset')`, which
also does not exist.

**Fixed:** a real empty state ("No training datasets yet") offering the two
actions that actually create one; the training button now targets the first
real dataset and is hidden when there are none; `${d.rows || 10}` became
`${Number(d.rows || 0)}`.

## 2. The PQC pane never showed the server's answer, and called a simulation VERIFIED

Two bugs stacked.

**It read a field that does not exist.** The pane read `algos.algorithms`.
`GET /api/pqc/algorithms` returns `kem_algorithms` and `signature_algorithms`.
The lookup was **always** `undefined`, so the `||` fallback fired on every
render and the pane displayed three invented entries — including
`AES-256-GCM-Lattice-Wrapped`, which the server has never mentioned. It never
once showed the server's real six.

**It badged each one `VERIFIED`.** Meanwhile `backend/routers/pqc.py` states on
its other routes:

> SIMULATED post-quantum cryptography. This implements SHA3 hashing and XOR
> masking, NOT ML-KEM/Kyber or Dilithium. **Provides no confidentiality.**

Telling a user their key exchange is quantum-resistant and VERIFIED when the
backend says it is a simulation is the most dangerous way this UI could be
wrong: it is precisely the claim someone would rely on before putting a real
secret in.

**Fixed:** the pane now reads both real fields, labels each entry as key
encapsulation or digital signature, badges them `SIMULATED` (amber) while the
backend says so, and surfaces the backend's warning text in full.

**Also fixed in the backend:** `/algorithms` was the *only* route in the PQC
router that omitted `simulated` and `warning`. That was the worst place to
omit them — it is the route the UI renders as a capability list, so with no
disclaimer in the payload the frontend had nothing to display one from.

## 3. An invented model count on key verification

```js
`✅ Verified & active! ${tj.models_count || 180}+ models ready (Claude 3.5 Sonnet, GPT-4o, Llama 3.3).`
```

When the backend cannot reach the catalogue it returns `models_count: 0`, and
`0 || 180` is `180` — so the UI invented a count nobody measured, then named
three specific models it had not confirmed the key can reach.

This one is pointed, because the backend goes to real trouble here: it verifies
against `/api/v1/auth/key` *precisely because* the public `/models` endpoint
returns 200 for any garbage (documented in `secrets.py` as an earlier fix). The
frontend was undoing that work by making the number up when the measurement was
unavailable.

**Fixed:** reports the real count, or omits the clause entirely.

---

## A trap hit again (9th time)

The first version of the fine-tune fix put the explanation in an **HTML
comment inside the template literal**. That comment ships into the DOM, so the
test asserting `'ds_chat_v1' not in html` failed against the *fixed* build —
matching the text of its own fix. Moved to a JS comment above the function.
This is the ninth instance of that trap in this review; the standing remedy is
to assert against comment-stripped source, which
`test_the_model_count_is_never_invented` does explicitly.

---

## Tests

`tests/e2e_browser/test_e2e_browser_06_fabricated_data.py` — 6 tests.

`test_a_dataset_shown_as_trainable_can_actually_be_trained` is the durable one:
it extracts every id the UI offers to `finetuneStartJob` and checks each against
the server's own list, so it would catch this class of bug even if the invented
ids were renamed.

**Proven to catch the bugs.** With all three fixes reverted: **5 failed, 1
skipped**. The skip is honest — that test gates on the backend declaring
`simulated`, which the reverted backend does not do.

With the fixes in place: **6 passed**.

## Regression status

| Suite | Result |
|---|---|
| Full non-browser | **3959 passed, 19 skipped, 0 failed** (unchanged) |
| Browser E2E | **74 passed, 0 failed** |
| `ruff check backend frontend scripts` | pass |
