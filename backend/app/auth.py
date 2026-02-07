from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: str
    full_name: str | None = None
    password_change_required: bool = False
    onboarding_completed: bool = False


@dataclass(frozen=True)
class _SeedUser:
    username: str
    password: str
    role: str
    full_name: str | None = None
    password_change_required: bool = False
    onboarding_completed: bool = False


class AuthManager:
    def __init__(
        self,
        *,
        db_path: str,
        secret_key: str,
        algorithm: str,
        access_token_exp_minutes: int,
        refresh_token_exp_minutes: int,
        login_max_attempts: int,
        login_window_seconds: int,
        login_lockout_seconds: int,
        seed_users: list[_SeedUser],
    ) -> None:
        self.db_path = db_path
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_exp_minutes = access_token_exp_minutes
        self.refresh_token_exp_minutes = refresh_token_exp_minutes
        self.login_max_attempts = max(1, login_max_attempts)
        self.login_window_seconds = max(1, login_window_seconds)
        self.login_lockout_seconds = max(1, login_lockout_seconds)
        self._init_storage(seed_users)

    @classmethod
    def from_env(cls) -> "AuthManager":
        secret_key = os.getenv("TRIAGE_AUTH_SECRET", "change-me-in-production")
        algorithm = os.getenv("TRIAGE_AUTH_ALGORITHM", "HS256")
        db_path = os.getenv("TRIAGE_AUTH_DB_PATH", os.getenv("TRIAGE_DB_PATH", "triage.db"))
        try:
            access_exp_minutes = int(os.getenv("TRIAGE_AUTH_EXPIRES_MINUTES", "30"))
        except ValueError:
            access_exp_minutes = 30
        try:
            refresh_exp_minutes = int(os.getenv("TRIAGE_AUTH_REFRESH_EXPIRES_MINUTES", "10080"))
        except ValueError:
            refresh_exp_minutes = 10080
        login_max_attempts = _env_int("TRIAGE_AUTH_LOGIN_MAX_ATTEMPTS", 5, min_value=1)
        login_window_seconds = _env_int("TRIAGE_AUTH_LOGIN_WINDOW_SECONDS", 300, min_value=1)
        login_lockout_seconds = _env_int("TRIAGE_AUTH_LOGIN_LOCKOUT_SECONDS", 900, min_value=1)
        force_change_defaults = _env_bool("TRIAGE_AUTH_FORCE_CHANGE_DEFAULTS", True)
        seed_users = _load_seed_users(force_change_defaults=force_change_defaults)
        return cls(
            db_path=db_path,
            secret_key=secret_key,
            algorithm=algorithm,
            access_token_exp_minutes=access_exp_minutes,
            refresh_token_exp_minutes=refresh_exp_minutes,
            login_max_attempts=login_max_attempts,
            login_window_seconds=login_window_seconds,
            login_lockout_seconds=login_lockout_seconds,
            seed_users=seed_users,
        )

    def authenticate(self, username: str, password: str) -> AuthUser | None:
        row = self._get_user_row(username)
        if not row:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return self._row_to_user(row)

    def check_login_allowed(self, username: str, source_ip: str | None) -> tuple[bool, int]:
        username_key = self._login_key_username(username)
        source_ip_key = self._login_key_source_ip(source_ip)
        now_epoch = self._now_epoch()
        window_start = now_epoch - self.login_window_seconds
        with self._connect() as conn:
            self._prune_login_failures(conn, now_epoch)
            failure_count, last_failure_epoch = self._get_recent_failure_stats(
                conn=conn,
                username_key=username_key,
                source_ip_key=source_ip_key,
                window_start=window_start,
            )
        if failure_count < self.login_max_attempts:
            return True, 0
        lockout_remaining = (last_failure_epoch + self.login_lockout_seconds) - now_epoch
        if lockout_remaining <= 0:
            return True, 0
        return False, int(lockout_remaining)

    def record_failed_login(self, username: str, source_ip: str | None) -> tuple[bool, int]:
        username_key = self._login_key_username(username)
        source_ip_key = self._login_key_source_ip(source_ip)
        now_epoch = self._now_epoch()
        window_start = now_epoch - self.login_window_seconds
        with self._connect() as conn:
            self._prune_login_failures(conn, now_epoch)
            conn.execute(
                """
                INSERT INTO auth_login_failures (
                    username,
                    source_ip,
                    attempted_at_epoch
                )
                VALUES (?, ?, ?);
                """,
                (username_key, source_ip_key, now_epoch),
            )
            failure_count, last_failure_epoch = self._get_recent_failure_stats(
                conn=conn,
                username_key=username_key,
                source_ip_key=source_ip_key,
                window_start=window_start,
            )
        if failure_count < self.login_max_attempts:
            return False, 0
        lockout_remaining = (last_failure_epoch + self.login_lockout_seconds) - now_epoch
        if lockout_remaining <= 0:
            return False, 0
        return True, int(lockout_remaining)

    def record_successful_login(self, username: str, source_ip: str | None) -> None:
        username_key = self._login_key_username(username)
        source_ip_key = self._login_key_source_ip(source_ip)
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM auth_login_failures
                WHERE username = ? AND source_ip = ?;
                """,
                (username_key, source_ip_key),
            )

    def get_user(self, username: str) -> AuthUser:
        row = self._get_user_row(username)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject.",
            )
        return self._row_to_user(row)

    def issue_access_token(self, user: AuthUser) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "typ": "access",
            "sub": user.username,
            "role": user.role,
            "full_name": user.full_name,
            "pwd_reset_required": bool(user.password_change_required),
            "onboarding_completed": bool(user.onboarding_completed),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self.access_token_exp_minutes)).timestamp()),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def issue_refresh_token(
        self,
        user: AuthUser,
        family_id: str | None = None,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        jti = str(uuid4())
        family = family_id or str(uuid4())
        exp = int((now + timedelta(minutes=self.refresh_token_exp_minutes)).timestamp())
        payload = {
            "typ": "refresh",
            "sub": user.username,
            "role": user.role,
            "full_name": user.full_name,
            "pwd_reset_required": bool(user.password_change_required),
            "onboarding_completed": bool(user.onboarding_completed),
            "jti": jti,
            "fid": family,
            "iat": int(now.timestamp()),
            "exp": exp,
        }
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        if conn is not None:
            conn.execute(
                """
                INSERT INTO auth_refresh_sessions (
                    jti,
                    username,
                    family_id,
                    expires_at_epoch,
                    revoked,
                    replaced_by_jti
                )
                VALUES (?, ?, ?, ?, 0, NULL);
                """,
                (jti, user.username, family, exp),
            )
        else:
            with self._connect() as local_conn:
                local_conn.execute(
                    """
                    INSERT INTO auth_refresh_sessions (
                        jti,
                        username,
                        family_id,
                        expires_at_epoch,
                        revoked,
                        replaced_by_jti
                    )
                    VALUES (?, ?, ?, ?, 0, NULL);
                    """,
                    (jti, user.username, family, exp),
                )
        return token

    def issue_token_pair(self, user: AuthUser, *, family_id: str | None = None) -> dict[str, Any]:
        return {
            "access_token": self.issue_access_token(user),
            "refresh_token": self.issue_refresh_token(user, family_id=family_id),
            "token_type": "bearer",
            "expires_in": self.access_token_exp_minutes * 60,
            "refresh_expires_in": self.refresh_token_exp_minutes * 60,
            "user": user,
        }

    def parse_access_token(self, token: str) -> AuthUser:
        payload = self._decode_token(token)
        if payload.get("typ") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type.",
            )
        username = payload.get("sub")
        if not isinstance(username, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token payload.",
            )
        return self.get_user(username)

    def rotate_refresh_token(self, refresh_token: str) -> dict[str, Any]:
        payload = self._decode_token(refresh_token)
        if payload.get("typ") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type.",
            )

        jti = payload.get("jti")
        family_id = payload.get("fid")
        username = payload.get("sub")
        if not isinstance(jti, str) or not isinstance(family_id, str) or not isinstance(username, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed refresh token payload.",
            )

        now_epoch = int(datetime.now(timezone.utc).timestamp())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute(
                """
                SELECT
                    jti,
                    username,
                    family_id,
                    expires_at_epoch,
                    revoked
                FROM auth_refresh_sessions
                WHERE jti = ?;
                """,
                (jti,),
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token is not recognized.",
                )

            if int(row["revoked"]) == 1:
                conn.execute(
                    """
                    UPDATE auth_refresh_sessions
                    SET revoked = 1, revoked_at = datetime('now')
                    WHERE family_id = ?;
                    """,
                    (row["family_id"],),
                )
                conn.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token reuse detected.",
                )

            if int(row["expires_at_epoch"]) < now_epoch:
                conn.execute(
                    """
                    UPDATE auth_refresh_sessions
                    SET revoked = 1, revoked_at = datetime('now')
                    WHERE jti = ?;
                    """,
                    (jti,),
                )
                conn.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token expired.",
                )

            user_row = conn.execute(
                """
                SELECT username, role, full_name, password_change_required, onboarding_completed
                FROM auth_users
                WHERE username = ?;
                """,
                (username,),
            ).fetchone()
            if not user_row:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token subject.",
                )
            user = self._row_to_user(user_row)

            conn.execute(
                """
                UPDATE auth_refresh_sessions
                SET revoked = 1, used_at = datetime('now'), revoked_at = datetime('now')
                WHERE jti = ?;
                """,
                (jti,),
            )

            new_refresh = self.issue_refresh_token(user, family_id=family_id, conn=conn)
            new_payload = self._decode_token(new_refresh)
            new_jti = str(new_payload["jti"])

            conn.execute(
                """
                UPDATE auth_refresh_sessions
                SET replaced_by_jti = ?
                WHERE jti = ?;
                """,
                (new_jti, jti),
            )

        return {
            "access_token": self.issue_access_token(user),
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": self.access_token_exp_minutes * 60,
            "refresh_expires_in": self.refresh_token_exp_minutes * 60,
            "user": user,
        }

    def revoke_refresh_token(self, refresh_token: str) -> None:
        try:
            payload = self._decode_token(refresh_token, verify_exp=False)
        except HTTPException:
            return
        jti = payload.get("jti")
        if not isinstance(jti, str):
            return
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE auth_refresh_sessions
                SET revoked = 1, revoked_at = datetime('now')
                WHERE jti = ?;
                """,
                (jti,),
            )

    def revoke_user_sessions(self, username: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE auth_refresh_sessions
                SET revoked = 1, revoked_at = datetime('now')
                WHERE username = ?;
                """,
                (username,),
            )

    def change_password(
        self,
        *,
        username: str,
        current_password: str,
        new_password: str,
    ) -> AuthUser:
        row = self._get_user_row(username)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found.",
            )
        if not verify_password(current_password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is invalid.",
            )
        if current_password == new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from current password.",
            )
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters.",
            )

        new_hash = hash_password(new_password)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE auth_users
                SET password_hash = ?, password_change_required = 0, updated_at = datetime('now')
                WHERE username = ?;
                """,
                (new_hash, username),
            )
            conn.execute(
                """
                UPDATE auth_refresh_sessions
                SET revoked = 1, revoked_at = datetime('now')
                WHERE username = ?;
                """,
                (username,),
            )
        return self.get_user(username)

    def complete_onboarding(self, *, username: str) -> AuthUser:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE auth_users
                SET onboarding_completed = 1, updated_at = datetime('now')
                WHERE username = ?;
                """,
                (username,),
            )
        return self.get_user(username)

    def reset_onboarding(self, *, username: str) -> AuthUser:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username
                FROM auth_users
                WHERE username = ?;
                """,
                (username,),
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found.",
                )
            conn.execute(
                """
                UPDATE auth_users
                SET onboarding_completed = 0, updated_at = datetime('now')
                WHERE username = ?;
                """,
                (username,),
            )
        return self.get_user(username)

    def list_users(self) -> list[AuthUser]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT username, role, full_name, password_change_required, onboarding_completed
                FROM auth_users
                ORDER BY role, username;
                """
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str,
        full_name: str | None = None,
    ) -> AuthUser:
        if role.lower() not in {"admin", "nurse", "operations"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Must be admin, nurse, or operations.",
            )
        if len(password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters.",
            )
        password_hash = hash_password(password)
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO auth_users (
                        username,
                        password_hash,
                        role,
                        full_name,
                        password_change_required,
                        onboarding_completed,
                        is_default
                    )
                    VALUES (?, ?, ?, ?, 1, 0, 0);
                    """,
                    (username, password_hash, role.lower(), full_name),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username already exists.",
                ) from exc
        return self.get_user(username)

    def update_user(
        self,
        *,
        username: str,
        role: str | None = None,
        full_name: str | None = None,
    ) -> AuthUser:
        if role and role.lower() not in {"admin", "nurse", "operations"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Must be admin, nurse, or operations.",
            )
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username
                FROM auth_users
                WHERE username = ?;
                """,
                (username,),
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found.",
                )
            if role:
                conn.execute(
                    """
                    UPDATE auth_users
                    SET role = ?, updated_at = datetime('now')
                    WHERE username = ?;
                    """,
                    (role.lower(), username),
                )
            if full_name is not None:
                conn.execute(
                    """
                    UPDATE auth_users
                    SET full_name = ?, updated_at = datetime('now')
                    WHERE username = ?;
                    """,
                    (full_name, username),
                )
        return self.get_user(username)

    def admin_reset_password(
        self,
        *,
        username: str,
        new_password: str,
    ) -> AuthUser:
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters.",
            )
        new_hash = hash_password(new_password)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username
                FROM auth_users
                WHERE username = ?;
                """,
                (username,),
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found.",
                )
            conn.execute(
                """
                UPDATE auth_users
                SET password_hash = ?, password_change_required = 1, updated_at = datetime('now')
                WHERE username = ?;
                """,
                (new_hash, username),
            )
            conn.execute(
                """
                UPDATE auth_refresh_sessions
                SET revoked = 1, revoked_at = datetime('now')
                WHERE username = ?;
                """,
                (username,),
            )
        return self.get_user(username)

    def delete_user(self, *, username: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username, is_default
                FROM auth_users
                WHERE username = ?;
                """,
                (username,),
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found.",
                )
            if int(row["is_default"]) == 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete default system users.",
                )
            conn.execute(
                """
                DELETE FROM auth_refresh_sessions
                WHERE username = ?;
                """,
                (username,),
            )
            conn.execute(
                """
                DELETE FROM auth_users
                WHERE username = ?;
                """,
                (username,),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_storage(self, seed_users: list[_SeedUser]) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS auth_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT,
            password_change_required INTEGER NOT NULL DEFAULT 0,
            onboarding_completed INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS auth_refresh_sessions (
            jti TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            family_id TEXT NOT NULL,
            expires_at_epoch INTEGER NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            replaced_by_jti TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            revoked_at TEXT,
            used_at TEXT,
            FOREIGN KEY(username) REFERENCES auth_users(username)
        );

        CREATE TABLE IF NOT EXISTS auth_login_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            source_ip TEXT NOT NULL,
            attempted_at_epoch INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_auth_users_role
            ON auth_users(role);
        CREATE INDEX IF NOT EXISTS idx_auth_refresh_username
            ON auth_refresh_sessions(username);
        CREATE INDEX IF NOT EXISTS idx_auth_refresh_family
            ON auth_refresh_sessions(family_id);
        CREATE INDEX IF NOT EXISTS idx_auth_login_failures_lookup
            ON auth_login_failures(username, source_ip, attempted_at_epoch);
        """
        with self._connect() as conn:
            conn.executescript(schema)
            self._ensure_auth_users_column(
                conn,
                column_name="onboarding_completed",
                column_sql="INTEGER NOT NULL DEFAULT 0",
            )
            for seed in seed_users:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO auth_users (
                        username,
                        password_hash,
                        role,
                        full_name,
                        password_change_required,
                        onboarding_completed,
                        is_default
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        seed.username,
                        hash_password(seed.password),
                        seed.role,
                        seed.full_name,
                        int(seed.password_change_required),
                        int(seed.onboarding_completed),
                        1,
                    ),
                )

    def _get_user_row(self, username: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT
                    username,
                    password_hash,
                    role,
                    full_name,
                    password_change_required,
                    onboarding_completed
                FROM auth_users
                WHERE username = ?;
                """,
                (username,),
            ).fetchone()

    def _prune_login_failures(self, conn: sqlite3.Connection, now_epoch: int) -> None:
        retention = max(self.login_window_seconds, self.login_lockout_seconds) * 2
        cutoff_epoch = now_epoch - retention
        conn.execute(
            """
            DELETE FROM auth_login_failures
            WHERE attempted_at_epoch < ?;
            """,
            (cutoff_epoch,),
        )

    @staticmethod
    def _get_recent_failure_stats(
        *,
        conn: sqlite3.Connection,
        username_key: str,
        source_ip_key: str,
        window_start: int,
    ) -> tuple[int, int]:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS failure_count,
                MAX(attempted_at_epoch) AS last_failure_epoch
            FROM auth_login_failures
            WHERE username = ?
              AND source_ip = ?
              AND attempted_at_epoch >= ?;
            """,
            (username_key, source_ip_key, window_start),
        ).fetchone()
        failure_count = int(row["failure_count"] or 0)
        last_failure_epoch = int(row["last_failure_epoch"] or 0)
        return failure_count, last_failure_epoch

    @staticmethod
    def _login_key_username(username: str) -> str:
        return username.strip().lower()

    @staticmethod
    def _login_key_source_ip(source_ip: str | None) -> str:
        value = (source_ip or "unknown").strip()
        return value or "unknown"

    @staticmethod
    def _now_epoch() -> int:
        return int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> AuthUser:
        return AuthUser(
            username=row["username"],
            role=row["role"],
            full_name=row["full_name"],
            password_change_required=bool(row["password_change_required"]),
            onboarding_completed=bool(row["onboarding_completed"]),
        )

    @staticmethod
    def _ensure_auth_users_column(
        conn: sqlite3.Connection,
        *,
        column_name: str,
        column_sql: str,
    ) -> None:
        existing = conn.execute("PRAGMA table_info(auth_users);").fetchall()
        names = {row["name"] for row in existing}
        if column_name in names:
            return
        conn.execute(f"ALTER TABLE auth_users ADD COLUMN {column_name} {column_sql};")

    def _decode_token(self, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        try:
            return jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": verify_exp},
            )
        except PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
            ) from exc


def hash_password(password: str) -> str:
    iterations = 390_000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${iterations}${salt_b64}${digest_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, *, min_value: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    if parsed < min_value:
        return default
    return parsed


def _load_seed_users(*, force_change_defaults: bool) -> list[_SeedUser]:
    raw = os.getenv("TRIAGE_AUTH_USERS_JSON", "")
    if not raw.strip():
        return _default_seed_users(force_change_defaults=force_change_defaults)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _default_seed_users(force_change_defaults=force_change_defaults)

    if not isinstance(data, list):
        return _default_seed_users(force_change_defaults=force_change_defaults)

    users: list[_SeedUser] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username", "")).strip()
        password = str(item.get("password", "")).strip()
        role = str(item.get("role", "")).strip().lower()
        full_name = str(item.get("full_name", "")).strip() or None
        password_change_required = bool(item.get("password_change_required", False))
        onboarding_completed = bool(item.get("onboarding_completed", False))
        if not username or not password or role not in {"admin", "nurse", "operations"}:
            continue
        users.append(
            _SeedUser(
                username=username,
                password=password,
                role=role,
                full_name=full_name,
                password_change_required=password_change_required,
                onboarding_completed=onboarding_completed,
            )
        )
    return users or _default_seed_users(force_change_defaults=force_change_defaults)


def _default_seed_users(*, force_change_defaults: bool) -> list[_SeedUser]:
    return [
        _SeedUser(
            username="admin",
            password="admin123",
            role="admin",
            full_name="System Admin",
            password_change_required=force_change_defaults,
        ),
        _SeedUser(
            username="nurse",
            password="nurse123",
            role="nurse",
            full_name="Triage Nurse",
            password_change_required=force_change_defaults,
        ),
        _SeedUser(
            username="ops",
            password="ops123",
            role="operations",
            full_name="Operations Analyst",
            password_change_required=force_change_defaults,
        ),
    ]


bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_manager(request: Request) -> AuthManager:
    manager = getattr(request.app.state, "auth_manager", None)
    if not manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth manager unavailable.",
        )
    return manager


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_manager: AuthManager = Depends(get_auth_manager),
) -> AuthUser:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )
    return auth_manager.parse_access_token(credentials.credentials)


def require_roles(*roles: str):
    allowed = {role.lower() for role in roles}

    def _dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.password_change_required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password change is required before accessing this resource.",
            )
        if not user.onboarding_completed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Onboarding is required before accessing this resource.",
            )
        if user.role.lower() not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role privileges.",
            )
        return user

    return _dependency
