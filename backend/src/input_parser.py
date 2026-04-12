from pydantic import BaseModel, Field

class StartupIdea(BaseModel):
    idea_id: str = Field(description="Unique identifier for the idea/session.")
    description: str = Field(description="The full detailed description of the startup idea.")
    target_market: str | None = Field(default=None, description="The intended target market.")
    business_model: str | None = Field(default=None, description="The business model (e.g. B2B, SaaS, B2C).")
    budget_constraints: str | None = Field(default=None, description="Budget or resource constraints.")

class ValidationReport(BaseModel):
    feasibility_score: float = Field(description="Feasibility score out of 100.")
    competitor_analysis: str = Field(description="Summary of the competitors found.")
    identified_gaps: list[str] = Field(description="Areas lacking in the market.")
    suggested_improvements: list[str] = Field(description="Actionable next steps or pivot ideas.")
