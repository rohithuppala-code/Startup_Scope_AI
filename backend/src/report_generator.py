from .input_parser import ValidationReport

class ReportGenerator:
    @staticmethod
    def generate_markdown(report: ValidationReport, idea_desc: str) -> str:
        """
        Takes the structured ValidationReport and returns a formatted markdown string.
        """
        md = f"# StartupScope AI: Validation Report\n\n"
        md += f"**Analyzed Idea:** {idea_desc}\n\n"
        md += f"## Feasibility Score: {report.feasibility_score}/100\n\n"
        
        md += "## Competitor Analysis\n"
        md += f"{report.competitor_analysis}\n\n"
        
        md += "## Identified Market Gaps\n"
        for gap in report.identified_gaps:
            md += f"- {gap}\n"
        md += "\n"
        
        md += "## Suggested Improvements / Pivots\n"
        for imp in report.suggested_improvements:
            md += f"- {imp}\n"
            
        return md
