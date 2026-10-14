# AEGIS browser extension (Chrome / Edge)

Turn any news headline into a simulated supply-chain impact, and keep an eye on your network's health.

* **Right-click "Ask AEGIS"** on selected text (e.g. *"Floods shut Chennai port for 10 days"*): the side panel opens
  and runs the What-if planner on it: unmet demand, revenue at risk, first stock-out, bad case (P90), the recommended
  recovery plan with its confidence, and the cascade timeline.
* **Side panel** (click the toolbar icon): Health Score, service level, revenue at risk, lead time, stock cover and the
  top 3 risks, with a one-click **Analyze**.
* **Alert badge**: the icon shows how many high/critical findings and high-risk weather lanes there are (checked every
  5 minutes); `!` means the backend is not reachable.

All numbers come from the AEGIS backend (`/whatif/run`, `/analysis/*`, `/expansion/baseline`, `/weather/risk`) and are
simulated. The extension has no build step and no dependencies.

## Install (developer mode)

1. Start the AEGIS backend (`uvicorn main:app --reload` in `backend/`, port 8000) and, optionally, the app (port 5173).
2. Chrome: open `chrome://extensions` (Edge: `edge://extensions`), switch on **Developer mode**.
3. Click **Load unpacked** and pick this `chrome-extension` folder.
4. Pin **AEGIS** in the toolbar. Click it to open the side panel, or select text on any page and right-click
   **Ask AEGIS**.

Backend somewhere else? Open the panel's ⚙ settings, enter the API URL and save; the browser asks for permission to
reach that host. The backend accepts calls from extension pages (`allow_origin_regex` for `chrome-extension://` in
`backend/main.py`).

## Tips for headlines

The question is parsed by the LLM when an API key is set, otherwise by the rule parser, which recognises site ids
(S2), site names, cities, lanes (F1->W3), durations ("for 10 days", "a week") and demand changes ("demand rises 40% in
Chennai"). A headline that names no place in your network gets a clear "couldn't map" message instead of a guess.
