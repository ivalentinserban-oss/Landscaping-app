# Run the Landscaping App on http://127.0.0.1:8000
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$python = $null
if (Test-Path ".venv\Scripts\python.exe") { $python = ".venv\Scripts\python.exe" }
elseif (Test-Path "..\.venv\Scripts\python.exe") { $python = "..\.venv\Scripts\python.exe" }
else { $python = "python" }

& $python app.py
