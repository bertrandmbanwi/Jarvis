# Deep Comparison: ethanplusai/jarvis vs Our Jarvis

**Date:** 2026-04-02
**Purpose:** Identify what ethanplusai's Jarvis does better than ours, with actionable takeaways.

## TL;DR

Our Jarvis is architecturally stronger: modular codebase, 86+ tools, multi-tier LLM routing, production-grade hardening, local-first voice, and enterprise UI. However, **ethanplusai has built several quality-of-life and continuous-improvement systems that we lack entirely**. These are the gaps worth closing.

---

## Where ethanplusai Wins

### 1. Automated Test Suite

**They have it. We don't.**

ethanplusai ships 5 test files covering:
- Intent classification (20+ real test cases)
- QA verification and auto-retry logic
- End-to-end pipeline integration tests
- Browser automation tests

**Our gap:** Zero automated tests. We enforce 80% coverage in our `.claude/rules/` but have no test files to back it up.

**Priority:** HIGH. This is the single biggest gap. Without tests, every change to the agent system, tool registry, or memory layer is a manual verification exercise.

**Recommendation:** Add `tests/` directory with pytest. Start with:
- `test_tools_schema.py` (tool registration and invocation)
- `test_memory.py` (fact extraction, preference tracking, vector search)
- `test_planner.py` (complexity detection, decomposition)
- `test_hardening.py` (circuit breaker, retry logic, input validation)
- `test_cost_tracker.py` (token counting, alert thresholds)

---

### 2. QA Verification with Auto-Retry

**They have it integrated. Ours exists but is weaker in practice.**

ethanplusai's `qa.py`:
- Spawns `claude -p` subprocess to verify completed work
- Structured JSON feedback with specific issue lists
- `auto_retry()` with up to 3 attempts, passing exact issues to the retry prompt
- `QAResult` dataclass with pass/fail and detailed issue tracking

**Our Jarvis:** We have `qa_agent.py` (335 lines), but it's more tightly coupled to the executor and doesn't have the same structured retry-with-feedback loop. Their approach of spawning a separate verification process creates genuine independence between "doer" and "checker."

**Priority:** MEDIUM. We have the foundation; the improvement is making the QA agent truly independent and adding structured retry-with-issues.

---

### 3. Template Evolution System

**They have it. We don't.**

ethanplusai's `evolution.py`:
- `TemplateEvolver` analyzes failure patterns across completed task logs
- Detects common issues (import errors, syntax failures, incomplete work, missing files)
- Automatically creates new versioned templates with improvements incorporated
- Maps failure patterns to specific template sections that need updating

**Our gap:** Our system prompt and templates are static. We have a learning loop that tracks tool reliability, but it doesn't modify prompts or templates based on failures.

**Priority:** MEDIUM-HIGH. This is a self-improving mechanism. When a planning template leads to failures, it should evolve.

**Recommendation:** Extend `learning.py` to:
1. Detect repeated failure patterns in plans
2. Generate improved prompt snippets
3. A/B test the new prompts against the old ones
4. Promote winners automatically

---

### 4. A/B Testing for Prompts

**Both have it, but theirs is more mature in practice.**

ethanplusai's `ab_testing.py`:
- Random version assignment per task
- Wilson confidence intervals for statistical rigor
- Winner detection: minimum 20 tasks per version, 10 percentage point difference threshold
- Automatic promotion of winning templates

**Our Jarvis:** We have `ab_testing.py` (321 lines) with the same core mechanics, but it's not visibly wired into the template evolution or prompt improvement pipeline.

**Priority:** LOW (we have the mechanism; just need to wire it to template evolution).

---

### 5. Settings UI with First-Time Setup Wizard

**They have it. We don't.**

ethanplusai's frontend includes:
- Multi-step setup wizard (API Keys -> Test -> Preferences -> Done)
- Real-time status indicators (green/red dots) for each integration
- API key testing with backend validation
- Persistent preferences (user name, honorific, calendar accounts)
- System info display (uptime, memory count, task count)
- Glass-morphism sliding panel UI

**Our gap:** Our setup is `./setup.sh` + manual `.env` editing. No in-app onboarding.

**Priority:** MEDIUM. This dramatically lowers the barrier for anyone else using the system. Our current setup assumes the user is comfortable editing dotfiles.

**Recommendation:** Add a `/settings` route to the Next.js UI with:
- Environment variable configuration
- Integration status checks
- Model tier selection
- Cost alert threshold adjustment
- Voice engine selection

---

### 6. Persistent Claude Code Work Sessions

**They have it as a first-class feature. We have a basic tool.**

ethanplusai's `work_mode.py`:
- `WorkSession` class wrapping `claude -p` subprocess
- Per-project session persistence across voice commands
- `--continue` flag reuses the last session in a directory
- Session state restored from disk (survives restarts)
- Casual vs. work mode detection (routes simple questions to Haiku, complex ones to persistent session)

**Our Jarvis:** We have `tools/claude_code.py` for delegating to Claude Code CLI, but it's a one-shot tool, not a persistent session manager. Context resets between invocations.

**Priority:** MEDIUM. For coding workflows, persistent sessions are significantly more productive.

---

### 7. Real-Time Conversation Monitor

**They have it. We have something similar but less focused.**

ethanplusai's `monitor.py`:
- Analyzes every JARVIS response in real-time
- Detects anti-patterns: corporate speak, breaking character, responses too long for voice
- Flags when personality markers ("sir") aren't used enough
- Detects user frustration patterns
- Reports issues every 30 seconds

**Our Jarvis:** We have `core/monitor.py` with voice output constraints (80-word limit, no em-dashes), but it's more of a formatting enforcer than a quality monitor.

**Priority:** LOW-MEDIUM. Nice to have for maintaining personality consistency.

---

### 8. Proactive Follow-Up Suggestions

**They have task-level suggestions. Ours are calendar/email-level.**

ethanplusai's `suggestions.py`:
- After every task completion, generates 1 contextual follow-up
- Checks for missing tests, missing README, missing favicon, etc.
- References QA results to suggest quality improvements
- Voice-friendly suggestion text

**Our Jarvis:** Our `core/proactive.py` handles calendar alerts and email notifications, but doesn't suggest follow-up actions after task completion.

**Priority:** MEDIUM. This is a natural extension of our task decomposition system.

---

### 9. Dispatch Registry with Project Context

**They have it. We don't.**

ethanplusai's `dispatch_registry.py`:
- SQLite-backed registry of all projects/builds JARVIS has touched
- Status tracking (pending -> building -> completed)
- Timestamps and summaries per dispatch
- `format_for_prompt()` generates LLM context from active/recent work
- Fuzzy project name matching

**Our gap:** No persistent record of which projects JARVIS has worked on. Each session starts fresh regarding project awareness.

**Priority:** MEDIUM. This would improve context continuity across sessions.

---

### 10. Structured Prompt Templates with Keyword Scoring

**They have it. We use static prompts.**

ethanplusai's `templates.py`:
- Keyword-based template selection (landing_page, bug_fix, feature, refactor, etc.)
- Each template has sections, acceptance criteria, design notes
- `get_template()` scores by keyword match and returns best fit
- Smart defaults per task type

**Our gap:** Our planner uses a single system prompt approach. No template library with scoring.

**Priority:** LOW-MEDIUM. Would improve planning quality for varied task types.

---

## Where We Win (for context)

These are areas where our Jarvis is clearly superior:

| Dimension | Our Advantage |
|-----------|--------------|
| **Architecture** | Modular 52-file package vs. monolithic 2600-line server.py |
| **Tools** | 86+ tools with safety guards vs. ~15-20 actions |
| **LLM Routing** | 3-tier (Haiku/Sonnet/Opus) with cost optimization vs. single model |
| **Voice** | Local-first (Moonshine + Whisper + Kokoro) vs. cloud-only (Fish Audio) |
| **Security** | PIN auth, rate limiting, circuit breakers, input validation vs. none |
| **Memory** | ChromaDB vectors + SQLite FTS5 + JSON facts vs. flat SQLite |
| **UI** | Next.js + React + Tailwind + Three.js vs. Vite + Three.js only |
| **Mobile** | Cloudflare Tunnel + PIN + responsive vs. none |
| **Cost Tracking** | Per-session/daily/monthly alerts vs. none |
| **Error Handling** | Circuit breakers, retries, error classification vs. basic try-catch |
| **Agent System** | 7 specialized agents with parallel execution vs. single generic |
| **Learning** | Tool reliability tracking, failure patterns, plan history vs. memory-only |
| **Setup** | Automated `setup.sh` + `start.sh` with modes vs. manual 7-step |
| **Deployment** | LaunchAgent, Cloudflare Tunnel, desktop overlay vs. local-only |

---

## Recommended Action Items (Prioritized)

### Phase 1: Foundation (High Priority)

1. **Add automated test suite** with pytest covering tools, memory, planner, and hardening
2. **Enhance QA agent** to use independent verification with structured retry-with-issues feedback

### Phase 2: Self-Improvement (Medium-High Priority)

3. **Build template evolution system** that modifies prompts based on failure patterns
4. **Add dispatch registry** for project context persistence across sessions
5. **Wire A/B testing** into the template evolution pipeline

### Phase 3: UX Polish (Medium Priority)

6. **Add settings UI** with first-time setup wizard in Next.js
7. **Implement persistent Claude Code sessions** for multi-turn development workflows
8. **Add task-level follow-up suggestions** after plan completion
9. **Build structured prompt template library** with keyword scoring

### Phase 4: Refinement (Low Priority)

10. **Enhance conversation monitor** for personality consistency and user frustration detection

---

## Conclusion

Our Jarvis is the better-engineered system at the infrastructure level. ethanplusai's Jarvis has invested more in the "getting smarter over time" layer: testing, template evolution, QA feedback loops, and user-facing polish. The biggest gap we should close is automated testing, followed by the self-improvement mechanisms (template evolution + A/B testing pipeline). These would compound our existing architectural advantages.
