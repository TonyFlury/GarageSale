# Project instructions

## Database

- PostgreSQL is required in every environment, including development and tests.
- Never use SQLite, create SQLite test settings, or fall back to SQLite when PostgreSQL is unavailable.
- Run database tests against a separate PostgreSQL test database, never against application data.
- If PostgreSQL cannot be reached, investigate the connection or report the blocker; do not switch database engines.

## Deployment

- Read and follow `General Deployment Instructions` for changes to this project.
- Commit and push task changes, including templates, static files and migrations where applicable. Preserve unrelated user changes.
