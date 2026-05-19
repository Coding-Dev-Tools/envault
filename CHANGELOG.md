# Changelog

All notable changes to Envault will be documented in this file.

## [Unreleased]

### Added

- CLI test suite with 19 tests covering version, help, init, diff, encrypt/decrypt, and sync (#22)
- `--fail-on-missing` flag to `diff` and `diff-files` commands — exit non-zero if keys are missing in target
- GitHub Pages deployment workflow
- `SECURITY.md` with security policy
- `CONTRIBUTING.md` with development setup and PR guidelines
- Homebrew and Scoop install methods
- npm wrapper (`package.json` + `cli.js`) for npm publishing
- Directory listing badges: Open Source Alternative, LibHunt

### Changed

- npm package renamed from `envault-secrets` to `envault`
- npm keywords optimized for discoverability (15 terms)
- Documentation branding updated from DevForge to Revenue Holdings
- README tool count updated (8 → 11)
- Pricing table formatting fixed (leading double-pipe removed from markdown)

### Fixed

- UTF-8 encoding (mojibake) in file output
- pyproject.toml dev dependencies formatting (trailing commas, ruff added)
- `ruff` added to dev dependencies for CI lint step

## v0.1.0

- Initial release
- Diff, sync, and rotate .env variables across environments
- AWS SSM, Vault, Doppler, and 1Password integration
- Moved revenueholdings-license to optional [license] extra
