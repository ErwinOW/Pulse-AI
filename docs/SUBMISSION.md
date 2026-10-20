# Submission draft (copy into the hackathon form)

## Project name
PULSE: the story behind the score

## Category
Best Enterprise Solution

## Elevator pitch (short)
PULSE turns a live stream of football events into trustworthy, multilingual match commentary. A deterministic engine detects tactical shifts, a Microsoft Agent Framework Storyteller agent explains them for fans or analysts in English or Bahasa Indonesia, and a fact-checker verifies every number and cited event before anything is shown.

## What it does and the problem it solves
Match dashboards show numbers but not the story, and AI-written commentary is risky for media businesses because models invent numbers and overstate causes. PULSE separates the two jobs:
- **Facts:** statistics, a pressing-shift detector and goal turning points are deterministic and tested, computed only from events before the current match time.
- **Words:** a Storyteller agent (Microsoft Agent Framework, Gemini model) writes the insight for the chosen audience (casual fan or analyst) and language.
- **Control:** a fact-checker rejects unsupported numbers, uncited events, unhedged cause-and-effect and wrong-language formatting, and sends its reasons back to the agent for one retry. If the agent still fails or is unavailable, a template built from the same verified numbers is used. Every text is labelled and shows its evidence.

The dashboard replays the match over WebSocket at up to 60× speed with a momentum chart, key events (chance creation and pressing, not every pass), the insight card with evidence, turning points, and an analyst numbers panel.

## Microsoft and Azure technologies used
- **Microsoft Agent Framework** (`agent-framework-core`, `agent-framework-openai`): the Storyteller agent with structured output, inside a write, check, retry, fallback loop.
- No Azure services. Hosting is free (Render) and the model is Google Gemini on its free tier via its OpenAI-compatible API, so judges can test at no cost.

## Data
100% synthetic, football-realistic matches from our own seeded simulator (fictional teams and players), with ground truth used only by tests and the detector evaluation.

## Links
- Live demo: https://pulse-k9mh.onrender.com
- Code: https://github.com/ErwinOW/Pulse-AI
- Video: (add YouTube or Vimeo link)

## Testing instructions
1. Open https://pulse-k9mh.onrender.com. On the free plan the first load can take about a minute if the server was asleep. No login is needed.
2. The "Demo: high-press turning point" match is selected. Press **Play** (10× speed), or drag the timeline to about **62'**.
3. At 63' an alert appears: Eastvale Athletic's high press. Read the insight, then click **Show evidence** to see the before/now numbers and the cited events.
4. Switch **Audience** (Casual / Analyst) and **Language** (English / Bahasa Indonesia). Analyst adds a numbers panel, chart scale and pitch zones.
5. Watch the 64' equaliser in **Turning points**: it is traced back to a pass lost under pressure.
6. Optional: **Regenerate** asks the agent for a new version live (fact-checked first; limited to 20 per day for the whole site).
