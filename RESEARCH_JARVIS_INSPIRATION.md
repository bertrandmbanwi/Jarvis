# JARVIS Project: Competitive Research & Architectural Inspiration

**Date:** March 21, 2026
**Purpose:** Research similar AI assistant projects to identify patterns, architectures, and features that can improve our JARVIS implementation, particularly around multi-step task completion and browser automation.

---

## Executive Summary

After researching 20+ JARVIS-like projects and the broader AI agent ecosystem, the single biggest architectural change that would transform our JARVIS is: **replacing our regex-based intent matching with a proper agentic loop where the LLM decides what tools to call.** Every successful project in this space has moved to this pattern. Our current approach (pattern-match user text -> call a hardcoded tool) is fundamentally brittle and is the root cause of the "can't complete full tasks" problem.

The second major insight: **Son of Simon** (github.com/spamsch/son-of-simon) is the closest existing project to what we're building and has already solved several of our pain points, particularly macOS app integration via AppleScript and multi-step task chaining.

---

## Repos Analyzed

### 1. Likhithsai2580/JARVIS-AGI (119 stars)

**What it does:** A modular AI assistant supporting 15+ LLM backends with voice, vision, and browser automation.

**Key takeaways for us:**
- **Multi-provider fallback:** Supports Blackbox AI, DeepSeek, OpenRouter, Hugging Face, and local Llama. This is similar to our Claude + Ollama fallback but much more extensive. We don't need 15 backends, but the architecture of a provider abstraction layer is solid.
- **Clap detection via CNN:** A neural network trained to detect claps as a wake trigger. Creative alternative to wake words.
- **Chrome URL tracking:** Has a `chrome_latest_url.py` module that can read the current URL from Chrome. This is the kind of browser state awareness we're missing.
- **Android ADB integration:** Extends beyond desktop to mobile device control. Relevant for our Phase 4 iPhone integration.
- **Streaming TTS from multiple providers:** Supports ElevenLabs, DeepGram, Speechify, Edge TTS all with streaming variants for low-latency responses.

**Architecture weakness:** Still uses predefined prompts and JSON conversation storage. No true agentic loop.

### 2. CraftJarvis/JARVIS-1 (Research project)

**What it does:** A Minecraft agent that uses multimodal LLMs to plan and execute 200+ different tasks in an open-world environment.

**Key takeaways for us:**
- **Task decomposition pattern:** Breaks complex objectives (e.g., "obtain a diamond pickaxe") into subtasks automatically. Achieves 5x better reliability than prior agents on long-horizon tasks.
- **Dual memory system:** Combines pre-trained knowledge (what the LLM already knows) with experience-based learning (what it learned from actually doing tasks). We could apply this: ChromaDB for long-term memory + a session "experience log" of what worked/failed during the current session.
- **Goal-conditioned controllers:** Instead of one monolithic executor, it dispatches subtasks to specialized controllers. We could have specialized executors for browser tasks, system tasks, file tasks, etc.

**Architecture weakness:** Domain-specific to Minecraft; the planning patterns are transferable but the implementation isn't.

### 3. OpenJarvis (Stanford Research)

**What it does:** A framework for local-first personal AI agents, developed at Stanford's Hazy Research Lab.

**Key takeaways for us:**
- **Local-first philosophy:** Their research shows local LLMs handle 88.7% of single-turn chat and reasoning queries. Validates our Ollama fallback strategy.
- **Energy/cost as first-class constraints:** They treat FLOPs, latency, and cost alongside accuracy. Aligns with our $2/day budget constraint.
- **Learning loops:** Models improve using local trace data. We could log every tool call + result and periodically fine-tune or adjust prompts based on what succeeds/fails.

**Architecture weakness:** More of a research framework than a consumer product. README is thin on implementation details.

### 4. Gladiator07/JARVIS (34 stars)

**What it does:** A Python voice assistant with PyQt GUI, modular feature system, and API integrations.

**Key takeaways for us:**
- **Clean modular architecture:** Features are isolated in a `features/` directory. Adding a new capability = one new file + register in `__init__.py` + map voice command. Our tool registration is already similar but could be cleaner.
- **Google Calendar integration:** Uses proper OAuth2 with credentials stored in `config/`. Good reference for our Phase 3 Calendar work.
- **WolframAlpha for math:** Routes math queries to WolframAlpha API instead of trying to make the LLM do calculations. Smart separation of concerns.

**Architecture weakness:** Traditional command-mapping (voice text -> function), no LLM-driven planning.

### 5. GitHub Topics: jarvis-ai (20+ projects surveyed)

**Common patterns across all projects:**
- Python is the dominant language (95%+)
- pyttsx3/gTTS for TTS, SpeechRecognition/Whisper for STT
- Most use simple keyword matching for intent detection
- Very few implement true agentic loops
- Most are single-turn: one command, one action, done
- The ones with higher stars tend to have GUIs (PyQt, Tkinter, or web)

---

## High-Value Projects Outside the JARVIS Ecosystem

### 6. Son of Simon (spamsch/son-of-simon) - MOST RELEVANT

**What it does:** An LLM-powered macOS automation agent using AppleScript for Mail, Calendar, Reminders, Notes, Safari, and Contacts. Supports 100+ LLM providers.

**This is the closest project to what we're building.** Key insights:

- **AppleScript-native integration:** Instead of fighting OAuth flows, it leverages the fact that macOS apps are already authenticated via Keychain. Mail, Calendar, Reminders all work through AppleScript directly. This is exactly the approach we should take for Phase 3.
- **Multi-step task chaining:** The agent automatically chains tool calls. Example: "Extract vacation dates from email and add them to Calendar" runs as a sequence of Mail read -> date extraction -> Calendar create, all orchestrated by the LLM.
- **Safari browser automation:** Opens URLs, reads page content, clicks buttons, fills forms, and executes JavaScript, all via AppleScript. This solves our browser state awareness gap.
- **Local memory in YAML:** Persistent `~/.macbot/memory.yaml` for user preferences and context between conversations.
- **Heartbeat mechanism:** A periodic automated check (stored in `~/.macbot/heartbeat.md`) that scans unread emails, upcoming meetings, etc. Could give our JARVIS proactive awareness.
- **Security model:** No passwords stored; relies on macOS Keychain. AppleScript communicates directly with apps.

### 7. GPT-Automator (chidiwilliams/GPT-Automator) - ARCHITECTURE REFERENCE

**What it does:** Voice-to-action on macOS using LangChain Agent + GPT-3 to generate AppleScript and JavaScript.

**Key takeaways:**
- **LLM generates AppleScript dynamically:** Instead of pre-written AppleScript templates (what we do), the LLM generates the AppleScript on the fly based on the user's request. This is far more flexible.
- **Dual code generation:** AppleScript for desktop automation, JavaScript for browser automation. The LangChain agent decides which to use.
- **Three-stage pipeline:** Speech (Whisper) -> Intent (LangChain Agent) -> Action (generated script). Clean separation.

**Risk:** The author notes it's susceptible to prompt injection since it executes LLM-generated code. We should add sandboxing/validation if we adopt this pattern.

### 8. Browser Use (browser-use/browser-use) - BROWSER AUTOMATION

**What it does:** Open-source framework for AI browser automation, optimized for agent workflows.

**Key takeaways:**
- Claims 3-5x faster task completion than alternatives
- State-of-the-art accuracy on browser benchmarks
- Could be integrated as our browser automation backend instead of raw AppleScript

### 9. Skyvern (Skyvern-AI/skyvern) - BROWSER AUTOMATION

**What it does:** AI-driven browser automation using Playwright with vision capabilities.

**Key takeaways:**
- Uses visual understanding of web pages, not just DOM parsing
- Can handle dynamic, JavaScript-heavy sites
- Task-driven autonomous design

---

## The Core Architectural Problem (and Solution)

### What we have now:
```
User says something
  -> Regex pattern matching (_looks_like_action, intent patterns in executor.py)
  -> Hardcoded tool call
  -> LLM summarizes the result
```

### What we should have:
```
User says something
  -> LLM receives the request + available tools as a schema
  -> LLM decides which tool(s) to call (or just responds conversationally)
  -> Tool executes, result feeds back to LLM
  -> LLM decides: done? Or call another tool?
  -> Loop until task is complete
```

This is the **ReAct (Reason + Act) pattern**, and it's the foundation of every successful AI agent in 2025-2026.

### Why this matters for us:

1. **Multi-step tasks work automatically.** "Search for Premier League scores and open the ESPN result" becomes: LLM calls search_web -> reads results -> decides to call open_url_in_browser with the ESPN URL. No regex splitting needed.

2. **Error recovery is built in.** If search_web fails, the LLM can try a different query or fall back to search_in_browser. No hardcoded fallback logic needed.

3. **New tools are trivially added.** Define a tool schema (name, description, parameters), register the function. The LLM figures out when to use it based on the description alone.

4. **Follow-up context is natural.** "Open the second result" works because the LLM already has the search results in its conversation context from the previous tool call.

### How to implement this with Claude API:

Claude's API has native tool use support. The flow is:

```python
# 1. Define tools as schemas
tools = [
    {
        "name": "search_web",
        "description": "Search the web using DuckDuckGo",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "open_url_in_browser",
        "description": "Open a URL in a specific browser via AppleScript",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "browser": {"type": "string", "default": "Safari"}
            },
            "required": ["url"]
        }
    },
    # ... more tools
]

# 2. Send message with tools
response = client.messages.create(
    model="claude-sonnet-4-6",
    messages=conversation_history,
    tools=tools,
    system=system_prompt,
)

# 3. Agentic loop
while response.stop_reason == "tool_use":
    # Extract tool calls from response
    tool_calls = [b for b in response.content if b.type == "tool_use"]

    # Execute each tool
    tool_results = []
    for call in tool_calls:
        result = await execute_tool(call.name, call.input)
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": call.id,
            "content": result
        })

    # Feed results back to Claude
    conversation_history.append({"role": "assistant", "content": response.content})
    conversation_history.append({"role": "user", "content": tool_results})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        messages=conversation_history,
        tools=tools,
        system=system_prompt,
    )

# 4. Final text response
final_answer = response.content[0].text
```

### What we can delete after this refactor:
- All regex intent patterns in `executor.py`
- `_split_compound_request()`
- `_resolve_pronouns()`
- `_cache_search_results()` (the LLM will have results in context)
- `_handle_open_nth_result()` (the LLM will know which URL to open)
- `_looks_like_action()` in `brain.py` (the LLM decides if tools are needed)
- `_resolve_followup()` in `brain.py` (the LLM has conversation context)
- `ACTION_KEYWORDS` and `DEEP_KEYWORDS` lists

All of that fragile regex/keyword logic gets replaced by Claude's native intelligence.

---

## Recommended Architecture (Post-Refactor)

```
                    +------------------+
                    |   Voice Input    |
                    |  (Whisper STT)   |
                    +--------+---------+
                             |
                    +--------v---------+
                    |   JarvisBrain    |
                    |  (Orchestrator)  |
                    +--------+---------+
                             |
                    +--------v---------+
                    |   Claude API     |
                    |  with Tool Use   |
                    |  (Agentic Loop)  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v-----+  +-----v------+
     | macOS Tools|  | Web Tools  |  | System     |
     | (AppleScript)| | (Search,  |  | Tools      |
     | Mail,Cal,  |  |  Browse,   |  | (Files,    |
     | Reminders, |  |  Fetch)    |  |  Apps,     |
     | Notes,     |  +------------+  |  Settings) |
     | Safari     |                  +------------+
     +------------+
```

### Tool Categories to Expose:

**macOS Native (via AppleScript):**
- open_application, quit_application
- open_url_in_browser, search_in_browser
- read_safari_page, click_safari_element (Son of Simon pattern)
- send_email, read_emails, search_emails
- create_calendar_event, check_schedule
- create_reminder, list_reminders
- create_note, search_notes
- get_contacts

**Web (Backend):**
- search_web (DuckDuckGo)
- search_news
- fetch_page_content
- get_weather (dedicated tool with proper API)

**System:**
- get_battery_status, get_disk_usage
- set_volume, set_brightness
- take_screenshot
- run_terminal_command (sandboxed)
- get_clipboard, set_clipboard

**Memory:**
- save_to_memory, recall_from_memory
- get_user_preferences

---

## Implementation Priority

### Phase 1.5: Agentic Loop Refactor (DO THIS FIRST)
1. Implement Claude tool_use agentic loop in `executor.py`
2. Define all existing tools as proper JSON schemas
3. Remove regex intent matching
4. Test multi-step task completion
5. Add cost tracking per agentic loop (multiple API calls per user request)

### Phase 2: UI (unchanged)
- Holographic + practical dashboard modes

### Phase 3: macOS Integrations (simplified by agentic loop)
- Add Mail/Calendar/Reminders/Notes AppleScript tools
- Just define the tool schemas and functions; the LLM handles orchestration
- Follow Son of Simon's Keychain-based auth approach

### Phase 4: iPhone + Polish (unchanged)

---

## Feature Ideas from Research

| Feature | Source | Priority | Effort |
|---------|--------|----------|--------|
| Agentic loop (tool_use) | Claude SDK docs, Agent Loop article | CRITICAL | Medium |
| Safari page reading via AppleScript | Son of Simon | High | Low |
| Safari form filling / JS execution | Son of Simon | Medium | Medium |
| Dynamic AppleScript generation by LLM | GPT-Automator | Medium | Medium |
| Heartbeat / proactive checks | Son of Simon | Medium | Low |
| Local YAML memory for preferences | Son of Simon | Low | Low |
| Multi-provider TTS fallback | JARVIS-AGI | Low | Medium |
| Experience-based learning loop | JARVIS-1, OpenJarvis | Low | High |
| Chrome URL state reading | JARVIS-AGI | Low | Low |

---

## Sources

- [GitHub Topics: jarvis-ai](https://github.com/topics/jarvis-ai)
- [Likhithsai2580/JARVIS-AGI](https://github.com/Likhithsai2580/JARVIS-AGI)
- [CraftJarvis/JARVIS-1](https://github.com/CraftJarvis/JARVIS-1)
- [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)
- [Gladiator07/JARVIS](https://github.com/Gladiator07/JARVIS)
- [Son of Simon (macOS Agent)](https://github.com/spamsch/son-of-simon)
- [GPT-Automator](https://github.com/chidiwilliams/GPT-Automator)
- [Browser Use](https://github.com/browser-use/browser-use)
- [Skyvern](https://github.com/Skyvern-AI/skyvern)
- [Claude Agent SDK: How the Agent Loop Works](https://platform.claude.com/docs/en/agent-sdk/agent-loop)
- [The Agent Execution Loop (Victor Dibia)](https://newsletter.victordibia.com/p/the-agent-execution-loop-how-to-build)
- [GenericAgent (Desktop Automation)](https://github.com/lsdefine/GenericAgent)
