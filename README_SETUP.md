# Google Places setup

1. In Google Cloud Console, create or select a project, attach a billing account, and enable **Places API (New)**.
2. Create an API key restricted to **Places API (New)**. Set sensible quotas and review billing alerts; API keys authenticate requests but do not make them free.
3. In the project root, copy `.env.example` to `.env`, then replace the placeholder with `GOOGLE_PLACES_API_KEY=your_real_key`. Keep `.env` private; it is ignored by Git.
4. Install requirements and start the custom local website from the project root:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m flask --app flask_server run
   ```

   Then open `http://127.0.0.1:5000` in your browser. The earlier Streamlit interface remains available with `.\.venv\Scripts\python.exe -m streamlit run app.py` if needed.

5. Enter your business details, choose an industry (or type a custom one), search for local businesses, select the ones with websites, and run the website analysis. Common misspellings of supported industry names are matched automatically; custom terms are sent as entered. A missing key produces a clear message and sends no request.

The custom website stores working data in memory for the current server session. Restarting the local server clears the current comparison and results. The older Streamlit interface remains available separately if you need it.

Google bills Places Text Search according to the fields requested and current pricing/usage rules. This app uses a small field mask, but business name/address/location and website fields can fall into paid SKUs. Review current [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing), enable budgets/alerts and set quota limits before searching. Actual charges vary by account, region, SKU and usage.

Run the offline tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Discovery tests mock the HTTP call; they do not use your key or contact Google. They are for the older Streamlit project modules; the custom Flask interface has not been runtime-verified yet.

