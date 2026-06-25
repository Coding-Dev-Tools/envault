# Envault — Agent Notes

## Status
- Missing `AGENTS.md` was the main structural gap in this repo.
- TL;DR fixes: add repo-level agent contract and document focused local workflow.
- Overall repo health: looks stable, with active coverage tools present.

## Local Workflow
- Use the existing Python toolchain.
- Run tests in `tests/` via pytest.
- Check lint with `ruff` before submitting a change.

## Notes for Contributors
- Keep commits small and security-conscious; this repo is related to handling secrets.
- Preserve existing files when possible, especially `.env` files outside of the tool's intended temp usage.