"""
A vibe-coded prompt-a-thon Leaderboard
"""

# Standard imports
import logging
import os
import time

from functools import lru_cache

# Library imports
import redis
from dotenv import load_dotenv
from nicegui import ui
from prettytable import PrettyTable

# Constants
DEFAULT_LEADERBOARD_TITLE = "Leaderboard"
DEFAULT_REFRESH_RATE = 60
DEFAULT_LEVEL_SCORE = 100
DEFAULT_BONUS_SCORE = 10

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# Load environment variables
load_dotenv()

try:
    if bool(int(os.environ.get('REDIS_CLUSTER_MODE', 0))):
        database = redis.RedisCluster(
            host=os.environ.get('REDIS_HOST', 'localhost'),
            port=int(os.environ.get('REDIS_PORT', 6379)),
            username=os.environ.get('REDIS_USERNAME', None),
            password=os.environ.get('REDIS_PASSWORD', None),
            ssl=bool(int(os.environ.get('REDIS_SSL', 0))),
            decode_responses=True,
        )
        logging.info("✨ Connected to Redis cluster!")
    else:
        database = redis.Redis(
            host=os.environ.get('REDIS_HOST', 'localhost'),
            port=int(os.environ.get('REDIS_PORT', 6379)),
            db=int(os.environ.get('REDIS_DB', 0)),
            username=os.environ.get('REDIS_USERNAME', None),
            password=os.environ.get('REDIS_PASSWORD', None),
            ssl=bool(int(os.environ.get('REDIS_SSL', 0))),
            decode_responses=True,
        )
        logging.info("🗃️ Connected to Redis database!")
except (KeyError, redis.exceptions.ConnectionError) as exc:
    logging.error("💥 Failed connection to Redis!")
    raise exc


def search_by_timestamp(start, end):
    """Returns all submissions within the given timestamp range"""
    keys = database.zrangebyscore("user_submissions_index", start.timestamp(), end.timestamp())
    submissions = [database.hgetall(key) for key in keys]
    return submissions


def list_all_cleared():
    """Returns a list all cleared level/model combinations with improved performance"""
    logging.debug("Listing all cleared levels")
    try:
        # Get all cleared level keys in batch
        keys = list(database.scan_iter("level:*:cleared"))

        # Extract level:model combinations efficiently
        all_cleared = []
        for key in keys:
            parts = key.split(":")
            if len(parts) >= 3:  # format: level:LEVEL:MODEL:cleared
                level_model = ":".join(parts[1:-1])  # Extract LEVEL:MODEL
                all_cleared.append(level_model)

        return all_cleared
    except (redis.exceptions.RedisError, ValueError) as e:
        logging.error("Error listing cleared levels: %s", e)
        return []


# Cache for cleared levels (expires after 60 seconds since it changes less frequently)
_CLEARED_LEVELS_CACHE = None
_CLEARED_LEVELS_CACHE_TIMESTAMP = 0
_CLEARED_LEVELS_CACHE_EXPIRY = 60  # seconds

def list_all_cleared_cached():
    """Returns cached cleared levels or fetches new ones"""
    global _CLEARED_LEVELS_CACHE, _CLEARED_LEVELS_CACHE_TIMESTAMP  # pylint: disable=global-statement
    current_time = time.time()

    if (_CLEARED_LEVELS_CACHE is not None and
        current_time - _CLEARED_LEVELS_CACHE_TIMESTAMP < _CLEARED_LEVELS_CACHE_EXPIRY):
        return _CLEARED_LEVELS_CACHE

    # Cache miss or expired, fetch new data
    _CLEARED_LEVELS_CACHE = list_all_cleared()
    _CLEARED_LEVELS_CACHE_TIMESTAMP = current_time
    logging.debug("Cleared levels cache refreshed with %d entries", len(_CLEARED_LEVELS_CACHE))
    return _CLEARED_LEVELS_CACHE

def clear_cleared_levels_cache():
    """Clear the cleared levels cache - call this when new levels are cleared"""
    global _CLEARED_LEVELS_CACHE  # pylint: disable=global-statement
    _CLEARED_LEVELS_CACHE = None
    logging.debug("Cleared levels cache cleared")


def list_all_users():
    """Returns a list of users who have made submissions with improved performance"""
    logging.debug("Listing all users")
    try:
        # Use a set to automatically handle duplicates
        users = set()

        # Get all user submission keys in batch
        keys = list(database.scan_iter("user_submission:*"))

        # Extract usernames from keys (format: user_submission:username:...)
        for key in keys:
            parts = key.split(":")
            if len(parts) >= 2:
                users.add(parts[1])

        return list(users)
    except (redis.exceptions.RedisError, ValueError) as e:
        logging.error("Error listing users: %s", e)
        return []


def list_all_user_submissions():
    """Returns all submissions"""
    logging.debug("Listing all user submissions")
    return [
        database.hgetall(submission)
            for submission in database.scan_iter("user_submission:*")
    ]


def get_user_submission(user, submission_datetime):
    """Returns a user submission by datetime"""
    logging.debug("Getting submission for user %s at %s", user, submission_datetime)
    return database.hgetall(f"user_submission:{user}:{submission_datetime.isoformat()}")


def get_user_submissions(user):
    """Returns all user submissions"""
    logging.debug("Getting all submissions for user %s", user)
    return [
        database.hgetall(submission)
            for submission in database.scan_iter(f"user_submission:{user}:*")
    ]


def get_user_submissions_by_level(user, level):
    """Returns user submissions for a level"""
    logging.debug("Getting submissions for user %s at level %s", user, level)
    return [
        database.hgetall(submission)
            for submission in database.scan_iter(f"user_submission:{user}:{level}:*")
    ]


# Cache for submissions (expires after 30 seconds)
_SUBMISSIONS_CACHE = {}
_CACHE_EXPIRY = 30  # seconds

def _get_cached_submissions(level, model):
    """Get cached submissions or fetch new ones"""
    cache_key = f"{level}:{model}"
    current_time = time.time()

    if cache_key in _SUBMISSIONS_CACHE:
        data, timestamp = _SUBMISSIONS_CACHE[cache_key]
        if current_time - timestamp < _CACHE_EXPIRY:
            return data

    # Cache miss or expired, fetch new data
    data = _get_submissions_uncached(level, model)
    _SUBMISSIONS_CACHE[cache_key] = (data, current_time)
    return data

def _get_submissions_uncached(level, model):
    """Internal function to get submissions without caching"""
    logging.debug("Getting submissions for level %s and model %s", level, model)

    # Use a more efficient approach with pipeline for batch operations
    try:
        # Get all matching keys first
        keys = list(database.scan_iter(f"user_submission:*:{level}:{model}:*"))

        if not keys:
            return []

        # Use pipeline for batch retrieval to reduce network round trips
        pipeline = database.pipeline()
        for key in keys:
            pipeline.hgetall(key)

        # Execute all operations in a single network call
        results = pipeline.execute()

        # Filter out any None results (in case keys were deleted between scan and hgetall)
        return [result for result in results if result]

    except (redis.exceptions.RedisError, ValueError) as e:
        logging.error("Error getting submissions for %s:%s: %s", level, model, e)
        return []


def is_cleared(level, model, user):
    """Checks if the user has cleared a given level/model combination"""
    logging.debug("Checking if %s cleared %s:%s", user, level, model)
    return database.sismember(f"level:{level}:{model}:cleared", user)


def list_cleared_by_user(user):
    """Returns the level/model combinations cleared by the user with improved performance"""
    logging.debug("Listing cleared levels for user %s", user)
    try:
        user_cleared = []

        # Use cached cleared levels and batch check membership
        cleared_levels = list_all_cleared_cached()

        # Use pipeline for batch membership checks
        if cleared_levels:
            pipeline = database.pipeline()
            for cleared in cleared_levels:
                level, model = cleared.split(":")
                pipeline.sismember(f"level:{level}:{model}:cleared", user)

            # Execute all membership checks in one call
            results = pipeline.execute()

            # Build the result list
            for i, is_member in enumerate(results):
                if is_member:
                    level, model = cleared_levels[i].split(":")
                    user_cleared.append((level, model))

        return user_cleared
    except (redis.exceptions.RedisError, ValueError) as e:
        logging.error("Error listing cleared levels for user %s: %s", user, e)
        return []


def count_cleared_level_users(level, model):
    """Counts the number of users who cleared the level"""
    logging.debug("Counting cleared users for %s:%s", level, model)
    return database.scard(f"level:{level}:{model}:cleared")


def list_cleared_users(level, model):
    """Returns the users who cleared the level"""
    logging.debug("Listing cleared users for %s:%s", level, model)
    return database.smembers(f"level:{level}:{model}:cleared")


def compute_user_score(user, shortest_submissions_by_level, bonus_scores_by_level):
    """Compute the score of a user"""
    logging.debug("Computing score for user %s", user)
    bonus_levels = []
    total_score = 0
    for cleared in list_all_cleared_cached():
        level, model = cleared.split(":")

        # Distribute level points evenly among users who cleared the level
        if is_cleared(level, model, user):
            total_cleared_level_users = count_cleared_level_users(level, model)
            level_score = get_level_score_cached(level)
            user_score = level_score // total_cleared_level_users
            total_score += user_score

        # Give bonus points for the user with the shortest submitted prompt
        level_model_key = f"{level}:{model}"
        shortest_submission = shortest_submissions_by_level.get(level_model_key)
        bonus_score = bonus_scores_by_level.get(level)
        if shortest_submission and shortest_submission.get('username') == user and bonus_score:
            bonus_levels.append((level, model))
            total_score += bonus_score

    cleared_levels = list_cleared_by_user(user)
    return total_score, cleared_levels, bonus_levels


def give_medals(leaderboard):
    """Gives medals to the top 3 users"""
    logging.debug("Giving medals to the top 3 users")
    medals = ["🥇", "🥈", "🥉"]
    for i, entry in enumerate(leaderboard):
        if i < len(medals):
            entry['prize'] = medals[i]
        else:
            entry['prize'] = ""
    return leaderboard


def get_leaderboard():
    """Get the leaderboard"""
    logging.debug("Creating leaderboard")
    users = list_all_users()
    
    # Pre-compute shortest submissions and bonus scores for all cleared levels
    cleared_levels = list_all_cleared_cached()
    shortest_submissions_by_level = {}
    bonus_scores_by_level = {}
    
    for cleared in cleared_levels:
        level, model = cleared.split(":")
        level_model_key = f"{level}:{model}"
        
        # Get shortest submission for this level/model combination
        shortest_submissions_by_level[level_model_key] = get_shortest_submission(level, model)
        
        # Get bonus score for this level (only compute once per level)
        if level not in bonus_scores_by_level:
            bonus_scores_by_level[level] = get_bonus_score_cached(level)
    
    leaderboard = []
    for user in users:
        score, cleared, bonus = compute_user_score(user, shortest_submissions_by_level, bonus_scores_by_level)
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

    # Add prizes and display names
    leaderboard = give_medals(leaderboard)
    for entry in leaderboard:
        if entry['prize']:
            entry['display_name'] = "{} {}".format(entry['prize'], entry['username'])  # pylint: disable=consider-using-f-string
        else:
            entry['display_name'] = entry['username']
    return leaderboard


def leaderboard_table(title_font='slant'):
    """Displays the leaderboard as a pretty table (literally)"""
    logging.debug("Creating leaderboard table")
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
                    "{}:{}".format(level, model) for level, model in entry['cleared']]  # pylint: disable=consider-using-f-string
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
    logging.debug("Creating leaderboard UI")
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
        entry['cleared'] = "\n".join(
            ["{}{}:{}".format('⭐' if (level, model) in entry.get('bonus', []) else '', level, model)  # pylint: disable=consider-using-f-string
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
    ui.run(
        host=os.environ.get('LEADERBOARD_HOST', "0.0.0.0"),
        port=int(os.environ.get('LEADERBOARD_PORT', 8080)),
    )


# Cache for shortest submissions (expires after 30 seconds)
_SHORTEST_SUBMISSION_CACHE = {}

def get_shortest_submission(level, model):
    """Returns the submission with the shortest prompt for a given level and model"""
    logging.debug("Getting shortest submission for level %s and model %s", level, model)

    # Check cache first
    cache_key = f"shortest:{level}:{model}"
    current_time = time.time()
    
    if cache_key in _SHORTEST_SUBMISSION_CACHE:
        data, timestamp = _SHORTEST_SUBMISSION_CACHE[cache_key]
        if current_time - timestamp < _CACHE_EXPIRY:
            return data

    try:
        # Get all matching keys
        keys = list(database.scan_iter(f"user_submission:*:{level}:{model}:*"))

        if not keys:
            # Cache the None result to avoid repeated database scans
            _SHORTEST_SUBMISSION_CACHE[cache_key] = (None, current_time)
            return None

        # First pass: only get prompt lengths to find the shortest
        pipeline = database.pipeline()
        for key in keys:
            pipeline.hget(key, 'prompt')

        prompt_results = pipeline.execute()

        # Find the index of the shortest prompt
        shortest_length = float('inf')
        shortest_index = None

        for i, prompt in enumerate(prompt_results):
            if prompt:  # Check if prompt exists
                prompt_length = len(prompt)
                if prompt_length < shortest_length:
                    shortest_length = prompt_length
                    shortest_index = i

        if shortest_index is not None:
            # Second pass: only get the username for the shortest submission
            shortest_key = keys[shortest_index]
            shortest_user = database.hget(shortest_key, 'username')
            
            if shortest_user:
                result = {
                    'username': shortest_user,
                    'prompt_length': shortest_length,
                    'key': shortest_key
                }
                # Cache the result
                _SHORTEST_SUBMISSION_CACHE[cache_key] = (result, current_time)
                return result

        # Cache the None result
        _SHORTEST_SUBMISSION_CACHE[cache_key] = (None, current_time)
        return None

    except (redis.exceptions.RedisError, ValueError) as e:
        logging.error("Error getting shortest submission for %s:%s: %s", level, model, e)
        return None


def get_submissions(level, model):
    """Returns all user submissions for a given level and model with optimized performance"""
    return _get_cached_submissions(level, model)


def clear_submissions_cache():
    """Clear the submissions cache - call this when new submissions are added"""
    _SUBMISSIONS_CACHE.clear()
    _SHORTEST_SUBMISSION_CACHE.clear()
    logging.debug("Submissions and shortest submission caches cleared")


def clear_all_caches():
    """Clear all caches - call this when data is updated"""
    clear_submissions_cache()
    clear_cleared_levels_cache()
    clear_score_cache()
    logging.debug("All caches cleared")


def get_submissions_cache_stats():
    """Get statistics about the submissions cache"""
    return {
        'cache_size': len(_SUBMISSIONS_CACHE),
        'cache_keys': list(_SUBMISSIONS_CACHE.keys()),
        'cache_expiry_seconds': _CACHE_EXPIRY,
        'shortest_submission_cache_size': len(_SHORTEST_SUBMISSION_CACHE),
        'shortest_submission_cache_keys': list(_SHORTEST_SUBMISSION_CACHE.keys())
    }


def get_all_cache_stats():
    """Get statistics about all caches"""
    return {
        'submissions_cache': get_submissions_cache_stats(),
        'cleared_levels_cached': _CLEARED_LEVELS_CACHE is not None,
        'cleared_levels_count': len(_CLEARED_LEVELS_CACHE) if _CLEARED_LEVELS_CACHE else 0,
        'score_cache_info': {
            'level_score_cache': get_level_score_cached.cache_info(),
            'bonus_score_cache': get_bonus_score_cached.cache_info()
        }
    }


# Add LRU cache for frequently accessed Redis data
@lru_cache(maxsize=128)
def get_level_score_cached(level):
    """Get level score with caching"""
    level_score = database.hget(f"level:{level}:score", "score")
    return int(level_score) if level_score is not None else DEFAULT_LEVEL_SCORE


@lru_cache(maxsize=128)
def get_bonus_score_cached(level):
    """Get bonus score with caching"""
    bonus_score = database.hget(f"level:{level}:score", "bonus")
    return int(bonus_score) if bonus_score is not None else DEFAULT_BONUS_SCORE


def clear_score_cache():
    """Clear the score cache - call this when scores are updated"""
    get_level_score_cached.cache_clear()
    get_bonus_score_cached.cache_clear()
    logging.debug("Score cache cleared")


if __name__ in {"__main__", "__mp_main__"}:
    mode = os.environ.get('LEADERBOARD_MODE', 'console')
    try:
        if mode == 'console':
            leaderboard_table(os.environ.get('LEADERBOARD_TITLE_FONT', 'slant'))
        elif mode == 'ui':
            leaderboard_ui()
        else:
            logging.error("🤷 Unknown mode: %s. Set LEADERBOARD_MODE to 'terminal' or 'ui'.", mode)
    except KeyboardInterrupt:
        logging.info("🚪 Exiting leaderboard...")
