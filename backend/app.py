"""
Resume Tailoring Agent v2 - FastAPI Backend
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import base64
import io

from dotenv import load_dotenv
load_dotenv()

import anthropic
import pdfplumber
import yaml
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, Response

from backend.tailoring_engine import TailoringEngine
from backend.pdf_generator import generate_resume_pdf, generate_cover_letter_pdf

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
RESUME_PATH = BASE_DIR / "data" / "base_resume.json"
EXAMPLE_RESUME_PATH = BASE_DIR / "data" / "base_resume_example.json"
PROFILES_DIR = BASE_DIR / "data" / "profiles"
HISTORY_DIR = BASE_DIR / "history"

app = FastAPI(title="Resume Tailoring Agent")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_resume() -> dict:
    with open(RESUME_PATH) as f:
        return json.load(f)


def save_resume(data: dict):
    with open(RESUME_PATH, "w") as f:
        json.dump(data, f, indent=2)


@app.get("/api/resume")
async def get_resume():
    if not RESUME_PATH.exists():
        raise HTTPException(404, "Resume not found. Use /api/load-example or upload a PDF to get started.")
    return load_resume()


@app.post("/api/load-example")
async def load_example_resume():
    if not EXAMPLE_RESUME_PATH.exists():
        raise HTTPException(404, "Example resume file not found")
    shutil.copy(EXAMPLE_RESUME_PATH, RESUME_PATH)
    return load_resume()


@app.post("/api/resume")
async def update_resume(request: Request):
    data = await request.json()
    save_resume(data)
    return {"status": "ok"}


@app.post("/api/resume/upload-pdf")
async def upload_resume_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "File must be a PDF")

    pdf_bytes = await file.read()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    config = load_config()
    api_key = os.environ.get("ANTHROPIC_API_KEY") or \
              config.get("anthropic", {}).get("api_key", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6-20250217")
    client = anthropic.Anthropic(api_key=api_key)

    prompt = """Extract this resume into a structured JSON object with exactly these fields:
{
  "name": "Full Name",
  "contact": {"email": "", "phone": "", "website": "", "portfolio": ""},
  "professional_summary": "...",
  "core_skills": ["skill1", "skill2"],
  "experience": [
    {
      "title": "Job Title",
      "company": "Company Name",
      "dates": "Start – End",
      "bullets": ["bullet 1", "bullet 2"]
    }
  ],
  "certifications": ["cert 1", "cert 2"],
  "education": [
    {"degree": "Degree Name", "school": "School Name"}
  ],
  "technical_projects": [
    {
      "name": "Project Name",
      "bullets": ["bullet 1", "bullet 2"]
    }
  ]
}

Return only valid JSON, no markdown fences, no extra text."""

    try:
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        parsed = json.loads(message.content[0].text)
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse AI response as JSON: {e}")
    except Exception as e:
        raise HTTPException(500, f"PDF parsing failed: {e}")

    save_resume(parsed)
    return parsed


@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "File must be a PDF")

    pdf_bytes = await file.read()

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        raise HTTPException(500, f"Failed to extract text from PDF: {e}")

    if not text.strip():
        raise HTTPException(400, "Could not extract any text from the PDF")

    config = load_config()
    api_key = os.environ.get("ANTHROPIC_API_KEY") or \
              config.get("anthropic", {}).get("api_key", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6-20250217")
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Extract the following resume text into a structured JSON object with exactly these fields:
{{
  "name": "Full Name",
  "contact": {{"email": "", "phone": "", "website": "", "portfolio": ""}},
  "professional_summary": "...",
  "core_skills": ["skill1", "skill2"],
  "experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "dates": "Start – End",
      "bullets": ["bullet 1", "bullet 2"]
    }}
  ],
  "certifications": ["cert 1", "cert 2"],
  "education": [
    {{"degree": "Degree Name", "school": "School Name"}}
  ],
  "technical_projects": [
    {{
      "name": "Project Name",
      "bullets": ["bullet 1", "bullet 2"]
    }}
  ]
}}

Return only valid JSON, no markdown fences, no extra text.

Resume text:
{text}"""

    try:
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        parsed = json.loads(message.content[0].text)
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse AI response as JSON: {e}")
    except Exception as e:
        raise HTTPException(500, f"Claude parsing failed: {e}")

    save_resume(parsed)
    return parsed


@app.post("/api/regenerate")
async def regenerate_section(request: Request):
    body = await request.json()
    section = body.get("section", "")
    original = body.get("original", "")
    previous_suggestion = body.get("previous_suggestion", "")
    job_description = body.get("job_description", "")
    user_feedback = body.get("user_feedback", "")

    if section not in ("summary", "skills", "experience_bullet"):
        raise HTTPException(400, "section must be 'summary', 'skills', or 'experience_bullet'")
    if not job_description.strip():
        raise HTTPException(400, "job_description is required")

    config = load_config()
    api_key = os.environ.get("ANTHROPIC_API_KEY") or \
              config.get("anthropic", {}).get("api_key", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6-20250217")
    model_light = config.get("anthropic", {}).get("model_light", "claude-haiku-4-5-20251001")
    engine = TailoringEngine(api_key=api_key, model=model, model_light=model_light)

    try:
        result = engine.regenerate_section(
            section=section,
            original=original,
            previous_suggestion=previous_suggestion,
            job_description=job_description,
            user_feedback=user_feedback,
        )
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse AI response: {e}")
    except Exception as e:
        raise HTTPException(500, f"Regeneration failed: {e}")

    return result


@app.post("/api/analyze")
async def analyze_job(request: Request):
    body = await request.json()
    job_description = body.get("job_description", "")

    if not job_description.strip():
        raise HTTPException(400, "Job description is required")

    config = load_config()
    resume = load_resume()

    api_key = os.environ.get("ANTHROPIC_API_KEY") or \
              config.get("anthropic", {}).get("api_key", "")

    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6-20250217")
    model_light = config.get("anthropic", {}).get("model_light", "claude-haiku-4-5-20251001")
    engine = TailoringEngine(api_key=api_key, model=model, model_light=model_light)

    try:
        suggestions = engine.analyze(resume, job_description)
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse AI response: {e}")
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")

    return suggestions


@app.post("/api/export-pdf")
async def export_pdf(request: Request):
    resume_data = await request.json()

    try:
        pdf_bytes = generate_resume_pdf(resume_data)
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {e}")

    # Save to history
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    company = resume_data.get("_meta", {}).get("company", "unknown")
    role = resume_data.get("_meta", {}).get("role", "unknown")
    slug = f"{timestamp}_{_slugify(company)}_{_slugify(role)}"

    hist_dir = HISTORY_DIR / slug
    hist_dir.mkdir(parents=True, exist_ok=True)
    (hist_dir / "resume.pdf").write_bytes(pdf_bytes)
    (hist_dir / "resume_data.json").write_text(json.dumps(resume_data, indent=2))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="resume_{slug}.pdf"'
        }
    )


@app.post("/api/cover-letter")
async def generate_cover_letter(request: Request):
    body = await request.json()
    resume_data = body.get("resume_data", {})
    job_description = body.get("job_description", "")
    company = body.get("company", "")
    role = body.get("role", "")
    length = body.get("length", "standard")
    tone = body.get("tone", "professional")
    user_feedback = body.get("user_feedback", "")
    current_text = body.get("current_text", "")

    if not job_description.strip():
        raise HTTPException(400, "job_description is required")

    config = load_config()
    api_key = os.environ.get("ANTHROPIC_API_KEY") or \
              config.get("anthropic", {}).get("api_key", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6-20250217")
    model_light = config.get("anthropic", {}).get("model_light", "claude-haiku-4-5-20251001")
    engine = TailoringEngine(api_key=api_key, model=model, model_light=model_light)

    try:
        result = engine.generate_cover_letter(
            resume_data=resume_data,
            job_description=job_description,
            company=company,
            role=role,
            length=length,
            tone=tone,
            user_feedback=user_feedback,
            current_text=current_text,
        )
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse AI response: {e}")
    except Exception as e:
        raise HTTPException(500, f"Cover letter generation failed: {e}")

    return result


@app.post("/api/export-cover-letter-pdf")
async def export_cover_letter_pdf(request: Request):
    body = await request.json()
    cover_letter_text = body.get("cover_letter", "")
    resume_data = body.get("resume_data", {})
    meta = body.get("_meta", {})
    hiring_manager = body.get("hiring_manager", "")
    closing_phrase = body.get("closing_phrase", "Sincerely,")
    closing_name = body.get("closing_name", "")
    closing_contact_lines = body.get("closing_contact_lines", None)

    if not cover_letter_text.strip():
        raise HTTPException(400, "cover_letter text is required")

    try:
        pdf_bytes = generate_cover_letter_pdf(
            cover_letter_text, resume_data, hiring_manager,
            closing_phrase, closing_name, closing_contact_lines,
        )
    except Exception as e:
        raise HTTPException(500, f"Cover letter PDF generation failed: {e}")

    # Save to history alongside resume if we have a slug
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    company = meta.get("company", "unknown")
    role = meta.get("role", "unknown")
    slug = f"{timestamp}_{_slugify(company)}_{_slugify(role)}"

    hist_dir = HISTORY_DIR / slug
    hist_dir.mkdir(parents=True, exist_ok=True)
    (hist_dir / "cover_letter.pdf").write_bytes(pdf_bytes)
    (hist_dir / "cover_letter.txt").write_text(cover_letter_text)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cover_letter_{slug}.pdf"'
        }
    )


@app.get("/api/history")
async def get_history():
    if not HISTORY_DIR.exists():
        return []
    entries = []
    for d in sorted(HISTORY_DIR.iterdir(), reverse=True):
        if d.is_dir():
            meta_file = d / "resume_data.json"
            meta = {}
            if meta_file.exists():
                with open(meta_file) as f:
                    data = json.load(f)
                    meta = data.get("_meta", {})
            entries.append({
                "id": d.name,
                "company": meta.get("company", ""),
                "role": meta.get("role", ""),
                "date": d.name[:10] if len(d.name) >= 10 else d.name,
            })
    return entries


@app.delete("/api/history")
async def clear_history():
    if HISTORY_DIR.exists():
        shutil.rmtree(HISTORY_DIR)
    HISTORY_DIR.mkdir(exist_ok=True)
    return {"status": "cleared"}


MAX_PROFILES = 5


def _list_profiles() -> list:
    profiles = []
    if PROFILES_DIR.exists():
        for f in sorted(PROFILES_DIR.glob("*.json")):
            with open(f) as fh:
                data = json.load(fh)
                data["filename"] = f.stem
                profiles.append(data)
    return profiles


@app.get("/api/profiles")
async def get_profiles():
    return _list_profiles()


@app.post("/api/profiles")
async def create_profile(request: Request):
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(PROFILES_DIR.glob("*.json"))
    if len(existing) >= MAX_PROFILES:
        raise HTTPException(400, f"Maximum of {MAX_PROFILES} profiles reached")

    body = await request.json()
    profile_name = body.get("profile_name", "").strip()
    if not profile_name:
        raise HTTPException(400, "profile_name is required")

    today = datetime.now().strftime("%Y-%m-%d")
    profile = {
        "profile_name": profile_name,
        "summary": body.get("summary", ""),
        "core_skills": body.get("core_skills", []),
        "bullet_overrides": body.get("bullet_overrides", {}),
        "target_roles": body.get("target_roles", []),
        "created": today,
        "last_used": today,
    }

    filename = _slugify(profile_name)
    path = PROFILES_DIR / f"{filename}.json"
    # Avoid collisions
    counter = 1
    while path.exists():
        path = PROFILES_DIR / f"{filename}_{counter}.json"
        counter += 1

    path.write_text(json.dumps(profile, indent=2))
    profile["filename"] = path.stem
    return profile


@app.put("/api/profiles/{filename}")
async def update_profile(filename: str, request: Request):
    path = PROFILES_DIR / f"{filename}.json"
    if not path.exists():
        raise HTTPException(404, "Profile not found")

    body = await request.json()
    existing = json.loads(path.read_text())
    existing.update({
        "profile_name": body.get("profile_name", existing.get("profile_name", "")),
        "summary": body.get("summary", existing.get("summary", "")),
        "core_skills": body.get("core_skills", existing.get("core_skills", [])),
        "bullet_overrides": body.get("bullet_overrides", existing.get("bullet_overrides", {})),
        "target_roles": body.get("target_roles", existing.get("target_roles", [])),
        "last_used": datetime.now().strftime("%Y-%m-%d"),
    })
    path.write_text(json.dumps(existing, indent=2))
    existing["filename"] = filename
    return existing


@app.delete("/api/profiles/{filename}")
async def delete_profile(filename: str):
    path = PROFILES_DIR / f"{filename}.json"
    if not path.exists():
        raise HTTPException(404, "Profile not found")
    path.unlink()
    return {"status": "deleted"}


@app.post("/api/profiles/duplicate/{filename}")
async def duplicate_profile(filename: str, request: Request):
    existing_profiles = list(PROFILES_DIR.glob("*.json"))
    if len(existing_profiles) >= MAX_PROFILES:
        raise HTTPException(400, f"Maximum of {MAX_PROFILES} profiles reached")

    path = PROFILES_DIR / f"{filename}.json"
    if not path.exists():
        raise HTTPException(404, "Profile not found")

    body = await request.json()
    new_name = body.get("profile_name", "").strip()

    source = json.loads(path.read_text())
    today = datetime.now().strftime("%Y-%m-%d")
    source["profile_name"] = new_name or source["profile_name"] + " (copy)"
    source["created"] = today
    source["last_used"] = today

    new_slug = _slugify(source["profile_name"])
    new_path = PROFILES_DIR / f"{new_slug}.json"
    counter = 1
    while new_path.exists():
        new_path = PROFILES_DIR / f"{new_slug}_{counter}.json"
        counter += 1

    new_path.write_text(json.dumps(source, indent=2))
    source["filename"] = new_path.stem
    return source


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    frontend_path = BASE_DIR / "frontend" / "index.html"
    if not frontend_path.exists():
        return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)
    return HTMLResponse(frontend_path.read_text())


def _slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")[:40]
