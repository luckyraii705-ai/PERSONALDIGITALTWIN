"""Registration and login. Passwords are never stored: only a salted PBKDF2-SHA256 hash."""
import hashlib
import hmac
import os
import re
import config
import db

ITERATIONS = 200_000
_USER = re.compile(r"^[a-z0-9_.]{3,30}$")


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password, hash_hex, salt_hex):
    digest, _ = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(digest, hash_hex)


def register(con, username, name, branch, year, password, consent=False, confirmed_adult=False):
    username = username.strip().lower()
    if not _USER.match(username):
        raise ValueError("Username: 3-30 characters, letters, digits, _ or . only")
    if not name.strip():
        raise ValueError("Please enter your name")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not confirmed_adult:
        raise ValueError("You must be 18 or older to register")
    if not consent:
        raise ValueError("Please read and accept the privacy notice")
    if db.get_student_by_username(con, username):
        raise ValueError("That username is already taken")
    h, s = hash_password(password)
    return db.create_student(con, username, name.strip(), branch.strip(), int(year), h, s,
                             consent_version=config.CONSENT_VERSION)


def login(con, username, password):
    row = db.get_student_by_username(con, username.strip().lower())
    if row is None:
        hash_password(password)  # same work as a real check, so timing does not reveal valid usernames
        return None
    if not verify_password(password, row["pw_hash"], row["salt"]):
        return None
    return {k: row[k] for k in ("student_id", "username", "name", "branch", "year", "consent_version")}
