Project: hackathon prototype called "Agents That Sleep".
Tonight we are only running small setup tests in a scratch folder.

Code style rules:
- Python, simplest possible style
- no list comprehensions, no inline if/else, no clever one-liners
- plain for loops and explicit steps
- only create a variable at the step that needs it
- read API keys from a .env file, never hardcode them

Tools:
- Hotdata via the hotdata-ibis package (one database per agent)
- RocketRide Python SDK (rocketride) for all LLM calls
