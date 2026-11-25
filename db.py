"""SQLite storage. Every table carries student_id, so each row belongs to one student."""
import datetime as dt
import re
import sqlite3
import pandas as pd
import config

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def connect(path=None, wal=True):
    """Open one connection per thread or request. WAL mode lets readers and one writer work at the
    same time, and the busy timeout makes a second writer wait instead of failing."""
    con = sqlite3.connect(path or config.DB_PATH, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    if wal:
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
    return con


def init_db(con):
    for f in config.DAILY_FIELDS:
        if not _IDENT.match(f["name"]):
            raise ValueError(f"Bad field name: {f['name']}")
    cols = ", ".join(f'{f["name"]} REAL' for f in config.DAILY_FIELDS)
    fk = "student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE"
    con.executescript(f"""
    CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, name TEXT NOT NULL, branch TEXT, year INTEGER,
        pw_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL,
        consent_at TEXT, consent_version TEXT);
    CREATE TABLE IF NOT EXISTS daily_entries (
        {fk}, entry_date TEXT NOT NULL, {cols}, PRIMARY KEY (student_id, entry_date));
    CREATE TABLE IF NOT EXISTS attendance (
        {fk}, subject TEXT NOT NULL, attendance_pct REAL NOT NULL, updated_on TEXT,
        PRIMARY KEY (student_id, subject));
    CREATE TABLE IF NOT EXISTS marks (
        mark_id INTEGER PRIMARY KEY AUTOINCREMENT, {fk}, subject TEXT NOT NULL,
        test_name TEXT NOT NULL, obtained REAL NOT NULL, total REAL NOT NULL, test_date TEXT);
    CREATE TABLE IF NOT EXISTS deadlines (
        deadline_id INTEGER PRIMARY KEY AUTOINCREMENT, {fk}, title TEXT NOT NULL,
        subject TEXT, due_date TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS rec_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT, {fk}, rec_code TEXT NOT NULL,
        helpful INTEGER NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT, {fk}, ease INTEGER, usefulness INTEGER,
        comments TEXT, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_marks_student ON marks(student_id);
    CREATE INDEX IF NOT EXISTS idx_deadlines_student ON deadlines(student_id);
    CREATE INDEX IF NOT EXISTS idx_recfb_student ON rec_feedback(student_id);
    CREATE INDEX IF NOT EXISTS idx_feedback_student ON feedback(student_id);
    """)
    have = {r["name"] for r in con.execute("PRAGMA table_info(students)")}
    for col in ("consent_at", "consent_version"):  # accounts made before Milestone 4 lack these
        if col not in have:
            con.execute(f"ALTER TABLE students ADD COLUMN {col} TEXT")
    existing = {r["name"] for r in con.execute("PRAGMA table_info(daily_entries)")}
    for f in config.DAILY_FIELDS:  # a field added to config later becomes a new column
        if f["name"] not in existing:
            con.execute(f'ALTER TABLE daily_entries ADD COLUMN {f["name"]} REAL')
    con.commit()


# ---- students ----
def create_student(con, username, name, branch, year, pw_hash, salt, consent_version=None):
    now = _now()
    with con:
        cur = con.execute(
            "INSERT INTO students (username, name, branch, year, pw_hash, salt, created_at, consent_at, "
            "consent_version) VALUES (?,?,?,?,?,?,?,?,?)",
            (username, name, branch, year, pw_hash, salt, now, now if consent_version else None,
             consent_version))
    return cur.lastrowid


def record_consent(con, sid, version):
    with con:
        con.execute("UPDATE students SET consent_at=?, consent_version=? WHERE student_id=?",
                    (_now(), version, sid))


def export_student_data(con, sid):
    """Everything stored about one student as plain data (right of access and data portability).
    The password hash and salt are never included."""
    row = con.execute("SELECT username, name, branch, year, created_at, consent_at, consent_version "
                      "FROM students WHERE student_id=?", (sid,)).fetchone()
    if row is None:
        return {}

    def q(sql):
        df = pd.read_sql_query(sql, con, params=(sid,))
        return df.astype(object).where(df.notna(), None).to_dict("records")

    fields = ", ".join(f["name"] for f in config.DAILY_FIELDS)
    return dict(
        exported_at=_now(),
        profile={k: row[k] for k in row.keys()},
        daily_entries=q(f"SELECT entry_date, {fields} FROM daily_entries WHERE student_id=? ORDER BY entry_date"),
        attendance=q("SELECT subject, attendance_pct, updated_on FROM attendance WHERE student_id=? ORDER BY subject"),
        marks=q("SELECT subject, test_name, obtained, total, test_date FROM marks WHERE student_id=? ORDER BY test_date"),
        deadlines=q("SELECT title, subject, due_date, done FROM deadlines WHERE student_id=? ORDER BY due_date"),
        tip_ratings=q("SELECT rec_code, helpful, created_at FROM rec_feedback WHERE student_id=? ORDER BY id"),
        feedback=q("SELECT ease, usefulness, comments, created_at FROM feedback WHERE student_id=? ORDER BY id"))


def get_student_by_username(con, username):
    return con.execute("SELECT * FROM students WHERE username=?", (username,)).fetchone()


def delete_student(con, sid):
    """Removes the student and, through ON DELETE CASCADE, all of their data."""
    with con:
        con.execute("DELETE FROM students WHERE student_id=?", (sid,))


# ---- daily entries ----
def upsert_daily(con, sid, date, values):
    fields = {f["name"]: f for f in config.DAILY_FIELDS}
    names, vals = [], []
    for k, v in values.items():
        if k not in fields:
            raise ValueError(f"Unknown field: {k}")
        f = fields[k]
        names.append(k)
        vals.append(min(max(float(v), f["min"]), f["max"]))
    ph = ", ".join("?" for _ in names)
    upd = ", ".join(f"{n}=excluded.{n}" for n in names)
    with con:
        con.execute(
            f"INSERT INTO daily_entries (student_id, entry_date, {', '.join(names)}) VALUES (?, ?, {ph}) "
            f"ON CONFLICT(student_id, entry_date) DO UPDATE SET {upd}", [sid, str(date), *vals])


def save_daily_rows(con, sid, rows):
    """rows: list of dicts with 'date' and every daily field. Saves them all (an existing date is
    updated). If any row is invalid, nothing is saved. Returns (number_saved, problems)."""
    names = [f["name"] for f in config.DAILY_FIELDS]
    good, problems = [], []
    for i, row in enumerate(rows, start=1):
        vals = [row.get(n) for n in names]
        if _to_date(row.get("date")) is None and all(v is None or pd.isna(v) for v in vals):
            continue  # blank row
        day = _to_date(row.get("date"))
        if day is None:
            problems.append(f"Row {i}: enter a valid date.")
            continue
        if day > dt.date.today().isoformat():
            problems.append(f"Row {i}: {day} is in the future.")
            continue
        try:
            nums = {n: float(v) for n, v in zip(names, vals)}
            if any(pd.isna(x) for x in nums.values()):
                raise ValueError
        except (TypeError, ValueError):
            problems.append(f"Row {i} ({day}): fill in every column.")
            continue
        good.append((day, nums))
    if problems:
        return 0, problems
    for day, nums in good:
        upsert_daily(con, sid, day, nums)
    return len(good), []


def get_daily(con, sid):
    df = pd.read_sql_query("SELECT * FROM daily_entries WHERE student_id=? ORDER BY entry_date",
                           con, params=(sid,))
    df = df.drop(columns="student_id").rename(columns={"entry_date": "date"})
    df["date"] = pd.to_datetime(df["date"])
    return df.reset_index(drop=True)


# ---- attendance / marks / deadlines ----
def upsert_attendance(con, sid, subject, pct):
    pct = min(max(float(pct), 0.0), 100.0)
    with con:
        con.execute("INSERT INTO attendance (student_id, subject, attendance_pct, updated_on) VALUES (?,?,?,?) "
                    "ON CONFLICT(student_id, subject) DO UPDATE SET attendance_pct=excluded.attendance_pct, "
                    "updated_on=excluded.updated_on", (sid, subject.strip(), pct, dt.date.today().isoformat()))


def save_attendance_table(con, sid, rows):
    """rows: list of (subject, pct). Makes the student's attendance list exactly these rows:
    new subjects are added, existing ones updated, subjects missing from rows are removed."""
    clean = {}
    for subject, pct in rows:
        name = str(subject or "").strip()
        if not name or pct is None or pd.isna(pct):
            continue
        clean[name] = min(max(float(pct), 0.0), 100.0)
    today = dt.date.today().isoformat()
    with con:
        if clean:
            marks = ",".join("?" for _ in clean)
            con.execute(f"DELETE FROM attendance WHERE student_id=? AND subject NOT IN ({marks})",
                        [sid, *clean])
        else:
            con.execute("DELETE FROM attendance WHERE student_id=?", (sid,))
        for name, pct in clean.items():
            con.execute("INSERT INTO attendance (student_id, subject, attendance_pct, updated_on) VALUES (?,?,?,?) "
                        "ON CONFLICT(student_id, subject) DO UPDATE SET attendance_pct=excluded.attendance_pct, "
                        "updated_on=excluded.updated_on", (sid, name, pct, today))


def get_attendance(con, sid):
    return pd.read_sql_query("SELECT subject, attendance_pct, updated_on FROM attendance WHERE student_id=? "
                             "ORDER BY subject", con, params=(sid,))


def add_mark(con, sid, subject, test_name, obtained, total, test_date):
    if float(total) <= 0 or float(obtained) < 0 or float(obtained) > float(total):
        raise ValueError("Marks must satisfy 0 <= obtained <= total and total > 0")
    with con:
        con.execute("INSERT INTO marks (student_id, subject, test_name, obtained, total, test_date) VALUES (?,?,?,?,?,?)",
                    (sid, subject.strip(), test_name.strip(), float(obtained), float(total), str(test_date)))


def get_marks(con, sid):
    return pd.read_sql_query("SELECT subject, test_name, obtained, total, test_date FROM marks "
                             "WHERE student_id=? ORDER BY test_date", con, params=(sid,))


def _to_date(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    try:
        d = pd.to_datetime(v)
    except Exception:
        return None
    return None if pd.isna(d) else d.date().isoformat()


def save_marks_table(con, sid, rows):
    """rows: (subject, test_name, obtained, total, test_date). Replaces the student's marks with these
    rows (several tests per subject or per day are fine). If any row is invalid, nothing is saved and a
    list of problems is returned; an empty list means success."""
    good, problems = [], []
    for i, (subject, test, ob, tot, day) in enumerate(rows, start=1):
        subject, test = str(subject or "").strip(), str(test or "").strip()
        if not subject and not test and (ob is None or pd.isna(ob)):
            continue  # blank row
        if not subject or not test:
            problems.append(f"Row {i}: enter both the subject and the test name.")
            continue
        try:
            ob, tot = float(ob), float(tot)
        except (TypeError, ValueError):
            ob = tot = float("nan")
        if pd.isna(ob) or pd.isna(tot) or tot <= 0 or ob < 0 or ob > tot:
            problems.append(f"Row {i} ({subject}, {test}): marks must be between 0 and the total.")
            continue
        good.append((subject, test, ob, tot, _to_date(day) or dt.date.today().isoformat()))
    if problems:
        return problems
    with con:
        con.execute("DELETE FROM marks WHERE student_id=?", (sid,))
        con.executemany("INSERT INTO marks (student_id, subject, test_name, obtained, total, test_date) "
                        "VALUES (?,?,?,?,?,?)", [(sid, *g) for g in good])
    return []


def save_deadlines_table(con, sid, rows):
    """rows: (title, subject, due_date, done). Replaces the student's deadlines with these rows.
    Same rule as marks: any invalid row means nothing is saved and the problems are returned."""
    good, problems = [], []
    for i, (title, subject, due, done) in enumerate(rows, start=1):
        title = str(title or "").strip()
        if not title:
            continue  # blank row
        due = _to_date(due)
        if due is None:
            problems.append(f"Row {i} ({title}): enter a valid due date.")
            continue
        flag = 0 if done is None or (not isinstance(done, str) and pd.isna(done)) else int(bool(done))
        good.append((title, str(subject or "").strip(), due, flag))
    if problems:
        return problems
    with con:
        con.execute("DELETE FROM deadlines WHERE student_id=?", (sid,))
        con.executemany("INSERT INTO deadlines (student_id, title, subject, due_date, done) VALUES (?,?,?,?,?)",
                        [(sid, *g) for g in good])
    return []


def add_deadline(con, sid, title, subject, due_date):
    with con:
        con.execute("INSERT INTO deadlines (student_id, title, subject, due_date) VALUES (?,?,?,?)",
                    (sid, title.strip(), (subject or "").strip(), str(due_date)))


def get_deadlines(con, sid, only_open=True):
    q = "SELECT deadline_id, title, subject, due_date, done FROM deadlines WHERE student_id=?"
    if only_open:
        q += " AND done=0"
    return pd.read_sql_query(q + " ORDER BY due_date", con, params=(sid,))


def mark_deadline_done(con, sid, deadline_id):
    with con:
        con.execute("UPDATE deadlines SET done=1 WHERE deadline_id=? AND student_id=?", (deadline_id, sid))


# ---- pilot feedback ----
def save_rec_feedback(con, sid, rec_code, helpful):
    with con:
        con.execute("INSERT INTO rec_feedback (student_id, rec_code, helpful, created_at) VALUES (?,?,?,?)",
                    (sid, rec_code, int(bool(helpful)), _now()))


def save_feedback(con, sid, ease, usefulness, comments):
    with con:
        con.execute("INSERT INTO feedback (student_id, ease, usefulness, comments, created_at) VALUES (?,?,?,?,?)",
                    (sid, int(ease), int(usefulness), (comments or "").strip(), _now()))
