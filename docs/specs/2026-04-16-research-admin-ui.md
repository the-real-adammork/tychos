# Research Admin UI

## Summary

Add React pages to the existing admin SPA for managing autonomous research jobs. A list page shows all jobs with status, budget progress, and best objective. A detail page renders a unified timeline of agent messages, param diffs, run cards, Nelder-Mead search results, checkpoints, and user messages — all streamed live via SSE. Users can start/pause/resume jobs and inject guidance messages from the same page.

## Goals

- Research Jobs list with status, model, iterations, best objective, last activity
- Create Job modal with dropdowns for param set, dataset, view, allowlist, model, budgets
- Job Detail page: collapsible objective-over-time chart + unified chronological timeline + message input
- Live streaming via existing `GET /api/research/{id}/logs/stream` SSE endpoint
- Run cards clickable through to existing run detail pages
- Start/pause/resume controls on the detail page

## Non-Goals

- New backend endpoints (all exist from Phase 2 daemon)
- WebSocket streaming (SSE is sufficient for Phase 2)
- Editing job config after creation (can add later)

---

## Pages

### Research Jobs List (`/research`)

Table columns:
| Column | Source |
|---|---|
| Name | `research_jobs.name` |
| Status | `research_jobs.status` — badge: green=active, yellow=paused, gray=pending, blue=completed |
| Model | `research_jobs.model` — display short name (sonnet-4.6 / opus-4.6) |
| View | `research_jobs.view_name` |
| Iterations | `current_iteration / max_iterations` |
| Best Objective | lowest `objective` from `research_iterations` for this job |
| Last Activity | most recent `research_logs.created_at` or `research_jobs.updated_at` |

Row click → navigate to `/research/{id}`.

Action buttons per row (conditional on status):
- Pending → "Start" button
- Active → "Pause" button
- Paused → "Resume" button
- Completed → no action

"New Research Job" button top-right → opens create modal.

Data source: `GET /api/research` (list) + `GET /api/research/{id}/iterations` (for best objective — or add to list response server-side if needed).

### Create Job Modal

Fields:
- **Name** — text input
- **Param Set** — dropdown populated from `GET /api/params`
- **Dataset** — dropdown populated from `GET /api/datasets`
- **View** — dropdown: v_solar_position, v_moon_position, v_combined_position
- **Allowlist** — text input (comma-separated globs, e.g. "sun.*, sun_def.*")
- **Date Start / Date End** — optional text inputs (ISO dates)
- **Model** — dropdown: claude-sonnet-4-6 (default), claude-opus-4-6
- **Max Iterations** — number input, default 40
- **Wall Clock (seconds)** — number input, default 3600
- **No-Improvement Plateau** — number input, default 6

Submit → `POST /api/research` → close modal, refresh list.

Uses shadcn Dialog + form components.

### Job Detail (`/research/{id}`)

#### Header

Job name, status badge, model, view, date range, allowlist (displayed as tags).

Controls: Start / Pause / Resume button (conditional on status).

#### Objective Chart (collapsible)

Small line chart (recharts `LineChart`) at the top of the page.
- X-axis: iteration number (from `research_iterations` rows)
- Y-axis: objective value (arcmin)
- Checkpoint markers: filled dots on the line at checkpoint iterations
- Search winners: star markers

Collapsed by default if no iterations yet; auto-expands on first data point. Collapsible via a toggle.

Data source: `GET /api/research/{id}/iterations`

#### Unified Timeline

A vertical feed of all events in chronological order. Built from `GET /api/research/{id}/logs` (initial load) + `GET /api/research/{id}/logs/stream` (SSE for live updates).

**Event types and their rendering:**

1. **Agent message** (`role='assistant'`, no `tool_name`)
   - Purple avatar "AI", left-aligned
   - Markdown-rendered content in a dark card

2. **`propose_params` tool call** (`role='tool_call'`, `tool_name='propose_params'`)
   - Purple avatar, left-aligned
   - Header: "🔧 propose_params"
   - Inline param diff: parse `input.params_json`, diff against previous version, show red/green lines
   - Followed by the tool_result's run card (next log entry)

3. **`propose_params` result** (`role='tool_result'`, `tool_name='propose_params'`)
   - Rendered as a run card: status dot, run ID (clickable → `/runs/{id}/results`), eclipse count, timing, objective with ↓/↑ indicator
   - Attached below the corresponding tool_call (not a separate bubble)

4. **`search` tool call** (`role='tool_call'`, `tool_name='search'`)
   - Purple avatar with "🔍 search" header
   - Shows: param_keys, budget, scale

5. **`search` result** (`role='tool_result'`, `tool_name='search'`)
   - Expanded card: start objective → best objective, Δ, eval count, timing
   - If improved: winner param diff (red/green) + winner run card (clickable)
   - Attached below the search tool_call

6. **`checkpoint`** (`role='tool_call'` or `role='tool_result'`, `tool_name='checkpoint'`)
   - Green horizontal divider line with "✓ Checkpoint v{N} — obj: {value}"

7. **`restore`** (`role='tool_result'`, `tool_name='restore'`)
   - Yellow horizontal divider: "↩ Restored from v{N}"

8. **User message** (`role='user_inject'`)
   - Blue avatar "U", right-aligned
   - Content in a blue-tinted card

9. **System message** (`role='system'`)
   - Centered, muted text (session start, budget exhaustion, errors)

**Live streaming:** On mount, fetch all existing logs via `GET /api/research/{id}/logs`. Then open an EventSource to `GET /api/research/{id}/logs/stream`. On each SSE `log` event, append the new log entry to the timeline and auto-scroll to bottom.

#### Message Input

Fixed at the bottom of the timeline. Text input + Send button. Submit → `POST /api/research/{id}/message`. Disabled when job status is not 'active'.

---

## Component Structure

```
admin/src/
  pages/
    ResearchPage.tsx              — list page
    ResearchJobDetailPage.tsx     — detail page (chart + timeline + input)
  components/
    research/
      create-job-modal.tsx        — create form in a Dialog
      objective-chart.tsx         — recharts LineChart wrapper
      timeline.tsx                — timeline container (fetches logs, manages SSE, renders events)
      param-diff.tsx              — red/green inline param diff renderer
      run-card.tsx                — compact run status card (clickable)
      search-result-card.tsx      — expanded search outcome card
```

## Data Flow

```
ResearchPage
  → GET /api/research → table rows
  → Create modal → POST /api/research → refresh

ResearchJobDetailPage
  → GET /api/research/{id} → header + controls
  → GET /api/research/{id}/iterations → objective chart data
  → timeline.tsx:
    → GET /api/research/{id}/logs → initial log entries
    → EventSource /api/research/{id}/logs/stream → append new entries
  → Message input → POST /api/research/{id}/message
  → Start/Pause/Resume → POST /api/research/{id}/{action} → refresh header
```

## Routing

Add to `App.tsx`:
```
/research           → ResearchPage
/research/:id       → ResearchJobDetailPage
```

Add to sidebar: "Research" nav item with `FlaskConical` (or `Brain`) lucide icon, between "Runs" and "Datasets".

## Dependencies

- `recharts` — add to `admin/package.json`
- No new backend work

## Param Diff Logic

To render inline param diffs, the timeline component needs to compare the proposed `params_json` against the previous version. Two approaches:

1. **Client-side diff:** Parse `params_json` from the tool_call input, fetch the previous version's params via `GET /api/params/{set_id}/versions/{prev_id}`, diff the two dicts. Requires knowing the previous version ID.

2. **Embed diff in tool_result:** The `propose_params` tool result already contains `version_id`. The client can fetch both the new version and its parent to compute the diff.

Approach #2 is simpler — the tool_result has `version_id`, the version has `parent_version_id`, and the client fetches both params_json to diff. Cache aggressively since params are immutable.

## Testing Strategy

- **Component tests:** Each event renderer gets a unit test with mock data (agent-message, run-card, search-result, checkpoint, param-diff)
- **Timeline integration:** Mock SSE stream, verify events render in order, auto-scroll works
- **Create modal:** Verify form validation, submit calls API, modal closes
- **List page:** Verify table renders, status badges correct, row click navigates
- **E2E (manual):** Start a real research job, watch the timeline update live via SSE
