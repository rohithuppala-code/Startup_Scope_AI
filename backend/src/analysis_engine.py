from .input_parser import StartupIdea, ValidationReport
from .firecrawl_agent import FirecrawlAgent
from .memento_manager import MementoManager
from .llm_client import LLMClient
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .data_cleaner import clean_markdown, limit_context

class AnalysisEngine:
    def __init__(self):
        self.firecrawl = FirecrawlAgent()
        self.memento = MementoManager()
        self.llm = LLMClient()

    def run_validation(self, idea_input: StartupIdea, user_id: str) -> ValidationReport:
        # 1. Check history
        history_context = self.memento.fetch_history(user_id=user_id)
        history_context = limit_context(history_context, max_chars=2000)

        # 2. Gather live data via Firecrawl
        query = f"top competitors for {idea_input.description} in {idea_input.target_market}"
        raw_competitors = self.firecrawl.search_and_scrape(query=query)
        clean_competitors = clean_markdown(raw_competitors)
        clean_competitors = limit_context(clean_competitors, max_chars=12000)

        # 3. Build prompts
        user_prompt = build_user_prompt(
            idea_desc=idea_input.description,
            market=idea_input.target_market,
            budget=idea_input.budget_constraints,
            competitors_context=clean_competitors,
            history_context=history_context
        )

        # 4. Generate report
        report_dict = self.llm.generate_validation_report(SYSTEM_PROMPT, user_prompt)
        
        # Validate through Pydantic
        report = ValidationReport(**report_dict)

        # 5. Save to memory
        memory_summary = f"Idea: {idea_input.description}. Score: {report.feasibility_score}. Feedback: {report.suggested_improvements[0]}"
        self.memento.append_history(user_id=user_id, text=memory_summary)

        return report
