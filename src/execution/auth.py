"""Commercial SaaS Authentication & Tier Governance Module.

Manages API keys, subscription tiers (Free, Pro, Institutional),
daily usage quotas, and route-level authorization.
"""

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import logging
from pathlib import Path
import secrets
import sqlite3
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class UserTierProfile:
    user_id: str
    email: str
    api_key: str
    tier: str  # "FREE", "PRO", "INSTITUTIONAL"
    requests_today: int
    daily_quota: int
    allowed_intervals: Tuple[str, ...]
    broker_execution_enabled: bool


class AuthManager:
    """Manages SaaS user registration, API keys, and subscription tier enforcement."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.db_path = base_dir / "data" / "trading_ledger.db"
        else:
            self.db_path = Path(db_path)

        self._init_auth_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_auth_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    api_key TEXT UNIQUE NOT NULL,
                    tier TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    requests_today INTEGER DEFAULT 0,
                    last_request_date TEXT NOT NULL
                )
            """)

            # Pre-seed a default Admin / Pro Demo Key if none exist
            cursor.execute("SELECT id FROM users WHERE api_key = 'synapse_demo_pro_key_2026'")
            if not cursor.fetchone():
                today_str = date.today().isoformat()
                now_str = datetime.utcnow().isoformat()
                cursor.execute("""
                    INSERT INTO users (id, email, api_key, tier, created_at, requests_today, last_request_date)
                    VALUES ('USR_DEMO', 'subscriber@synapse-titan.io', 'synapse_demo_pro_key_2026', 'INSTITUTIONAL', ?, 0, ?)
                """, (now_str, today_str))
            conn.commit()

    def generate_api_key(self, prefix: str = "syn_") -> str:
        """Generates cryptographically secure API key."""
        return f"{prefix}{secrets.token_urlsafe(24)}"

    def register_user(self, email: str, tier: str = "PRO") -> UserTierProfile:
        """Creates a new subscriber profile and returns their API key."""
        email = email.strip().lower()
        tier = tier.strip().upper()
        if tier not in ["FREE", "PRO", "INSTITUTIONAL"]:
            tier = "FREE"

        api_key = self.generate_api_key(prefix="syn_live_" if tier == "INSTITUTIONAL" else "syn_")
        user_id = f"USR_{secrets.token_hex(4).upper()}"
        now_str = datetime.utcnow().isoformat()
        today_str = date.today().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (id, email, api_key, tier, created_at, requests_today, last_request_date)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (user_id, email, api_key, tier, now_str, today_str))
            conn.commit()

        return self.get_user_by_key(api_key)

    def get_user_by_key(self, api_key: str) -> Optional[UserTierProfile]:
        """Validates API key and updates rate-limit usage counters."""
        if not api_key:
            return None

        today_str = date.today().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE api_key = ?", (api_key,))
            row = cursor.fetchone()
            if not row:
                return None

            reqs_today = int(row["requests_today"])
            last_date = str(row["last_request_date"])

            # Reset daily counter if day changed
            if last_date != today_str:
                reqs_today = 0
                cursor.execute("""
                    UPDATE users SET requests_today = 0, last_request_date = ? WHERE api_key = ?
                """, (today_str, api_key))
                conn.commit()

            tier = str(row["tier"]).upper()
            if tier == "FREE":
                quota = 25
                intervals = ("1d",)
                broker_enabled = False
            elif tier == "PRO":
                quota = 1000
                intervals = ("1d", "1h", "30m", "15m")
                broker_enabled = False  # Strictly paper-trading-only: live brokerage disabled
            else:  # INSTITUTIONAL
                quota = 100000
                intervals = ("1d", "1h", "30m", "15m", "5m", "1m")
                broker_enabled = False  # Strictly paper-trading-only: live brokerage disabled

            # Increment count
            cursor.execute("""
                UPDATE users SET requests_today = requests_today + 1 WHERE api_key = ?
            """, (api_key,))
            conn.commit()

            return UserTierProfile(
                user_id=row["id"],
                email=row["email"],
                api_key=row["api_key"],
                tier=tier,
                requests_today=reqs_today + 1,
                daily_quota=quota,
                allowed_intervals=intervals,
                broker_execution_enabled=broker_enabled,
            )
