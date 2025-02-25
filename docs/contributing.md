# Contributing

Thank you for being interested in contributing to open source software! There are lots of ways to contribute to the project:

- Try it out, and [report any bugs or issues](https://github.com/will-ockmore/httpx-retries) that you find
- [Implement new features](https://github.com/will-ockmore/httpx-retries/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
- Review other contributor's pull requests
- Write documentation
- Participate in discussions

## Development

To set up for development:

1. Fork the repository on GitHub by clicking the "Fork" button on the [project's GitHub page](https://github.com/will-ockmore/httpx-retries)
2. Clone your fork (replace `YOUR-USERNAME` with your GitHub username):
   ```shell
   git clone https://github.com/YOUR-USERNAME/httpx-retries.git
   cd httpx-retries
   ```

3. Add the original repository as a remote to sync latest changes:
   ```shell
   git remote add upstream https://github.com/will-ockmore/httpx-retries.git
   ```

4. Install dependencies:
   ```shell
   uv sync
   ```

## Running Tests

Run the test suite:

```shell
./scripts/test
```

This will run the tests with coverage reporting.

## Code Quality

We use several tools to maintain code quality. Run all checks with:

```shell
./scripts/check
```

This runs:

* [ruff](https://docs.astral.sh/ruff/) - For code formatting and linting
* [mypy](https://mypy.readthedocs.io/en/stable/) - For type checking

## Documentation

Documentation is built using MkDocs. To preview locally:

```shell
mkdocs serve
```

Then visit `http://127.0.0.1:8000` in your browser.

## Pull Requests

To submit changes:

1. Fork the repository
2. Create a new branch for your changes
3. Make your changes
4. Run tests and code quality checks
5. Submit a pull request

We aim to review pull requests promptly and provide constructive feedback if needed.

## Releasing

*This section is for maintainers only.*

To release a new version:

1. Update version in `pyproject.toml` following [Semantic versioning](https://semver.org/spec/v2.0.0.html) (for example: `0.2.4`)
2. Update `CHANGELOG.md`, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
3. Create a new release on GitHub:
   - Tag version like `0.2.4`
   - Title `0.2.4`
   - Description copied from the changelog
4. The GitHub release will automatically trigger a PyPI publish

If the PyPI publish fails, you can manually publish using:
```shell
./scripts/publish
```
