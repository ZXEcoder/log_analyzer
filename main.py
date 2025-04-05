from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
import subprocess
import shutil
import os

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <h2>Log Analyzer</h2>
    <form action="/trigger" method="post">
        <button type="submit">Run System Log Export</button>
    </form>
    <form action="/upload" enctype="multipart/form-data" method="post">
        <input type="file" name="file"/>
        <button type="submit">Export Logs from File</button>
    </form>
    <a href="/plot">View Plot & Reports</a>
    """

@app.post("/trigger")
async def run_sys_py():
    subprocess.run(["python", "loge.py"])
    
    return {"message": "System logs collected and report generated."}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    logs_path = "logs/service.log"
    with open(logs_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    subprocess.run(["python", "app2.py"])
    return {"message": "File uploaded and report generated."}

@app.get("/plot", response_class=HTMLResponse)
async def view_plot_and_report():
    with open("reports/system_report.md", "r") as f:
        system_report = f.read()
    with open("reports/performance_report.md", "r") as f:
        micro_report = f.read()

    return f"""
    <h2>Generated Plot</h2>
    <img src="plots\resource_usage.png" alt="System Plot" width="600"/>
    <h3>System Report</h3>
    <pre>{system_report}</pre>
    <h3>Microservice Report</h3>
    <pre>{micro_report}</pre>
    """
