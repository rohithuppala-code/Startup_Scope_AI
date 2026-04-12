# Implementation Plan: StartupScope AI

This plan outlines the steps to build the entire StartupScope AI project based on the `Architecture.md` document.

## User Review Required

> [!IMPORTANT]
> The "Memento API" was specified as the memory layer. Since "Memento" could refer to internal systems or the open-source memory layer `mem0` (formerly Embedchain), I will use the `mem0ai` python package to implement this context memory layer. If you have a different specific API for Memento in mind, please let me know. 

> [!WARNING]
> This build will require valid API keys for OpenAI (`OPENAI_API_KEY`) and Firecrawl (`FIRECRAWL_API_KEY`) to be set in your `.env` file to function completely. I will create a `.env.example` file for you.

## Proposed Changes

---

### Project Setup
Initialize the directory structure and environmental configuration.

#### [NEW] [requirements.txt](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/requirements.txt)
- Create dependencies list: `openai`, `firecrawl-py`, `python-dotenv`, `pydantic`, `mem0ai`.

#### [NEW] [.env.example](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/.env.example)
- Define environment variables for API keys.

---

### Source Code (`src/`)

#### [NEW] [src/input_parser.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/input_parser.py)
- Code Pydantic models (`StartupIdea`) for structured input representation.

#### [NEW] [src/llm_client.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/llm_client.py)
- Connect to OpenAI API. Provide helper methods for chat completions and extracting JSON schemas.

#### [NEW] [src/firecrawl_agent.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/firecrawl_agent.py)
- Interface with Firecrawl using `FirecrawlApp(api_key=...)`. Code functions to scrape competitor domains and extract markdown.

#### [NEW] [src/data_cleaner.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/data_cleaner.py)
- Simple utilities to handle rate limits, clean raw Firecrawl markdown, and limit prompt context size.

#### [NEW] [src/memento_manager.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/memento_manager.py)
- Wrapper around `mem0` client to store the user's past validation reports and search historical runs based on `user_id`.

#### [NEW] [src/prompts.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/prompts.py)
- Hold system prompts and templating strings designed to shape the LLM output as a VC startup validation expert.

#### [NEW] [src/analysis_engine.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/analysis_engine.py)
- Orchestrate data gathering: takes input -> gets competitors via Firecrawl -> retrieves Memento history -> yields combined prompt for the LLM -> parses response into `ValidationReport`.

#### [NEW] [src/report_generator.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/report_generator.py)
- Take the `ValidationReport` Pydantic object and convert it into a well-formatted Markdown string.

#### [NEW] [src/main.py](file:///c:/Users/sairo/OneDrive/Desktop/Startup%20Scope%20AI/src/main.py)
- Serve as the CLI entry point tying everything together using `argparse`. Includes the main execution loop.

---

## Verification Plan

### Automated Tests
- N/A for this initial deployment phase. We will rely on manual run testing.

### Manual Verification
- We will execute a test run with a dummy startup idea: `python src/main.py --idea "AI app that checks your fridge and generates recipes" --user_id "user_1"`.
- We will verify that it calls Firecrawl, interfaces with the LLM API, and creates a report markdown file in an `outputs/` folder.
