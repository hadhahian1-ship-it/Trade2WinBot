import asyncio
import json
import os
import time

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

_default: dict = {
    "approved_users": [],
    "pending_kyc": [],
    "referrals": {},
    "referred_by": {},
    "all_users": [],
    "user_names": {},
    "user_joined_at": {},    # {user_id_str: unix_timestamp}
    "spin_history": {},
    "financial_prizes": [],
    "link_clicks": [],       # [{user_id, timestamp}]  — Monaxa reg link
    "support_clicks": [],    # [{user_id, timestamp}]  — Monaxa support section
}

SPIN_COOLDOWN   = 86400       # 24 hours in seconds
ADMIN_WHEEL_ID  = 8633546148  # bypass 24-h limit; unlimited spins for testing


def _load() -> dict:
    if not os.path.exists(DATA_FILE):
        return {k: v.copy() if isinstance(v, (dict, list)) else v for k, v in _default.items()}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, val in _default.items():
            if key not in data:
                data[key] = val.copy() if isinstance(val, (dict, list)) else val
        return data
    except Exception:
        return {k: v.copy() if isinstance(v, (dict, list)) else v for k, v in _default.items()}


def _save(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Users ───

def register_user(user_id: int, display_name: str = "") -> None:
    data = _load()
    uid_str = str(user_id)
    if user_id not in data["all_users"]:
        data["all_users"].append(user_id)
        # Record join timestamp for new users only
        data.setdefault("user_joined_at", {})[uid_str] = time.time()
    if display_name:
        data["user_names"][uid_str] = display_name
    _save(data)


def get_user_name(user_id: int) -> str:
    data = _load()
    return data["user_names"].get(str(user_id), f"مستخدم #{user_id}")


def get_all_users() -> list:
    return _load()["all_users"]


def get_total_users() -> int:
    return len(_load()["all_users"])


# ─── Referrals ───

def get_top_referrers(n: int = 10) -> list:
    """Returns list of (user_id, display_name, count) sorted descending."""
    data = _load()
    items = []
    for uid_str, count in data["referrals"].items():
        uid = int(uid_str)
        name = data["user_names"].get(uid_str, f"مستخدم #{uid}")
        items.append((uid, name, count))
    items.sort(key=lambda x: x[2], reverse=True)
    return items[:n]


def get_user_referral_info(user_id: int) -> dict:
    data = _load()
    uid_str = str(user_id)
    return {
        "user_id": user_id,
        "name": data["user_names"].get(uid_str, f"مستخدم #{user_id}"),
        "referral_count": data["referrals"].get(uid_str, 0),
        "is_registered": user_id in data["all_users"],
        "is_approved": user_id in data["approved_users"],
        "is_pending": user_id in data["pending_kyc"],
    }


def is_approved(user_id: int) -> bool:
    data = _load()
    return user_id in data["approved_users"]


def approve_user(user_id: int) -> None:
    data = _load()
    if user_id not in data["approved_users"]:
        data["approved_users"].append(user_id)
    if user_id in data["pending_kyc"]:
        data["pending_kyc"].remove(user_id)
    _save(data)


def reject_user(user_id: int) -> None:
    data = _load()
    if user_id in data["pending_kyc"]:
        data["pending_kyc"].remove(user_id)
    _save(data)


def set_pending(user_id: int) -> None:
    data = _load()
    if user_id not in data["pending_kyc"]:
        data["pending_kyc"].append(user_id)
    _save(data)


def is_pending(user_id: int) -> bool:
    data = _load()
    return user_id in data["pending_kyc"]


def record_referral(new_user_id: int, inviter_id: int) -> bool:
    data = _load()
    key = str(new_user_id)
    if key in data["referred_by"]:
        return False
    if new_user_id == inviter_id:
        return False
    data["referred_by"][key] = inviter_id
    inv_key = str(inviter_id)
    data["referrals"][inv_key] = data["referrals"].get(inv_key, 0) + 1
    _save(data)
    return True


def get_referral_count(user_id: int) -> int:
    data = _load()
    return data["referrals"].get(str(user_id), 0)


# ─── Financial Prizes Ledger ───

def log_financial_prize(
    user_id: int,
    full_name: str,
    username: str,
    prize_key: str,
    amount: int,
) -> str:
    """
    Securely logs a financial prize to the immutable prizes ledger.
    Returns a unique prize_id for reference in admin alerts.
    """
    data = _load()
    prize_id = f"PZ-{int(time.time())}-{user_id}"
    entry = {
        "prize_id": prize_id,
        "user_id": user_id,
        "full_name": full_name,
        "username": username or "N/A",
        "prize_key": prize_key,
        "amount_usd": amount,
        "timestamp": time.time(),
        "status": "pending",
    }
    data["financial_prizes"].append(entry)
    _save(data)
    return prize_id


def get_financial_prizes() -> list:
    """Returns the full financial prizes ledger, newest first."""
    data = _load()
    prizes = data.get("financial_prizes", [])
    return list(reversed(prizes))


# ─── Lucky Wheel ───

def can_spin(user_id: int) -> tuple[bool, int]:
    """Returns (can_spin: bool, seconds_remaining: int).
    Admin ID always gets (True, 0) regardless of history.
    """
    if user_id == ADMIN_WHEEL_ID:
        return True, 0
    data = _load()
    uid_str = str(user_id)
    history = data["spin_history"].get(uid_str, {})
    last_spin = history.get("last_spin", 0)
    elapsed = time.time() - last_spin
    if elapsed >= SPIN_COOLDOWN:
        return True, 0
    remaining = int(SPIN_COOLDOWN - elapsed)
    return False, remaining


def record_spin(user_id: int, prize_key: str, update_cooldown: bool = True) -> None:
    """
    Records a spin and its prize to the user's history.
    If update_cooldown=False the 24-hour timer is NOT advanced (used for 'try_again').
    Admin ID never advances the cooldown so unlimited testing is preserved.
    """
    data = _load()
    uid_str = str(user_id)
    if uid_str not in data["spin_history"]:
        data["spin_history"][uid_str] = {"last_spin": 0, "wins": []}
    # Admin never consumes the 24-h slot
    if update_cooldown and user_id != ADMIN_WHEEL_ID:
        data["spin_history"][uid_str]["last_spin"] = time.time()
    entry = {"prize": prize_key, "timestamp": time.time()}
    data["spin_history"][uid_str]["wins"].append(entry)
    _save(data)


def reset_spin(user_id: int) -> None:
    """
    Manually resets a user's 24-hour spin cooldown by zeroing last_spin.
    After this call, can_spin(user_id) will return (True, 0) immediately.
    """
    data = _load()
    uid_str = str(user_id)
    if uid_str not in data["spin_history"]:
        data["spin_history"][uid_str] = {"last_spin": 0, "wins": []}
    else:
        data["spin_history"][uid_str]["last_spin"] = 0
    _save(data)


def get_user_spin_history(user_id: int) -> list:
    """Returns list of win dicts for this user."""
    data = _load()
    return data["spin_history"].get(str(user_id), {}).get("wins", [])


def get_available_spins(user_id: int) -> int:
    """
    Returns 1 if the user is eligible to spin right now, 0 otherwise.
    Returns -1 (sentinel) for the Admin ID to signal unlimited spins.
    """
    if user_id == ADMIN_WHEEL_ID:
        return -1
    ok, _ = can_spin(user_id)
    return 1 if ok else 0


def get_spin_stats() -> dict:
    """Global spin stats for the admin dashboard."""
    data = _load()
    total_spins = 0
    total_try_again = 0
    total_vip = 0
    total_money_5 = 0
    total_money_10 = 0
    unique_spinners = 0

    for uid_str, hist in data["spin_history"].items():
        wins = hist.get("wins", [])
        if wins:
            unique_spinners += 1
        for w in wins:
            total_spins += 1
            p = w.get("prize", "")
            if p == "try_again":
                total_try_again += 1
            elif p == "vip":
                total_vip += 1
            elif p == "money_5":
                total_money_5 += 1
            elif p == "money_10":
                total_money_10 += 1

    return {
        "total_spins": total_spins,
        "unique_spinners": unique_spinners,
        "try_again": total_try_again,
        "vip": total_vip,
        "money_5": total_money_5,
        "money_10": total_money_10,
        "prize_money_total": total_money_5 * 5 + total_money_10 * 10,
    }


# ─── Event Tracking (link clicks / support requests) ─────────────────────────

def record_link_click(user_id: int) -> None:
    """Record a tap on the Monaxa registration link page."""
    data = _load()
    data.setdefault("link_clicks", []).append(
        {"user_id": user_id, "timestamp": time.time()}
    )
    _save(data)


def record_support_click(user_id: int) -> None:
    """Record a tap on the Monaxa support section."""
    data = _load()
    data.setdefault("support_clicks", []).append(
        {"user_id": user_id, "timestamp": time.time()}
    )
    _save(data)


# ─── Daily Report Stats ───────────────────────────────────────────────────────

def get_daily_stats(since_ts: float) -> dict:
    """
    Return aggregated metrics for events that occurred after `since_ts`.
    Used by the admin daily report job.
    """
    data = _load()

    # New users joined since `since_ts`
    joined_at = data.get("user_joined_at", {})
    new_users = sum(1 for ts in joined_at.values() if ts >= since_ts)

    # Wheel spins since `since_ts`
    total_spins = 0
    money_winners = 0
    for hist in data.get("spin_history", {}).values():
        for w in hist.get("wins", []):
            if w.get("timestamp", 0) >= since_ts:
                total_spins += 1
                if w.get("prize") in ("money_5", "money_10"):
                    money_winners += 1

    # Financial prize entries since `since_ts`
    money_5_wins  = sum(
        1 for p in data.get("financial_prizes", [])
        if p.get("timestamp", 0) >= since_ts and p.get("prize_key") == "money_5"
    )
    money_10_wins = sum(
        1 for p in data.get("financial_prizes", [])
        if p.get("timestamp", 0) >= since_ts and p.get("prize_key") == "money_10"
    )

    # Link clicks since `since_ts`
    link_clicks = sum(
        1 for e in data.get("link_clicks", [])
        if e.get("timestamp", 0) >= since_ts
    )

    # Support section clicks since `since_ts`
    support_clicks = sum(
        1 for e in data.get("support_clicks", [])
        if e.get("timestamp", 0) >= since_ts
    )

    return {
        "new_users":      new_users,
        "total_spins":    total_spins,
        "money_5_wins":   money_5_wins,
        "money_10_wins":  money_10_wins,
        "link_clicks":    link_clicks,
        "support_clicks": support_clicks,
        "total_users":    len(data.get("all_users", [])),
        "approved_users": len(data.get("approved_users", [])),
    }


# ─── Async wrappers (asyncio.to_thread) ──────────────────────────────────────
# These let bot handlers await storage calls without blocking the event loop.

async def async_register_user(user_id: int, display_name: str = "") -> None:
    await asyncio.to_thread(register_user, user_id, display_name)


async def async_is_approved(user_id: int) -> bool:
    return await asyncio.to_thread(is_approved, user_id)


async def async_is_pending(user_id: int) -> bool:
    return await asyncio.to_thread(is_pending, user_id)


async def async_can_spin(user_id: int) -> tuple[bool, int]:
    return await asyncio.to_thread(can_spin, user_id)


async def async_record_spin(
    user_id: int, prize_key: str, update_cooldown: bool = True
) -> None:
    await asyncio.to_thread(record_spin, user_id, prize_key, update_cooldown)


async def async_get_available_spins(user_id: int) -> int:
    return await asyncio.to_thread(get_available_spins, user_id)


async def async_log_financial_prize(
    user_id: int,
    full_name: str,
    username: str,
    prize_key: str,
    amount: int,
) -> str:
    return await asyncio.to_thread(
        log_financial_prize, user_id, full_name, username, prize_key, amount
    )


async def async_reset_spin(user_id: int) -> None:
    await asyncio.to_thread(reset_spin, user_id)


async def async_get_all_users() -> list:
    return await asyncio.to_thread(get_all_users)


async def async_get_spin_stats() -> dict:
    return await asyncio.to_thread(get_spin_stats)


async def async_record_link_click(user_id: int) -> None:
    await asyncio.to_thread(record_link_click, user_id)


async def async_record_support_click(user_id: int) -> None:
    await asyncio.to_thread(record_support_click, user_id)


async def async_get_daily_stats(since_ts: float) -> dict:
    return await asyncio.to_thread(get_daily_stats, since_ts)
