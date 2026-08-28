# Design

The interface decisions, and the reasoning behind them.

---

## 1. Principles

**Show the working.** Every figure is displayed with the SQL that produced it. An officer
who cannot verify a number cannot defend it to a senior, and a tool that cannot be
verified will be used once and abandoned. This is the single decision the rest of the
interface is arranged around.

**Say what is missing.** When the data cannot answer a question, the interface says which
part is missing and what it can answer instead. A blank result or a hedged paragraph
teaches officers to stop asking.

**Operations room, not consumer app.** Dense, dark, information-first. Officers use this
alongside CCTNS at a station desk, often at night. Nothing bounces, nothing celebrates.

**Kannada is an input language, not a locale toggle.** Roughly half the intended users
write Kannada more fluently than English. Kannada input is first-class throughout,
including voice, and the numbers are identical either way.

**Degrade visibly, never silently.** When the model is unavailable, the answer arrives as
a plain table rather than an error. An empty panel is the worst outcome, because it looks
like a real zero.

---

## 2. Information architecture

Nine destinations in two groups. The split reflects two different jobs.

```
WORKSPACE                 things an officer does with a specific case
  Chat & Investigate      ask questions, the default landing view
  Analytics               charts, trends, live crime news
  Browse Records          direct table access for someone who wants the raw rows
  Audit Trail             what was asked, and the SQL that ran

INTELLIGENCE              things the system surfaces without being asked
  Investigate             autonomous agent, give it a goal
  AI Brief                synthesised executive briefing
  Evidence Intel          statement or document against prior records
  Intel Map               district hotspots and the criminal network
  Case Solver             52 solved Indian cases for comparison
```

**Why chat is first.** It is the only view that answers a question the designer did not
anticipate. Everything else is a fixed lens.

**Why the audit trail is a destination, not a settings page.** In a policing tool,
accountability is a feature, not an administrative afterthought.

**Depth is capped at two.** Sidebar to panel. Nothing is three clicks away, because an
officer mid-call will not go looking.

---

## 3. Key interaction states

Every asynchronous surface has four defined states. The failure state is specified, not
left to whatever the browser does.

### Chat

| State | Treatment |
|---|---|
| Empty | Suggested crime-type prompts. A blank box invites nothing |
| Thinking | Typing indicator, stop button available |
| Answered | Answer, database badge, source badge, collapsible SQL |
| Refused | Same layout as an answer. A refusal is a result, not an error |
| Degraded | Result table with a note. Figures intact, prose plain |
| Failed | "Cannot reach server", input stays populated so nothing is retyped |
| Invalid | Inline guidance ("keep it under 2000 characters, use Evidence Intel for a full statement") rather than a raw 422 |

**Refusals are styled as answers on purpose.** Making them look like errors would teach
officers that asking about missing data is a mistake. It is not; it is how you learn what
the system holds.

### Investigation agent

Steps reveal one at a time as they complete, each showing the reasoning, the tool and the
observation, with the brief last. The reveal is not decoration: the point of the feature
is that the system chose its own next step, and a finished block hides that entirely. The
header states `autonomous` or `playbook` honestly, so a rate-limited run is visibly a
fallback rather than quietly presented as reasoning.

### Intel Map

Zoom drives density.

| Zoom | Shown |
|---|---|
| State (7 and below) | 31 district hotspot circles, radius by volume, colour by severity. Hint: "Zoom in to plot individual suspects" |
| District (8 and above) | Individual suspects appear, sized by network connections, coloured by risk |

At state zoom, 131 suspects scattered inside 31 circles collapsed into unreadable blobs.
The fix was not a better basemap, it was showing less. This also matches how an officer
works: state view, then a district.

### Live news

Severity as a coloured left edge, district as a chip, relative age ("8m ago") so
freshness is legible without reading dates. Refresh states its own progress
("Refreshing…", disabled) because a button that silently re-fetches identical data reads
as broken.

### Evidence Intelligence

Matches lead, not the summary. A name with 260 priors is the finding; the prose is
context. A person with no record is shown as *no record*, which is a real result worth
seeing rather than an absence to hide.

---

## 4. Visual system

**Dark, blue-biased neutrals.** `#0a0f1c` ground through `#e8eef8` text. Not pure grey:
a slight blue bias keeps large dark areas from reading as dead, and suits a room where
this sits beside CCTNS at night.

**One accent, semantic colour kept separate.** Blue is interface. Red, orange, amber and
green mean severity and risk *only*, so a red element is always a finding, never a
decoration. Applied consistently across map markers, news stripes, alert badges and risk
chips, which lets colour be scanned rather than read.

**Type.** A single sans family across the interface with a monospace face reserved for
SQL, table output and identifiers. Monospace signals "this is the machine's exact words",
which supports the show-the-working principle. Numerals are tabular anywhere figures
stack in a column.

**Density.** Deliberately tighter than a consumer product. The comparison is a records
system, not a marketing page. Charts are given room; text is not padded.

---

## 5. Responsive behaviour

| Width | Layout |
|---|---|
| 1280 and above | Sidebar plus content. Analytics in two columns |
| 1024 to 1280 | Sidebar persists, analytics collapses to one column |
| 768 to 1024 | Sidebar collapses to icons, charts full width |
| Below 768 | Single column, sidebar behind a toggle, map full width |

The rule throughout: **the page body never scrolls sideways.** Wide content, meaning
tables, SQL blocks, the network graph and charts, scrolls inside its own container.
Horizontal page scroll on a dense data view makes content unreachable rather than merely
awkward.

The map is the one component that reflows rather than scaling. Its controls move to a
stacked row below 768 so they do not cover Karnataka.

---

## 6. Accessibility

**Done**

- Keyboard reachable throughout: navigation, chat, filters, map controls. Visible focus
  states, no keyboard traps.
- Colour is never the only signal. Severity carries a label or a number as well as a hue.
  Risk appears as a text badge, not just a coloured dot.
- Body text meets WCAG AA against the dark ground; muted text is reserved for secondary
  content and is not the only place information appears.
- Reduced motion respected. The step reveal and transitions collapse to instant.
- Semantic HTML with real buttons and links, so activation and focus behave as expected.
- Text scales to 200% without clipping.
- Voice input is an accessibility feature as much as a convenience one: it removes typing
  and removes the Kannada keyboard problem.

**Known gaps, listed honestly**

- The map is visual only. District figures are reachable through Analytics and chat, but
  there is no equivalent keyboard path through the network graph.
- Charts have accessible labels but no data-table alternative.
- Screen-reader passes have been informal. No formal audit has been done.
- New chat messages are not announced through a live region.

None of these are hard to close, and they are listed here rather than quietly omitted.

---

## 7. Design decisions and their reasons

**Single-page application, no framework, no build step.** The entire UI is one HTML file.
It deploys as a static asset inside the same container, has no supply chain, and cannot
break because a build failed. For a prototype that must survive a deploy on judging day,
zero build steps is a feature. The cost is a large file, accepted deliberately.

**SQL shown by default, not hidden behind a toggle.** Hiding it would make verification
opt-in, and nobody opts in. It is collapsible, but present.

**Refusals look like answers.** Covered above. This is the most consequential visual
decision in the product.

**Demo access button.** Judges get full Superintendent access in one click. Requiring an
account before anyone can see the work would lose more than the realism gains.

**Suspects hidden until zoomed in.** Showing everything at once was honest but unreadable.
Density is a design decision, not a data decision.

**Keyless map tiles with automatic fallback.** CARTO began requiring an API key and
stamped "API KEY REQUIRED" across every tile. The replacement is keyless, and falls
through to a second provider after repeated tile failures. Google Maps was considered and
rejected: without a billing-enabled key it stamps "For development purposes only", which
is the same failure with a different logo.

**Live news on Analytics, not its own tab.** It is context for the charts, not a
destination. An officer reads a spike, then sees whether it is already in the press.

**Relative timestamps.** "8m ago" answers the question an officer is actually asking,
which is whether this is current.

**English fallback in Kannada mode is tolerated, for now.** The model sometimes replies
in English when Kannada is selected. The figures are always correct. Given a choice
between a correct number in English and a delayed release, correctness ships first. It is
recorded as a known gap in the PRD rather than hidden.
