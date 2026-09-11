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


def _extract_text(response):
    text = ""

    if "data" in response:
        data = response["data"]
        if data is not None:
            if "answer" in data:
                answer = data["answer"]
                if hasattr(answer, "getText"):
                    text = answer.getText()
                else:
                    text = str(answer)

    if text == "":
        if "answers" in response:
            answers = response["answers"]
            if answers is not None:
                if len(answers) > 0:
                    first = answers[0]
                    if hasattr(first, "getText"):
                        text = first.getText()
                    else:
                        text = str(first)

    return text


def _extract_tokens(response, prompt, text):
    tokens = None

    if "tokens" in response:
        token_info = response["tokens"]
        if token_info is not None:
            if hasattr(token_info, "total"):
                tokens = token_info.total
            else:
                if isinstance(token_info, dict):
                    if "total" in token_info:
                        tokens = token_info["total"]
                    else:
                        if "total_tokens" in token_info:
                            tokens = token_info["total_tokens"]
                else:
                    if isinstance(token_info, (int, float)):
                        tokens = token_info

    if tokens is None:
        if "usage" in response:
            usage = response["usage"]
            if usage is not None:
                if isinstance(usage, dict):
                    if "total_tokens" in usage:
                        tokens = usage["total_tokens"]
                    else:
                        if "total" in usage:
                            tokens = usage["total"]

    if tokens is None:
        combined = prompt + text
        tokens = len(combined) // 4

    tokens = int(tokens)
    return tokens


async def ask_llm(client, token, prompt):
    question = Question()
    question.addQuestion(prompt)

    response = await client.chat(token=token, question=question)

    text = _extract_text(response)
    tokens = _extract_tokens(response, prompt, text)

    result = {}
    result["text"] = text
    result["tokens"] = tokens
    result["raw"] = response
    return result


async def stop_pipeline(client, token):
    await client.terminate(token)
