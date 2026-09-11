import asyncio
import time

from src.rocketride_client import ask_llm, connect, start_pipeline, stop_pipeline


async def main():
    client = await connect()
    print("Connected to RocketRide")

    token = await start_pipeline(client)
    print("Started pipeline token=", token)

    prompt = "Reply with only the word pong"
    start = time.time()
    result = await ask_llm(client, token, prompt)
    elapsed = time.time() - start

    print("FULL raw response object:")
    print(result["raw"])
    print("text=", result["text"])
    print("tokens=", result["tokens"])
    print("seconds=", round(elapsed, 2))

    await stop_pipeline(client, token)
    print("Stopped pipeline")

    await client.disconnect()
    print("Disconnected")


asyncio.run(main())
