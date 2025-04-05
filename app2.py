import os
import time
import psutil
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from datetime import datetime

from crewai import LLM, Agent, Task, Crew, Process
from crewai.tools import tool
from crewai.project import CrewBase, agent, task, crew, before_kickoff
from crewai_tools import DirectoryReadTool, FileReadTool
from dotenv import load_dotenv

load_dotenv()
import os
# ensure the key is set in this process
os.environ.setdefault("AGENTOPS_API_KEY", "08ffcdfd-c544-438b-ada3-ecb4fb8eb50a")

import agentops
# you can still add tags here if you like
agentops.init(default_tags=["crewai"])

# ——————————————————————————————————————————————
# 0) LLM: configure your Gemini (or swap in Azure) here
# ——————————————————————————————————————————————
gemini_llm = LLM(
    api_key=os.getenv("GOOGLE_API_KEY"),
    model="gemini/gemini-2.0-flash"
)

# ——————————————————————————————————————————————
# 1) Custom tools via @tool decorator (per docs) :contentReference[oaicite:0]{index=0}
# ——————————————————————————————————————————————
# 1) Fixed custom tools with proper @tool syntax


@tool("resource_metrics")
def resource_metrics(metrics_directory: str) -> str:
    """Collect resource usage metrics from CSV files or live-sample for 60s, then save to CSV."""
    dfs = []
    for fn in os.listdir(metrics_directory):
        if fn.endswith(".csv") and "metrics" in fn:
            df = pd.read_csv(os.path.join(metrics_directory, fn),
                             parse_dates=["timestamp"])
            dfs.append(df)
    if dfs:
        combined = pd.concat(dfs).sort_values("timestamp")
    else:
        samples = []
        for _ in range(60):
            samples.append({
                "timestamp": pd.Timestamp.now(),
                "cpu_percent": psutil.cpu_percent(),
                "mem_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage("/").percent
            })
            time.sleep(1)
        combined = pd.DataFrame(samples)

    out_path = os.path.join(metrics_directory, "resource_metrics.csv")
    combined.to_csv(out_path, index=False)
    return out_path  # <-- str, JSON‑serializable

@tool("seaborn_line_viz")
def seaborn_line_viz(
    df_path: str,
    x_col: str,
    y_cols: list[str],
    title: str,
    out_path: str
) -> str:
    """Generate a Seaborn line chart from CSV at df_path and save PNG to out_path."""
    df = pd.read_csv(df_path, parse_dates=[x_col])
    plt.figure(figsize=(10, 6))
    for y_col in y_cols:
        sns.lineplot(x=x_col, y=y_col, data=df, label=y_col)
    plt.title(title)
    plt.xlabel(x_col)
    plt.ylabel(", ".join(y_cols))
    plt.legend()
    plt.grid(True)
    plt.savefig(out_path)
    plt.close()
    return out_path

@tool("anomaly_detection")
def anomaly_detection(
    df_path: str,
    cpu_thresh: float = 85.0,
    mem_thresh: float = 90.0
) -> str:
    """Detect CPU/memory anomalies in CSV at df_path and return a text summary."""
    df = pd.read_csv(df_path, parse_dates=["timestamp"])
    alerts = []
    high_cpu = df[df.cpu_percent > cpu_thresh]
    if not high_cpu.empty:
        alerts.append(f"High CPU (> {cpu_thresh}%) at {len(high_cpu)} timestamps")
    low_cpu = df[df.cpu_percent < 10.0]
    if not low_cpu.empty:
        alerts.append(f"Under‑utilized CPU (< 10%) at {len(low_cpu)} timestamps")
    high_mem = df[df.mem_percent > mem_thresh]
    if not high_mem.empty:
        alerts.append(f"High Memory (> {mem_thresh}%) at {len(high_mem)} timestamps")
    return "\n".join(alerts) or "No anomalies detected."



# ——————————————————————————————————————————————
# 2) Decorator‑based Crew definition
# ——————————————————————————————————————————————
@CrewBase
class PerformanceAnalysisCrew:
    """Pipeline: latest‑file → log‑analysis (system & app) → metrics → viz (system & app) → anomaly → final report"""

    @before_kickoff
    def prepare_inputs(self, inputs):
        inputs.setdefault("logs_directory", "./logs")
        inputs.setdefault("metrics_directory", "./logs")
        os.makedirs("./plots", exist_ok=True)  # Ensure the plots directory exists
        os.makedirs("./reports", exist_ok=True) # Ensure the reports directory exists
        return inputs

    # — Agents —
    @agent
    def file_reader_agent(self) -> Agent:
        return Agent(
            role="Log Categorization Specialist",
            goal="Identify and categorize log files in the directory as either system logs or application/microservice logs based on their filenames.",
            backstory="Expert in distinguishing different types of log files.",
            memory=True,
            tools=[DirectoryReadTool()],
            allow_delegation=False,
            verbose=True,
            llm=gemini_llm
        )

    @agent
    def system_log_analyzer_agent(self) -> Agent:
        return Agent(
            role="System Log Analysis Specialist",
            goal="Analyze system logs and surface errors, warnings, and any relevant performance indicators, focusing on data that can be plotted over time.",
            backstory="Deep understanding of operating system logs and their trends.",
            memory=True,
            tools=[FileReadTool()],
            allow_delegation=False,
            verbose=True,
            llm=gemini_llm
        )

    @agent
    def app_log_analyzer_agent(self) -> Agent:
        return Agent(
            role="Application/Microservice Log Analysis Specialist",
            goal="Analyze application and microservice logs and surface errors, exceptions, performance metrics (like request timings, error rates) that can be plotted over time.",
            backstory="Extensive experience with debugging application logs and identifying performance trends.",
            memory=True,
            tools=[FileReadTool()],
            allow_delegation=False,
            verbose=True,
            llm=gemini_llm
        )

    @agent
    def metrics_agent(self) -> Agent:
        return Agent(
            role="Resource Metrics Collector",
            goal="Collect or parse CPU, memory, disk utilization data and save it to a CSV file.",
            backstory="Gather and normalize resource metrics.",
            memory=False,
            tools=[resource_metrics],
            allow_delegation=False,
            verbose=True,
            llm=gemini_llm
        )

    @agent
    def viz_agent(self) -> Agent:
        return Agent(
            role="Visualization Specialist",
            goal="Generate informative Seaborn graphs for resource metrics and log trends.",
            backstory="Turn raw metrics and log insights into clear and informative charts.",
            memory=False,
            tools=[seaborn_line_viz],
            allow_delegation=False,
            verbose=True,
            llm=gemini_llm
        )

    @agent
    def anomaly_agent(self) -> Agent:
        return Agent(
            role="Anomaly Detection Specialist",
            goal="Identify over/under‑utilization and recommend tunings based on the metrics CSV file.",
            backstory="Detect anomalies and right‑size resources.",
            memory=False,
            tools=[anomaly_detection],
            allow_delegation=False,
            verbose=True,
            llm=gemini_llm
        )

    @agent
    def report_agent(self) -> Agent:
        return Agent(
            role="Performance Report Compiler",
            goal="Merge logs, metrics, visuals, and recommendations into a comprehensive Markdown report with a structured format.",
            backstory="Expert in synthesizing complex data into clear, actionable reports.",
            memory=False,
            tools=[FileReadTool()],
            allow_delegation=False,
            verbose=True,
            llm=gemini_llm
        )

    # — Tasks —
    @task
    def categorize_logs_task(self) -> Task:
        return Task(
            description="Read file names in {logs_directory} and categorize them into two lists: 'system_logs' and 'application_logs'. Assume system logs might contain keywords like 'system', 'kernel', or 'os', and application logs might contain keywords like 'app', 'service', or the application name. Return these two lists of file paths.",
            expected_output="Dictionary containing two keys: 'system_logs' (list of system log paths) and 'application_logs' (list of application log paths).",
            agent=self.file_reader_agent(),
            tools=[DirectoryReadTool()]
        )

    @task
    def analyze_system_logs_task(self) -> Task:
        return Task(
            description=(
                "Analyze the provided system log files. Identify the date and time format used in the system logs. Extract key observations, potential security events, and any traffic patterns or relevant numerical data that can be plotted over time (e.g., number of errors/warnings per hour). If you find such data, save it to a CSV file named 'system_log_trends.csv' in the './logs' directory with columns 'timestamp' and 'value'. Summarize your findings in './reports/system_report.md'."
            ),
            expected_output="Markdown table summarizing system log analysis.",
            output_file="./reports/system_report.md",
            agent=self.system_log_analyzer_agent(),
            context=[self.categorize_logs_task()],
            tools=[FileReadTool()]
        )

    @task
    def analyze_app_logs_task(self) -> Task:
        return Task(
            description=(
                "Analyze the provided application/microservice log files. Identify the date and time format used in the application logs. Extract key observations, potential security events, and any traffic patterns or relevant numerical data that can be plotted over time (e.g., request latency, error rates). If you find such data, save it to a CSV file named 'app_log_trends.csv' in the './logs' directory with columns 'timestamp' and 'value'. Summarize your findings in './reports/app_report.md'."
            ),
            expected_output="Markdown table summarizing application log analysis.",
            output_file="./reports/app_report.md",
            agent=self.app_log_analyzer_agent(),
            context=[self.categorize_logs_task()],
            tools=[FileReadTool()]
        )

    @task
    def collect_metrics_task(self) -> Task:
        return Task(
            description="Gather resource metrics from {metrics_directory} and save them to a CSV file named 'resource_metrics.csv'.",
            expected_output="Path to the saved metrics CSV file",
            agent=self.metrics_agent(),
            tools=[resource_metrics]
        )

    @task
    def generate_viz_task(self) -> Task:
        return Task(
            description=(
                "Produce Seaborn line charts in the './plots' directory based on the analyzed data:\n"
                "1. Generate 'resource_usage.png' using the data from the CSV file located at the path provided by the collect_metrics_task. Set the x-axis to 'timestamp' and the y-axis to ['cpu_percent', 'mem_percent', 'disk_percent']. The title should be 'Resource Usage Over Time'. Save the output to './plots/resource_usage.png'.\n"
                "2. Check if './logs/system_log_trends.csv' exists. If it does, load the data and generate 'system_log_trends.png'. Set the x-axis to 'timestamp' and the y-axis to 'value'. The title should be 'System Log Trends'. Save the output to './plots/system_log_trends.png'.\n"
                "3. Check if './logs/app_log_trends.csv' exists. If it does, load the data and generate 'app_log_trends.png'. Set the x-axis to 'timestamp' and the y-axis to 'value'. The title should be 'Application Log Trends'. Save the output to './plots/app_log_trends.png'."
            ),
            expected_output="List of paths to generated PNG plots.",
            agent=self.viz_agent(),
            context=[self.collect_metrics_task(), self.analyze_system_logs_task(), self.analyze_app_logs_task()],
            tools=[seaborn_line_viz, FileReadTool()]
        )

    @task
    def anomaly_task(self) -> Task:
        return Task(
            description="Analyze the metrics in the CSV file from the previous step for CPU and memory anomalies and suggest performance tunings.",
            expected_output="Anomaly summary & recommendations",
            agent=self.anomaly_agent(),
            context=[self.collect_metrics_task()],
            tools=[anomaly_detection]
        )

    @task
    def compile_report_task(self) -> Task:
        current_time = datetime.now(tz=datetime.now().astimezone().tzinfo).strftime("%Y-%m-%d %H:%M:%S %Z%z")
        return Task(
            description=(
                f"Compile a comprehensive Log Analysis Report in './reports/performance_report.md' using the following format:\n\n"
                f"Log Analysis Report - {current_time}\n\n"
                "Analysis Summary:\n"
                "Summary: Provide a high-level summary of the findings from both system and application logs, resource metrics, and anomaly detection.\n"
                "Highest Severity: [Specify the highest severity level found]\n"
                "Requires Immediate Attention: [True/False based on findings]\n\n"
                "Key Observations (System Logs):\n"
                "[List key observations from the system log analysis in bullet points]\n\n"
                "Key Observations (Application/Microservice Logs):\n"
                "[List key observations from the application/microservice log analysis in bullet points]\n\n"
                "Security Events (System Logs):\n"
                "[List any security events found in system logs with details]\n\n"
                "Security Events (Application/Microservice Logs):\n"
                "[List any security events found in application/microservice logs with details]\n\n"
                "Traffic Patterns (System Logs):\n"
                "[Summarize any identified traffic patterns in system logs, if applicable]\n\n"
                "Traffic Patterns (Application/Microservice Logs):\n"
                "[Summarize any identified traffic patterns in application/microservice logs]\n\n"
                "Resource Usage Analysis:\n"
                "- Link to Resource Usage Chart: [./plots/resource_usage.png]\n"
                "- Anomaly Detection Summary: [Output from anomaly_task]\n\n"
                "Link to System Log Trends Chart (if generated): [./plots/system_log_trends.png]\n"
                "Link to Application Log Trends Chart (if generated): [./plots/app_log_trends.png]\n\n"
                "Tuning Recommendations:\n"
                "[Provide recommendations based on the log analysis, resource metrics, and anomaly detection.]\n"
                ":::---"
            ),
            expected_output="Markdown performance report",
            output_file="./reports/performance_report.md",
            agent=self.report_agent(),
            context=[
                self.analyze_system_logs_task(),
                self.analyze_app_logs_task(),
                self.collect_metrics_task(),
                self.generate_viz_task(),
                self.anomaly_task()
            ],
            tools=[FileReadTool()],
            verbose=True
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True
        )

# ——————————————————————————————————————————————
# 3) Kick it off
# ——————————————————————————————————————————————
if __name__ == "__main__":
    crew = PerformanceAnalysisCrew().crew()
    result = crew.kickoff({
        "logs_directory": "./logs",
        "metrics_directory": "./logs"
    })
    print(result)