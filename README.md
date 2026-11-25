# Student Digital Twin

Multi-student version with testing, optimization and data protection (Milestone 4).

    pip install -r requirements-dev.txt
    python -m pytest                                  # all tests
    python -m pytest --cov=. --cov-report=term        # tests plus code coverage
    python load_test.py                               # many students at once (saves load_test_results.csv)
    python benchmark.py                               # speed of each action and of each optimization
    python seed_demo.py                               # optional: demo students (password demo12345)
    python -m streamlit run app.py                    # the app

| File | Job |
|---|---|
| config.py | Settings: daily fields, limits, retention days, privacy contact |
| db.py | SQLite storage: one connection per request, WAL mode, indexes, consent, data export |
| auth.py | Register (age and consent checks) and login with salted password hashes |
| recommend.py | Rule-based tips |
| ml.py | Day-type clustering (21+ days), baselines and LSTM (30+ days) |
| privacy.py, PRIVACY.md | Privacy notice text and the data protection checklist |
| retention.py | Deletes inactive accounts (`--apply` to really delete) |
| app.py | Streamlit app |
| tests/ | Unit tests, privacy tests, integration tests (including the real app screens) |
| load_test.py | Load test: shared connection (old design) against connection per student (new design) |
| benchmark.py | Timing before and after each optimization |
| pilot_report.py | Pilot numbers from Milestone 3 |

Before the pilot or any upload: do not share the `.db` files; they hold students' real data.
