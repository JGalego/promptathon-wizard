# Prompt-A-Thon Wizard 🦉

## Overview

A simple Gradio application for hosting custom [Prompt-A-Thon](https://hackworks.com/promptathon/) competitions.

![](examples/demo.png)

## Prerequisites ✅

* 🐍 [Python](https://www.python.org) (version `>3.10`, tested with `3.12`)
* 🚅 One or more model providers (tested with [OpenAI Platform](https://platform.openai.com/))

    >❗We use [LiteLLM](https://docs.litellm.ai) to connect with different model providers. Make sure youe model provider is [supported by LiteLLM](https://docs.litellm.ai/docs/providers).

## Local Deployment 🏕️

0. Install dependencies

    ```bash
    pip install -r requirements.txt
    ```

1. Start the competition!

    ```bash
    # OpenAI
    export OPENAI_API_KEY=sk-...

    # Azure
    export AZURE_API_KEY=...
    export AZURE_API_BASE=...

    # Start promptathon!
    export PROMPTATHON_CONFIG=...
    gradio main.py
    ```

## What if I want to go live? ✨

> ☝ For more information, see [Gradio Docs > Sharing your app](https://www.gradio.app/guides/sharing-your-app)

Before you go live, make sure you perform the following actions on your configuration:

* 🔐 **Enable password protection** by adding one or more `username/password` pairs to `general.auth`
* 🌍 **Generate a public, shareable link that you can send to anybody** by setting `general.share` to `true`

## Azure Deployment 🚀

0. Login to Azure

1. Deploy the bicep file using either Azure CLI or Azure PowerShell

    ```bash
    az group create --name ai-promptathon --location eastus
    az deployment group create --resource-group ai-promptathon --template-file main.bicep
    ```

2. [Deploy Gradio app on Azure with Azure App Service](https://techcommunity.microsoft.com/blog/azure-ai-services-blog/deploy-a-gradio-web-app-on-azure-with-azure-app-service-a-step-by-step-guide/4121127)
