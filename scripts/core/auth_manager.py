# -*- coding: utf-8 -*-
"""
Authentication, Multi-User Database, Granular Permissions & VK Whitelist/Invite Manager
Supports:
- User database in config/users_db.json
- SHA-256 password hashing with salt
- Default Admin ('ardont') and User ('maxim')
- Session Tokens & TTL
- Granular permissions: can_chat, can_storage, can_execute_scripts, can_manage_skills, is_admin
- VK User ID binding & Invite Codes generation
"""
import os
import sys
import json
import time
import uuid
import hashlib
import secrets
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
CONFIG_DIR = BASE_DIR / "config"
USERS_DB_FILE = CONFIG_DIR / "users_db.json"
SESSIONS_FILE = CONFIG_DIR / "sessions.json"
INVITES_FILE = CONFIG_DIR / "invites.json"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Helper for secure hashing
def hash_password(password: str, salt: str = "") -> Tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    pwd_bytes = (salt + password).encode("utf-8")
    pwd_hash = hashlib.sha256(pwd_bytes).hexdigest()
    return pwd_hash, salt

def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    pwd_bytes = (salt + password).encode("utf-8")
    actual_hash = hashlib.sha256(pwd_bytes).hexdigest()
    return secrets.compare_digest(actual_hash, expected_hash)

# Initial Users Initialization
def init_users_db() -> Dict[str, Any]:
    if USERS_DB_FILE.exists():
        try:
            with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                users = data.get("users", {})
                updated = False
                if "ardont" not in users:
                    h, s = hash_password("148259_zZz")
                    users["ardont"] = {
                        "username": "ardont",
                        "password_hash": h,
                        "salt": s,
                        "role": "admin",
                        "display_name": "Ardont (Главный Админ)",
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_login": "",
                        "is_active": True,
                        "vk_user_id": "",
                        "permissions": {
                            "can_chat": True,
                            "can_storage": True,
                            "can_execute_scripts": True,
                            "can_manage_skills": True,
                            "is_admin": True
                        }
                    }
                    updated = True
                if "maxim" not in users:
                    h, s = hash_password("5152")
                    users["maxim"] = {
                        "username": "maxim",
                        "password_hash": h,
                        "salt": s,
                        "role": "user",
                        "display_name": "Maxim",
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_login": "",
                        "is_active": True,
                        "vk_user_id": "",
                        "permissions": {
                            "can_chat": True,
                            "can_storage": False,
                            "can_execute_scripts": False,
                            "can_manage_skills": False,
                            "is_admin": False
                        }
                    }
                    updated = True
                if updated:
                    data["users"] = users
                    save_users_db(data)
                return data
        except Exception as e:
            print(f"[Auth Error] Failed to read users_db.json: {e}")

    # Create fresh default DB
    h_admin, s_admin = hash_password("148259_zZz")
    h_maxim, s_maxim = hash_password("5152")

    default_db = {
        "users": {
            "ardont": {
                "username": "ardont",
                "password_hash": h_admin,
                "salt": s_admin,
                "role": "admin",
                "display_name": "Ardont (Главный Админ)",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_login": "",
                "is_active": True,
                "vk_user_id": "",
                "permissions": {
                    "can_chat": True,
                    "can_storage": True,
                    "can_execute_scripts": True,
                    "can_manage_skills": True,
                    "is_admin": True
                }
            },
            "maxim": {
                "username": "maxim",
                "password_hash": h_maxim,
                "salt": s_maxim,
                "role": "user",
                "display_name": "Maxim",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_login": "",
                "is_active": True,
                "vk_user_id": "",
                "permissions": {
                    "can_chat": True,
                    "can_storage": False,
                    "can_execute_scripts": False,
                    "can_manage_skills": False,
                    "is_admin": False
                }
            }
        }
    }
    save_users_db(default_db)
    return default_db

def save_users_db(data: Dict[str, Any]) -> bool:
    try:
        with open(USERS_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Auth Error] Failed to save users_db.json: {e}")
        return False

# Session Management
def load_sessions() -> Dict[str, Any]:
    if not SESSIONS_FILE.exists():
        return {}
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_sessions(sessions: Dict[str, Any]) -> None:
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Session Error] {e}")

def create_session(username: str) -> str:
    token = f"hs_sess_{secrets.token_urlsafe(32)}"
    sessions = load_sessions()
    sessions[token] = {
        "username": username,
        "created_at": time.time(),
        "expires_at": time.time() + (86400 * 30)
    }
    save_sessions(sessions)
    return token

def get_user_by_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    sessions = load_sessions()
    sess = sessions.get(token)
    if not sess:
        return None
    if time.time() > sess.get("expires_at", 0):
        del sessions[token]
        save_sessions(sessions)
        return None
        
    username = sess.get("username")
    db = init_users_db()
    user = db.get("users", {}).get(username)
    if user and user.get("is_active", True):
        safe_user = dict(user)
        safe_user.pop("password_hash", None)
        safe_user.pop("salt", None)
        return safe_user
    return None

def invalidate_session(token: str) -> None:
    sessions = load_sessions()
    if token in sessions:
        del sessions[token]
        save_sessions(sessions)

# Authentication
def authenticate_user(username: str, password: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    clean_user = username.strip().lower()
    db = init_users_db()
    users = db.get("users", {})
    user_record = users.get(clean_user)
    if not user_record or not user_record.get("is_active", True):
        return None
        
    salt = user_record.get("salt", "")
    pwd_hash = user_record.get("password_hash", "")
    if verify_password(password, salt, pwd_hash):
        user_record["last_login"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_users_db(db)
        
        token = create_session(clean_user)
        safe_user = dict(user_record)
        safe_user.pop("password_hash", None)
        safe_user.pop("salt", None)
        return token, safe_user
    return None

def list_all_users() -> List[Dict[str, Any]]:
    db = init_users_db()
    users = db.get("users", {})
    res = []
    for u in users.values():
        safe_u = dict(u)
        safe_u.pop("password_hash", None)
        safe_u.pop("salt", None)
        res.append(safe_u)
    return res

def create_new_user(username: str, password: str, role: str = "user", display_name: str = "", permissions: Dict[str, bool] = None) -> Tuple[bool, str]:
    clean_user = username.strip().lower()
    if not clean_user or len(clean_user) < 3:
        return False, "Логин должен быть не короче 3 символов."
    if not password or len(password) < 3:
        return False, "Пароль должен быть не короче 3 символов."
        
    db = init_users_db()
    users = db.get("users", {})
    if clean_user in users:
        return False, f"Пользователь с логином '{clean_user}' уже существует."
        
    h, s = hash_password(password)
    default_perms = {
        "can_chat": True,
        "can_storage": role == "admin",
        "can_execute_scripts": role == "admin",
        "can_manage_skills": role == "admin",
        "is_admin": role == "admin"
    }
    if permissions:
        default_perms.update(permissions)
        
    users[clean_user] = {
        "username": clean_user,
        "password_hash": h,
        "salt": s,
        "role": role,
        "display_name": display_name if display_name else clean_user.capitalize(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_login": "",
        "is_active": True,
        "vk_user_id": "",
        "permissions": default_perms
    }
    save_users_db(db)
    return True, f"Пользователь '{clean_user}' успешно создан."

def update_user_permissions(username: str, permissions: Dict[str, bool], is_active: Optional[bool] = None) -> Tuple[bool, str]:
    clean_user = username.strip().lower()
    db = init_users_db()
    users = db.get("users", {})
    if clean_user not in users:
        return False, f"Пользователь '{clean_user}' не найден."
        
    user_rec = users[clean_user]
    user_rec.setdefault("permissions", {}).update(permissions)
    if is_active is not None:
        user_rec["is_active"] = is_active
        
    if permissions.get("is_admin"):
        user_rec["role"] = "admin"
        
    save_users_db(db)
    return True, f"Права пользователя '{clean_user}' обновлены."

def update_user_password(username: str, new_password: str) -> Tuple[bool, str]:
    clean_user = username.strip().lower()
    if not new_password or len(new_password) < 3:
        return False, "Пароль должен быть не короче 3 символов."
        
    db = init_users_db()
    users = db.get("users", {})
    if clean_user not in users:
        return False, f"Пользователь '{clean_user}' не найден."
        
    h, s = hash_password(new_password)
    users[clean_user]["password_hash"] = h
    users[clean_user]["salt"] = s
    save_users_db(db)
    return True, f"Пароль пользователя '{clean_user}' успешно изменен."

def delete_user(username: str) -> Tuple[bool, str]:
    clean_user = username.strip().lower()
    if clean_user == "ardont":
        return False, "Нельзя удалить главного администратора 'ardont'."
        
    db = init_users_db()
    users = db.get("users", {})
    if clean_user not in users:
        return False, f"Пользователь '{clean_user}' не найден."
        
    del users[clean_user]
    save_users_db(db)
    return True, f"Пользователь '{clean_user}' удален."

# ==============================================================================
# 📲 VK WHITELIST & INVITE CODES SYSTEM
# ==============================================================================

def load_invites() -> Dict[str, Any]:
    if not INVITES_FILE.exists():
        return {}
    try:
        with open(INVITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_invites(data: Dict[str, Any]) -> None:
    try:
        with open(INVITES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Invite Error] {e}")

def generate_invite_code(target_username: str = "", note: str = "") -> str:
    code = f"INV-{secrets.token_hex(3).upper()}-{secrets.token_hex(2).upper()}"
    invites = load_invites()
    invites[code] = {
        "code": code,
        "target_username": target_username.strip().lower(),
        "note": note,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "claimed_by_vk": "",
        "claimed_at": "",
        "is_active": True
    }
    save_invites(invites)
    return code

def claim_invite_code(code: str, vk_user_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    clean_code = code.strip().upper()
    clean_vk = str(vk_user_id).strip()
    invites = load_invites()
    inv = invites.get(clean_code)
    
    if not inv or not inv.get("is_active"):
        return False, "Неверный или уже использованный инвайт-код.", None
        
    target_user = inv.get("target_username") or f"vk_user_{clean_vk}"
    db = init_users_db()
    users = db.get("users", {})
    
    if target_user not in users:
        # Auto-create user for this invite
        create_new_user(target_user, secrets.token_urlsafe(8), role="user", display_name=f"VK #{clean_vk}")
        db = init_users_db()
        users = db.get("users", {})
        
    # Bind VK ID
    users[target_user]["vk_user_id"] = clean_vk
    save_users_db(db)
    
    # Mark invite as claimed
    inv["is_active"] = False
    inv["claimed_by_vk"] = clean_vk
    inv["claimed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_invites(invites)
    
    safe_u = dict(users[target_user])
    safe_u.pop("password_hash", None)
    safe_u.pop("salt", None)
    return True, f"Инвайт успешно активирован! Приветствуем, {safe_u.get('display_name')}!", safe_u

def get_user_by_vk_id(vk_user_id: str) -> Optional[Dict[str, Any]]:
    clean_vk = str(vk_user_id).strip()
    if not clean_vk:
        return None
    db = init_users_db()
    for u in db.get("users", {}).values():
        if str(u.get("vk_user_id", "")).strip() == clean_vk and u.get("is_active", True):
            safe = dict(u)
            safe.pop("password_hash", None)
            safe.pop("salt", None)
            return safe
    return None

def bind_vk_id_to_user(username: str, vk_user_id: str) -> Tuple[bool, str]:
    clean_user = username.strip().lower()
    clean_vk = str(vk_user_id).strip()
    db = init_users_db()
    users = db.get("users", {})
    if clean_user not in users:
        return False, f"Пользователь '{clean_user}' не найден."
    users[clean_user]["vk_user_id"] = clean_vk
    save_users_db(db)
    return True, f"VK ID {clean_vk} успешно привязан к @{clean_user}."

def unbind_vk_id_from_user(username: str) -> Tuple[bool, str]:
    clean_user = username.strip().lower()
    db = init_users_db()
    users = db.get("users", {})
    if clean_user in users:
        users[clean_user]["vk_user_id"] = ""
        save_users_db(db)
        return True, f"VK ID отвязан от @{clean_user}."
    return False, "Пользователь не найден."

def list_all_invites() -> List[Dict[str, Any]]:
    return list(load_invites().values())

init_users_db()
