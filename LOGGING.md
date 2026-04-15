# Logging and Performance Note

This project uses logging for observability while keeping runtime overhead low.

## Level policy

- Use `DEBUG` for verbose internals, per-step diagnostics, and developer-only traces.
- Use `INFO` for major process milestones (start, key output written, publish success).
- Use `WARNING` for recoverable anomalies and fallback behavior.
- Use `ERROR`/`EXCEPTION` for failures that prevent expected flow.

## Performance guidelines

- Prefer parameterized logging: `logger.info("value=%s", value)` instead of f-strings.
- Avoid `INFO` logs in hot loops or per-feature/per-pixel operations.
- Keep one start and one finish `INFO` per major workflow step.
- Log context once (e.g., `sessionid`, `hazard`, `layer`) and avoid repeating it in every message.
- Guard expensive debug-only computation with:
  - `if logger.isEnabledFor(logging.DEBUG): ...`

## Configuration

- Configure logging once at the application entrypoint.
- Library/handler modules should not call `logging.basicConfig()`.
