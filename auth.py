"""
Verifies Supabase-issued JWTs so FastAPI endpoints know which user is
calling them. Supabase handles the actual login (password checking, token
issuing, refresh) on the frontend via its SDK - this file's only job is to
check that an incoming request's token is genuine and extract the user's
id from it, so endpoints can scope data (like saved charts) to the right
person.

Uses Supabase's JWKS (public key) endpoint to verify ES256-signed tokens -
the current default for new Supabase projects (visible as "ECC (P-256)"
under Project Settings > API > JWT Keys > JWT Signing Keys). This is
simpler to set up than the older shared-secret approach: no secret to
store at all, since verification uses Supabase's PUBLIC key, which is
meant to be fetched openly.

Setup required:
    SUPABASE_URL - your project's URL (e.g. https://xxxxx.supabase.co).
    SUPABASE_ANON_KEY - the project's public "anon" key (Project Settings
    > API > Project API keys) - safe to use here since it's the same key
    your frontend already uses; it only grants what a logged-in user's own
    token allows, which is exactly what get_supabase_client relies on.
    Both loaded automatically from a .env file (same folder as main.py)
    via load_dotenv() below.
"""
import os
from dotenv import load_dotenv
from fastapi import Header, HTTPException
from jwt import PyJWKClient
from supabase import create_client, Client
import jwt

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# PyJWKClient fetches and caches Supabase's public signing keys from this
# endpoint, automatically handling key rotation (e.g. when Supabase
# rotates from the old Legacy HS256 key to the current ECC key, as your
# project already has) - no manual key management needed on this side.
_jwks_client = PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json") if SUPABASE_URL else None


def _verify_token(authorization: str) -> dict:
    """Shared by both dependencies below - verifies the token once, each
    dependency then pulls out what it specifically needs from the result."""
    if not _jwks_client:
        # Fails loudly rather than silently accepting every request as
        # "authenticated" - a missing SUPABASE_URL is a deployment
        # mistake, not something that should quietly disable auth.
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL is not set on the server - auth cannot be verified.",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",  # Supabase sets this on every user token it issues
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired - please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    payload["_raw_token"] = token
    return payload


def get_current_user_id(authorization: str = Header(...)) -> str:
    """
    FastAPI dependency - add `user_id: str = Depends(get_current_user_id)`
    as a parameter to any endpoint that should require login but doesn't
    need to touch the database (e.g. just needs to know who's calling).
    Raises 401 if the token is missing, malformed, expired, or signed with
    a key that doesn't match Supabase's current public keys.
    """
    payload = _verify_token(authorization)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token did not contain a user id")
    return user_id


def get_supabase_client(authorization: str = Header(...)) -> Client:
    """
    FastAPI dependency - add `db: Client = Depends(get_supabase_client)` to
    any endpoint that reads or writes user data (like saved charts).
    Returns a Supabase client authenticated AS the calling user (via their
    own verified token), so every query automatically respects Row Level
    Security - e.g. `db.table("saved_charts").select("*")` returns only
    THIS user's rows, not everyone's, enforced by the database itself
    rather than by application code remembering to filter correctly.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL or SUPABASE_ANON_KEY is not set on the server.",
        )

    payload = _verify_token(authorization)
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    # Attaches the user's own token to this client's requests, which is
    # what makes auth.uid() resolve correctly inside the RLS policies.
    client.postgrest.auth(payload["_raw_token"])
    return client
