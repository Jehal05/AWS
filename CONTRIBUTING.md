# Contributing

```bash
pip install -e ".[dev]"
python -m pytest -q        # tests, including a browser run if Playwright is installed
ruff check .               # lint
python -m renewflow.eval   # golden conversations
python -m renewflow --reset
```

Guidelines

- Keep the agent behind the `Channel` and `ChatModel` interfaces. New channels and models are new
  adapters, not changes to the agent.
- Anything a customer can see goes through `send_message`, so the guardrails always run. Do not send
  around them.
- Every ₹ amount in a message must come from a tool result.
- When you change behaviour, add a case to `src/renewflow/evalset.py` or a test.
- Update the diagram in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) when the flow it shows changes.
- Say plainly in docs and the UI what is simulated and what is live.
