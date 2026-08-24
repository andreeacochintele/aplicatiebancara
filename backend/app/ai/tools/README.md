# Agent tools

Each tool is a typed Python function an agent can call. A tool's only job is
to call a backend SERVICE and return the result — tools never touch the
database or SQLAlchemy models directly (architecture.md §28, §44):

    Agent -> Tool -> Backend Service -> Database

`base.py` defines the shared contract: `ToolContext` (user_id + db session,
passed into every tool) and `ToolDataUnavailableError` (raised instead of
inventing a figure when the service layer doesn't expose something yet).

Tools are colocated per-agent (e.g. `ai/personal_finance/tools.py`) rather
than in this folder, since each agent's tool set wraps that agent's own
backend modules — `base.py` here is the only piece actually shared.
