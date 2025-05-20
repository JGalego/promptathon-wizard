"""
Generate dataset of all submissions
"""

import os
import redis
import pandas as pd

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

def get_submissions():
    """
    Retrieve all submissions from the Redis database.
    """
    # Collect user submissions
    submissions = []
    for submission in database.scan_iter('user_submission:*'):
        submission_data = database.hgetall(submission)
        submission_data = {
            'level': submission_data.get('level'),
            'model': submission_data.get('model'),
            'prompt': submission_data.get('prompt')
        }
        submissions.append(submission_data)

    # Convert to DataFrame and check if there are any submissions
    print(f"📦 Found {len(submissions)} submissions in the database.")
    df = pd.DataFrame(submissions)
    if df.empty:
        print("⚠️ No submissions found.")
        return

    # Save to CSV
    df.to_csv('submissions.csv', index_label='id')
    print("💾 Submissions saved to submissions.csv")

if __name__ == "__main__":
    get_submissions()
