# Generated tests

Run the OpenAPI-driven generator:

```pwsh
uv run python tests_generated/generator.py
```

When `OPENROUTER_API_KEY` is unavailable, the command runs the committed
`generated_test.py` fallback. LLM output is accepted only when it is one async
`test_...` function using the provided `client`, relative `/api/` paths, and no
imports, external URLs, filesystem/process/environment access, dynamic code,
skips, decorators, nested code, or bypassing control flow. Assertions must use
data derived from a preceding fixture-client request, and the required status
assertion must reference the direct result of `await client.<verb>(...)` with a
non-`5xx` expected status. Pytest subprocesses receive a credential-scrubbed
environment and a five-minute timeout.

Run the committed generated tests directly:

```pwsh
uv run pytest tests_generated/generated_test.py -v -p no:cacheprovider
```
