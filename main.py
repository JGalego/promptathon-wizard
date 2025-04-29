# pylint: disable=line-too-long,no-member,redefined-outer-name
r"""
"Pay no attention to that man behind the curtain."

                                    - The Wizard of Oz
                    ____
                  .'* *.'
               __/_*_*(_
              / _______ \
             _\_)/___\(_/_
            / _((\- -/))_ \
            \ \())(-)(()/ /
             ' \(((()))/ '
            / ' \)).))/ ' \
           / _ \ - | - /_  \
          (   ( .;''';. .'  )
          _\"__ /    )\ __"/_
            \/  \   ' /  \/
             .'  '...' ' )
              / /  |  \ \
             / .   .   . \
            /   .     .   \
           /   /   |   \   \
         .'   /    b    '.  '.
     _.-'    /     Bb     '-. '-._
 _.-'       |      BBb       '-.  '-.
(________mrf\____.dBBBb.________)____)
"""

# Standard import
import os
import secrets
import string

from datetime import datetime

# Library imports
import gradio as gr
import redis
import yaml

from fastapi import FastAPI
from litellm import completion

# Constants
DEFAULT_TITLE = "Prompt-a-thon"
DEFAULT_DESCRIPTION = "A platform to test and improve your prompt engineering skills."

# 0a. Load configuration
with open(os.environ.get('PROMPTATHON_CONFIG', "promptathon.yml"), 'r', encoding='utf-8') as config_file:
    config = yaml.full_load(config_file)
    general = config.get('general', {})

    try:
        levels = config['levels']
    except KeyError as exc:
        raise ValueError("Configuration file must contain a 'levels' section.") from exc

    try:
        models = config['models']
    except KeyError as exc:
        raise ValueError("Configuration file must contain a 'models' section.") from exc

# 0b. Connect to database
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

except (KeyError, redis.ConnectionError):
    database = None  # pylint: disable=invalid-name

with gr.Blocks() as demo:
    promptathon_title = general.get('title', DEFAULT_TITLE)
    promptathon_description = general.get('description', DEFAULT_DESCRIPTION)
    gr.Markdown(
        f"""
# {promptathon_title}

{promptathon_description}
""")

    # 1. Select level
    levels = {level['name']: level for level in levels}
    level_names = list(levels.keys())
    level = gr.Radio(level_names, label="Level", value=level_names[0])

    # 2. Select model
    models = {model['name']: model for model in models}
    model_names = list(models.keys())
    model = gr.Radio(model_names, label="Model", value=model_names[0])

    with gr.Row():

        # 3. Prompt model
        with gr.Column():
            prompt = gr.TextArea(label="Prompt", placeholder="Enter your prompt here...")
            generate_button = gr.Button("Generate 🪄")
            submit_button = gr.Button("Submit 🚀", interactive=False)

        with gr.Column():
            with gr.Column():
                expected_completion = gr.Textbox(
                    interactive=False,
                    label="Expected Completion",
                    value=levels[level.value]['expected_completion'],
                )
            with gr.Column():
                response = gr.Textbox(label="Response", placeholder="Response will appear here...")

    def generate_response(model, level, prompt):
        """Generates a text completion and checks if it matches the expected output."""
        response = completion(
            model=model,
            messages=[{
                'role': "user",
                'content': levels[level]['prompt_template'].format(PROMPT=prompt)
            }],
            **models[model].get('model_kwargs', {}),
        )
        content = response.choices[0].message['content']
        if content == levels[level]['expected_completion']:
            return f"{content} ✅", gr.Button(interactive=True)
        return content, gr.Button(interactive=False)

    def submit_response(level, model, prompt, response, expected_completion, request: gr.Request):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """Registers a user submission in the database"""
        if database is not None:
            submission_datetime = datetime.now()
            submission_key = f"user_submission:{request.username}:{level}:{model}:{submission_datetime.isoformat()}"
            submission = {
                'username': request.username,
                'level': level,
                'model': model,
                'prompt': prompt,
                'response': response,
                'expected_completion': expected_completion,
            }
            database.zadd("user_submissions_index", {submission_key: submission_datetime.timestamp()})
            database.hset(submission_key, mapping=submission)
            database.sadd(f"level:{level}:{model}:cleared", request.username)
            return "Response submitted! 🎉", gr.Button(interactive=False)
        return "Database not connected 🥀 Please check your configuration.", gr.Button(interactive=False)

    # 4. Generate response
    generate_button.click(generate_response, inputs=(model, level, prompt), outputs=[response, submit_button])

    # 5. Submit response
    submit_button.click(submit_response, inputs=[level, model, prompt, response, expected_completion], outputs=[response, submit_button])


def generate_password(length=12, use_special_chars=True):
    """Generates a random password with the specified length and character set."""
    characters = string.ascii_letters + string.digits
    if use_special_chars:
        characters += string.punctuation
    password = ''.join(secrets.choice(characters) for i in range(length))
    return password


if gr.NO_RELOAD:

    try:
        from pyfiglet import Figlet  # pylint: disable=import-outside-toplevel
        figlet = Figlet(font='slant')
        print(figlet.renderText(promptathon_title))
    except ImportError:
        print(f"Starting {promptathon_title}...")

    # Process authentication configuration data
    auth = general.get('auth', None)
    if isinstance(auth, list):
        # Standardize auth format as a list of username/password dictionaries
        auth = [{'username': user} if isinstance(user, str) else user for user in auth]

        # Generate passwords for users without passwords
        for user in auth:
            if 'password' not in user:
                user['password'] = generate_password()

        # Display authentication details
        print("Authentication enabled! 🔐 \n\nHere's the list of participants and their passwords:\n")
        auth = list(map(lambda x: (x['username'], x['password']), auth))
        for username, password in auth:
            print(f"{username},{password}")

        print("\n💾 Please save this information in a secure location.\n")


if general.get('fastapi', os.environ.get('USE_FASTAPI', '0') == '1'):
    # Mount Gradio app to FastAPI
    app = FastAPI()
    app = gr.mount_gradio_app(
        app,
        demo,
        path="",
        auth=auth
    )
else:
    demo.launch(
        auth=auth,
        share=general.get('share', False)
    )
