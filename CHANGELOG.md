# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.2] - 2025-04-20

### Added
- Debug logging is now emitted for core functions
- Documentation updated to include guides to retry behaviour & logging

### Fixed
- When `Retry-After` is in the past, the default backoff is now used

## [0.3.1] - 2025-03-30

### Fixed
- Included missing HTTP verbs PATCH and CONNECT in the backwards-compatible HTTPMethod enum

## [0.3.0] - 2025-02-27

### Added
- Added a new parameter and behaviour for the Retry class to retry on a specified set of httpx exceptions.

## [0.2.4] - 2025-02-25

### Added
- Add contributor's guide and changelog

## [0.2.3] - 2025-01-27

### Fixed
- Add missing `py.typed` marker

## [0.2.2] - 2025-01-26

### Changed
- Improve documentation
- Include details about custom transport usage

## [0.2.1] - 2025-01-26

### Changed
- Tidy docs and correct CI workflows

## [0.2.0] - 2025-01-26

### Added
- Initial release

[Unreleased]: https://github.com/will-ockmore/httpx-retries/compare/0.3.0...HEAD
[0.3.0]: https://github.com/will-ockmore/httpx-retries/releases/tag/0.3.0
[0.2.4]: https://github.com/will-ockmore/httpx-retries/releases/tag/0.2.4
[0.2.3]: https://github.com/will-ockmore/httpx-retries/releases/tag/0.2.3
[0.2.2]: https://github.com/will-ockmore/httpx-retries/releases/tag/0.2.2
[0.2.1]: https://github.com/will-ockmore/httpx-retries/releases/tag/0.2.1
[0.2.0]: https://github.com/will-ockmore/httpx-retries/releases/tag/0.2.0
