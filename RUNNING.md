# Running the Staffing Optimizer

Quick reference for starting and stopping the app yourself. Commands are written for
**Windows PowerShell** (your setup). Run them from the project folder:

```powershell
cd C:\Users\myfir\Repos\Git\Staffing_Optimizer
```

---

## One-time setup

Install the package and its dependencies (only needed once, or after pulling new deps):

```powershell
pip install -e ".[web]"     # the web app: fastapi, uvicorn, jinja2 (+ numpy, pyyaml)
pip install -e ".[viz]"     # optional: matplotlib, networkx (for PNG diagram export)
pip install -e ".[dev]"     # optional: pytest, ruff, httpx (for running tests)
```

---

## The web app (primary)

### Start it

```powershell
python -m webapp
```

- Open **http://localhost:8000** in your browser (Builder is the home page).
- This terminal is now running the server; leave it open while you use the app.

### Stop it

- Click in the terminal and press **Ctrl + C**.

### Free the port if it's stuck (port 8000)

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  Select-Object -Expand OwningProcess |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

Saved designs live in the `designs/` folder as timestamped `.json` files; export/import from the
**Saved designs** page to move a system between machines.

---

## The Streamlit dashboard (deprecated)

Superseded by the web app above; kept for reference. Needs `pip install -e ".[app]"`.

```powershell
streamlit run app/dashboard.py        # http://localhost:8501, Ctrl + C to stop
```

---

## The headless report (no browser, prints to the terminal)

```powershell
python solve.py                                                  # default example
python solve.py examples/warehouse_5dept.yaml --headcount 45     # try a smaller pool
python solve.py examples/warehouse_5dept.yaml --actual 15,11,10,7,4   # compare a real plan
```

`--actual` takes one number per department, in table order.

---

## Validate a design and draw its diagram

Author a system in the arrow-flow format (see `examples/warehouse_5dept.flow`), then:

```powershell
python design.py examples/warehouse_5dept.flow            # check soundness; write .dot + .mmd
python design.py examples/warehouse_5dept.flow --image    # also write a .png (needs the viz extra)
python design.py examples/warehouse_5dept.flow --to-yaml scenario.yaml   # convert to engine YAML
```

Prints errors/warnings (with line numbers) and a feasibility summary; exits non-zero if unsound.
The dashboard's **Design & diagram** tab does the same live and can load a sound design into the
other tabs.

---

## Run the tests

```powershell
python -m pytest -q          # all 24 tests
python -m ruff check .       # lint
```

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `streamlit : command not found` | Run the one-time setup above, or use `python -m streamlit run app/dashboard.py`. |
| Browser shows "can't connect" | The server isn't running — start it, and check the terminal for the actual URL/port. |
| "Port 8501 is already in use" | An old server is still up. Stop it with the port-kill command above, then start again. |
| Edits to a table throw an error in the app | A half-typed row (blank name or makespan) — finish or delete the row; the app recovers automatically. |
