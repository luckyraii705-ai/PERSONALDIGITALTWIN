"""Student Digital Twin. Run: streamlit run app.py"""
import datetime as dt
import json
import pandas as pd
import streamlit as st
import auth
import db
import ml
import privacy
import recommend
from config import (CONSENT_VERSION, DAILY_FIELDS, MIN_DAYS_CLUSTER, MIN_DAYS_INSIGHTS,
                    MIN_DAYS_LSTM, TARGET)

st.set_page_config(page_title="Student Digital Twin", layout="wide")


@st.cache_resource
def init_database():
    setup = db.connect()
    db.init_db(setup)
    setup.close()
    return True


init_database()
con = db.connect()  # a new connection for every script run, so users never share one
if "student" not in st.session_state:
    st.session_state.student = None

st.title("Student Digital Twin")

# ---------------- login / register ----------------
if st.session_state.student is None:
    st.write("Track your sleep, study, attendance and marks, and get personal tips.")
    tab_in, tab_reg = st.tabs(["Log in", "Register"])
    with tab_in:
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            go = st.form_submit_button("Log in")
        if go:
            student = auth.login(con, u, p)
            if student:
                st.session_state.student = student
                st.rerun()
            else:
                st.error("Wrong username or password.")
    with tab_reg:
        with st.form("register"):
            r_user = st.text_input("Choose a username")
            r_name = st.text_input("Your name")
            r_branch = st.text_input("Branch", value="AI and Data Science")
            r_year = st.number_input("Year", min_value=1, max_value=6, value=1, step=1)
            r_pw = st.text_input("Password (8+ characters)", type="password")
            r_adult = st.checkbox("I confirm that I am 18 years or older")
            r_agree = st.checkbox("I have read the privacy notice below and I agree")
            go = st.form_submit_button("Create account")
        with st.expander("Privacy notice"):
            st.markdown(privacy.notice_markdown())
        if go:
            try:
                auth.register(con, r_user, r_name, r_branch, int(r_year), r_pw,
                              consent=r_agree, confirmed_adult=r_adult)
                st.success("Account created. Now log in from the Log in tab.")
            except ValueError as e:
                st.error(str(e))
    st.stop()

# ---------------- logged in ----------------
me = st.session_state.student
sid = me["student_id"]


def sign_out():
    st.session_state.student = None
    st.session_state.pred_cache = None  # never keep one student's result for the next login
    st.rerun()


# Consent gate: new students agree at registration; older accounts agree here once.
if me.get("consent_version") != CONSENT_VERSION:
    st.subheader("Privacy notice")
    st.markdown(privacy.notice_markdown())
    agree = st.checkbox("I have read the privacy notice and I agree")
    if st.button("Continue"):
        if agree:
            db.record_consent(con, sid, CONSENT_VERSION)
            me["consent_version"] = CONSENT_VERSION
            st.rerun()
        else:
            st.warning("Please tick the box to continue.")
    if st.sidebar.button("Log out"):
        sign_out()
    st.stop()

st.sidebar.write(f"Logged in as **{me['name']}**")
if st.sidebar.button("Log out"):
    sign_out()
with st.sidebar.expander("Privacy notice"):
    st.markdown(privacy.notice_markdown())
st.sidebar.download_button("Download my data (JSON)",
                           data=json.dumps(db.export_student_data(con, sid), indent=2, default=str),
                           file_name="my_digital_twin_data.json", mime="application/json")
with st.sidebar.expander("Delete my account and data"):
    confirm = st.text_input("Type DELETE to confirm")
    if st.button("Delete everything") and confirm == "DELETE":
        db.delete_student(con, sid)
        sign_out()

t_today, t_att, t_marks, t_dead, t_ins, t_fb = st.tabs(
    ["Today", "Attendance", "Marks", "Deadlines", "Insights", "Feedback"])

with t_today:
    st.subheader("Today's entry")
    st.info("Only this form is daily and takes about 30 seconds. Attendance and marks are NOT daily: "
            "update attendance only when it changes (for example once a week), and add marks only when you "
            "get a test result.")
    with st.form("daily"):
        day = st.date_input("Date", value=dt.date.today(), max_value=dt.date.today())
        vals = {f["name"]: st.number_input(f["label"], min_value=f["min"], max_value=f["max"],
                                           value=f["default"], step=f["step"]) for f in DAILY_FIELDS}
        saved = st.form_submit_button("Save entry")
    if saved:
        db.upsert_daily(con, sid, day, vals)
        st.success(f"Saved for {day}. Saving again for the same date updates it.")
    recent = db.get_daily(con, sid).tail(7)
    if not recent.empty:
        st.write("Your last entries")
        st.dataframe(recent.assign(date=recent["date"].dt.date), hide_index=True)

    with st.expander("Add several past days at once"):
        st.caption("Missed some days? Add one row per day and click Save days. If a date already has an "
                   "entry, it is updated. Your Insights unlock faster this way.")
        blank = pd.DataFrame({"date": pd.Series([], dtype="datetime64[ns]"),
                              **{f["name"]: pd.Series([], dtype="float") for f in DAILY_FIELDS}})
        cfg = {"date": st.column_config.DateColumn("Date", max_value=dt.date.today(), required=True)}
        for f in DAILY_FIELDS:
            cfg[f["name"]] = st.column_config.NumberColumn(f["label"], min_value=f["min"], max_value=f["max"],
                                                           step=f["step"], default=f["default"], required=True)
        past = st.data_editor(blank, num_rows="dynamic", hide_index=True, use_container_width=True,
                              key="past_editor", column_config=cfg)
        if st.button("Save days"):
            count, problems = db.save_daily_rows(con, sid, past.to_dict("records"))
            for p in problems:
                st.error(p)
            if not problems:
                st.success(f"Saved {count} day(s). Open the Insights tab to see your tips.")

with t_att:
    st.subheader("Attendance")
    st.caption("Update this only when your attendance changes, for example once a week. "
               "One row per subject. Click the empty row at the bottom to add a subject, change a number "
               "to update it, or select a row and press Delete to remove it. Then click Save.")
    current = db.get_attendance(con, sid)[["subject", "attendance_pct"]]
    current = current.astype({"subject": "object", "attendance_pct": "float"})
    edited = st.data_editor(
        current, num_rows="dynamic", hide_index=True, use_container_width=True, key="att_editor",
        column_config={
            "subject": st.column_config.TextColumn("Subject", required=True),
            "attendance_pct": st.column_config.NumberColumn("Attendance %", min_value=0, max_value=100,
                                                            step=1, required=True)})
    if st.button("Save attendance"):
        db.save_attendance_table(con, sid, list(zip(edited["subject"], edited["attendance_pct"])))
        st.success("Attendance saved. Check the Insights tab for your tips.")

with t_marks:
    st.subheader("Marks")
    st.caption("Add a row only when you get a test result, there is no need to fill this daily. "
               "One row per test. You can add several tests for the same subject or on the same day. "
               "Leave it empty if you have no tests yet. Add a row at the bottom, edit a cell, or select a "
               "row and press Delete. Then click Save.")
    cur = db.get_marks(con, sid).astype({"subject": "object", "test_name": "object",
                                         "obtained": "float", "total": "float"})
    cur["test_date"] = pd.to_datetime(cur["test_date"]).dt.date
    edited = st.data_editor(
        cur, num_rows="dynamic", hide_index=True, use_container_width=True, key="marks_editor",
        column_config={
            "subject": st.column_config.TextColumn("Subject", required=True),
            "test_name": st.column_config.TextColumn("Test (e.g. Quiz 1)", required=True),
            "obtained": st.column_config.NumberColumn("Marks obtained", min_value=0.0, step=0.5, required=True),
            "total": st.column_config.NumberColumn("Total marks", min_value=1.0, step=0.5, default=20.0,
                                                   required=True),
            "test_date": st.column_config.DateColumn("Test date", default=dt.date.today())})
    if st.button("Save marks"):
        problems = db.save_marks_table(con, sid, list(zip(
            edited["subject"], edited["test_name"], edited["obtained"], edited["total"], edited["test_date"])))
        for p in problems:
            st.error(p)
        if not problems:
            st.success("Marks saved.")

with t_dead:
    st.subheader("Deadlines")
    st.caption("Add a row at the bottom for each deadline. Tick Done when finished (finished items stop "
               "giving alerts). To remove a deadline, select its row and press Delete. Then click Save.")
    cur = db.get_deadlines(con, sid, only_open=False)[["title", "subject", "due_date", "done"]]
    cur = cur.astype({"title": "object", "subject": "object", "done": "bool"})
    cur["due_date"] = pd.to_datetime(cur["due_date"]).dt.date
    edited = st.data_editor(
        cur, num_rows="dynamic", hide_index=True, use_container_width=True, key="dl_editor",
        column_config={
            "title": st.column_config.TextColumn("What is due?", required=True),
            "subject": st.column_config.TextColumn("Subject (optional)"),
            "due_date": st.column_config.DateColumn("Due date", default=dt.date.today() + dt.timedelta(days=7),
                                                    required=True),
            "done": st.column_config.CheckboxColumn("Done", default=False)})
    if st.button("Save deadlines"):
        problems = db.save_deadlines_table(con, sid, list(zip(
            edited["title"], edited["subject"], edited["due_date"], edited["done"])))
        for p in problems:
            st.error(p)
        if not problems:
            st.success("Deadlines saved.")

with t_ins:
    daily = db.get_daily(con, sid)
    n = len(daily)
    st.metric("Days with entries", n)
    names = [f["name"] for f in DAILY_FIELDS if f["name"] in daily.columns]
    if n < MIN_DAYS_INSIGHTS:
        st.info(f"Log at least {MIN_DAYS_INSIGHTS} days to see trends ({n} so far). "
                "Tips from your attendance, marks and deadlines work already.")
    if n:
        st.line_chart(daily.set_index("date")[names].tail(30))

    st.subheader("Your tips")
    recs = recommend.generate(daily, db.get_attendance(con, sid), db.get_marks(con, sid),
                              db.get_deadlines(con, sid))
    icons = {"alert": "🔴", "warn": "🟠", "info": "🔵"}
    if not recs:
        st.success("No warnings right now. Keep it up!")
    for r in recs:
        st.markdown(f"{icons[r['severity']]} **{r['title']}**  \n{r['detail']}")
        a, b, _ = st.columns([1, 1, 8])
        if a.button("👍 Helpful", key=f"up_{r['code']}"):
            db.save_rec_feedback(con, sid, r["code"], True)
            st.toast("Thanks for the feedback!")
        if b.button("👎 Not helpful", key=f"down_{r['code']}"):
            db.save_rec_feedback(con, sid, r["code"], False)
            st.toast("Thanks, we will improve this tip.")

    st.subheader("Your day types")
    prof = ml.cluster_profile(daily)
    if prof:
        st.write(f"Today looks like one of your **{prof['today']}**.")
        st.dataframe(prof["summary"])
        st.caption(f"Cluster separation (silhouette): {prof['silhouette']:.2f}")
    else:
        st.info(f"Day types appear after {MIN_DAYS_CLUSTER} days of data.")

    st.subheader(f"Predict tomorrow's {TARGET}")
    if n >= MIN_DAYS_LSTM:
        data_key = (sid, n, str(daily["date"].iloc[-1].date()))  # changes whenever this student's data changes
        if st.button("Run prediction"):
            cache = st.session_state.get("pred_cache")
            if cache and cache["key"] == data_key:
                st.caption("Showing the saved result, because your data has not changed since the last run.")
            else:
                try:
                    with st.spinner("Training on your history..."):
                        st.session_state.pred_cache = dict(key=data_key, result=ml.train_lstm(daily))
                except ImportError:
                    st.warning("TensorFlow is not installed on this computer.")
                except ValueError as e:
                    st.warning(str(e))
        cache = st.session_state.get("pred_cache")
        p = cache["result"] if cache and cache["key"] == data_key else None
        if p:
            st.metric(f"Predicted {TARGET} tomorrow", f"{p['next_value']:.1f}")
            verdict = "better than" if p["beats_baseline"] else "not better than"
            st.caption(f"Typical error {p['rmse']:.2f}, {verdict} the best simple method "
                       f"({p['baseline_rmse']:.2f}: your average, yesterday's value or linear regression). "
                       f"Based on {p['n_days']} days. Training took {p['train_seconds']:.1f} s and the "
                       f"prediction {p['inference_ms']:.0f} ms.")
    else:
        st.info(f"Predictions unlock after {MIN_DAYS_LSTM} days of data ({n} so far).")

with t_fb:
    st.subheader("Help us improve (pilot feedback)")
    with st.form("fb"):
        ease = st.slider("How easy is it to use? (1 = hard, 5 = easy)", 1, 5, 4)
        useful = st.slider("How useful are the tips? (1 = not, 5 = very)", 1, 5, 4)
        text = st.text_area("What is missing or confusing?")
        ok = st.form_submit_button("Send feedback")
    if ok:
        db.save_feedback(con, sid, ease, useful, text)
        st.success("Thank you!")
