# pylint: disable=line-too-long,no-member,redefined-outer-name
"""
Prompt-a-thon Generator
"""

import os
import yaml

import gradio as gr

from litellm import completion

# Constants
DEFAULT_TITLE = "Prompt-a-thon"
DEFAULT_DESCRIPTION = "A platform to test and improve your prompt engineering skills."

# 0. Load configuration
with open(os.environ.get('PROMPTATHON_CONFIG') or input("Promptathon Config:"), 'r', encoding='utf-8') as config_file:
    config = yaml.full_load(config_file)

with gr.Blocks() as demo:
    gr.Markdown(
        f"""
# {config.get('general', {}).get('title', DEFAULT_TITLE)}

{config.get('general', {}).get('description', DEFAULT_DESCRIPTION)}
""")

    # 1. Select level
    levels = config['levels']
    levels = {level['name']: level for level in levels}
    level_names = list(levels.keys())
    level = gr.Radio(level_names, label="Level", value=level_names[0])

    # 2. Select model
    models = config['models']
    models = {model['name']: model for model in models}
    model_names = list(models.keys())
    model = gr.Radio(model_names, label="Model", value=model_names[0])

    with gr.Row():

        # 3. Prompt model
        with gr.Column():
            prompt = gr.TextArea(label="Prompt", placeholder="Enter your prompt here...")
            generate_button = gr.Button("Generate 🪄")
            # save_button = gr.DownloadButton("Save 💾")
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

    def submit_response():
        """Sends the prompt for evaluation."""
        return "Response submitted! 🎉", gr.Button(interactive=False)

    # 4. Generate response
    generate_button.click(generate_response, inputs=(model, level, prompt), outputs=[response, submit_button])

    # 5. Submit response
    submit_button.click(submit_response, outputs=[response, submit_button])

# Start app
demo.queue(default_concurrency_limit=8).launch()
