import os
# ensure the key is set in this process
os.environ.setdefault("AGENTOPS_API_KEY", "08ffcdfd-c544-438b-ada3-ecb4fb8eb50a")

import agentops
# you can still add tags here if you like
agentops.init(default_tags=["crewai"])

import os
from crewai import LLM, Agent, Task, Crew, Process
from crewai_tools import DirectoryReadTool, FileReadTool

# 1) Configure your Gemini key in your environment:
#    export GEMINI_API_KEY="…"

# 2) Instantiate the CrewAI LLM for Gemini
gemini_llm = LLM(
    api_key="AIzaSyBpxYPNK5t_Qg6iIsymJoAD5oL6fOgQxTE",
    model="gemini/gemini-2.0-flash"   # or "gemini/gemini-pro", "gemini/gemini-1.5-flash", etc.
)

# 3) Build your agents exactly as before, but pass `gemini_llm` in:
directory_reader = DirectoryReadTool()
file_read_tool   = FileReadTool()

latest_file_agent = Agent(
    role="File Reader Agent",
    goal="Find the newest files in a directory by parsing dates in their filenames.",
    backstory="You’re a detail‑oriented file reader.",
    memory=True,
    tools=[directory_reader],
    allow_delegation=False,
    verbose=True,
    llm=gemini_llm
)

log_analyzer_agent = Agent(
    role="Senior Log Analysis Specialist",
    goal="Analyze system logs and surface errors, timings, and exceptions.",
    backstory="15+ years in IT, master’s in CS, log‑analysis guru.",
    memory=True,
    tools=[file_read_tool],
    allow_delegation=False,
    verbose=True,
    llm=gemini_llm
)

find_latest_task = Task(
    description="Read file names in {logs_directory} and return the newest for each job.",
    expected_output="Array of file paths",
    agent=latest_file_agent,
    tools=[directory_reader]
)

analyze_logs_task = Task(
    description=(
        "From the files found, produce markdown tables:\n"
        "- Import jobs: coverage type, table name, environment, time spent\n"
        "- Microservices: error, exception type, exception message"
    ),
    expected_output="Markdown report",
    output_file="./report.md",
    agent=log_analyzer_agent,
    context=[find_latest_task],
    tools=[file_read_tool],
    verbose=True
)

crew = Crew(
    agents=[latest_file_agent, log_analyzer_agent],
    tasks=[find_latest_task, analyze_logs_task],
    process=Process.sequential
)

if __name__ == "__main__":
    result = crew.kickoff({"logs_directory": "./logs"})
    print(result)
