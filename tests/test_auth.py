"""Unit tests: registration, login and password storage."""
import pytest
import auth
import db
from helpers import make_student


def test_hash_is_salted_and_verifies():
    h1, s1 = auth.hash_password("password123")
    h2, s2 = auth.hash_password("password123")
    assert h1 != h2 and s1 != s2          # same password, different salt, different hash
    assert auth.verify_password("password123", h1, s1)
    assert not auth.verify_password("password124", h1, s1)


def test_password_is_never_stored_in_plain_text(con):
    make_student(con)
    row = db.get_student_by_username(con, "asha_1")
    assert "password123" not in str(dict(row))


@pytest.mark.parametrize("username,name,password,consent,adult,message", [
    ("ab", "Asha", "password123", True, True, "Username"),
    ("bad name!", "Asha", "password123", True, True, "Username"),
    ("asha_1", "   ", "password123", True, True, "name"),
    ("asha_1", "Asha", "short", True, True, "Password"),
    ("asha_1", "Asha", "password123", False, True, "privacy"),
    ("asha_1", "Asha", "password123", True, False, "18"),
])
def test_register_rejects_bad_input(con, username, name, password, consent, adult, message):
    with pytest.raises(ValueError, match=message):
        auth.register(con, username, name, "AI", 1, password, consent=consent, confirmed_adult=adult)
    assert con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0   # nothing was saved


def test_duplicate_username_is_rejected_ignoring_case(con):
    make_student(con, "Asha_1")
    with pytest.raises(ValueError, match="taken"):
        make_student(con, "asha_1")


def test_login_success_and_failures(con):
    sid = make_student(con)
    assert auth.login(con, "ASHA_1", "password123")["student_id"] == sid
    assert auth.login(con, "asha_1", "wrongpass") is None
    assert auth.login(con, "nobody", "password123") is None


@pytest.mark.parametrize("attack", ["' OR '1'='1", "asha_1' --", "admin'; DROP TABLE students;--"])
def test_login_is_not_fooled_by_sql_injection(con, attack):
    make_student(con)
    assert auth.login(con, attack, attack) is None
    assert con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 1


def test_sql_injection_username_is_rejected_at_registration(con):
    with pytest.raises(ValueError):
        auth.register(con, "x'; DROP TABLE students;--", "Evil", "AI", 1, "password123",
                      consent=True, confirmed_adult=True)
