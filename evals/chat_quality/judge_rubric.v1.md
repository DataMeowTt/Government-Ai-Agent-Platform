# Chat Quality Judge Rubric v1

Score each target response from 0 to 100. Evaluate only the final user-visible answer and the provided metadata.

## General Rubric

- Task fulfillment: 20
- Data correctness / grounding: 20
- Routing & tool behavior: 15
- Completeness & usefulness: 15
- Clarity & Vietnamese UX: 10
- Safety / scope control: 10
- Conversation context handling: 5
- Formatting / UI compatibility: 5

## Category-Specific Weights

### DIRECT_ANSWER / GENERAL_EXPLANATION

- Task fulfillment: 25
- Concept accuracy: 25
- Clarity Vietnamese UX: 20
- No internal terms: 15
- Conciseness: 10
- Formatting: 5

### DATA_QUERY_RANKING / DATA_QUERY_COMPARE / DATA_QUERY_TREND_TIME_SERIES / DATA_QUERY_COVERAGE_ANOMALY

- Task fulfillment: 15
- Data correctness / grounding: 30
- Parsed intent / slots / tool behavior: 20
- Answer usefulness: 10
- Chart/table compatibility: 10
- No hallucination: 10
- Formatting: 5

### FOLLOW_UP_ANALYSIS

- Context usage: 25
- Answer usefulness: 20
- No parser/DB new query: 15
- Qualitative caveat when giving reasons: 15
- No internal terms: 15
- Clarity: 10

### FOLLOW_UP_MODIFY_QUERY

- Rewrite correctness: 25
- Parsed intent / slots correctness: 25
- Data correctness: 20
- Context usage: 10
- Chart/table compatibility: 10
- Clarity: 10

### NEED_CLARIFICATION

- Asks the right missing information: 35
- Does not query DB unnecessarily: 25
- Clear suggestions/examples: 20
- Tone: 10
- No irrelevant answer: 10

### UNSUPPORTED / OFF_TOPIC

- Correct refusal / scope control: 35
- Suggests supported alternatives: 25
- Does not query DB: 20
- Clarity/tone: 10
- No hallucination: 10

## Hard Block Rules

Mark `should_block_release=true` if any of these apply:

- HTTP failed or target turn `ok=false`.
- Answer is empty for a non-error response.
- Final answer contains internal terms: Gemini Router, router, parser, parsedQuery, AI Agent, AI Agent Service, database, DB, query planner, model parser, ngrok, Kaggle.
- DATA_QUERY expected success but status is `needs_clarification`, `off_topic`, or `unsupported`.
- FOLLOW_UP_ANALYSIS called parser or DB: `parserDebug` is not null, `routerDebug.needs_parser=true`, or `routerDebug.needs_db=true`.
- FOLLOW_UP_MODIFY_QUERY expected but final route is not `FOLLOW_UP_MODIFY_QUERY`.
- NEED_CLARIFICATION expected but no clarification questions and the answer does not ask a clear clarifying question.
- UNSUPPORTED/OFF_TOPIC expected but response status is success with DB execution.
- Parsed year/limit mismatch with expected values.
- Country false positive `NAM` for Vietnam compare cases.
- Judge score is below 50.
