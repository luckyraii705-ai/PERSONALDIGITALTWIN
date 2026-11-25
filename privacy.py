"""Plain-language privacy notice shown at registration, in the sidebar and as PRIVACY.md."""
import config


def notice_markdown():
    return f"""
**What we collect.** Your name, branch, year and username; the daily sleep, study, mood and screen time you
enter; the attendance, marks and deadlines you type in; and the tip ratings and feedback you give.

**Why.** To show your own trends and tips, and to check how well the project works (using only counts and
average ratings, not your individual entries).

**Who can see it.** Only you can see your data in the app. The project team can open the database file on the
project computer for testing and evaluation. We do not share it with anyone else.

**How it is protected.** Passwords are stored only as salted hashes. Every query is limited to your own
account. The data stays in one file on the project computer and is not sold or posted online.

**How long we keep it.** Until you delete your account, or until {config.INACTIVITY_DAYS} days after your last
activity, when inactive accounts are deleted.

**Your choices.** You can download all your data from the sidebar at any time, and you can delete your
account and all of its data at any time. Deleting your account also withdraws your consent.

**Age.** This app is for students aged 18 or older.

**Questions or complaints.** Contact: {config.PRIVACY_CONTACT}

*This is a college project prototype, so please do not enter anything you would not want the project team to
see.*
"""
