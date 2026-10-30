# Contributing to Resonance

Thanks for helping improve Resonance. The project is a learning-oriented,
self-hosted semantic music discovery tool. Contributions to chunking, embeddings,
retrieval quality, Navidrome integration, and operator experience are welcome.

## Before changing code

- Read the [root README](README.md) for the current product and learning overview.
- Read [AGENTS.md](AGENTS.md) for architecture, data boundaries, and code conventions.
- Check the [roadmap](docs/roadmap.md), current PRDs, and source before relying on an
  older plan. Historical docs describe earlier directions too.
- For larger behavior changes, update or propose a PRD/plan so the product intent is
  reviewable before implementation.

## Local setup

Requirements: Python 3.14+, `uv`, Node.js with pnpm 9.15.4, and Docker Compose for
integration with Navidrome/Qdrant/TEI.

```bash
make install
pnpm --dir vue-ui install
make run
make ui
```

Useful checks:

```bash
make lint
uv run ty check src/
make test
```

Tests should use synthetic lyrics and mocked external services. Do not make tests
depend on a maintainer's Navidrome server, library, model endpoint, or credentials.

## Design and review

- Keep application policy in `src/resonance/application/`; CLI and FastAPI modules
  should remain adapters.
- Preserve Navidrome song IDs and per-user library authorization. Do not introduce
  filesystem identity or assume access to the audio files.
- Be explicit about whether a change affects chunking, embedding profiles, collection
  compatibility, or search ranking. These choices affect whether indexed vectors can
  be compared and reused.
- Treat playlist creation as a write with an uncertain-outcome recovery path. Never
  retry an unknown result with a new operation ID without first checking Navidrome.
- Avoid logging credentials, tokens, complete lyric text, or private library data.
- Do not commit `.env`, `data/`, model caches, SQLite journals, generated frontend
  output, or real-library fixtures. Use synthetic/original content or material with
  clear redistribution permission.
- Update operator docs when commands, defaults, network exposure, data paths, or
  support claims change.

Use conventional commit prefixes where practical: `feat:`, `fix:`, `docs:`,
`refactor:`, `test:`, or `chore:`. Pull requests should explain the user-facing
behavior, important tradeoffs, how it was checked, and any migration or data impact.

## License

The project uses AGPL-3.0-only; see the repository's [`LICENSE`](LICENSE) file. The
package metadata declares the same identifier. Contributions are intended to be
distributed under that project license; contributors should submit only work they have
the right to contribute. There is currently no separate CLA or DCO process.

AGPL-3.0 section 13 has source-offer requirements for modified versions that let
users interact with them remotely over a network. See the
[GNU AGPLv3 text](https://www.gnu.org/licenses/agpl-3.0.en.html). This project license
does not grant rights to redistribute a user's music or lyrics.

## Reporting security issues

Do not include credentials, tokens, private lyrics, or personal library data in public
issues. Until a dedicated private security contact is published, use GitHub's private
vulnerability reporting feature for the repository if it is enabled; otherwise contact
the maintainer through a private channel before sharing exploit details publicly.
