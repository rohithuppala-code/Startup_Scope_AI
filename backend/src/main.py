from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid

from .input_parser import StartupIdea, ValidationReport
from .analysis_engine import AnalysisEngine
from .report_generator import ReportGenerator

app = FastAPI(title="StartupScope AI API", description="Validate your startup idea using an elite AI VC analyst.")

# Configure CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = AnalysisEngine()

class ValidateRequest(BaseModel):
    user_id: str | None = None
    idea: StartupIdea

class ValidateResponse(BaseModel):
    user_id: str
    report: ValidationReport
    markdown_report: str

@app.post("/validate-idea", response_model=ValidateResponse)
async def validate_idea(req: ValidateRequest):
    try:
        u_id = req.user_id if req.user_id else str(uuid.uuid4())
        report = engine.run_validation(idea_input=req.idea, user_id=u_id)
        
        md_report = ReportGenerator.generate_markdown(report, req.idea.description)
        
        return ValidateResponse(
            user_id=u_id,
            report=report,
            markdown_report=md_report
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
