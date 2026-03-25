"""
Tailoring Engine v2
Analyzes a job description against the base resume and generates
per-section suggestions that the user can approve, reject, or edit.
"""

import hashlib
import json
import os
import sys

import anthropic


BANNED_WORDS = [
    "leverage", "leveraging", "leveraged",
    "spearhead", "spearheading", "spearheaded",
    "cutting-edge", "cutting edge",
    "synergy", "synergize",
    "utilize", "utilizing",
    "innovative", "innovate",
    "passionate",
    "dynamic",
    "results-oriented",
    "self-starter",
    "go-getter",
    "think outside the box",
    "paradigm",
    "disrupt", "disruptive",
    "best-in-class",
    "world-class",
    "game-changer",
    "move the needle",
    "circle back",
    "deep dive",
    "robust",
    "seamlessly",
    "holistic",
    "aligns perfectly",
    "perfect fit",
    "ideal candidate",
    "uniquely positioned",
    "I'm excited to", "I'm thrilled to", "I'm eager to",
    "brings valuable", "well-positioned", "strong foundation",
    "proven ability", "track record of", "passion for", "dedicated to",
]

# Module-level cache for condensed resume summaries (keyed by MD5 of JSON)
_resume_summary_cache: dict = {"hash": None, "summary": None}



ANALYSIS_PROMPT = """You are a resume tailoring expert. You help job seekers adjust their resume to better match specific job descriptions.

CRITICAL RULES:
1. Write like a human professional. No corporate buzzwords, no filler.
2. NEVER use em dashes (the long dash). Use commas, periods, or rewrite the sentence.
3. NEVER use these words/phrases: {banned_words}
4. Keep all facts truthful. Only reframe and emphasize, never fabricate experience.
5. Be specific and concrete. Numbers, tools, and outcomes are good.
6. Match the tone of the existing resume. It is direct and professional, not flashy.
7. NEVER describe experience as something it wasn't. If the candidate worked in digital media production, do not call it "mission-critical infrastructure" or "defense-relevant" unless it actually was.
8. If the candidate is making a career transition, acknowledge it directly in the summary. Frame it as a strength (diverse background, transferable skills), not something to hide.
9. For experience bullets, only reframe language to highlight transferable skills. Do NOT add responsibilities or technical terms the candidate did not actually perform. "Maintained shared production environments" should NOT become "managed enterprise network infrastructure."
10. match_score_before and match_score_after must be realistic. If the candidate does not meet hard requirements (years of specific experience, specific certifications), the score must reflect that. Never inflate scores to make a poor fit look good.
11. Always preserve the "Seeking a [role type]" line in the summary so recruiters immediately understand the candidate's intent.
12. When generating experience bullet suggestions, check that your suggested rewrites do not repeat phrasing or meaning already used in other bullets across the resume. Each bullet should make a unique point. If two bullets would end up saying the same thing, only suggest changing one of them.

Analyze this job description against the candidate's resume and return suggestions as JSON.

Return ONLY valid JSON with this exact structure (no markdown, no backticks, no commentary):
{{
  "company": "extracted company name",
  "role": "extracted role title",
  "match_score_before": 72,
  "match_score_after": 88,
  "section_scores": {{
    "summary": {{ "before": 65, "after": 85, "reasoning": "why this score changed" }},
    "skills": {{ "before": 70, "after": 90, "reasoning": "why this score changed" }},
    "experience": {{ "before": 75, "after": 85, "reasoning": "why this score changed" }}
  }},
  "summary_suggestion": {{
    "original": "the current summary text",
    "suggested": "rewritten summary targeting this role",
    "reasoning": "brief explanation of what changed and why"
  }},
  "skills_suggestion": {{
    "original": ["current skills list"],
    "suggested": ["reordered and adjusted skills list, prioritize JD matches, keep roughly same count"],
    "added": ["skills from JD that candidate has but are not listed"],
    "removed": ["skills least relevant to this role that were swapped out"],
    "reasoning": "brief explanation"
  }},
  "experience_suggestions": [
    {{
      "job_index": 0,
      "job_title": "the job title",
      "bullet_index": 0,
      "original": "original bullet text",
      "suggested": "rewritten bullet text",
      "reasoning": "why this change helps"
    }}
  ],
  "keywords_matched": ["JD keywords that already appear in the resume"],
  "keywords_missing": ["JD keywords the candidate could address"],
  "ats_tips": ["specific tips for getting past ATS for this role"],
  "hard_requirements_missing": ["requirements the candidate definitely does not meet, like 10+ years of specific experience they don't have"],
  "worth_noting": ["requirements that might be flexible or sponsorable, like security clearance, preferred certifications, or nice-to-have qualifications the candidate is close to"]
}}

For "hard_requirements_missing": list genuine gaps that would likely disqualify the candidate (e.g. the role needs 10 years of network engineering and the candidate has none). For "worth_noting": list things that could go either way — security clearances (many employers sponsor), preferred but not required certifications, or experience ranges the candidate is close to. Never put clearance requirements in hard_requirements_missing since many employers will sponsor.

IMPORTANT for experience_suggestions:
- Only suggest changes for bullets that would meaningfully benefit from rewording.
- Do NOT suggest changes for every bullet. If a bullet is already good, skip it.
- Focus on the top 3-5 highest impact changes.

CANDIDATE RESUME:
{resume}

JOB DESCRIPTION:
{job_description}"""


class TailoringEngine:
    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-6-20250217", model_light: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.model_light = model_light
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def analyze(self, resume: dict, job_description: str) -> dict:
        """Analyze JD against resume and return structured suggestions."""
        prompt = ANALYSIS_PROMPT.format(
            banned_words=", ".join(BANNED_WORDS),
            resume=json.dumps(resume, indent=2),
            job_description=job_description
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        text_block = next(b for b in response.content if b.type == "text")
        raw = text_block.text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]

        result = json.loads(raw)
        result = self._scrub_banned_words(result)
        return result

    def get_resume_summary(self, resume_data: dict) -> str:
        """Return a condensed text summary of the resume (~500 tokens). Cached by content hash."""
        resume_str = json.dumps(resume_data, sort_keys=True)
        resume_hash = hashlib.md5(resume_str.encode()).hexdigest()

        if _resume_summary_cache["hash"] == resume_hash and _resume_summary_cache["summary"]:
            return _resume_summary_cache["summary"]

        name = resume_data.get("name", "")
        summary = resume_data.get("professional_summary", "")
        skills = resume_data.get("core_skills", [])
        experience = resume_data.get("experience", [])
        certs = resume_data.get("certifications", [])

        exp_lines = []
        for exp in experience:
            title = exp.get("title", "")
            company = exp.get("company", "")
            dates = exp.get("dates", "")
            exp_lines.append(f"{title} at {company} ({dates})")
            for b in exp.get("bullets", [])[:2]:
                exp_lines.append(f"  - {b}")

        compact = (
            f"Name: {name}\n\n"
            f"Summary: {summary}\n\n"
            f"Skills: {', '.join(skills[:20])}\n\n"
            f"Experience:\n{chr(10).join(exp_lines)}\n\n"
            f"Certifications: {', '.join(certs)}"
        )

        # If already short enough, cache and return as-is
        if len(compact) < 2000:
            _resume_summary_cache["hash"] = resume_hash
            _resume_summary_cache["summary"] = compact
            return compact

        prompt = (
            "Condense this resume into a plain-text summary of no more than 500 tokens. "
            "Include: name, total years of experience, key skills, job titles and companies, "
            "certifications, and career transition context if relevant. Be factual and specific.\n\n"
            f"RESUME:\n{compact}\n\n"
            "Return only the condensed summary text, no JSON, no commentary."
        )

        response = self.client.messages.create(
            model=self.model_light,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        condensed = response.content[0].text.strip()
        _resume_summary_cache["hash"] = resume_hash
        _resume_summary_cache["summary"] = condensed
        return condensed

    def regenerate_section(
        self,
        section: str,
        original: str,
        previous_suggestion: str,
        job_description: str,
        user_feedback: str = "",
    ) -> dict:
        """Regenerate a single section suggestion with optional user feedback."""
        banned = ", ".join(BANNED_WORDS)

        feedback_block = ""
        if user_feedback.strip():
            feedback_block = f"""
The user had this feedback about the previous suggestion or provided a partial rewrite:
\"{user_feedback}\"

If this looks like a partial rewrite, use it as the basis and refine it. Keep their intent and phrasing where possible, just clean it up and make sure it fits the job description. If it is general feedback (e.g. "less aggressive"), apply that direction to a fresh attempt."""

        if section == "summary":
            prompt = f"""You are a resume tailoring expert. Regenerate ONLY the professional summary for a resume targeting the job description below.

CRITICAL RULES:
- Write like a human professional. No buzzwords, no filler.
- NEVER use em dashes. Use commas or periods instead.
- NEVER use these words: {banned}
- Keep all facts truthful. Only reframe and emphasize.
- Preserve the "Seeking a [role type]" line so recruiters understand the candidate's intent.
- If the candidate is making a career transition, acknowledge it directly as a strength.{feedback_block}

ORIGINAL SUMMARY:
{original}

PREVIOUS SUGGESTION (the one the user wants changed):
{previous_suggestion}

JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON, no markdown, no extra text:
{{"suggested": "the new summary text", "reasoning": "what changed and why"}}"""

        elif section == "skills":
            prompt = f"""You are a resume tailoring expert. Regenerate ONLY the skills list for a resume targeting the job description below.

CRITICAL RULES:
- Keep all facts truthful. Only reorder and add skills the candidate actually has.
- No buzzwords, no fabricated skills.
- NEVER use these words: {banned}{feedback_block}

ORIGINAL SKILLS (comma-separated or JSON array):
{original}

PREVIOUS SUGGESTION (the one the user wants changed):
{previous_suggestion}

JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON, no markdown, no extra text:
{{"suggested": ["skill1", "skill2"], "added": ["newly added skills"], "removed": ["removed skills"], "reasoning": "what changed and why"}}"""

        else:  # experience_bullet
            prompt = f"""You are a resume tailoring expert. Regenerate ONLY this single experience bullet for a resume targeting the job description below.

CRITICAL RULES:
- Write like a human professional. No buzzwords, no filler.
- NEVER use em dashes. Use commas or periods instead.
- NEVER use these words: {banned}
- Keep all facts truthful. Only reframe language to highlight transferable skills.
- Do NOT add responsibilities or technical terms the candidate did not actually perform.
- Be specific and concrete. Numbers, tools, outcomes.{feedback_block}

ORIGINAL BULLET:
{original}

PREVIOUS SUGGESTION (the one the user wants changed):
{previous_suggestion}

JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON, no markdown, no extra text:
{{"suggested": "the new bullet text", "reasoning": "what changed and why"}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        text_block = next(b for b in response.content if b.type == "text")
        raw = text_block.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]

        return json.loads(raw)

    def generate_cover_letter(
        self,
        resume_data: dict,
        job_description: str,
        company: str,
        role: str,
        length: str = "standard",
        tone: str = "professional",
        user_feedback: str = "",
        current_text: str = "",
    ) -> dict:
        """Generate or refine a cover letter for the given resume and job description."""
        banned = ", ".join(BANNED_WORDS)

        length_map = {
            "short": "around 150 words",
            "standard": "around 200 words",
            "long": "around 300 words",
        }
        length_target = length_map.get(length, "around 200 words")

        tone_map = {
            "professional": "professional and direct",
            "conversational": "warm and conversational while staying professional",
            "confident": "confident and assertive, with strong declarative statements",
            "formal": "formal and structured",
        }
        tone_desc = tone_map.get(tone, "professional and direct")

        if current_text.strip() and (user_feedback.strip() or length != "standard" or tone != "professional"):
            task_block = f"""Refine the following existing cover letter draft. Keep the candidate's voice and intent. Apply the adjustments described below.

EXISTING DRAFT:
{current_text}"""
        else:
            task_block = "Write a cover letter from scratch for this candidate and role."

        feedback_block = ""
        if user_feedback.strip():
            feedback_block = f"\nUser direction: {user_feedback}\nIf this is a partial rewrite, use it as the basis and refine it. Keep their intent and phrasing where possible, just clean it up."

        name = resume_data.get("name", "the candidate")
        resume_summary = self.get_resume_summary(resume_data)

        prompt = f"""You are writing a cover letter for a real person applying to a real job. It needs to sound like a human wrote it, not an AI. {task_block}

STRUCTURE (follow this exactly):

Paragraph 1 (2-3 sentences):
- State the role you're applying for
- One genuine, specific reason you're interested in this company or role
- If the company has a strong identity (automotive, defense, healthcare, etc.), include one sentence showing awareness of that domain. Keep it professional, not fan-based.

Paragraph 2 (3-4 sentences):
- Your most relevant hands-on experience
- Focus on troubleshooting, supporting systems, or solving real problems
- Be specific about what you actually did, not what you "oversaw" or "led"

Paragraph 3 (2-3 sentences):
- Your career transition and current certifications/training
- Use honest language: "familiar with", "developing experience with", "currently studying" for things you're still learning
- Keep it brief, this isn't the main sell

Paragraph 4 (2-3 sentences):
- Why you'd be good to work with (communication, teamwork, reliability)
- Connect to something specific in the JD

Closing (1 sentence):
- Short and friendly. "I'd welcome the chance to talk more about how I can help your team." or similar. No corporate sign-offs.

HARD RULES:
1. Total length: {length_target}. Not longer.
2. Keep sentences under 20-25 words. If a sentence has a comma and an "and" and another comma, it's too long. Split it.
3. Do NOT repeat resume bullet points. The cover letter should add context and personality, not summarize the resume.
4. Do NOT use compound sentences that stack multiple ideas. One idea per sentence.
5. Do NOT exaggerate experience. Use "familiar with" or "developing experience with" for skills still being learned. Use "hands-on experience with" only for things actually done on the job.
6. Do NOT include personal stories, hobbies, or casual details unless directly relevant to the company's domain.
7. Do NOT repeat the same idea in multiple paragraphs.
8. Sound like someone a hiring manager would want on their team: competent, clear, and easy to work with.
9. The reader should think: "This person can troubleshoot, communicate, and won't be a pain to work with."

TONE RULES:
1. Write like a real person writing an email to someone they respect, not a press release or corporate announcement.
2. NEVER use em dashes. Use commas or periods instead.
3. NEVER use these words/phrases: {banned}
4. Keep all facts truthful. Only highlight real experience.
5. Tone: {tone_desc}.
6. If the candidate is making a career transition, acknowledge it directly as a strength, not something to hide.
7. Start sentences with "I" sometimes. Real people do this. Don't contort sentences to avoid it.
8. NEVER start a paragraph with the company name followed by a grand statement about their mission. That's the most obvious AI tell in cover letters.
9. Don't use "I bring X years of experience" — just describe what you did.
10. Avoid stacking more than two skills or qualifications in a single sentence. It sounds like a list pretending to be prose.
11. Don't mirror the exact language from the job description back at the recruiter. They wrote it, they know what it says. Use your own words.
12. Do NOT start with "I am writing to" or any of the banned phrases above. Open with something specific and real.
13. Always start the letter body with "Dear Hiring Manager," on its own line, unless a specific hiring manager name is provided.
14. When referencing skills, integrate them naturally into context — write "used Jira to track sprint progress" not just "Jira".
15. Do NOT include a closing line like "Sincerely" or the candidate's name — that will be added separately by the PDF generator.{feedback_block}

CANDIDATE: {name}

RESUME BACKGROUND:
{resume_summary}

COMPANY: {company}
ROLE: {role}

JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON, no markdown, no extra text:
{{"cover_letter": "the full cover letter text with paragraph breaks as \\n\\n", "reasoning": "brief explanation of the approach"}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        text_block = next(b for b in response.content if b.type == "text")
        raw = text_block.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]

        return json.loads(raw)

    def _scrub_banned_words(self, result: dict) -> dict:
        """Flag any suggestions that accidentally contain banned words."""
        def check_text(text: str) -> list:
            found = []
            lower = text.lower()
            for word in BANNED_WORDS:
                if word in lower:
                    found.append(word)
            if "\u2014" in text:
                found.append("em dash detected")
            return found

        if "summary_suggestion" in result:
            issues = check_text(result["summary_suggestion"].get("suggested", ""))
            if issues:
                result["summary_suggestion"]["warnings"] = issues

        for exp in result.get("experience_suggestions", []):
            issues = check_text(exp.get("suggested", ""))
            if issues:
                exp["warnings"] = issues

        return result
