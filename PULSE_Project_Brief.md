# PULSE — The Match Has a Memory
## Hackathon Project Brief and Development Roadmap

**Working name:** PULSE  
**Tagline:** Discover the story behind the score.  
**Project type:** AI-powered football analytics and storytelling platform  
**Primary input:** Synthetic football match-event data  
**Primary output:** Real-time, evidence-backed match insights and personalized narratives

---

## 1. Project Overview

PULSE is an AI-powered football intelligence platform that identifies meaningful changes during a match, explains the event sequences behind pivotal moments, and presents insights in ways suited to different audiences.

Traditional match dashboards show statistics such as possession, shots, and passing accuracy. PULSE aims to connect those statistics over time and explain what they may mean. For example, instead of only reporting a goal, PULSE could identify an earlier increase in pressing, repeated midfield turnovers, and a breakdown in the opposing team's buildup.

The system must distinguish **observed facts**, **statistical interpretations**, and **hypothetical scenarios**. AI-generated explanations should be grounded in event data and must not invent statistics or present correlation as proven causation.

### Core value proposition

- **Detect:** Identify meaningful tactical and statistical changes.
- **Explain:** Connect insights to timestamped evidence from the match.
- **Personalize:** Explain the same event differently for casual fans, analysts, and broadcasters.
- **Explore:** Let users rewind a match timeline and investigate how a key moment developed.

---

## 2. Objectives

### Primary objectives

1. Build a working prototype that consumes a stream of synthetic football events.
2. Maintain an up-to-date match state and calculate core football statistics.
3. Detect potentially important patterns, such as rising pressure, repeated turnovers, and changes in attacking threat.
4. Generate concise narratives that cite the underlying events and metrics.
5. Provide multiple commentary styles for different user profiles.
6. Visualize the match through a timeline, momentum chart, and tactical-pitch view.
7. Estimate plausible coach/team tactics for an upcoming matchup using historical tendencies and comparable reference matches, when sufficient evidence is available.
8. Demonstrate reliable AI behavior through evidence validation, confidence labels, and graceful fallbacks.

### Secondary objectives

- Support English commentary in the initial version.
- Allow users to rewind to earlier match states and inspect the evidence for an insight.
- Produce an end-of-match summary that highlights turning points.
- Explore counterfactual scenarios, clearly labeled as hypothetical.
- Keep the architecture modular enough to support future real event feeds or richer tracking data.

### Success criteria

The prototype should be considered successful when it can:

- Replay a complete scripted match from start to finish.
- Update statistics as events arrive.
- Detect at least one deliberately scripted tactical shift.
- Generate an insight that links to specific supporting events.
- Show different versions of an insight for at least two audience profiles.
- Reject or flag a narrative containing a statistic that does not match the source data.
- Continue showing deterministic statistics if an AI call fails.
- For the tactical tendency feature, show evidence-backed scenarios or explicitly report insufficient evidence.
- Run reliably during a short live demonstration.

---

## 3. Target Users

### Casual football fans
Want to understand why a goal, substitution, or change in momentum matters without needing advanced tactical knowledge.

### Tactical analysts and serious fans
Want detailed evidence about pressing, passing patterns, turnovers, territory, and changes across match phases.

### Broadcasters and content creators
Want concise, compelling, fact-checked observations that can enrich live commentary, clips, and post-match content.

### Coaches and players (future audience)
Could use structured event summaries to review patterns and decisions. The prototype should not claim professional-grade scouting accuracy.

---

## 4. Core Features

### Feature A — Live Match Event Simulator

**Priority:** P0 — Required

Generate realistic, timestamped synthetic events such as:

- Pass attempted and completed
- Ball recovery and turnover
- Shot and shot outcome
- Tackle or interception
- Carry or progressive movement
- Possession change
- Pressure event
- Foul, corner, or substitution (optional)

Each event should include only fields appropriate to its type. A useful common event structure is:

- `event_id`
- `match_id`
- `timestamp_seconds`
- `team_id`
- `player_id` (optional)
- `event_type`
- `start_x`, `start_y` (optional)
- `end_x`, `end_y` (optional)
- `outcome` (optional)
- `metadata` (optional)

Coordinates should use a consistent pitch coordinate system, for example 0–100 in both directions. The simulator should support both randomly generated sequences and carefully scripted scenarios that make a meaningful demo repeatable.

**Acceptance criteria**
- Events are ordered by match time.
- Event IDs are unique.
- Invalid event types and impossible field combinations are rejected.
- A demo match can be replayed deterministically using a fixed random seed or scripted input.

### Feature B — Live Statistics Engine

**Priority:** P0 — Required

Calculate metrics from events rather than asking an LLM to calculate them.

Initial metrics:
- Possession share, with the estimation method documented
- Pass completion rate
- Turnovers by team and field zone
- Shots and shots on target
- Attacks or entries into a defined dangerous zone
- Rolling-window pressure indicators
- Momentum indicator based on explicitly defined weighted features

**Acceptance criteria**
- Every displayed metric has a documented formula.
- Values update when new events arrive.
- The UI can show the time window and definition used.
- Unknown or missing data is displayed as unavailable rather than fabricated.

**Important caveat:** Synthetic event streams may not contain enough information to calculate official possession, expected goals (xG), or true pressure metrics. Label approximations clearly and only implement advanced metrics when their required inputs exist.

### Feature C — Momentum and Tactical Shift Detection

**Priority:** P0 — Required

Detect meaningful changes over rolling time windows, rather than treating every event as noteworthy.

Potential signals:
- Increase in turnovers under pressure
- Decline in pass completion
- Increase in dangerous entries or shots
- Change in territory or field position
- Repeated loss of possession in a specific zone

A simple, explainable rules-based detector is suitable for the first version. More advanced statistical models can be added after the baseline works.

Each alert should include:
- A short title
- Match timestamp
- Direction of change
- Metrics and time windows used
- Supporting event IDs
- Confidence or evidence-strength label
- A note when the sample size is too small

**Acceptance criteria**
- The scripted demo triggers at least one intended alert.
- The system avoids alerts based on a single weak signal when possible.
- Alerts are deduplicated or updated instead of repeatedly spamming the user.

### Feature D — Butterfly Effect: Turning-Point Explorer

**Priority:** P0/P1 — Core differentiator

Let users inspect the sequence of events before a goal, major chance, or tactical shift.

Example:
1. The opposing team increases its pressing intensity.
2. The buildup team loses possession in midfield.
3. Similar turnovers recur.
4. The opposing team enters a dangerous area.
5. A shot or goal follows.

The product should describe this as an evidence-backed sequence or plausible contributing pattern—not definitive causation unless the evidence supports that claim.

UI elements:
- Rewindable event timeline
- Key-moment marker
- Linked supporting events
- Relevant metric changes before and after the moment
- “Why this matters” explanation

**Acceptance criteria**
- Every turning-point explanation links to events that actually exist in the match data.
- Users can click an evidence item and jump to its timestamp.
- The UI distinguishes observed sequence from inferred interpretation.

### Feature E — Parallel Commentary / Fan Modes

**Priority:** P0 — Required for personalization

Generate multiple explanations from the same verified match facts.

**Casual Fan**
- Plain language
- Short explanations
- Minimal jargon
- Focus on why the moment matters

**Tactical Analyst**
- More detailed metrics
- Tactical terminology
- Explicit time windows and comparisons
- Links to supporting events

**Broadcaster** (stretch)
- Concise, natural, on-air-friendly wording
- Avoid unsupported predictions
- Appropriate length for a live overlay

**Language support**
- English for the initial version

**Acceptance criteria**
- Changing audience mode changes the explanation, not the underlying facts.
- All modes use the same validated metrics and evidence.
- Translation must preserve numbers, names, and uncertainty labels.

### Feature F — Evidence Validator

**Priority:** P0 — Required for trustworthiness

Validate AI-generated narratives against structured match data before showing them.

Checks should include:
- Every referenced event ID exists.
- Every numerical claim matches the computed statistics.
- The cited time window matches the data queried.
- Unsupported claims are removed, rewritten, or flagged.
- Hypothetical scenarios are labeled as hypothetical.
- The system does not state that one event caused another solely because it happened earlier.

Use structured output for AI responses, for example:
- `headline`
- `summary`
- `event_ids`
- `metric_claims`
- `interpretation`
- `confidence`
- `is_hypothetical`

**Fallback:** If validation fails or the model is unavailable, show a deterministic insight based on the statistics engine.

### Feature G — Opponent & Coach Tactical Tendencies

**Priority:** P1 — High-value differentiator; build a rules-based baseline before adding complex prediction models.

Estimate the tactical approach a coach or team is likely to use against a specific opponent by analyzing historical match data, recurring team behaviors, coach preferences, and how comparable opponents have approached that matchup.

This feature should answer questions such as:
- How might this team build up against an opponent that presses high?
- Is this coach more likely to use a high press, mid-block, or low block against a stronger possession team?
- Which pressing triggers, defensive shapes, buildup patterns, or transition approaches recur under this coach?
- How has the coach adapted against teams with similar formations, strengths, or playing styles?
- Which reference teams have used similar tactical approaches against this opponent, and what happened?
- What tactical alternatives are plausible if the opponent changes its setup?

#### Inputs and evidence

Use available, permitted historical data, with the source and coverage documented:
- Match event data and, when available, player-tracking or positional data
- Team formations and observed in-possession / out-of-possession shapes
- Pressing intensity and pressing triggers, where measurable
- Defensive block height, line behavior, compactness, and transition patterns, where measurable
- Build-up routes, progression through zones, directness, and wide/central tendencies
- Opponent strength and style, match venue, score state, and competition context
- Coach tenure and the number of relevant matches managed
- Lineup availability or substitutions only when reliable data is available
- Historical matches against the same opponent
- Matches against opponents with comparable tactical profiles

Do not infer a coach's intentions from a single match or assume that past behavior guarantees future behavior. Separate the coach's broader tendencies from the team's current behavior and account for changes in personnel, formations, and coaching staff.

#### Analysis approach

1. **Create tactical fingerprints.** Summarize a team or coach using measurable features such as press height, defensive block, buildup directness, transition speed, preferred progression zones, and formation changes.
2. **Find relevant historical matches.** Weight matches by recency, coaching continuity, tactical similarity, opponent similarity, and available lineup/context data.
3. **Retrieve reference matches.** Identify matches in which the target opponent faced a team with a comparable style. Explain why each reference is relevant rather than treating the comparison as proof.
4. **Estimate tactical scenarios.** Rank a small set of plausible approaches, such as high press, mid-block, low block, direct buildup, or patient possession. Provide confidence or evidence-strength labels and show the supporting matches/features.
5. **Explain likely adaptations.** Identify what the coach may change in response to the opponent, and which observations support that hypothesis.
6. **Update during the match.** Compare observed events with the pre-match hypotheses and report whether the team appears to follow, modify, or abandon the expected approach.

Start with interpretable similarity scoring and historical frequency estimates. Only use a trained predictive model if there is sufficient labeled data and a meaningful evaluation set. An LLM can explain the findings, but should not independently invent probabilities or tactical facts.

#### Example output

**Matchup:** Team A vs Team B  
**Scenario 1 — Mid-block with fast transitions**  
- Evidence: In relevant historical matches, Team A often defended in a mid-block against possession-oriented opponents and attacked quickly after recoveries.
- Reference matches: Show the closest historical examples, dates, and similarity reasons.
- Potential advantage: Could reduce space behind the midfield while leaving opportunities to counter.
- Risk: Team B may dominate territory if Team A cannot progress after recovering the ball.
- Confidence: Moderate, based on the amount and relevance of available historical evidence.

**Scenario 2 — Aggressive high press**  
- Evidence: Team A has used a higher press in some recent matches, but the pattern is less consistent against opponents with strong press-resistant buildup.
- What to watch: Pressing height, pressure events near the opponent's buildup line, and turnovers in the first two thirds.

The system should avoid unsupported statements such as “the coach will definitely use a 4-3-3.” Prefer: “A 4-3-3 is one plausible setup; the recent evidence is limited, and formation alone does not determine the pressing or defensive behavior.”

#### UI elements
- Coach/team tactical fingerprint
- Ranked tactical scenarios with evidence-strength labels
- Historical reference-match cards
- “Why this comparison?” explanation
- Tactical matchup comparison: strengths, vulnerabilities, and potential adjustments
- Pre-match expectations versus live observed behavior
- A clear distinction between historical facts, model estimates, and analyst-style hypotheses

#### Acceptance criteria
- Every prediction links to relevant historical matches or measurable features.
- The interface displays the size and recency of the evidence sample.
- The system can return “insufficient evidence” instead of forcing a prediction.
- Similar-team references include a reason for similarity and relevant context.
- Predictions are evaluated on held-out historical matches where possible.
- The UI uses calibrated uncertainty and does not present scenarios as certainties.
- During a live match, observed behavior can be compared with the pre-match estimate.

**Data limitation:** Detailed pressing patterns and defensive shapes often require event or tracking data that may not be present in basic synthetic event feeds. For the hackathon prototype, implement a small synthetic historical-match library with labeled tactical profiles and known outcomes. Clearly mark it as simulated data. Keep the feature modular so real, licensed historical data can replace it later.

### Feature H — End-of-Match Story

**Priority:** P1 — Important extension

Generate a match recap based on the event timeline:
- Three to five key moments
- Major statistical changes
- Turning points
- Team-specific summaries
- A short casual recap and a deeper tactical recap

The recap should only use validated events and metrics. It should not fabricate quotes, injuries, player emotions, or off-field context.

---

## 5. Stretch Features and Future Improvements

These should only be attempted after all P0 features work reliably.

### Stretch 1 — Counterfactual Match Lab
Let users ask questions such as, “What if Team A had played a longer pass instead of building through the middle?”

The system can run a simplified scenario model and compare hypothetical outcomes with the observed sequence.

Requirements:
- Clearly label results as simulations, not facts or predictions.
- Explain assumptions.
- Avoid presenting one simulated outcome as certain.
- Keep the initial model small and interpretable.

### Stretch 2 — Interactive Tactical Pitch
Display player and event coordinates, passing lanes, turnover zones, and attacking directions. Start with event markers and simple arrows before attempting animated player tracking.

### Stretch 3 — Personalized Match Briefing
Let users select a team or player of interest and prioritize relevant events without changing the underlying facts.

### Stretch 4 — Adaptive Insight Timing
Adjust how often insights appear based on match activity and importance, reducing repetitive or low-value notifications.

### Stretch 5 — Confidence Calibration
Compare detected patterns with scripted ground truth across multiple synthetic matches. Track false positives and missed events.

### Stretch 6 — Real Data Integration
If permitted by the competition and data licenses, replace or supplement synthetic data with a legitimate event feed. Keep the simulator as a reliable demo and test fixture.

### Stretch 7 — Accessibility and Export
Add keyboard navigation, readable contrast, mobile-friendly layouts, and exportable match reports.

---

## 6. Technical Architecture

A modular architecture keeps the prototype testable and makes it possible to replace components later.

1. **Synthetic Event Generator**
   - Produces normal play and scripted tactical scenarios.
   - Supports deterministic replay.

2. **Event Ingestion Layer**
   - Validates schema and ordering.
   - Handles duplicate events and malformed records.
   - Publishes valid events to the match state.

3. **Match State and Statistics Engine**
   - Maintains current score, team statistics, event history, and rolling windows.
   - Uses deterministic code for numerical calculations.

4. **Pattern Detection Engine**
   - Detects threshold changes, repeated patterns, and potential turning points.
   - Returns structured evidence rather than free-form prose.

5. **AI Narrative Layer**
   - Interprets the verified evidence.
   - Produces audience-specific narratives.
   - Uses structured responses and explicit uncertainty.

6. **Evidence Validation Layer**
   - Checks all references and numerical claims.
   - Rejects unsupported output and triggers fallbacks.

7. **Frontend**
   - Match status and score
   - Live event feed
   - Momentum chart
   - Tactical pitch
   - Insight cards and evidence drill-down
   - Audience and language controls
   - Match rewind and recap

8. **Storage and Observability**
   - Store events and derived metrics as needed.
   - Log latency, errors, validation failures, and model usage.
   - Avoid storing unnecessary personal information.

### Suggested technology options

Choose tools based on hackathon requirements, available credits, and the team's familiarity.

- **Frontend:** React with TypeScript
- **Charts:** Recharts or another lightweight charting library
- **Backend:** Python with FastAPI, or a TypeScript backend
- **Data validation:** Pydantic (Python) or Zod (TypeScript)
- **Storage:** SQLite for a simple local prototype; a managed database if needed
- **Streaming:** Start with a timed replay or WebSocket. Add Azure Event Hubs only if the project benefits from a real event-stream service.
- **AI orchestration:** Microsoft Foundry and/or Microsoft Agent Framework, if appropriate to the current competition requirements
- **Development assistance:** GitHub Copilot
- **Deployment:** A small Azure-hosted service if available and appropriate

Do not add every cloud service just to make the architecture look complex. A working, measurable system is better than an unfinished distributed system.

---

## 7. Agent Responsibilities

Agents should have distinct roles and share structured evidence. Avoid building several agents that all perform the same summarization task.

### Pattern Analyst
**Input:** Recent events and computed metrics  
**Output:** Candidate patterns, metric deltas, time windows, evidence IDs

### Turning-Point Analyst
**Input:** Important event plus surrounding timeline  
**Output:** Candidate contributing sequences, alternative explanations, evidence IDs

### Storyteller
**Input:** Validated pattern and selected audience/language  
**Output:** Concise, audience-appropriate narrative

### Evidence Validator
**Input:** Proposed narrative and authoritative match data  
**Output:** Pass/fail, invalid claims, corrected or fallback response

**Orchestration rule:** Use ordinary code for deterministic calculations and checks. Invoke AI only when interpretation or natural-language generation adds value. If multi-agent orchestration is too expensive or slow, preserve the same roles as modular functions and add agent handoffs later.

---

## 8. Data Design and Ground Truth

A synthetic dataset should be football-realistic enough to demonstrate the system's capabilities.

### Required scenarios

1. **Balanced match:** Both teams create chances; no major tactical shift.
2. **High-press turning point:** One team increases pressure, the opponent repeatedly loses possession, and a dangerous attack follows.
3. **False alarm scenario:** A short burst of events looks important but does not lead to sustained pressure.
4. **Comeback scenario:** A trailing team changes its approach and generates more attacking activity.
5. **Low-event period:** Few meaningful events occur, so the system should avoid filling the screen with weak insights.

### Ground-truth labels

For scripted scenarios, record the intended:
- Tactical shift start time
- Relevant team
- Key supporting events
- Expected alert
- Major event or outcome
- Known limitations of the scenario

Use these labels to test whether the detector finds the intended pattern and whether it raises too many false alerts.

---

## 9. Evaluation and Quality Metrics

Evaluate the product on correctness, usefulness, and responsiveness.

### Analytics quality
- Accuracy of calculated metrics against test fixtures
- Percentage of scripted turning points detected
- False-alert rate
- Event processing success rate

### Narrative quality
- Percentage of claims passing validation
- Percentage of narratives with valid supporting event IDs
- Human rating for clarity and usefulness
- Consistency across audience modes and languages

### Performance and reliability
- Event-to-dashboard update latency
- Time to generate an insight
- AI timeout and failure rate
- Fallback success rate

### Demo quality
- Can a judge understand the value within the first minute?
- Is the turning point visible without a long explanation?
- Can the judge inspect the evidence behind the insight?
- Does changing audience mode visibly change the experience?

Avoid claiming a metric is “accurate” without defining the test set and measurement method.

---

## 10. Demo Storyboard

Build the demo around one scripted match so the key behavior is repeatable.

1. **Kickoff:** Show the pitch, score, event feed, and initial statistics.
2. **Early phase:** Team A controls possession; the dashboard establishes a baseline.
3. **Shift:** Team B increases pressure. PULSE detects repeated turnovers and a change in attacking activity.
4. **Insight:** Display an alert with the time window, statistics, and linked events.
5. **Goal:** A scripted dangerous attack results in a goal.
6. **Rewind:** The user selects “Trace the turning point” and sees the events preceding the goal.
7. **Personalization:** Switch from Casual Fan to Tactical Analyst and show two grounded explanations.
8. **Trust check:** Demonstrate the validator rejecting an intentionally incorrect numerical claim.
9. **Recap:** Generate a short evidence-backed match story.

The demo should use real application behavior, not prerecorded AI text disguised as live output. Scripted match events are fine; the product should still process them through the actual pipeline.

---

## 11. Development Roadmap

### Phase 1 — Foundation
- [ ] Confirm competition requirements and submission format.
- [ ] Set up the repository and project structure.
- [ ] Define the event schema.
- [ ] Generate and validate a scripted synthetic match.
- [ ] Write unit tests for event parsing and core statistics.

### Phase 2 — Analytics
- [ ] Implement live match state.
- [ ] Implement the first set of deterministic metrics.
- [ ] Add rolling windows and tactical shift rules.
- [ ] Add event-linked evidence for each alert.
- [ ] Test against normal, turning-point, and false-alarm scenarios.

### Phase 3 — AI Narratives
- [ ] Define structured insight output.
- [ ] Generate a casual explanation.
- [ ] Generate a tactical explanation.
- [ ] Add numerical and event-reference validation.
- [ ] Add deterministic fallbacks and error handling.

### Phase 4 — Interface
- [ ] Build the match dashboard.
- [ ] Add event timeline and momentum chart.
- [ ] Add insight cards and evidence drill-down.
- [ ] Add audience mode selector.
- [ ] Add rewind and match recap.

### Phase 5 — Reliability and Demo
- [ ] Test the complete scripted match from start to finish.
- [ ] Check narrative claims against source data.
- [ ] Measure latency and AI failures.
- [ ] Improve visual hierarchy and responsive layout.
- [ ] Prepare a short demo script and architecture diagram.
- [ ] Document limitations and future work.

### Phase 6 — Stretch Work
- [ ] Add the tactical pitch visualization.
- [ ] Add coach/team tactical tendency analysis using historical and reference matches.
- [ ] Prototype counterfactual scenarios.
- [ ] Add more synthetic match types.

**Rule:** Do not start a stretch feature while a P0 feature is broken.

---

## 12. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Synthetic data appears unrealistic | Script realistic phases and validate event sequences; document simulation assumptions. |
| AI invents statistics | Compute metrics in code, use structured outputs, and validate claims before display. |
| Correlation is presented as causation | Use cautious language such as “preceded,” “coincided with,” or “may have contributed.” |
| Too many low-value alerts | Use rolling windows, thresholds, minimum sample sizes, and alert deduplication. |
| Multi-agent latency or cost | Limit calls, cache results, use deterministic fallbacks, and keep agent roles modular. |
| Cloud architecture consumes development time | Start locally and add only the services required by the rules or demonstrated value. |
| Demo is unpredictable | Use deterministic scripted scenarios and run the full demo repeatedly. |
| Advanced metrics lack sufficient inputs | Display only metrics supported by the available event fields and label approximations. |
| Counterfactuals are misleading | Label them as hypothetical and expose the assumptions. |
| Coach/tactical predictions overstate certainty | Show supporting matches, sample size, recency, uncertainty, and an insufficient-evidence state. |
| Reference-team comparisons are superficial | Explain the specific tactical similarities and account for match context and coaching changes. |

---

## 13. Scope Prioritization

### P0 — Must work
- Synthetic event generator
- Live event replay
- Deterministic statistics
- At least one tactical shift detector
- Evidence-linked turning-point explanation
- Two audience modes
- Narrative validation and fallback
- Functional dashboard and repeatable demo

### P1 — Should work if time allows
- Coach/team tactical tendency predictions with historical reference matches
- Match recap
- Interactive tactical pitch
- More synthetic scenarios
- Better alert deduplication and evaluation metrics

### P2 — Stretch goals
- Counterfactual simulation
- More advanced learned models
- Real data feed integration, if permitted
- Personalized player tracking
- Advanced streaming infrastructure

---

## 14. Competition Compliance Checklist

Before submission, verify every item against the current official rules:

- [ ] Required Microsoft technologies are used where mandated.
- [ ] The project meets the required AI and/or multi-agent criteria.
- [ ] Synthetic data follows the rules and is documented.
- [ ] All data sources and licenses are permitted.
- [ ] The project meets repository, README, demo, and submission requirements.
- [ ] Any required deployment or public access works.
- [ ] The demo clearly explains the problem, solution, technical implementation, and impact.
- [ ] The team has checked deadlines and eligibility directly from the official rules.
- [ ] No unsupported performance or football-accuracy claims are made.

Official rules: https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md

---

## 15. Short Project Pitch

**PULSE turns synthetic football events into an explainable live story.** It detects when a match is changing, connects pivotal moments to the events that preceded them, and generates evidence-backed commentary for different audiences. Unlike a conventional statistics dashboard, PULSE lets fans rewind the match's hidden story, inspect the supporting evidence, and understand the tactical patterns behind the score.

### One-line pitch

**PULSE doesn't just tell you what happened. It helps you investigate how the match got there.**
