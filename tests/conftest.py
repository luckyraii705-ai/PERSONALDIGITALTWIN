import os
import shutil
import sys
import tempfile
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import db  # noqa: E402
from helpers import make_student  # noqa: E402


@pytest.fixture
def con():
    """A fresh empty database for each test."""
    folder = tempfile.mkdtemp()
    c = db.connect(os.path.join(folder, "test.db"))
    db.init_db(c)
    yield c
    c.close()
    shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture
def sid(con):
    return make_student(con)
