"""
Prompt-a-thon Leaderboard
"""

# Standard imports
import os
import time

# Library imports
import redis

from nicegui import ui
from prettytable import PrettyTable

# Constants
DEFAULT_LEADERBOARD_TITLE = "Leaderboard"
DEFAULT_REFRESH_RATE = 5
DEFAULT_LEVEL_SCORE = 100
DEFAULT_BONUS_SCORE = 10

try:
    database = redis.Redis(
        host=os.environ.get('REDIS_HOST', "localhost"),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=int(os.environ.get('REDIS_DB', 0)),
        username=os.environ.get('REDIS_USERNAME', None),
        password=os.environ.get('REDIS_PASSWORD', None),
        decode_responses=True,
    )
except (KeyError, redis.ConnectionError) as exc:
    raise exc


def search_by_user(user):
    """Returns all user submissions"""
    cursor = '0'
    submissions = []
    while cursor != 0:
        cursor, keys = database.scan(cursor, match=f"user_submission:{user}:*")
        for key in keys:
            submissions.append(database.hgetall(key))
    return submissions


def search_by_timestamp(start, end):
    """Returns all submissions within the given timestamp range"""
    keys = database.zrangebyscore("user_submissions_index", start.timestamp(), end.timestamp())
    submissions = [database.hgetall(key) for key in keys]
    return submissions


def list_all_cleared():
    """Returns a list all cleared level/model combinations"""
    cursor = '0'
    all_cleared = []
    while cursor != 0:
        cursor, keys = database.scan(cursor, match="level:*:cleared")
        for key in keys:
            all_cleared.append(":".join(key.split(":")[1:-1]))
    return all_cleared


def list_all_users():
    """Returns a list of all users"""
    cursor = '0'
    users = []
    while cursor != 0:
        cursor, keys = database.scan(cursor, match="user_submission:*")
        for key in keys:
            user = key.split(":")[1]
            if user not in users:
                users.append(user)
    return users


def list_all_user_submissions():
    """Returns a list of all user submissions"""
    cursor = '0'
    submissions = []
    while cursor != 0:
        cursor, keys = database.scan(cursor, match="user_submission:*")
        for key in keys:
            submission = database.hgetall(key)
            if submission not in submissions:
                submissions.append(submission)
    return submissions


def get_user_submission(user, submission_datetime):
    """Returns a user submission"""
    submission_key = f"user_submission:{user}:{submission_datetime.isoformat()}"
    return database.hgetall(submission_key)


def get_user_submissions(user):
    """Returns all user submissions"""
    cursor = '0'
    submissions = []
    while cursor != 0:
        cursor, keys = database.scan(cursor, match=f"user_submission:{user}:*")
        for key in keys:
            submission = database.hgetall(key)
            if submission not in submissions:
                submissions.append(submission)
    return submissions


def get_user_submissions_by_level(user, level):
    """Returns user submissions for a level"""
    cursor = '0'
    submissions = []
    while cursor != 0:
        cursor, keys = database.scan(cursor, match=f"user_submission:{user}:{level}:*")
        for key in keys:
            submission = database.hgetall(key)
            if submission not in submissions:
                submissions.append(submission)
    return submissions


def get_submissions(level, model):
    """Returns all user submissions for a level/model combination"""
    cursor = '0'
    submissions = []
    while cursor != 0:
        cursor, keys = database.scan(cursor, match=f"user_submission:*:{level}:{model}:*")
        for key in keys:
            submission = database.hgetall(key)
            if submission not in submissions:
                submissions.append(submission)
    return submissions


def is_cleared(level, model, user):
    """Checks if the user has cleared a given level/model combination"""
    return database.sismember(f"level:{level}:{model}:cleared", user)


def list_cleared_by_user(user):
    """Returns the level/model combinations cleared by the user"""
    user_cleared = []
    for cleared in list_all_cleared():
        level, model = cleared.split(":")
        if is_cleared(level, model, user):
            user_cleared.append((level, model))
    return user_cleared


def count_cleared_level_users(level, model):
    """Counts the number of users who cleared the level"""
    return database.scard(f"level:{level}:{model}:cleared")


def list_cleared_users(level, model):
    """Returns the users who cleared the level"""
    return database.smembers(f"level:{level}:{model}:cleared")


def compute_user_score(user):
    """Compute the score of a user"""
    bonus_levels = []
    total_score = 0
    for cleared in list_all_cleared():
        level, model = cleared.split(":")

        # Distribute level points evenly among users who cleared the level
        if is_cleared(level, model, user):
            total_cleared_level_users = count_cleared_level_users(level, model)
            level_score = database.hget(f"level:{level}:score", "score")
            if level_score is None:
                level_score = DEFAULT_LEVEL_SCORE
            level_score = int(level_score)
            user_score = level_score / total_cleared_level_users
            total_score += user_score

        # Give bonus points for the user with the shortest submitted prompt
        submissions = get_submissions(level, model)
        submissions.sort(key=lambda x: len(x['prompt']))
        bonus_score = database.hget(f"level:{level}:score", "bonus")
        if bonus_score is None:
            bonus_score = DEFAULT_BONUS_SCORE
        if submissions and submissions[0]['username'] == user:
            print(f"User {user} got bonus points for level {level} and model {model}")
            bonus_levels.append((level, model))
            total_score += bonus_score

    cleared_levels = list_cleared_by_user(user)
    return total_score, cleared_levels, bonus_levels


def give_medals(leaderboard):
    """Gives medals to the top 3 users"""
    medals = ["🥇", "🥈", "🥉"]
    for i, entry in enumerate(leaderboard):
        if i < len(medals):
            entry['prize'] = medals[i]
        else:
            entry['prize'] = ""
    return leaderboard


def get_leaderboard():
    """Get the leaderboard"""
    users = list_all_users()
    leaderboard = []
    for user in users:
        score, cleared, bonus = compute_user_score(user)
        leaderboard.append((user, score, cleared, bonus))

    # Sort the leaderboard by score
    leaderboard.sort(key=lambda x: x[1], reverse=True)

    # Remove duplicates and format the leaderboard
    leaderboard = [{
        'rank': rank,
        'username': user,
        'score': score,
        'cleared': cleared,
        'bonus': bonus,
    } for rank, (user, score, cleared, bonus) in enumerate(leaderboard, start=1)]
    leaderboard = give_medals(leaderboard)
    for entry in leaderboard:
        if entry['prize']:
            entry['display_name'] = f"{entry['prize']} {entry['username']}"
        else:
            entry['display_name'] = entry['username']
    return leaderboard


def leaderboard_table(title_font='slant'):
    """Displays the leaderboard as a pretty table (literally)"""
    while True:
        try:
            os.system('cls' if os.name == 'nt' else 'clear')
            leaderboard_title = os.environ.get('LEADERBOARD_TITLE', DEFAULT_LEADERBOARD_TITLE)
            try:
                from pyfiglet import Figlet  # pylint: disable=import-outside-toplevel
                figlet = Figlet(font=title_font)
                print(figlet.renderText(leaderboard_title))
            except ImportError:
                print(leaderboard_title)
            leaderboard = get_leaderboard()
            if not leaderboard:
                print("No submissions found!")
                time.sleep(DEFAULT_REFRESH_RATE)
                continue
            table = PrettyTable()
            table.field_names = ["Rank", "User", "Score", "Levels Cleared"]
            for entry in leaderboard:
                entry['cleared'] = "\n".join([
                    f"{level}:{model}" for level, model in entry['cleared']]
                )
                table.add_row([
                    entry['rank'], entry['display_name'], entry['score'], entry['cleared']]
                )
            print(table)
            time.sleep(DEFAULT_REFRESH_RATE)
        except KeyboardInterrupt:
            print("\nExiting...")
            break


def leaderboard_ui():
    """Displays the leaderboard using NiceGUI"""
    ui.page_title(os.environ.get('LEADERBOARD_TITLE', DEFAULT_LEADERBOARD_TITLE))
    ui.markdown("#### Prompt-a-thon Leaderboard")
    ui.label(
        "Scores are calculated based on the levels cleared "
        "and the length of the prompts submitted."
    )
    columns = [
        {'name': 'Rank', 'field': 'rank', 'label': 'Rank'},
        {'name': 'User', 'field': 'display_name', 'label': 'User'},
        {'name': 'Score', 'field': 'score', 'label': 'Score'},
        {'name': 'Cleared', 'field': 'cleared', 'label': 'Cleared'},
    ]
    leaderboard = get_leaderboard()
    for entry in leaderboard:
        print(entry)
        entry['cleared'] = "\n".join(
            [f"{'⭐' if (level, model) in entry['bonus'] else ''}{level}:{model}"
                for level, model in entry['cleared']]
        )

    ui.table(
        columns=columns,
        rows=leaderboard,
        row_key='rank'
    ).classes('table table-striped table-hover')
    ui.add_head_html(
        """
        <style>
            .table {
                width: 100%;
                margin: 0 auto;
                border-collapse: collapse;
            }
            .table th, .table td {
                padding: 8px 12px;
                text-align: left;
            }
            .table th {
                background-color: #f2f2f2;
            }
            .table td {
                border-bottom: 1px solid #ddd;
                white-space: pre-line;
            }
        </style>
        """
    )
    ui.run()

if __name__ in {"__main__", "__mp_main__"}:
    mode = os.environ.get('LEADERBOARD_MODE', 'console')
    if mode == 'console':
        leaderboard_table(os.environ.get('LEADERBOARD_TITLE_FONT', 'slant'))
    elif mode == 'ui':
        leaderboard_ui()
    else:
        print(f"Unknown mode: {mode}. Please set LEADERBOARD_MODE to 'terminal' or 'ui'.")
