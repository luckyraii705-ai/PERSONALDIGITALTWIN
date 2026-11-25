"""Rule-based recommendation engine. Works from day one, no minimum data needed.
Each rule returns a recommendation with a stable code so pilot feedback can be tracked per rule."""
import datetime as dt
import re
import pandas as pd
import config

_ORDER = {"alert": 0, "warn": 1, "info": 2}


def _rec(code, severity, title, detail):
    return dict(code=code, severity=severity, title=title, detail=detail)


def _slug(text):
    return re.sub(r"\W+", "_", str(text).lower()).strip("_")


def generate(daily, attendance, marks, deadlines, today=None):
    today = today or dt.date.today()
    recs = []

    if daily is None or daily.empty:
        recs.append(_rec("start_logging", "info", "Start logging",
                         "Add today's entry in the Today tab. Personal tips appear after a few days."))
    else:
        last7 = daily.tail(7)

        def avg(col):
            return float(last7[col].mean()) if col in last7 and last7[col].notna().any() else None

        if len(last7) >= 3:
            sleep, screen, study = avg("sleep_hours"), avg("screen_time"), avg("study_hours")
            if sleep is not None and sleep < 6.5:
                recs.append(_rec("low_sleep", "warn", "You are sleeping less than you need",
                                 f"Your average sleep over the last {len(last7)} days is {sleep:.1f} h. "
                                 "Try to get 7-8 h, especially before tests."))
            if screen is not None and screen > 7:
                recs.append(_rec("high_screen", "warn", "High screen time",
                                 f"You average {screen:.1f} h of screen time. Try short screen-free breaks "
                                 "and keep your phone away while studying."))
            if study is not None and study < 2:
                recs.append(_rec("low_study", "info", "Low study time lately",
                                 f"You average {study:.1f} h of study per day. Even one extra focused hour "
                                 "helps; pick your weakest subject."))
        if len(daily) >= 7 and "mood" in daily:
            recent, prev = daily["mood"].tail(3).mean(), daily["mood"].iloc[-7:-3].mean()
            if pd.notna(recent) and pd.notna(prev) and prev - recent >= 1.5:
                recs.append(_rec("mood_drop", "warn", "Your mood has dropped recently",
                                 "Your mood is lower than earlier this week. Consider a break, some exercise, "
                                 "or talking to a friend or mentor."))
        if len(daily) >= 14 and {"sleep_hours", "mood"} <= set(daily.columns):
            flat = daily["sleep_hours"].std() == 0 or daily["mood"].std() == 0   # no variation, no correlation
            c = float("nan") if flat else daily["sleep_hours"].corr(daily["mood"])
            if pd.notna(c) and c >= 0.3:
                recs.append(_rec("sleep_mood", "info", "Sleep and mood go together for you",
                                 "Your mood tends to be higher on days when you sleep more."))

    if attendance is not None and not attendance.empty:
        for _, r in attendance.iterrows():
            pct = float(r["attendance_pct"])
            code = f"attendance_{_slug(r['subject'])}"
            if pct < config.ATTENDANCE_MIN:
                recs.append(_rec(code, "alert", f"Low attendance in {r['subject']}",
                                 f"{pct:.0f}% is below the {config.ATTENDANCE_MIN:.0f}% requirement. "
                                 "Try not to miss any more classes."))
            elif pct < config.ATTENDANCE_MIN + 5:
                recs.append(_rec(code + "_near", "warn", f"Attendance in {r['subject']} is close to the limit",
                                 f"{pct:.0f}% is only a little above {config.ATTENDANCE_MIN:.0f}%."))

    if marks is not None and not marks.empty:
        m = marks.assign(pct=marks["obtained"] / marks["total"] * 100).groupby("subject")["pct"].mean()
        for subject, pct in m.items():
            if pct < config.WEAK_MARKS_PCT:
                recs.append(_rec(f"weak_{_slug(subject)}", "warn", f"{subject} needs attention",
                                 f"Your average in {subject} is {pct:.0f}%. Plan extra study sessions "
                                 "for it this week."))

    if deadlines is not None and not deadlines.empty:
        for _, r in deadlines.iterrows():
            days = (pd.to_datetime(r["due_date"]).date() - today).days
            label = r["title"] + (f" ({r['subject']})" if r["subject"] else "")
            if days < 0:
                recs.append(_rec(f"overdue_{r['deadline_id']}", "alert", f"Overdue: {label}",
                                 f"This was due {-days} day(s) ago."))
            elif days <= 3:
                when = "today" if days == 0 else f"in {days} day(s)"
                recs.append(_rec(f"due_{r['deadline_id']}", "warn", f"Due soon: {label}", f"Due {when}."))

    return sorted(recs, key=lambda r: _ORDER[r["severity"]])
