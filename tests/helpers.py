import auth


def make_student(con, username="asha_1", password="password123"):
    return auth.register(con, username, "Asha", "AI&DS", 1, password, consent=True, confirmed_adult=True)
