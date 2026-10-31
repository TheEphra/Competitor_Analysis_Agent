"""Local Flask web interface for Competitor Analysis Agent."""

from __future__ import annotations

import csv
import io
import os
import secrets
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, flash, g, make_response, redirect, render_template, request, session, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.competitor_discovery import INDUSTRY_QUERIES, discover_competitors
from src.insights_engine import generate_insights
from src.website_analyzer import analyze_website

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=10 * 1024 * 1024)

# This is a local, single-process app. The browser cookie stores only a random
# workspace ID; business data stays in the Python process, not in the cookie.
WORKSPACES: dict[str, dict] = {}


def fresh_workspace() -> dict:
    return {
        "profile": {"company": "", "location": "", "industry": "Salon", "website": ""},
        "competitors": [],
        "discovered": [],
        "results": [],
        "csrf": secrets.token_urlsafe(24),
    }


@app.before_request
def load_workspace() -> None:
    workspace_id = session.get("workspace_id")
    if not workspace_id:
        workspace_id = secrets.token_urlsafe(24)
        session["workspace_id"] = workspace_id
    g.workspace = WORKSPACES.setdefault(workspace_id, fresh_workspace())
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        if not secrets.compare_digest(submitted, g.workspace["csrf"]):
            flash("Your form expired. Please try again.", "error")
            return redirect(url_for("index"))


@app.context_processor
def inject_template_values() -> dict:
    return {"csrf_token": getattr(g, "workspace", {}).get("csrf", "")}


@app.get("/")
def index():
    state = g.workspace
    scores = [row.get("Website Score") for row in state["results"] if isinstance(row.get("Website Score"), (int, float))]
    return render_template(
        "index.html",
        profile=state["profile"],
        competitors=state["competitors"],
        discovered=state["discovered"],
        results=state["results"],
        insights=generate_insights(pd.DataFrame(state["results"])) if state["results"] else [],
        industries=sorted({key.title() for key in INDUSTRY_QUERIES}, key=str.casefold),
        is_custom=bool(state["profile"]["industry"]) and state["profile"]["industry"].casefold() not in {key.casefold() for key in INDUSTRY_QUERIES},
        successful_count=sum(row.get("Status") == "Analysed" for row in state["results"]),
        average_score=round(sum(scores) / len(scores)) if scores else None,
        analyzed_at=datetime.now().astimezone().strftime("%d %b %Y, %H:%M"),
    )


@app.post("/profile")
def save_profile():
    state = g.workspace
    industry = request.form.get("industry", "").strip()
    if industry == "__custom__":
        industry = request.form.get("custom_industry", "").strip()
    state["profile"] = {
        "company": request.form.get("company", "").strip(),
        "location": request.form.get("location", "").strip(),
        "industry": industry,
        "website": request.form.get("website", "").strip(),
    }
    flash("Business details saved.", "success")
    return redirect(url_for("index") + "#workspace")


@app.post("/discover")
def discover():
    profile = g.workspace["profile"]
    location = request.form.get("location", profile.get("location", "")).strip()
    industry = request.form.get("industry", profile.get("industry", "")).strip()
    try:
        found = discover_competitors(location, industry, int(request.form.get("limit", 10)))
        g.workspace["discovered"] = found
        if found:
            websites = sum(bool(item.get("Website")) for item in found)
            flash(f"Found {len(found)} businesses, {websites} with a website listed.", "success")
        else:
            flash("No businesses matched that search. Try a nearby town or a broader category.", "info")
    except (RuntimeError, ValueError) as exc:
        message = str(exc)
        if "could not be reached" in message.casefold():
            flash("Google Places could not be reached. Check your internet connection and try again. A timeout alone does not mean your API key is wrong.", "error")
        else:
            flash(message, "error")
    return redirect(url_for("index") + "#discovery")


@app.post("/add-discovered")
def add_discovered():
    state = g.workspace
    selected = set(request.form.getlist("place_index"))
    known = {item["Business"].casefold() for item in state["competitors"]}
    added = 0
    for index, item in enumerate(state["discovered"]):
        if str(index) not in selected or not item.get("Website"):
            continue
        name = item["Business"].strip()
        if name.casefold() not in known:
            state["competitors"].append({"Business": name, "Website": item["Website"]})
            known.add(name.casefold())
            added += 1
    state["results"] = []
    flash(f"Added {added} business(es) to your comparison list." if added else "Select businesses with websites that are not already on your list.", "success" if added else "info")
    return redirect(url_for("index") + "#competitors")


@app.post("/competitors/add")
def add_competitor():
    name = request.form.get("business", "").strip()
    website = request.form.get("website", "").strip()
    if not name or not website:
        flash("Enter both the business name and its public website.", "error")
    elif any(item["Business"].casefold() == name.casefold() for item in g.workspace["competitors"]):
        flash("That business is already on your list.", "info")
    else:
        g.workspace["competitors"].append({"Business": name, "Website": website})
        g.workspace["results"] = []
        flash(f"{name} added to your comparison list.", "success")
    return redirect(url_for("index") + "#competitors")


@app.post("/competitors/delete")
def delete_competitor():
    index = request.form.get("index", "")
    if index.isdigit() and int(index) < len(g.workspace["competitors"]):
        removed = g.workspace["competitors"].pop(int(index))
        g.workspace["results"] = []
        flash(f"Removed {removed['Business']}.", "info")
    return redirect(url_for("index") + "#competitors")


@app.post("/competitors/clear")
def clear_competitors():
    g.workspace["competitors"] = []
    g.workspace["results"] = []
    flash("Comparison list cleared.", "info")
    return redirect(url_for("index") + "#competitors")


@app.post("/competitors/import")
def import_competitors():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Choose a CSV file first.", "error")
        return redirect(url_for("index") + "#competitors")
    try:
        content = io.StringIO(upload.stream.read().decode("utf-8-sig"), newline="")
        reader = csv.DictReader(content)
        mapping = {key.strip().casefold(): key for key in (reader.fieldnames or []) if key}
        if not {"business", "website"}.issubset(mapping):
            raise ValueError("CSV needs columns named Business and Website.")
        incoming, seen = [], set()
        for row in reader:
            name = (row.get(mapping["business"]) or "").strip()
            website = (row.get(mapping["website"]) or "").strip()
            if name and website and name.casefold() not in seen:
                incoming.append({"Business": name, "Website": website})
                seen.add(name.casefold())
        g.workspace["competitors"] = incoming
        g.workspace["results"] = []
        flash(f"Imported {len(incoming)} business(es) from CSV.", "success")
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        flash(f"Could not import that file: {exc}", "error")
    return redirect(url_for("index") + "#competitors")


@app.post("/analyze")
def analyze():
    state = g.workspace
    profile = state["profile"]
    rows = []
    if profile.get("website"):
        rows.append(analyze_website(profile.get("company") or "Your business", profile["website"]))
    for item in state["competitors"]:
        rows.append(analyze_website(item["Business"], item["Website"]))
    if not rows:
        flash("Add competitors or enter your own website before running an analysis.", "error")
    else:
        state["results"] = rows
        done = sum(row.get("Status") == "Analysed" for row in rows)
        flash(f"Analysis complete: {done} of {len(rows)} websites returned usable results.", "success")
    return redirect(url_for("index") + "#results")


@app.get("/download.csv")
def download_csv():
    rows = g.workspace["results"]
    if not rows:
        flash("Run a website analysis before downloading a report.", "error")
        return redirect(url_for("index") + "#results")
    buffer = io.StringIO()
    columns = list(dict.fromkeys(key for row in rows for key in row))
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    response = make_response(buffer.getvalue().encode("utf-8-sig"))
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=competitor_analysis.csv"
    return response


@app.get("/download.pdf")
def download_pdf():
    rows = g.workspace["results"]
    if not rows:
        flash("Run a website analysis before downloading a report.", "error")
        return redirect(url_for("index") + "#results")
    profile = g.workspace["profile"]
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=28, leftMargin=28, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = [Paragraph("Competitor Analysis Report", styles["Title"]), Spacer(1, 8),
             Paragraph(f"Business: {profile.get('company') or 'Not specified'}", styles["Normal"]),
             Paragraph(f"Location: {profile.get('location') or 'Not specified'} · Industry: {profile.get('industry') or 'Not specified'}", styles["Normal"]),
             Paragraph(f"Generated: {datetime.now().astimezone().strftime('%d %b %Y, %H:%M %Z')}", styles["Normal"]), Spacer(1, 14)]
    data = [["Business", "Website", "Status", "Score", "Coverage", "HTTPS"]]
    for row in rows:
        score = row.get("Website Score")
        data.append([str(row.get("Business", ""))[:28], str(row.get("Website", ""))[:48],
                     str(row.get("Status", "")), "N/A" if score is None else f"{score}/100",
                     str(row.get("Coverage", "")), "Yes" if row.get("HTTPS") else "No"])
    table = Table(data, repeatRows=1, colWidths=[110, 220, 90, 70, 80, 45])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#292044")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                               ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("GRID", (0, 0), (-1, -1), .35, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(table)
    story.extend([Spacer(1, 12), Paragraph("These preliminary checks describe visible website signals. They do not measure traffic, reputation, market share, or overall business strength.", styles["BodyText"])])
    doc.build(story)
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=competitor_analysis_report.pdf"
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
