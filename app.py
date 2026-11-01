
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from urllib.parse import urlparse
import ipaddress
import socket
from xml.sax.saxutils import escape

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from src.competitor_discovery import INDUSTRY_QUERIES, discover_competitors
from src.insights_engine import generate_insights
from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)


# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="Competitor Analysis Agent",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
    :root {--portfolio-bg:#080910;--portfolio-panel:#10121d;--portfolio-line:rgba(255,255,255,.1);--portfolio-text:#f5f5fb;--portfolio-muted:#a4a7bb;--portfolio-purple:#9b87ff;--portfolio-cyan:#74d8f5;}
    html, body, [data-testid="stAppViewContainer"] {background:var(--portfolio-bg); color:var(--portfolio-text); font-family:'DM Sans',sans-serif;}
    [data-testid="stHeader"] {background:transparent;}
    .block-container {padding-top:1.35rem;padding-bottom:3rem;max-width:1160px;}
    h1,h2,h3 {font-family:'Manrope','DM Sans',sans-serif;letter-spacing:-.035em;}
    [data-testid="stSidebar"] {background:#0c0d17;border-right:1px solid rgba(255,255,255,.07);}
    [data-testid="stTabs"] [role="tablist"] {gap:.45rem;border-bottom:1px solid var(--portfolio-line);}
    [data-testid="stTabs"] button[role="tab"] {border-radius:9px 9px 0 0;padding:.72rem 1.05rem;color:#c1c2d0;font-weight:600;}
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {color:#d7ceff;border-bottom-color:var(--portfolio-purple);}
    [data-testid="stMetric"] {background:linear-gradient(145deg,rgba(155,135,255,.1),rgba(116,216,245,.045));padding:18px 20px;border:1px solid var(--portfolio-line);border-radius:14px;}
    [data-testid="stMetricLabel"] {font-size:.8rem;color:var(--portfolio-muted);}
    [data-testid="stMetricValue"] {font-family:'Manrope',sans-serif;font-weight:700;color:#f5f5fb;}
    .hero-card {padding:1.8rem 2rem;border:1px solid rgba(174,157,255,.2);border-radius:17px;margin:.2rem 0 1.25rem;position:relative;overflow:hidden;background:radial-gradient(ellipse at 85% 10%,rgba(116,216,245,.16),transparent 38%),radial-gradient(ellipse at 68% 100%,rgba(155,135,255,.2),transparent 48%),linear-gradient(135deg,#10121d,#0c0e18);}
    .hero-card h1 {color:#f5f5fb;margin:0 0 .35rem;font-size:2.05rem;}
    .hero-card p {color:#a4a7bb;margin:0;font-size:1rem;}
    .hero-kicker {font:11px 'DM Mono',monospace;text-transform:uppercase;letter-spacing:.14em;color:#9b87ff;margin-bottom:.6rem;}
    .section-note {color:#a4a7bb;font-size:.92rem;}
    [data-testid="stAlert"], [data-testid="stExpander"] {border-radius:12px;border-color:var(--portfolio-line);}
    div[data-testid="stButton"] button {border-radius:9px;font-weight:600;transition:transform .18s,border-color .18s;}
    div[data-testid="stButton"] button:hover {transform:translateY(-1px);border-color:var(--portfolio-purple);}
    [data-testid="stDataFrame"], [data-testid="stTable"] {border:1px solid var(--portfolio-line);border-radius:12px;overflow:hidden;}
    input, textarea {border-radius:8px!important;}
    [data-baseweb="input"]>div,[data-baseweb="textarea"]>div,[data-baseweb="select"]>div {background:#10121d;border-color:rgba(255,255,255,.12);}
    [data-baseweb="input"] input,[data-baseweb="textarea"] textarea,[data-baseweb="select"] input {color:#f5f5fb;}
    [data-testid="stFileUploader"] section {background:#10121d;border-color:rgba(255,255,255,.16);border-radius:12px;}
    @media(max-width:700px){.hero-card{padding:1.25rem}.hero-card h1{font-size:1.55rem}.block-container{padding-left:1rem;padding-right:1rem}}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# WEBSITE ANALYSIS
# ---------------------------------------------------------

HEADERS = {
    "User-Agent": "CompetitorAnalysisStudentProject/1.0"
}


def safe_csv_cell(value):
    """Prevent spreadsheet apps from treating exported text as a formula."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def normalize_url(value: str) -> str:
    """Normalize a website URL and allow only public HTTP(S) hosts."""
    value = (value or "").strip()

    if not value:
        raise ValueError("Enter a website URL.")

    if "://" not in value:
        value = "https://" + value

    parsed = urlparse(value)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS websites are supported.")

    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter a valid public website URL.")

    host = parsed.hostname.lower()

    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Local addresses are not allowed.")

    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(
                    host, None, type=socket.SOCK_STREAM
                )
            }
        except (socket.gaierror, OSError):
            raise ValueError("The website address could not be resolved.")

    if any(
        not address.is_global
        for address in addresses
    ):
        raise ValueError("Private or non-public addresses are not allowed.")

    return value.rstrip("/")


def analyze_website(name: str, website: str) -> dict:
    """Collect basic signals from a publicly accessible website."""
    result = {
        "Business": name,
        "Website": website,
        "Status": "Not analysed",
        "HTTPS": None,
        "Title": "",
        "Meta Description": "",
        "H1 Count": None,
        "Heading Count": None,
        "Word Count": None,
        "Contact Signal": None,
        "Website Score": None,
        "Score Coverage": "0/6 signals",
        "Evidence": "",
        "Source Checked At": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
    }

    try:
        url = normalize_url(website)

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=(5, 12),
            allow_redirects=False,
            stream=True,
        )

        try:
            if response.is_redirect:
                result["Website"] = url
                result["HTTPS"] = url.startswith("https://")
                result["Status"] = "Redirect not followed"
                result["Evidence"] = (
                    "Website returned a redirect. Add and validate its "
                    "destination before analyzing it."
                )
                return result

            final_url = normalize_url(response.url)
            result["Website"] = final_url
            result["HTTPS"] = final_url.startswith("https://")

            if response.status_code >= 400:
                result["Status"] = f"HTTP {response.status_code}"
                result["Evidence"] = (
                    f"The website returned HTTP {response.status_code}."
                )
                return result

            content_type = response.headers.get("Content-Type", "").lower()

            if "text/html" not in content_type:
                result["Status"] = "Non-HTML response"
                result["Evidence"] = (
                    "The requested page did not return HTML."
                )
                return result

            chunks = []
            total_bytes = 0

            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue

                total_bytes += len(chunk)

                if total_bytes > 1_500_000:
                    break

                chunks.append(chunk)

            html = b"".join(chunks).decode(
                response.encoding or "utf-8",
                errors="replace",
            )

        finally:
            response.close()

        soup = BeautifulSoup(html, "html.parser")

        if soup.title:
            result["Title"] = soup.title.get_text(" ", strip=True)

        meta = soup.find(
            "meta",
            attrs={"name": lambda value: value and value.lower() == "description"},
        )
        if meta:
            result["Meta Description"] = (
                meta.get("content", "").strip()
            )

        result["H1 Count"] = len(soup.find_all("h1"))
        result["Heading Count"] = len(
            soup.find_all(["h1", "h2", "h3"])
        )

        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()

        page_text = soup.get_text(" ", strip=True)
        words = page_text.split()
        result["Word Count"] = len(words)

        text_lower = page_text.lower()
        links = " ".join(
            (link.get("href") or "").lower()
            for link in soup.find_all("a", href=True)
        )

        result["Contact Signal"] = any(
            marker in text_lower or marker in links
            for marker in [
                "contact", "phone", "email", "address",
                "mailto:", "tel:"
            ]
        )

        # Score only observable signals. Missing values are excluded
        # from the denominator rather than treated as failures.
        signals = [
            (bool(result["Title"]), bool(result["Title"])),
            (
                bool(result["Meta Description"]),
                bool(result["Meta Description"]),
            ),
            (result["H1 Count"] is not None, result["H1 Count"] == 1),
            (
                result["Heading Count"] is not None,
                result["Heading Count"] >= 2,
            ),
            (
                result["Word Count"] is not None,
                result["Word Count"] >= 100,
            ),
            (
                result["Contact Signal"] is not None,
                result["Contact Signal"],
            ),
        ]

        available = [signal for signal in signals if signal[0]]
        passed = sum(1 for _, good in available if good)

        result["Website Score"] = (
            round(100 * passed / len(available))
            if available else None
        )
        result["Score Coverage"] = f"{len(available)}/6 signals"
        result["Status"] = "Analysed"
        result["Evidence"] = (
            "Signals: page title, meta description, heading structure, "
            "page text length and contact information. "
            "This is a preliminary heuristic, not a full SEO audit."
        )

    except (ValueError, requests.RequestException, OSError) as exc:
        result["Status"] = "Unavailable"
        result["Evidence"] = str(exc)[:250]

    except Exception as exc:
        result["Status"] = "Analysis error"
        result["Evidence"] = str(exc)[:250]

    return result


# ---------------------------------------------------------
# REPORT GENERATION
# ---------------------------------------------------------

def make_pdf(
    company: str,
    location: str,
    industry: str,
    data: pd.DataFrame,
) -> bytes:
    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=28,
        leftMargin=28,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph("Competitor Analysis Report", styles["Title"]),
        Spacer(1, 8),
        Paragraph(f"<b>Business:</b> {escape(str(company or ''))}", styles["Normal"]),
        Paragraph(f"<b>Location:</b> {escape(str(location or ''))}", styles["Normal"]),
        Paragraph(f"<b>Industry:</b> {escape(str(industry or ''))}", styles["Normal"]),
        Paragraph(
            f"<b>Generated:</b> {datetime.now().astimezone().strftime('%d %b %Y, %H:%M %Z')}",
            styles["Normal"],
        ),
        Spacer(1, 14),
        Paragraph("Website Signal Comparison", styles["Heading2"]),
        Spacer(1, 6),
    ]

    columns = [
        "Business", "Website", "Status",
        "Website Score", "Coverage", "HTTPS",
    ]
    table_data = [columns]

    for _, row in data.iterrows():
        score = row.get("Website Score")
        table_data.append([
            str(row.get("Business", ""))[:28],
            str(row.get("Website", ""))[:42],
            str(row.get("Status", ""))[:18],
            "N/A" if pd.isna(score) else f"{int(score)}/100",
            str(row.get("Score Coverage", "")),
            "Yes" if row.get("HTTPS") is True else (
                "No" if row.get("HTTPS") is False else "Unknown"
            ),
        ])

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=[105, 205, 80, 80, 75, 50],
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#26364A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F2F5F8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    story.extend([
        table,
        Spacer(1, 14),
        Paragraph("Interpretation and Limitations", styles["Heading2"]),
        Paragraph(
            "The website score is a preliminary rule-based measure of "
            "six observable website signals. It is not a complete measure "
            "of competitive strength, search ranking, traffic, customer "
            "reputation, advertising spend or market share. Unavailable "
            "signals are excluded from the score denominator. Source "
            "timestamps are recorded for each analysis.",
            styles["BodyText"],
        ),
    ])

    document.build(story)
    return output.getvalue()


# ---------------------------------------------------------
# APP STATE
# ---------------------------------------------------------

if "competitors" not in st.session_state:
    st.session_state.competitors = []

if "results" not in st.session_state:
    st.session_state.results = None


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

st.sidebar.title("📊 Competitor Intelligence")
st.sidebar.caption("Free-first research workspace")

company = st.sidebar.text_input(
    "Your business name",
    value="My Business",
)
location = st.sidebar.text_input(
    "Business location",
    value="Kozhikode, Kerala, India",
)
industry_choices = sorted({name.title() for name in INDUSTRY_QUERIES}, key=str.casefold)
industry_choices.append("Other / type your own")
industry_choice = st.sidebar.selectbox(
    "Industry",
    options=industry_choices,
    index=industry_choices.index("Salon"),
    help="Close spelling mistakes in known industries are corrected automatically.",
    key="industry_choice",
)
industry = (
    st.sidebar.text_input(
        "Type an industry",
        value="Local services",
        help="You can enter a custom category; Google Places will search for that phrase.",
        key="custom_industry",
    )
    if industry_choice == "Other / type your own"
    else industry_choice
)
company_website = st.sidebar.text_input(
    "Your website (optional)",
    value="",
    placeholder="https://yourbusiness.com",
)

st.sidebar.divider()
st.sidebar.subheader("Add a competitor")

with st.sidebar.form("add_competitor_form", clear_on_submit=True):
    new_name = st.text_input("Competitor name")
    new_website = st.text_input("Competitor website")
    add_clicked = st.form_submit_button(
        "Add competitor",
        use_container_width=True,
    )

    if add_clicked:
        if not new_name.strip() or not new_website.strip():
            st.sidebar.error("Enter both a business name and website.")
        elif any(
            item["Business"].casefold() == new_name.strip().casefold()
            for item in st.session_state.competitors
        ):
            st.sidebar.warning("That competitor is already listed.")
        else:
            st.session_state.competitors.append({
                "Business": new_name.strip(),
                "Website": new_website.strip(),
            })
            st.session_state.results = None
            st.rerun()

if st.sidebar.button("Clear competitor list", use_container_width=True):
    st.session_state.competitors = []
    st.session_state.results = None
    st.rerun()


# ---------------------------------------------------------
# MAIN DASHBOARD
# ---------------------------------------------------------

st.markdown(
    """
    <div class="hero-card">
      <div class="hero-kicker">Local market research</div>
      <h1>Competitor Analysis Agent</h1>
      <p>Compare public website signals and find practical areas to investigate.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info(
    "Competitor discovery uses Google Places API (New) when GOOGLE_PLACES_API_KEY "
    "is configured. Google Cloud billing is required and requests may incur "
    "charges. Without a key, discovery makes no live request. Add real competitors "
    "before comparing their websites."
)

tab_overview, tab_competitors, tab_reports, tab_method = st.tabs([
    "Overview",
    "Competitors",
    "Reports",
    "Methodology",
])

with tab_overview:
    st.subheader("Analysis workspace")
    st.markdown('<p class="section-note">Start with your business details, add real competitors, then run a website comparison.</p>', unsafe_allow_html=True)

    left, right = st.columns([2, 1])
    with left:
        st.write(f"**Business:** {company or 'Not specified'}")
        st.write(f"**Location:** {location or 'Not specified'}")
        st.write(f"**Industry:** {industry or 'Not specified'}")
    with right:
        st.metric("Competitors listed", len(st.session_state.competitors))
        st.caption("Only submitted websites are analysed.")

    st.caption("🔒 Analyse public websites only. The app does not access private or logged-in pages.")

    if st.button("Run website analysis", type="primary", use_container_width=True):
        records = []
        competitors = st.session_state.competitors.copy()

        if company_website.strip():
            records.append(
                analyze_website(company or "My Business", company_website)
            )

        if not competitors and not records:
            st.warning("Add competitors in the Competitors tab, or enter your own website, before running an analysis.")
        else:
            progress = st.progress(0) if competitors else None
            status_text = st.empty()

            for index, item in enumerate(competitors):
                status_text.write(
                    f"Analysing {index + 1} of {len(competitors)}: "
                    f"{item['Business']}"
                )
                records.append(
                    analyze_website(item["Business"], item["Website"])
                )
                progress.progress((index + 1) / len(competitors))

            st.session_state.results = pd.DataFrame(records)
            status_text.success("Website analysis finished.")

    results = st.session_state.results

    if results is not None and not results.empty:
        st.divider()

        competitor_results = results[
            results["Business"] != (company or "My Business")
        ].copy()

        valid_scores = pd.to_numeric(
            competitor_results["Website Score"], errors="coerce"
        ).dropna()

        col1, col2, col3 = st.columns(3)
        col1.metric("Websites checked", len(results))
        col2.metric("Successfully analysed", int(
            (results["Status"] == "Analysed").sum()
        ))
        col3.metric(
            "Average website signal score",
            f"{valid_scores.mean():.1f}/100" if not valid_scores.empty else "N/A",
        )

        st.subheader("Competitor comparison")
        display_columns = [
            "Business", "Website", "Status", "HTTPS",
            "Website Score", "Score Coverage",
        ]
        st.dataframe(
            results[display_columns],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Summary observations")
        for insight in generate_insights(competitor_results):
            st.write(f"• {insight}")

        chart_data = results.dropna(subset=["Website Score"]).copy()
        if not chart_data.empty:
            chart_data["Website Score"] = pd.to_numeric(
                chart_data["Website Score"]
            )
            fig = px.bar(
                chart_data,
                x="Business",
                y="Website Score",
                color="Website Score",
                range_y=[0, 100],
                title="Preliminary website signal score",
                hover_data=["Website", "Score Coverage", "Status"],
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Evidence and findings")
        for _, row in results.iterrows():
            with st.expander(str(row["Business"])):
                st.write(f"**Status:** {row['Status']}")
                st.write(f"**Evidence:** {row['Evidence']}")
                st.write(f"**Source checked:** {row['Source Checked At']}")

                if row["Status"] == "Analysed":
                    gaps = []
                    if not row["Title"]:
                        gaps.append("No detectable page title")
                    if not row["Meta Description"]:
                        gaps.append("No detectable meta description")
                    if row["H1 Count"] != 1:
                        gaps.append("Heading structure may need review")
                    if row["Contact Signal"] is False:
                        gaps.append("No obvious contact signal detected")

                    if gaps:
                        st.write("**Potential checks to investigate:**")
                        for gap in gaps:
                            st.write(f"- {gap}")
                    else:
                        st.write(
                            "The basic checks passed. This does not guarantee "
                            "search performance or website quality."
                        )



with tab_competitors:
    st.subheader("Competitor discovery")

    st.caption(
        "Find local businesses, review their website URLs, then add them to your comparison."
    )

    st.info("Google Places searches require a configured API key and may incur charges. You can also add businesses manually or import a CSV below.")

    discovery_limit = st.slider(
        "Maximum businesses to find",
        min_value=1,
        max_value=20,
        value=10,
        key="discovery_limit",
    )

    if st.button("Discover competitors", type="primary"):
        search_location = location.strip()

        with st.spinner("Searching Google Places..."):
            try:
                discovered = discover_competitors(
                    location=search_location,
                    industry=industry,
                    limit=discovery_limit,
                )

                if not discovered:
                    st.warning(
                        "No named businesses were found. "
                        "Try another supported industry or location."
                    )
                else:
                    discovered_df = pd.DataFrame(discovered)
                    st.session_state["discovered_competitors"] = discovered_df
                    websites_found = int(discovered_df["Website"].fillna("").astype(str).str.strip().ne("").sum())
                    st.success(f"Found {len(discovered_df)} businesses · {websites_found} with a website to analyse.")

            except (RuntimeError, ValueError) as exc:
                message = str(exc)
                if "could not be reached" in message.casefold():
                    st.error("Google Places could not be reached. Check your internet connection and try again; a timeout alone does not mean your API key is wrong.")
                    with st.expander("Technical details"):
                        st.code(message)
                else:
                    st.error(message)
                st.caption("You can add businesses manually or import a CSV below while discovery is unavailable.")

    discovered_df = st.session_state.get("discovered_competitors")

    if discovered_df is not None and not discovered_df.empty:
        st.dataframe(discovered_df, use_container_width=True, hide_index=True)

        with_websites = discovered_df[
            discovered_df["Website"].fillna("").astype(str).str.strip() != ""
        ]

        without_websites = len(discovered_df) - len(with_websites)

        if without_websites:
            st.caption(
                f"{without_websites} businesses have no website listed "
                "in the public data and cannot yet be analysed by URL."
            )

        if st.button("Add businesses with websites", type="primary", use_container_width=True):
            existing_names = {
                item["Business"].strip().casefold()
                for item in st.session_state.competitors
            }

            added = 0

            for _, row in with_websites.iterrows():
                name = str(row["Business"]).strip()
                website = str(row["Website"]).strip()

                if name and name.casefold() not in existing_names:
                    st.session_state.competitors.append({
                        "Business": name,
                        "Website": website,
                    })
                    existing_names.add(name.casefold())
                    added += 1

            st.session_state.results = None

            if added:
                st.success(f"Added {added} new competitors.")
                st.rerun()
            else:
                st.info(
                    "No new competitors with websites were available "
                    "to add. They may already be in your list."
                )

    st.divider()
    st.subheader("Your comparison list")
    st.caption("Edit the names and URLs below, or use the CSV uploader to add several at once.")


    competitor_df = pd.DataFrame(
        st.session_state.competitors, columns=["Business", "Website"]
    )
    edited_df = st.data_editor(
        competitor_df,
        num_rows="dynamic",
        use_container_width=True,
        key="competitor_editor",
    )

    if st.button("Save competitor list"):
        cleaned = edited_df.fillna("")
        cleaned["Business"] = cleaned["Business"].astype(str).str.strip()
        cleaned["Website"] = cleaned["Website"].astype(str).str.strip()
        cleaned = cleaned[
            (cleaned["Business"] != "") & (cleaned["Website"] != "")
        ]
        cleaned = cleaned.drop_duplicates(
            subset=["Business"], keep="first"
        )
        st.session_state.competitors = cleaned.to_dict("records")
        st.session_state.results = None
        st.success("Competitor list saved. Run the analysis again.")

    uploaded_csv = st.file_uploader(
        "Or import competitors from CSV",
        type=["csv"],
        help="CSV must contain Business and Website columns.",
    )

    if uploaded_csv is not None:
        try:
            uploaded_df = pd.read_csv(uploaded_csv)
            uploaded_df.columns = [
                str(column).strip() for column in uploaded_df.columns
            ]

            if {"Business", "Website"}.issubset(uploaded_df.columns):
                st.dataframe(uploaded_df.head(10), use_container_width=True)

                if st.button("Import CSV competitors"):
                    imported = uploaded_df[["Business", "Website"]].fillna("")
                    imported["Business"] = imported["Business"].astype(str).str.strip()
                    imported["Website"] = imported["Website"].astype(str).str.strip()
                    imported = imported[
                        (imported["Business"] != "")
                        & (imported["Website"] != "")
                    ].drop_duplicates(subset=["Business"])

                    st.session_state.competitors = imported.to_dict("records")
                    st.session_state.results = None
                    st.success("CSV imported. Open Overview to run analysis.")
            else:
                st.error("CSV needs columns named Business and Website.")
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")


with tab_reports:
    st.subheader("Export your analysis")

    if st.session_state.results is None:
        st.info("Run website analysis in the Overview tab before exporting.")
    else:
        export_df = st.session_state.results.copy()
        for column in export_df.columns:
            export_df[column] = export_df[column].map(safe_csv_cell)

        st.download_button(
            "Download results as CSV",
            data=export_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="competitor_analysis.csv",
            mime="text/csv",
            use_container_width=True,
        )

        pdf_bytes = make_pdf(
            company or "My Business",
            location,
            industry,
            export_df,
        )

        st.download_button(
            "Download analysis report as PDF",
            data=pdf_bytes,
            file_name="competitor_analysis_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


with tab_method:
    st.subheader("How this version works")

    st.markdown(
        """
        **Competitor discovery:** Google Places API (New) Text Search, if a key is configured in `.env`. Requests ask for business name, address, website and location only. Google Cloud billing is required and charges may apply. Without a key, the app makes no live request.

        **Website data source:** publicly accessible website pages entered by the user.

        **Analysis:** Python requests and BeautifulSoup extract a small set of
        observable website signals.

        **Score:** the percentage of available checks that pass. Checks that
        cannot be measured are excluded from the denominator. The coverage
        column shows how many of six signals were available.

        **Interpretation:** this is a preliminary website signal score, not a
        comprehensive competitive-strength score.

        **Not currently measured:** Google search rankings, keyword volumes,
        Google Business Profile reviews, advertising spend, Meta commercial ad
        coverage, actual traffic, conversion rates or market share.

        **Data limitations:** website content can change, block automated
        requests, or vary by device and location. A failed request does not
        necessarily mean a business has a poor website.

        **Privacy and safety:** the app does not request credentials or scrape
        logged-in pages. Website requests use timeouts and reject private IP
        addresses. Only use public websites you are authorised to access.
        """
    )

st.caption(
    "Competitor Analysis Agent · Student project · "
    "Scores are heuristic indicators, not verified market rankings."
)
