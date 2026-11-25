"""Central settings. To add a new daily field, add one dict to DAILY_FIELDS.
The database column, the form input and the models all pick it up automatically."""
import os

DB_PATH = os.environ.get("TWIN_DB", "twin_v3.db")

DAILY_FIELDS = [
    dict(name="sleep_hours", label="Sleep (hours)", min=0.0, max=24.0, default=7.0, step=0.5),
    dict(name="study_hours", label="Study (hours)", min=0.0, max=24.0, default=3.0, step=0.5),
    dict(name="mood", label="Mood (1 = low, 10 = great)", min=1.0, max=10.0, default=7.0, step=1.0),
    dict(name="screen_time", label="Screen time (hours)", min=0.0, max=24.0, default=5.0, step=0.5),
]

TARGET = "mood"            # value the LSTM predicts for tomorrow
ATTENDANCE_MIN = 75.0      # alert below this percentage
WEAK_MARKS_PCT = 50.0      # subject average below this = weak subject
MIN_DAYS_INSIGHTS = 7      # days of data before trends are shown
MIN_DAYS_CLUSTER = 21      # days needed for day-type clustering
MIN_DAYS_LSTM = 30         # days needed for the LSTM prediction
WINDOW = 7                 # LSTM looks at the last 7 days

KMEANS_N_INIT = 3          # clustering restarts (was 10; benchmark.py shows the speed gain and same quality)

# data protection settings
CONSENT_VERSION = "2026-11"            # change this when the privacy notice changes; students then agree again
INACTIVITY_DAYS = 180                  # accounts with no activity for this long can be deleted (retention.py)
PRIVACY_CONTACT = "BTAD26O1033"   # shown in the privacy notice for questions and complaints
