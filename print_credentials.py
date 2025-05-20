"""
Retrieve credentials for all participants.
"""

# Standard imports
import os
import redis

# Library imports
from prettytable import PrettyTable

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
        print("✨ Connected to Redis cluster!")
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
        print("🗃️ Connected to Redis database!")
except (KeyError, redis.ConnectionError) as exc:
    raise exc


def get_credentials():
    """
    Retrieve credentials for all participants.
    """
    table = PrettyTable(["username", "password"])
    for user in database.scan_iter('user:*'):
        table.add_row([user.split(':')[1], database.hget(user, 'password')])
    print(table)

if __name__ == "__main__":
    get_credentials()
