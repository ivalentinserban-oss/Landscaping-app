# Landscaping Contractor App

A FastAPI web app for landscaping contractors: manage clients, jobs, quotes, crews, members, invoices, and reports.

## Run locally

```bash
cd landscaping_app
python app.py
```

Then open **http://localhost:5050** (or the port shown in the terminal).

See [HOW_TO_RUN.txt](landscaping_app/HOW_TO_RUN.txt) for more options.

## Stack

- Python 3, FastAPI, SQLite, Jinja2
- Optional: WeasyPrint (PDF invoices)

## Features

- **Clients** – Add, edit, delete; view jobs per client  
- **Jobs** – Create, edit, schedule; assign crew and members; tasks; status; complete with actuals  
- **Quotes** – Draft → Sent → Accept (creates job) or Decline  
- **Crews & Members** – Assign per job  
- **Invoices** – Mark sent, record payments (Cash/Check/Card/Other), PDF download  
- **Calendar** – Month view of jobs  
- **Reports** – Revenue by month, jobs by status, unpaid jobs  
