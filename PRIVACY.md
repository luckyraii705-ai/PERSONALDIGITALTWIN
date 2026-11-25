# Privacy notice (shown to students)

**What we collect.** Your name, branch, year and username; the daily sleep, study, mood and screen time you
enter; the attendance, marks and deadlines you type in; and the tip ratings and feedback you give.

**Why.** To show your own trends and tips, and to check how well the project works (using only counts and
average ratings, not your individual entries).

**Who can see it.** Only you can see your data in the app. The project team can open the database file on the
project computer for testing and evaluation. We do not share it with anyone else.

**How it is protected.** Passwords are stored only as salted hashes. Every query is limited to your own
account. The data stays in one file on the project computer and is not sold or posted online.

**How long we keep it.** Until you delete your account, or until 180 days after your last
activity, when inactive accounts are deleted.

**Your choices.** You can download all your data from the sidebar at any time, and you can delete your
account and all of its data at any time. Deleting your account also withdraws your consent.

**Age.** This app is for students aged 18 or older.

**Questions or complaints.** Contact: [add your email here]

*This is a college project prototype, so please do not enter anything you would not want the project team to
see.*

---

# Data protection checklist (Milestone 4)

Aligned with the principles of India's Digital Personal Data Protection Act, 2023 and the DPDP Rules, 2025.
The main duties of the Rules start about 18 months after they were notified in November 2025, so the app is not
yet legally bound by them. This is a student project, not legal advice; it simply follows the principles.

| Principle | What the app does | Where | Status |
|---|---|---|---|
| Clear notice | Plain-language privacy notice at registration and in the sidebar | privacy.py, app.py | Done |
| Consent | Tick box at registration; consent time and notice version saved; older accounts must agree at next login | auth.py, db.py, app.py | Done |
| Children's data | Students must confirm they are 18 or older (a declaration, not age verification) | auth.py | Done |
| Purpose limitation, data minimisation | Only sleep, study, mood, screen time, attendance, marks, deadlines and feedback; no phone, address or ID numbers | config.py | Done |
| Accuracy and correction | Students can edit or delete any of their entries | app.py | Done |
| Access and portability | "Download my data" button gives all stored data as JSON, without password data | db.export_student_data | Done |
| Erasure | "Delete my account and data" removes the student and every linked row (cascade delete) | db.delete_student | Done |
| Storage limitation | `python retention.py --apply` deletes accounts inactive for INACTIVITY_DAYS (180) | retention.py | Done (run by hand) |
| Security: passwords | Salted PBKDF2-SHA256, 200,000 rounds | auth.py | Done; raise the rounds for a real launch |
| Security: access control | Every query is limited to the logged-in student's id; all SQL uses parameters | db.py | Done, covered by tests |
| Security: connection | HTTPS when hosted online | hosting | Planned |
| Security: data at rest | Encrypt the database (for example disk encryption or SQLCipher) | hosting | Planned |
| Backups | Encrypted backups, kept no longer than the retention period | process | Planned |
| Grievance contact | Contact shown in the notice (edit PRIVACY_CONTACT in config.py) | config.py | Edit before use |

## If data is leaked or lost (response plan)

1. Take the app offline and keep the database file as it is.
2. Find out what was exposed and which students are affected.
3. Tell the affected students and the faculty guide straight away, saying what happened and what they should do.
4. Fix the cause, change the passwords or ask students to change theirs, and note what you changed.
5. Write down what happened, when, and what was done.
