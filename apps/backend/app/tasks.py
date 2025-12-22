from app.celery_app import celery_app
import logging
import time
import os
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def generate_meeting_minutes(self, meeting_id: str, template_type: str = "general"):
    """
    Celery task to generate structured meeting minutes using CrewAI.
    """
    logger.info(f"Starting meeting minutes generation for {meeting_id} with template {template_type}")
    
    # Check for OpenAI API Key (or other LLM provider)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not found. Running in simulation mode.")
        time.sleep(5) # Simulate processing
        return {
            "status": "completed", 
            "meeting_id": meeting_id, 
            "summary": {
                "overview": "Simulation: Meeting overview generated without LLM.",
                "actionItems": ["Simulated Action Item 1", "Simulated Action Item 2"],
                "decisions": ["Simulated Decision 1"],
                "risks": ["Simulated Risk 1"]
            }
        }

    try:
        # TODO: Retrieve meeting transcript from Database based on meeting_id
        # For now, we use a placeholder transcript
        transcript_text = "Placeholder transcript text for meeting " + meeting_id

        # --- Define Agents ---
        # 1. Summarizer Agent
        summarizer = Agent(
            role='Senior Meeting Secretary',
            goal='Summarize meeting transcripts into concise and accurate overviews.',
            backstory="You are an expert at distilling long conversations into key points, ensuring no critical information is lost.",
            verbose=True,
            allow_delegation=False,
            # llm=ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0) # Optional: Custom LLM
        )

        # 2. Extractor Agent
        extractor = Agent(
            role='Structured Data Analyst',
            goal='Extract specific fields like Action Items, Decisions, and Risks from the summary.',
            backstory="You specialize in structuring unstructured text into JSON-like formats for database storage.",
            verbose=True,
            allow_delegation=False
        )

        # --- Define Tasks ---
        # Task 1: Summarize
        summary_task = Task(
            description=f"Analyze the following meeting transcript and write a comprehensive summary:\n\n{transcript_text}",
            agent=summarizer,
            expected_output="A comprehensive summary of the meeting."
        )

        # Task 2: Extract Structure (dependant on template_type)
        extraction_prompt = "Extract the following fields from the summary: Overview, Action Items, Decisions, Risks."
        if template_type == "sales":
            extraction_prompt = "Extract BANT fields (Budget, Authority, Need, Timing) and next steps."
        
        extraction_task = Task(
            description=f"{extraction_prompt}\n\nEnsure the output is formatted as a JSON object.",
            agent=extractor,
            context=[summary_task], # Depends on the summary
            expected_output="A JSON object containing the extracted fields."
        )

        # --- Instantiate Crew ---
        crew = Crew(
            agents=[summarizer, extractor],
            tasks=[summary_task, extraction_task],
            verbose=True, # Changed from 2 to True which is bool or int (1/2) usually
            process=Process.sequential
        )

        # --- Kickoff ---
        result = crew.kickoff()
        
        logger.info(f"Meeting minutes generated for {meeting_id}")
        
        # TODO: Parse 'result' (which might be string) into JSON and save to Database
        
        return {"status": "completed", "meeting_id": meeting_id, "raw_result": str(result)}
        
    except Exception as e:
        logger.error(f"Failed to generate minutes for {meeting_id}: {e}")
        return {"status": "failed", "error": str(e)}
