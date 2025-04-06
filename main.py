# app.py
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import subprocess, shutil, os

# Markdown → HTML + syntax highlighting
import markdown2
from pygments.formatters import HtmlFormatter

# Jinja2 for templating
from jinja2 import Environment, DictLoader

app = FastAPI()

# 1) Mount static directories
app.mount("/plots", StaticFiles(directory="plots"), name="plots")

# 2) Shared HTML snippets
BOOTSTRAP_CSS = """
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body { background-color: #f8f9fa; }
  .navbar-custom { background-color: #2c3e50; }
  .card-custom { border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
  .btn-custom { transition: all 0.3s ease; }
  .report-box { 
    background: white; 
    border-radius: 8px; 
    padding: 20px; 
    margin: 15px 0; 
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    height: 100%;
  }
  .report-box h4 {
    color: #2c3e50;
    border-bottom: 2px solid #3498db;
    padding-bottom: 0.5rem;
    margin-bottom: 1.5rem;
  }
</style>
"""

NAVBAR = """
<nav class="navbar navbar-expand-lg navbar-dark navbar-custom mb-4">
  <div class="container">
    <a class="navbar-brand" href="/">Log Analyzer</a>
    <div class="navbar-nav">
      <a class="nav-link" href="/plot">Reports & Plots</a>
    </div>
  </div>
</nav>
"""

FOOTER = """
<footer class="mt-5 py-4 text-center text-muted">
  <div class="container">
    <p>© 2023 Log Analyzer. All rights reserved.</p>
  </div>
</footer>
"""

# 3) Enhanced Jinja2 template
template_str = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Reports</title>
  {{ BOOTSTRAP_CSS | safe }}

  <!-- GitHub Markdown CSS -->
  <link rel="stylesheet"
        href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown-light.min.css"
        crossorigin="anonymous" />

  <!-- Pygments code‑highlighting CSS -->
  <style>
  {{ pygments_css | safe }}
  </style>

  <style>
    .markdown-body {
      box-sizing: border-box;
      max-width: 800px;
      margin: 0 auto;
      padding: 30px;
    }
    
    .markdown-body table {
      width: 100%;
      border-collapse: collapse;
      margin: 1.5rem 0;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      overflow: hidden;
    }

    .markdown-body th {
      background-color: #2c3e50;
      color: white;
      padding: 12px;
      text-align: left;
      font-weight: 600;
    }

    .markdown-body td {
      padding: 12px;
      border-bottom: 1px solid #e1e4e8;
      background-color: white;
    }

    .markdown-body tr:hover {
      background-color: #f8f9fa;
    }

    .markdown-body pre {
      background: #f8f9fa;
      border-radius: 6px;
      padding: 1rem;
      margin: 1.5rem 0;
      overflow-x: auto;
      border: 1px solid #e1e4e8;
    }

    .metric-highlight {
      background: #e9f5ff;
      padding: 1rem;
      border-radius: 6px;
      margin: 1rem 0;
      border-left: 4px solid #3498db;
    }

    .status-badge {
      display: inline-block;
      padding: 0.25em 0.6em;
      border-radius: 4px;
      font-weight: 500;
      font-size: 0.9em;
    }

    .status-ok {
      background: #d4edda;
      color: #155724;
    }

    .status-warning {
      background: #fff3cd;
      color: #856404;
    }

    .status-critical {
      background: #f8d7da;
      color: #721c24;
    }

    @media (max-width: 768px) {
      .markdown-body {
        padding: 15px;
      }
      .row.g-4 {
        gap: 1rem !important;
      }
      .report-box {
        margin: 10px 0;
        padding: 15px;
      }
    }
  </style>
</head>
<body>
  {{ NAVBAR | safe }}
  <div class="container">
    <h2 class="mb-4 text-center">Analysis Results</h2>

    <div class="row justify-content-center mb-5">
      <div class="col-lg-10">
        <div class="report-box">
          <h4 class="mb-3">Resource Usage Plot</h4>
          <img src="/plots/resource_usage.png"
               class="img-fluid rounded-3 mb-3"
               alt="System Plot">
        </div>
      </div>
    </div>

    <div class="row g-4">
      <div class="col-lg-6">
        <div class="report-box">
          <h4 class="mb-3">System Report</h4>
          <article class="markdown-body">
            {{ sys_report | safe }}
          </article>
        </div>
      </div>
      
      <div class="col-lg-6">
        <div class="report-box">
          <h4 class="mb-3">Microservice Report</h4>
          <article class="markdown-body">
            {{ micro_report | safe }}
          </article>
        </div>
      </div>
    </div>
  </div>
  {{ FOOTER | safe }}
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

jinja_env = Environment(loader=DictLoader({"reports.html": template_str}))

@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""
    <html>
      <head>
        <title>Log Analyzer</title>
        {BOOTSTRAP_CSS}
      </head>
      <body>
        {NAVBAR}
        <div class="container">
          <h2 class="mb-4 text-center">Log Analysis Dashboard</h2>
          <div class="row g-4">
            <div class="col-md-6">
              <div class="card card-custom h-100">
                <div class="card-body text-center">
                  <h5 class="card-title">System Logs</h5>
                  <form action="/trigger" method="post">
                    <button type="submit" class="btn btn-primary btn-custom px-5 py-2">
                      Run System Log Export
                    </button>
                  </form>
                </div>
              </div>
            </div>
            <div class="col-md-6">
              <div class="card card-custom h-100">
                <div class="card-body text-center">
                  <h5 class="card-title">Upload Logs</h5>
                  <form action="/upload" enctype="multipart/form-data" method="post">
                    <input type="file" name="file" class="form-control mb-3">
                    <button type="submit" class="btn btn-success btn-custom px-5 py-2">
                      Process Uploaded File
                    </button>
                  </form>
                </div>
              </div>
            </div>
          </div>
        </div>
        {FOOTER}
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
      </body>
    </html>
    """

@app.post("/trigger")
async def run_sys_py():
    subprocess.run(["python", "loge.py"], check=False)
    return JSONResponse({"message": "System logs collected and report generated."})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    os.makedirs("logs", exist_ok=True)
    with open("logs/service.log", "wb") as buf:
        shutil.copyfileobj(file.file, buf)
    subprocess.run(["python", "app2.py"], check=False)
    return JSONResponse({"message": "File uploaded and report generated."})

@app.get("/plot", response_class=HTMLResponse)
async def view_plot_and_report(request: Request):
    # Read Markdown files
    with open("reports/system_report.md", "r") as f:
        md_sys = f.read()
    with open("reports/performance_report.md", "r") as f:
        md_micro = f.read()

    # Convert to HTML with code highlighting
    extras = ["fenced-code-blocks", "tables", "highlight"]
    sys_html   = markdown2.markdown(md_sys,   extras=extras)
    micro_html = markdown2.markdown(md_micro, extras=extras)

    # Generate Pygments CSS
    pygments_css = HtmlFormatter().get_style_defs(".highlight")

    # Render template
    tpl = jinja_env.get_template("reports.html")
    html = tpl.render(
        BOOTSTRAP_CSS=BOOTSTRAP_CSS,
        NAVBAR=NAVBAR,
        FOOTER=FOOTER,
        sys_report=sys_html,
        micro_report=micro_html,
        pygments_css=pygments_css,
    )
    return HTMLResponse(html)