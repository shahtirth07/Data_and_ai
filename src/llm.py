import os

from dotenv import load_dotenv

from src.rocketride_client import ask_llm as rocketride_ask_llm


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env():
    env_path = os.path.join(_project_root(), ".env")
    load_dotenv(env_path)


def _use_rocketride():
    _load_env()
    flag = os.getenv("USE_ROCKETRIDE")
    if flag is None:
        flag = ""
    flag = flag.strip().lower()
    if flag == "true":
        return True
    return False


def _ask_openai(prompt):
    from openai import OpenAI

    _load_env()
    api_key = os.getenv("OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    text = response.choices[0].message.content
    if text is None:
        text = ""

    tokens = 0
    if response.usage is not None:
        tokens = response.usage.total_tokens

    result = {}
    result["text"] = text
    result["tokens"] = tokens
    result["tokens_estimated"] = False
    return result


async def ask_llm(client, token, prompt):
    if _use_rocketride():
        rr = await rocketride_ask_llm(client, token, prompt)
        result = {}
        result["text"] = rr["text"]
        result["tokens"] = rr["tokens"]
        result["tokens_estimated"] = rr["tokens_estimated"]
        return result

    result = _ask_openai(prompt)
    return result
