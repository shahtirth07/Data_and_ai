import os

from dotenv import load_dotenv
from rocketride import RocketRideClient
from rocketride.schema import Question


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env():
    env_path = os.path.join(_project_root(), ".env")
    load_dotenv(env_path)


async def connect():
    _load_env()

    uri = os.getenv("ROCKETRIDE_URI")
    api_key = os.getenv("ROCKETRIDE_API_KEY")
    if api_key is None:
        api_key = ""
    api_key = api_key.strip()

    if api_key == "":
        client = RocketRideClient(uri=uri, auth="local")
    else:
        client = RocketRideClient(uri=uri, auth=api_key)

    await client.connect()
    return client


async def start_pipeline(client):
    pipeline_path = os.path.join(_project_root(), "pipelines", "sql_writer.pipe")
    result = await client.use(filepath=pipeline_path)
    token = result["token"]
    return token


async def ask_llm(client, token, prompt):
    question = Question()
    question.addQuestion(prompt)

    response = await client.chat(token=token, question=question)

    text = ""
    if "answers" in response:
        answers = response["answers"]
        if answers is not None:
            if len(answers) > 0:
                text = answers[0]
                if text is None:
                    text = ""
                else:
                    text = str(text)

    combined = prompt + text
    tokens = len(combined) // 4

    result = {}
    result["text"] = text
    result["tokens"] = tokens
    result["tokens_estimated"] = True
    result["raw"] = response
    return result


async def stop_pipeline(client, token):
    await client.terminate(token)
