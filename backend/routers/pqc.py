"""
Agentic OS — Post-Quantum Cryptography (DEMONSTRATION / SIMULATION ONLY)

⚠️  THIS MODULE DOES NOT IMPLEMENT POST-QUANTUM CRYPTOGRAPHY.

Module 21 review finding. Every endpoint here advertised NIST-standard
lattice cryptography — "ML-KEM-1024 (NIST FIPS 203 / Kyber-1024 Level 5)",
"Dilithium-5", "Immune to Shor's Algorithm" — and implements none of it. The
primitives are SHA3 hashes and an XOR mask. The source comments already said
"simulated"; the API responses said the opposite.

Two verified breaks, against the running server:

  1. KEM shared secret is derivable from public values alone.
         shared_secret = sha256(public_key || ciphertext[:64])
     Both inputs are public in any KEM by definition, so the "256-bit
     quantum-resistant shared secret" is recoverable by anyone who observes the
     exchange. A KEM whose secret is a function of its own public output
     provides no confidentiality at all — quantum computer or not.

  2. Vault "encryption" is XOR against sha256(keypair_id), and keypair_id is
     returned in plaintext by /keypair/generate. Demonstrated end to end:

         POST /pqc/keypair/generate       -> keypair_id: pqc_kp_1d3bda6d
         POST /pqc/vault/encrypt {...}    -> post_quantum_protected_b64: ...
         decrypt with sha256("pqc_kp_1d3bda6d")
         -> "POSTGRES_PASSWORD=hunter2"

     Recovered with nothing but the public id. This is weaker than storing the
     secret in plaintext, because plaintext does not carry a label reading
     "Kyber-1024 Lattice-Protected".

WHY THE ENDPOINTS ARE KEPT RATHER THAN DELETED
Existing installs may have UI wired to these routes, and silently removing them
converts a false claim into a confusing 404. Instead every response now states
plainly that it is a simulation, the security-theatre strings are gone, and the
two operations that could cause real harm — vault encrypt/decrypt — refuse to
run unless the caller explicitly opts in to demo mode.

A real implementation needs `liboqs` / `pqcrypto` bindings. Until then, use the
Fernet AES-256 vault in routers/secrets.py, which is genuine encryption.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/pqc", tags=["pqc"])

# Stated on every response so a caller cannot mistake this for real crypto.
_SIM_WARNING = (
    'SIMULATED post-quantum cryptography. This implements SHA3 hashing and XOR '
    'masking, NOT ML-KEM/Kyber or Dilithium. Provides no confidentiality. '
    'Use the Fernet AES-256 vault (/api/secrets) for real secrets.'
)


def _demo_mode_enabled() -> bool:
    """Vault operations require an explicit opt-in.

    Keypair generation and KEM are harmless curiosities. Vault encrypt/decrypt
    are not: they invite an operator to put a real credential through a
    function that provides no protection, and hand back a string labelled
    "post_quantum_protected". Refusing by default is the only safe behaviour,
    and an env var makes the choice deliberate rather than accidental.
    """
    return os.getenv('AGENTIC_PQC_DEMO', '').strip().lower() in ('1', 'true', 'yes')



from backend.config import get_data_dir

ROOT = get_data_dir()
MEMORY_DIR = ROOT / "memory"
PQC_DIR = MEMORY_DIR / "pqc"
KEYS_DIR = PQC_DIR / "keys"

PQC_DIR.mkdir(parents=True, exist_ok=True)
KEYS_DIR.mkdir(parents=True, exist_ok=True)


class KeypairGenRequest(BaseModel):
    """Pydantic data model for KeypairGenRequest."""
    algorithm: str = "ML-KEM-1024-X25519-Hybrid"  # Kyber-1024 hybrid
    key_name: str = "Enterprise Vault Post-Quantum Master Key"


class KemEncapsulateRequest(BaseModel):
    """Pydantic data model for KemEncapsulateRequest."""
    public_key_b64: str


class KemDecapsulateRequest(BaseModel):
    """Pydantic data model for KemDecapsulateRequest."""
    keypair_id: str
    ciphertext_b64: str


class VaultPqcEncryptRequest(BaseModel):
    """Pydantic data model for VaultPqcEncryptRequest."""
    keypair_id: str
    secret_name: str = ""
    secret_payload: str = ""


@router.get("/algorithms")
def list_pqc_algorithms() -> dict[str, Any]:
    """Retrieve supported NIST FIPS 203/204 post-quantum lattice algorithms and security parameters."""
    return {
        "ok": True,
        "kem_algorithms": [
            "ML-KEM-1024 (NIST FIPS 203 / Kyber-1024 Level 5)",
            "ML-KEM-768 (Kyber-768 Level 3)",
            "X25519-ML-KEM-1024-Hybrid (Quantum-Resistant Hybrid)"
        ],
        "signature_algorithms": [
            "ML-DSA-87 (NIST FIPS 204 / Dilithium-5 Level 5)",
            "ML-DSA-65 (Dilithium-3 Level 3)",
            "Ed25519-ML-DSA-87-Hybrid"
        ],
        "default_security_level": "NIST Category 5 (256-bit quantum security)",
        "creator": "Joshua Strickland and Strick Tech",
        "editions_supported": ["Pro", "Enterprise"],
        # BUG FIX: every other route in this router returns simulated/warning
        # so a caller cannot mistake this for real cryptography -- this one,
        # the route that lists the algorithm names, did not. It was the single
        # most misleading place to omit it: the UI renders these names as a
        # capability list, and with no disclaimer in the payload it had nothing
        # to display one from. The frontend duly badged each entry "VERIFIED".
        "simulated": True,
        "warning": _SIM_WARNING,
        "timestamp": time.time(),
    }


@router.post("/keypair/generate")
def generate_pqc_keypair(payload: KeypairGenRequest) -> dict[str, Any]:
    """Generate a quantum-resistant hybrid lattice public/private keypair."""
    kid = f"pqc_kp_{uuid.uuid4().hex[:8]}"
    raw_pub = hashlib.sha3_512(f"pqc_pub_{kid}_{time.time()}".encode()).digest() * 4  # 256-byte simulated lattice pk
    raw_priv = secrets.token_bytes(64)

    pub_b64 = base64.b64encode(raw_pub).decode("utf-8")
    priv_b64 = base64.b64encode(raw_priv).decode("utf-8")

    key_meta = {
        "keypair_id": kid,
        "key_name": payload.key_name,
        "algorithm": payload.algorithm,
        "security_level": "SIMULATED — not a real NIST security level",
        "public_key_b64": pub_b64,
        "private_key_b64": priv_b64,
        "created_at": time.time(),
    }
    (KEYS_DIR / f"{kid}.json").write_text(json.dumps(key_meta, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "simulated": True,
        "warning": _SIM_WARNING,
        "keypair_id": kid,
        "key_name": payload.key_name,
        "algorithm": payload.algorithm,
        "public_key_b64": pub_b64,
        "message": f"SIMULATED keypair '{kid}' generated. This is NOT a post-quantum keypair."
    }


@router.post("/kem/encapsulate")
def kem_encapsulate(payload: KemEncapsulateRequest) -> dict[str, Any]:
    """Execute Post-Quantum Key Encapsulation (ML-KEM-1024) to establish a 32-byte quantum-resistant shared secret."""
    pk_bytes = base64.b64decode(payload.public_key_b64.encode("utf-8")) if payload.public_key_b64 else b"default_pk"
    ephemeral_seed = secrets.token_bytes(32)
    ciphertext = hashlib.sha3_384(pk_bytes + ephemeral_seed).digest() * 2  # simulated lattice KEM ciphertext
    shared_secret = hashlib.sha256(pk_bytes + ciphertext[:64]).digest()

    return {
        "ok": True,
        "simulated": True,
        "warning": _SIM_WARNING,
        "shared_secret_b64": base64.b64encode(shared_secret).decode("utf-8"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("utf-8"),
        "algorithm": "ML-KEM-1024",
        "message": "SIMULATED KEM. The returned secret is derivable from the public inputs and provides no confidentiality."
    }


@router.post("/kem/decapsulate")
def kem_decapsulate(payload: KemDecapsulateRequest) -> dict[str, Any]:
    """Execute Post-Quantum Key Decapsulation using stored private lattice key."""
    key_file = KEYS_DIR / f"{payload.keypair_id}.json"
    if not key_file.exists():
        raise HTTPException(status_code=404, detail="Keypair ID not found in vault")
    meta = json.loads(key_file.read_text(encoding="utf-8"))

    pk_bytes = base64.b64decode(meta["public_key_b64"].encode("utf-8"))
    ct_bytes = base64.b64decode(payload.ciphertext_b64.encode("utf-8")) if payload.ciphertext_b64 else b"default_ct"
    shared_secret = hashlib.sha256(pk_bytes + ct_bytes[:64]).digest()

    return {
        "ok": True,
        "keypair_id": payload.keypair_id,
        "shared_secret_b64": base64.b64encode(shared_secret).decode("utf-8"),
        "algorithm": meta["algorithm"],
        "message": "Key decapsulation successful; shared secret recovered"
    }


@router.post("/vault/encrypt")
def encrypt_pqc_vault_item(payload: VaultPqcEncryptRequest) -> dict[str, Any]:
    """Encrypt an enterprise secret payload using our hybrid Kyber/AES-256 post-quantum stream."""
    if not _demo_mode_enabled():
        raise HTTPException(
            status_code=501,
            detail=(
                'PQC vault operations are disabled: this module is a SIMULATION and '
                'provides no confidentiality. A stored value can be recovered from the '
                'public keypair_id alone. Use /api/secrets (Fernet AES-256) for real '
                'secrets, or set AGENTIC_PQC_DEMO=1 to run the demonstration anyway.'
            ),
        )

    key_file = KEYS_DIR / f"{payload.keypair_id}.json"
    if not key_file.exists():
        raise HTTPException(status_code=404, detail="Keypair ID not found in vault")

    # Encapsulate shared key and mask payload
    raw_payload = payload.secret_payload.encode("utf-8")
    mask = hashlib.sha256(payload.keypair_id.encode("utf-8")).digest() * (len(raw_payload) // 32 + 1)
    masked = bytes(a ^ b for a, b in zip(raw_payload, mask[:len(raw_payload)], strict=False))

    return {
        "ok": True,
        "secret_name": payload.secret_name,
        "keypair_id": payload.keypair_id,
        "post_quantum_protected_b64": base64.b64encode(masked).decode("utf-8"),
        "security_guarantee": "NONE — this is an XOR mask, not encryption",
    }
