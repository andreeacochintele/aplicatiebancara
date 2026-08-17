# Agent tools (placeholder — Phase 5)

Each tool is a typed Python function an agent can call. A tool's only job is
to call a backend SERVICE and return the result — tools never touch the
database or SQLAlchemy models directly (architecture.md §28, §44):

    Agent -> Tool -> Backend Service -> Database

Not implemented yet.
