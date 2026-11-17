"""The only place that talks to an AI model (handbook section 2, ADR-004, ADR-009).

Code decides, AI explains: nothing here sets a status, date, score or priority. Every
call goes through `runner.run`, which hashes and caches the input, parses the output
into a schema, validates it, retries once with the reason, and logs it to `ai_actions`.
"""
