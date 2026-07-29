# Scheduler and Application Logs

## Problem Statement

As an operator of Parames, I must currently log into a container or Komodo to inspect scheduler and API logs. I need to see retained scheduler and API application output in the Parames webapp and through its API, including failures and tracebacks, so I can diagnose alert evaluation and delivery problems without container access.

## Solution

Parames will persist selected API and scheduler process output in MongoDB and expose it through a read-only logs API and a dedicated Logs page. The page will support filtering and incremental loading, and will link scheduled and manually triggered evaluation output to the corresponding persisted Run. Log retention is configured in the shared YAML configuration and defaults to 30 days.

## User Stories

1. As a Parames operator, I want to open a dedicated Logs page, so that I can inspect application output without container or Komodo access.
2. As a Parames operator, I want to retrieve logs through the API, so that I can inspect the same operational information programmatically.
3. As a Parames operator, I want to see scheduler lifecycle messages, so that I can confirm the scheduler started and is configured as expected.
4. As a Parames operator, I want to see API process logs, so that I can diagnose failures from manual operations and API requests.
5. As a Parames operator, I want Parames application log records at INFO level and above, so that normal operational activity is visible without excessive dependency noise.
6. As a Parames operator, I want warnings and errors from every Python logger, so that scheduler, framework, and dependency failures are not hidden.
7. As a Parames operator, I want direct stdout output captured, so that console-rendered operational output is available in the webapp.
8. As a Parames operator, I want direct stderr output captured, so that process error output is available in the webapp.
9. As a Parames operator, I want each Python log record stored once, so that duplicate entries do not obscure the event sequence.
10. As a Parames operator, I want Python log entries to preserve their timestamp, service, level, logger name, and complete formatted text, so that I have enough context to diagnose an event.
11. As a Parames operator, I want direct stdout entries classified as INFO and direct stderr entries classified as ERROR, so that severity filtering remains useful for raw process output.
12. As a Parames operator, I want exception tracebacks retained in full, so that I can diagnose failures without accessing the container.
13. As a Parames operator, I want terminal ANSI control codes removed only when displaying logs, so that stored raw output is retained while the webapp remains readable.
14. As a Parames operator, I want stream output stored one line at a time, so that the log list is navigable and ordered like conventional logs.
15. As a Parames operator, I want any partial stream line flushed when a process shuts down, so that relevant final output is not silently lost.
16. As a Parames operator, I want output produced during an evaluation to be associated with its Run, so that I can distinguish one evaluation from another.
17. As a Parames operator, I want to open the Logs page from a Dashboard Run, prefiltered to that Run, so that I can diagnose that execution directly.
18. As a Parames operator, I want to filter the Logs page by service, so that I can focus on API or scheduler activity.
19. As a Parames operator, I want to filter by minimum severity, so that I can focus on warnings and errors when troubleshooting.
20. As a Parames operator, I want to search stored log text, so that I can find a relevant message, exception, alert name, or failure quickly.
21. As a Parames operator, I want the Logs page to load the newest 200 matching entries first, so that recent events are immediately visible.
22. As a Parames operator, I want to load older matching logs incrementally, so that long retention periods do not make the page slow or overwhelming.
23. As a Parames operator, I want the page to detect new matching entries every five seconds without moving the list I am reading, so that I do not lose my place in a traceback.
24. As a Parames operator, I want a visible new-entry action, so that I can choose when to refresh the displayed list.
25. As a Parames operator, I want an optional auto-refresh control, so that I can choose a live-view experience when monitoring a run.
26. As a Parames operator, I want configured secrets and common credential patterns redacted before logs are persisted, so that viewing logs through the existing unauthenticated app does not expose credentials.
27. As a Parames operator, I want logs to remain accessible under the same network access model as the current webapp and API, so that no separate authentication flow is required.
28. As a Parames operator, I want log retention to default to 30 days and be configurable in YAML, so that storage duration can match my operational needs.
29. As a Parames operator, I want expired logs removed automatically, so that log storage does not grow indefinitely.
30. As a Parames operator, I want logs to be read-only in the API and webapp, so that retention is controlled consistently and accidental deletion is avoided.
31. As a Parames operator, I want API and scheduler operation to continue if MongoDB cannot accept log entries, so that observability failure does not stop alert evaluation or delivery.
32. As a Parames operator, I want normal container output to continue if log persistence is unavailable, so that container-level diagnosis remains possible as a fallback.
33. As a Parames operator, I want an output item that cannot fit in MongoDB to be dropped rather than truncated or split, so that persisted entries are never misleading partial representations.

## Implementation Decisions

- Add a persisted log-entry model and repository operations for recording and querying entries. Each entry includes its occurrence time, originating service (`api` or `scheduler`), severity, optional logger name, source type, full text, and optional Run identifier.
- Add MongoDB indexes that support newest-first log retrieval, filters, and automatic retention expiration. Retention is governed by a `logging.retention_days` setting in the shared YAML configuration, with a default of 30 days.
- Install process-local logging and stream-capture infrastructure in both long-running application services. It persists Parames logger records at INFO and above, records all logger warnings and errors, and captures non-logging stdout and stderr content.
- Avoid duplicate entries by persisting Python log records through the logging integration and capturing only stream content that did not originate from Python logging.
- Preserve complete formatted exception text, including multi-line tracebacks. Store stream output one newline-delimited line at a time and flush a final partial line during orderly shutdown.
- Store raw text before display transformation. The webapp removes ANSI control sequences only at rendering time.
- Apply redaction before persistence. Redaction covers configured Telegram secrets, MongoDB URI credentials, and common authorization, token, password, and API-key patterns.
- Use Run-scoped context while an evaluation executes so log records generated during both scheduler-triggered and API-triggered runs can reference the persisted Run. Scheduler lifecycle output that occurs outside a Run remains unlinked.
- When persistence fails, the logging integration must fail open: it must not terminate or block API, scheduler, evaluation, or delivery behavior, and it must leave ordinary container output available.
- Do not truncate or chunk an output item that exceeds MongoDB's document limit; drop that item instead.
- Add a read-only logs API contract with cursor-safe newest-first pagination and optional service, minimum-severity, text-search, and Run filters. The default page size is 200 entries.
- Add a Logs navigation destination and a dedicated Logs view. It displays text in a readable monospaced form, exposes the agreed filters, supports Load more, offers manual refresh, polls every five seconds for new matching entries, and provides an optional auto-refresh mode.
- Make Dashboard Run rows navigate to the Logs view with that Run preselected.
- No manual log-deletion API or webapp control will be provided.
- The implementation covers only Parames API and scheduler processes. It does not read Docker, Komodo, MongoDB, or other container logs.

## Testing Decisions

- Prefer high-level behavior tests at the persisted-log repository and logs API seam: write representative entries, query them through the public contract, and assert ordering, filters, pagination, redaction, Run association, and expiry configuration behavior rather than handler internals.
- Test logging integration with controlled logger records, stdout, stderr, and exceptions. Assert that selected records are persisted once, stdout and stderr receive their agreed severities, tracebacks are retained, and ANSI text remains stored while presentation is plain.
- Test failure isolation by making log persistence fail and asserting that the originating application behavior and normal stream output continue.
- Test the Logs page with browser automation against the API: initial newest entries, filter application, Load more, new-entry notification, optional auto-refresh, and Dashboard Run navigation.
- Follow the project’s existing pytest unit-test style for configuration, persistence, delivery, and evaluation behavior. Add API-level tests alongside the existing router behavior, and use the project’s Playwright workflow for the webapp behavior.
- Tests must run local commands with `PARAMES_DEV_MODE=true`; browser tests use the local API on port 7000.

## Out of Scope

- Reading Docker daemon, Komodo, MongoDB, or other infrastructure-container stdout/stderr.
- Adding authentication or authorization specifically for logs.
- Manual clearing or deletion of logs.
- Persisting logs indefinitely.
- Persisting an individual output item that exceeds MongoDB's document-size limit.
- Replacing the existing container log tooling or providing a general-purpose log aggregation platform.
- Changing alert evaluation, detection, delivery, or scheduler timing behavior except for associating their output with a Run.

## Further Notes

- The existing webapp/API access model is unchanged. Stored text must therefore be redacted before it is made queryable or displayable.
- The existing Run records already provide the operational unit needed to connect evaluation output from both the scheduler and the Dashboard's manual Run action.
- No domain glossary or ADR currently applies to this operational observability feature. An ADR is not proposed because this is a reversible implementation choice within the current MongoDB-backed application architecture.
