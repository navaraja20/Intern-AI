"""
InternAI – Streamlit Frontend
==============================
Communicates with FastAPI backend via HTTP requests.
Pages:
  🔐 Login / Register
  👤 Profile          (resume, LinkedIn, GitHub, skills)
  🚀 Optimize Job     (JD → tailored resume + cover letter + ATS)
  📁 History          (all applications + status tracking)
  📊 Analytics        (dashboard, trends, skill gaps)
"""

import streamlit as st
import requests
import json
import time
import os
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

# In Docker: API_BASE=http://backend:8000  |  Locally: http://localhost:8000
API_BASE = os.environ.get("API_BASE", "http://localhost:8000").rstrip("/")
APP_TITLE = "InternAI"

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Global CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
:root {
    --primary:  #4f46e5;
    --primary2: #7c3aed;
    --success:  #16a34a;
    --warning:  #ea580c;
    --danger:   #dc2626;
    --dark:     #0f0e17;
    --text:     #1e1b4b;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, var(--primary), var(--primary2));
    color: white !important;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: .5rem 1.5rem;
    transition: all 0.2s;
}
.stButton > button:hover { opacity: .85; transform: translateY(-1px); }

/* Cards */
.stat-card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    text-align: center;
    box-shadow: 0 1px 4px rgba(0,0,0,.07);
}
.stat-val   { font-size: 2rem; font-weight: 800; color: var(--primary); }
.stat-label { font-size: .82rem; color: #6b7280; margin-top: 3px; }

/* Section headers */
.section-hdr {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--text);
    border-bottom: 2.5px solid var(--primary);
    padding-bottom: 5px;
    margin-bottom: 1rem;
}

/* ATS score big */
.ats-big   { font-size: 3.8rem; font-weight: 900; text-align: center; line-height: 1.1; }
.ats-sub   { text-align: center; font-size: .88rem; color: #6b7280; }
.grade-tag {
    display: inline-block; padding: .2rem .8rem;
    border-radius: 999px; font-weight: 700; font-size: 1rem;
}

/* Sidebar */
[data-testid="stSidebar"] { background: var(--dark); }
[data-testid="stSidebar"] * { color: #fffffe !important; }

/* Skill pill */
.skill-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    background: #ede9fe;
    color: var(--primary);
    font-size: .8rem;
    font-weight: 600;
    margin: 2px;
}

/* Status badge */
.badge-draft      { background:#f3f4f6; color:#374151; }
.badge-applied    { background:#dbeafe; color:#1d4ed8; }
.badge-interview  { background:#d1fae5; color:#065f46; }
.badge-rejected   { background:#fee2e2; color:#991b1b; }
.badge-offer      { background:#fef9c3; color:#713f12; }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# API CLIENT
# ═════════════════════════════════════════════════════════════════════════════

class APIClient:
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base = base_url
        self.token = token

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _fh(self) -> dict:
        """File upload headers (no Content-Type – let requests set it)."""
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _handle(self, resp: requests.Response) -> dict:
        try:
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            detail = ""
            try:
                detail = resp.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            raise RuntimeError(detail)

    def post(self, path: str, **kwargs) -> dict:
        return self._handle(
            requests.post(f"{self.base}{path}", headers=self._headers(),
                          timeout=360, **kwargs)
        )

    def get(self, path: str, **kwargs) -> dict:
        return self._handle(
            requests.get(f"{self.base}{path}", headers=self._headers(),
                         timeout=60, **kwargs)
        )

    def put(self, path: str, **kwargs) -> dict:
        return self._handle(
            requests.put(f"{self.base}{path}", headers=self._headers(),
                         timeout=60, **kwargs)
        )

    def delete(self, path: str, **kwargs) -> dict:
        return self._handle(
            requests.delete(f"{self.base}{path}", headers=self._headers(),
                            timeout=30, **kwargs)
        )

    def upload_file(self, path: str, file_bytes: bytes, filename: str) -> dict:
        return self._handle(
            requests.post(
                f"{self.base}{path}",
                headers=self._fh(),
                files={"file": (filename, file_bytes,
                                "application/octet-stream")},
                timeout=120,
            )
        )

    def download(self, path: str) -> bytes:
        resp = requests.get(f"{self.base}{path}",
                            headers=self._headers(), timeout=120)
        resp.raise_for_status()
        return resp.content

    def stream_optimize(self, payload: dict):
        """Yield parsed SSE chunks from /api/applications/optimize/stream."""
        with requests.post(
            f"{self.base}/api/applications/optimize/stream",
            headers=self._headers(),
            json=payload,
            stream=True,
            timeout=600,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    line = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line.startswith("data: "):
                        try:
                            yield json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue


def get_api() -> APIClient:
    return APIClient(API_BASE, st.session_state.get("token"))


# ── Backend health check ───────────────────────────────────────────────────────

def check_backend() -> bool:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ═════════════════════════════════════════════════════════════════════════════
# SESSION STATE HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def is_logged_in() -> bool:
    return bool(st.session_state.get("token"))


def logout():
    for key in ["token", "user", "profile"]:
        st.session_state.pop(key, None)
    st.rerun()


def get_profile_cached() -> Optional[dict]:
    """Load profile from API, caching in session state."""
    if "profile" not in st.session_state and is_logged_in():
        try:
            st.session_state["profile"] = get_api().get("/api/profile")
        except Exception:
            st.session_state["profile"] = None
    return st.session_state.get("profile")


def invalidate_profile_cache():
    st.session_state.pop("profile", None)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: AUTHENTICATION
# ═════════════════════════════════════════════════════════════════════════════

def page_auth():
    col_c = st.columns([1, 2, 1])[1]
    with col_c:
        st.markdown("""
        <div style="text-align:center;padding:2rem 0 1rem">
            <div style="font-size:3rem">🎓</div>
            <h1 style="color:#1e1b4b;margin:0">InternAI</h1>
            <p style="color:#6b7280">AI-powered internship application optimizer</p>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_reg = st.tabs(["🔐 Login", "📝 Register"])

        with tab_login:
            with st.form("login_form"):
                email    = st.text_input("Email", placeholder="you@example.com")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login", use_container_width=True)
            if submitted:
                if not email or not password:
                    st.error("Please enter email and password.")
                else:
                    try:
                        resp = requests.post(
                            f"{API_BASE}/api/auth/login",
                            data={"username": email, "password": password},
                            timeout=10,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        st.session_state["token"] = data["access_token"]
                        st.session_state["user"]  = {
                            "id": data["user_id"], "email": data["email"]
                        }
                        st.success("✅ Logged in!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Login failed: {e}")

        with tab_reg:
            with st.form("reg_form"):
                full_name = st.text_input("Full Name")
                email_r   = st.text_input("Email", placeholder="you@example.com")
                pass_r    = st.text_input("Password (min 6 chars)", type="password")
                submitted_r = st.form_submit_button("Create Account", use_container_width=True)
            if submitted_r:
                try:
                    resp = requests.post(
                        f"{API_BASE}/api/auth/register",
                        json={"email": email_r, "password": pass_r,
                              "full_name": full_name},
                        timeout=10,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    st.session_state["token"] = data["access_token"]
                    st.session_state["user"]  = {
                        "id": data["user_id"], "email": data["email"]
                    }
                    st.success("✅ Account created! Welcome to InternAI.")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    try:
                        detail = resp.json().get("detail", str(e))
                    except Exception:
                        detail = str(e)
                    st.error(f"Registration failed: {detail}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    st.title("🏠 Dashboard")
    api = get_api()

    # Stats
    try:
        summary = api.get("/api/analytics/summary")
    except Exception:
        summary = {}

    profile = get_profile_cached()

    c1, c2, c3, c4 = st.columns(4)
    def _card(col, val, label):
        col.markdown(
            f'<div class="stat-card"><div class="stat-val">{val}</div>'
            f'<div class="stat-label">{label}</div></div>',
            unsafe_allow_html=True,
        )

    _card(c1, summary.get("total_applications", 0), "Applications")
    _card(c2, summary.get("average_ats_score", "—"), "Avg ATS Score")
    _card(c3, summary.get("highest_ats_score", "—"), "Best ATS Score")
    has_resume = profile and profile.get("resume")
    _card(c4, "✅ Ready" if has_resume else "❌ Missing", "Resume")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="section-hdr">🚦 Profile Checklist</div>',
                    unsafe_allow_html=True)
        p = profile or {}
        items = [
            ("Resume uploaded",     bool(p.get("resume"))),
            ("LinkedIn connected",  bool(p.get("linkedin"))),
            ("GitHub connected",    bool(p.get("github_repos"))),
            ("First application",   (summary.get("total_applications", 0) > 0)),
        ]
        for label, done in items:
            icon = "✅" if done else "🔲"
            st.markdown(f"{icon} {label}")

    with col_right:
        st.markdown('<div class="section-hdr">📑 How It Works</div>',
                    unsafe_allow_html=True)
        st.markdown("""
1. **Upload** your master resume once → stored in DB + vector index
2. **Connect** GitHub → repos embedded into ChromaDB
3. **Paste** any job description → click Optimize
4. **RAG pipeline** retrieves most relevant profile chunks
5. **AI writes** tailored resume & cover letter (streaming)
6. **ATS scorer** rates: keywords + semantic + skills + format
7. **Download** PDF/DOCX → apply with confidence
        """)

    # Recent applications
    try:
        apps = api.get("/api/applications?limit=5")
        if apps:
            st.divider()
            st.markdown('<div class="section-hdr">📁 Recent Applications</div>',
                        unsafe_allow_html=True)
            for app in apps:
                _render_app_row(app)
    except Exception:
        pass

    # Missing skills widget
    if summary.get("most_common_missing_skills"):
        st.divider()
        st.markdown('<div class="section-hdr">🎯 Most Frequent Skill Gaps</div>',
                    unsafe_allow_html=True)
        for item in summary["most_common_missing_skills"][:8]:
            st.markdown(
                f'<span class="skill-pill">⚠️ {item["skill"]} ({item["count"]}×)</span>',
                unsafe_allow_html=True,
            )


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: PROFILE
# ═════════════════════════════════════════════════════════════════════════════

def page_profile():
    st.title("👤 My Profile")
    st.caption("Your profile is stored permanently. Upload once, optimize forever.")

    api = get_api()
    tab_resume, tab_li, tab_gh, tab_skills = st.tabs(
        ["📄 Resume", "💼 LinkedIn", "🐙 GitHub", "🛠️ Skills"]
    )

    # ── Resume Tab ─────────────────────────────────────────────────────────
    with tab_resume:
        profile = get_profile_cached()
        existing = profile.get("resume") if profile else None

        if existing:
            st.success(
                f"✅ Resume stored: **{existing.get('file_name','upload')}**  "
                f"| Updated: {existing['updated_at'][:10]}  "
                f"| Indexed: {'✅' if existing['chroma_indexed'] else '⚠️'}"
            )

            # ATS improvement suggestions button
            col_a, col_b = st.columns([1, 3])
            with col_a:
                if st.button("💡 Improve My Resume"):
                    st.session_state["show_improve"] = True
            with col_b:
                if existing:
                    try:
                        pdf_bytes = api.download(f"/api/profile/resume/download/pdf")
                        st.download_button("⬇️ Download PDF", pdf_bytes,
                                           file_name="my_resume.pdf",
                                           mime="application/pdf")
                    except Exception:
                        pass

            with st.expander("👁️ Preview resume text"):
                st.text(existing.get("raw_text", "")[:3000])

            replace = st.checkbox("🔄 Replace my resume")
        else:
            replace = True

        if replace:
            st.markdown("### Upload Resume")
            uploaded = st.file_uploader(
                "PDF, DOCX, or TXT",
                type=["pdf", "docx", "doc", "txt"],
            )
            if uploaded:
                if st.button("💾 Save Resume", type="primary"):
                    with st.spinner("Parsing, validating, embedding..."):
                        try:
                            api.upload_file("/api/profile/resume",
                                            uploaded.read(), uploaded.name)
                            invalidate_profile_cache()
                            st.success("✅ Resume saved and indexed!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ {e}")

    # ── LinkedIn Tab ───────────────────────────────────────────────────────
    with tab_li:
        profile = get_profile_cached()
        li = profile.get("linkedin") if profile else None

        if li:
            st.success(f"✅ LinkedIn profile saved | Updated: {li['updated_at'][:10]}")
            with st.expander("📋 Saved data"):
                st.markdown(f"**Headline:** {li.get('headline','—')}")
                st.markdown(f"**Skills:** {', '.join(li.get('skills') or [])[:200]}")

        st.markdown("### Paste LinkedIn Data")
        st.caption("Copy sections from your LinkedIn profile. No login required – privacy-first.")

        with st.form("li_form"):
            headline = st.text_input("Headline",
                                     placeholder="MSc Data Science Student | EPITA Paris")
            about = st.text_area("About Section", height=120,
                                  placeholder="Paste your LinkedIn About section...")
            exp_text = st.text_area("Experience Section", height=200,
                                     placeholder="Paste your experience entries...")
            skills_text = st.text_area("Skills (one per line or comma-separated)", height=100,
                                        placeholder="Python, Machine Learning, SQL...")
            saved = st.form_submit_button("💾 Save LinkedIn Profile", use_container_width=True)

        if saved:
            with st.spinner("Saving and indexing..."):
                try:
                    api.post("/api/profile/linkedin", json={
                        "about": about,
                        "headline": headline,
                        "experiences_text": exp_text,
                        "skills_text": skills_text,
                    })
                    invalidate_profile_cache()
                    st.success("✅ LinkedIn profile saved and embedded!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")

    # ── GitHub Tab ─────────────────────────────────────────────────────────
    with tab_gh:
        profile = get_profile_cached()
        repos = profile.get("github_repos", []) if profile else []

        if repos:
            st.success(f"✅ {len(repos)} GitHub repos cached")
            with st.expander("📦 View repositories"):
                for repo in repos[:15]:
                    lang  = f" `{repo['language']}`" if repo.get("language") else ""
                    stars = f" ⭐{repo['stars']}" if repo.get("stars") else ""
                    desc  = repo.get("description") or ""
                    url   = repo.get("html_url", "")
                    st.markdown(f"**[{repo['repo_name']}]({url})**{lang}{stars}  \n{desc}")

            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("🔄 Refresh GitHub"):
                    with st.spinner("Re-fetching repos..."):
                        try:
                            api.post("/api/profile/github/refresh")
                            invalidate_profile_cache()
                            st.success("✅ GitHub refreshed!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ {e}")

        st.markdown("### Connect GitHub")
        gh_input = st.text_input(
            "GitHub profile URL or username",
            placeholder="https://github.com/yourusername  or  yourusername",
            value=(get_profile_cached() or {}).get("user", {}).get("github_url", "") or "",
        )
        if st.button("🔗 Fetch & Index GitHub Profile", type="primary"):
            if not gh_input.strip():
                st.error("Please enter a GitHub URL or username.")
            else:
                with st.spinner(f"Fetching repos (may take 30s)..."):
                    try:
                        result = api.post("/api/profile/github",
                                          json={"github_url": gh_input.strip()})
                        invalidate_profile_cache()
                        st.success(f"✅ {len(result)} repos fetched and indexed!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")

    # ── Skills Tab ─────────────────────────────────────────────────────────
    with tab_skills:
        profile = get_profile_cached()
        skills = profile.get("skills", []) if profile else []

        if not skills:
            st.info("Upload your resume and connect GitHub to auto-populate your skill inventory.")
        else:
            # Deduplicate by lowercase name, summing frequencies
            deduped: dict[str, dict] = {}
            for s in skills:
                key = s.get("name", "").lower()
                if not key:
                    continue
                if key not in deduped:
                    deduped[key] = dict(s)
                else:
                    deduped[key]["frequency"] = deduped[key].get("frequency", 0) + s.get("frequency", 0)
            skills = list(deduped.values())

            st.success(f"**{len(skills)} skills** extracted from your profile")

            # Group by category
            by_cat: dict[str, list] = {}
            for s in skills:
                cat = s.get("category", "Other")
                by_cat.setdefault(cat, []).append(s)

            for cat, cat_skills in sorted(by_cat.items()):
                st.markdown(f"**{cat}**")
                pills = " ".join(
                    f'<span class="skill-pill">{s["name"]} ({s["frequency"]})</span>'
                    for s in sorted(cat_skills, key=lambda x: x["frequency"], reverse=True)
                )
                st.markdown(pills, unsafe_allow_html=True)
                st.write("")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: OPTIMIZE JOB
# ═════════════════════════════════════════════════════════════════════════════

def page_optimize():
    st.title("🚀 Optimize Job Application")
    st.caption("Paste a job description → AI generates tailored resume + cover letter + ATS score.")

    api = get_api()
    profile = get_profile_cached()

    # Guard
    if not profile or not profile.get("resume"):
        st.error("❌ Upload your resume first in **👤 My Profile → Resume tab**")
        st.stop()

    # Job details form
    st.markdown('<div class="section-hdr">📋 Job Information</div>',
                unsafe_allow_html=True)

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        job_title = st.text_input("Job Title *",
                                   placeholder="Data Science Intern")
    with col2:
        company = st.text_input("Company",
                                 placeholder="Airbus, BNP Paribas, LVMH...")
    with col3:
        export_fmt = st.radio("Export as", ["PDF", "DOCX", "Both"], index=0)

    job_url = st.text_input("Job URL (optional)",
                             placeholder="https://linkedin.com/jobs/...")
    jd = st.text_area("Job Description *", height=300,
                       placeholder="Paste the full job description here...")

    if st.button("⚡ Optimize Application", type="primary",
                 use_container_width=True, disabled=not jd.strip()):

        payload = {
            "job_description": jd,
            "job_title":       job_title or None,
            "company":         company or None,
            "job_url":         job_url or None,
        }

        # ── Streaming pipeline UI ────────────────────────────────────────
        status_ph  = st.empty()
        progress   = st.progress(0)

        resume_hdr  = st.markdown("### 📄 Tailored Resume")
        resume_ph   = st.empty()
        cover_hdr   = st.markdown("### ✉️ Cover Letter")
        cover_ph    = st.empty()

        tailored_resume  = ""
        cover_letter     = ""
        final_meta       = {}
        reviewer_text    = ""

        step_map = {
            "Retrieving": 5,
            "Tailoring":  15,
            "Writing":    55,
            "Running":    75,
            "Computing":  82,
            "Saving":     93,
        }

        try:
            for chunk in api.stream_optimize(payload):
                ctype   = chunk.get("type", "")
                content = chunk.get("content", "")

                if ctype == "status":
                    status_ph.info(f"⏳ {content}")
                    for key, pct in step_map.items():
                        if key.lower() in content.lower():
                            progress.progress(pct)
                            break

                elif ctype == "resume_token":
                    tailored_resume += content
                    resume_ph.text_area("", value=tailored_resume, height=450,
                                        label_visibility="collapsed")

                elif ctype == "cover_token":
                    cover_letter += content
                    cover_ph.text_area("", value=cover_letter, height=350,
                                       label_visibility="collapsed")

                elif ctype == "reviewer_done":
                    reviewer_text = content

                elif ctype == "done":
                    try:
                        final_meta = json.loads(content)
                    except Exception:
                        pass
                    progress.progress(100)
                    status_ph.success("✅ Done! Application optimized and saved.")

        except Exception as e:
            st.error(f"❌ Optimization failed: {e}")
            st.stop()

        # ── ATS Score ─────────────────────────────────────────────────────
        if final_meta:
            st.divider()
            render_ats_score(final_meta.get("ats_breakdown", final_meta))

        # ── Reviewer feedback ──────────────────────────────────────────────
        if reviewer_text:
            with st.expander("🔍 AI Reviewer Feedback"):
                st.markdown(reviewer_text)

        # ── Download buttons ───────────────────────────────────────────────
        app_id = final_meta.get("app_id")
        if app_id:
            st.divider()
            st.markdown("### ⬇️ Download Documents")
            dcols = st.columns(4)
            safe  = (job_title or "resume").replace(" ", "_")

            if export_fmt in ("PDF", "Both"):
                try:
                    r_pdf = api.download(f"/api/applications/{app_id}/download/resume/pdf")
                    dcols[0].download_button("📄 Resume PDF", r_pdf,
                                             file_name=f"resume_{safe}.pdf",
                                             mime="application/pdf")
                except Exception:
                    pass
                try:
                    c_pdf = api.download(f"/api/applications/{app_id}/download/cover/pdf")
                    dcols[1].download_button("✉️ Cover Letter PDF", c_pdf,
                                             file_name=f"cover_{safe}.pdf",
                                             mime="application/pdf")
                except Exception:
                    pass

            if export_fmt in ("DOCX", "Both"):
                try:
                    r_docx = api.download(f"/api/applications/{app_id}/download/resume/docx")
                    dcols[2].download_button(
                        "📄 Resume DOCX", r_docx,
                        file_name=f"resume_{safe}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                except Exception:
                    pass
                try:
                    c_docx = api.download(f"/api/applications/{app_id}/download/cover/docx")
                    dcols[3].download_button(
                        "✉️ Cover Letter DOCX", c_docx,
                        file_name=f"cover_{safe}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                except Exception:
                    pass


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: HISTORY
# ═════════════════════════════════════════════════════════════════════════════

def page_history():
    st.title("📁 Application History")
    api = get_api()

    try:
        apps = api.get("/api/applications?limit=100")
    except Exception as e:
        st.error(f"Failed to load history: {e}")
        return

    if not apps:
        st.info("No applications yet. Use **🚀 Optimize Job** to get started!")
        return

    st.caption(f"{len(apps)} applications total")

    # Filter by status
    statuses = ["All"] + list({a.get("status","draft") for a in apps})
    sel_status = st.selectbox("Filter by status", statuses, index=0)
    filtered = apps if sel_status == "All" else [
        a for a in apps if a.get("status") == sel_status
    ]

    for app in filtered:
        title   = app.get("job_title") or "Untitled"
        company = app.get("company") or "—"
        score   = app.get("ats_score") or 0
        grade   = (app.get("ats_breakdown") or {}).get("grade", "—")
        date    = app.get("created_at", "")[:16].replace("T", " ")
        status  = app.get("status", "draft")
        color   = "#16a34a" if score >= 75 else "#ea580c" if score >= 55 else "#dc2626"

        with st.expander(
            f"**{title}** @ {company}  "
            f"|  ATS: {score}  |  Grade: {grade}  |  {date}  |  {status.upper()}"
        ):
            # Status update
            col_st, col_notes = st.columns([1, 3])
            with col_st:
                new_status = st.selectbox(
                    "Status",
                    ["draft", "applied", "interview", "rejected", "offer"],
                    index=["draft","applied","interview","rejected","offer"]
                        .index(status),
                    key=f"st_{app['id']}",
                )
                if new_status != status:
                    try:
                        api.put(f"/api/applications/{app['id']}/status",
                                json={"status": new_status})
                        st.success("Updated!")
                    except Exception as e:
                        st.error(str(e))

            with col_notes:
                st.text_input("Notes", value=app.get("notes") or "",
                              key=f"notes_{app['id']}",
                              placeholder="Interview scheduled, follow-up needed...")

            # Resume + Cover Letter
            r_col, c_col = st.columns(2)
            with r_col:
                st.markdown("**📄 Tailored Resume**")
                st.text_area("", value=app.get("optimized_resume", ""),
                             height=300, key=f"rv_{app['id']}",
                             label_visibility="collapsed")
                try:
                    r_pdf = api.download(f"/api/applications/{app['id']}/download/resume/pdf")
                    st.download_button("⬇️ PDF", r_pdf,
                                       file_name=f"resume_{app['id']}.pdf",
                                       key=f"rpdf_{app['id']}")
                except Exception:
                    pass

            with c_col:
                st.markdown("**✉️ Cover Letter**")
                st.text_area("", value=app.get("cover_letter", ""),
                             height=300, key=f"cl_{app['id']}",
                             label_visibility="collapsed")
                try:
                    c_pdf = api.download(f"/api/applications/{app['id']}/download/cover/pdf")
                    st.download_button("⬇️ PDF", c_pdf,
                                       file_name=f"cover_{app['id']}.pdf",
                                       key=f"cpdf_{app['id']}")
                except Exception:
                    pass

            # ATS details
            bd = app.get("ats_breakdown")
            if bd:
                st.divider()
                render_ats_score(bd, compact=True)

            # Delete
            if st.button("🗑️ Delete this application", key=f"del_{app['id']}"):
                try:
                    api.delete(f"/api/applications/{app['id']}")
                    st.success("Deleted")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: ANALYTICS
# ═════════════════════════════════════════════════════════════════════════════

def page_analytics():
    st.title("📊 Analytics Dashboard")
    api = get_api()

    try:
        summary = api.get("/api/analytics/summary")
        trend   = api.get("/api/analytics/ats-trend")
    except Exception as e:
        st.error(f"Failed to load analytics: {e}")
        return

    if summary.get("total_applications", 0) == 0:
        st.info("No applications yet. Start optimizing to see analytics!")
        return

    # Top stats
    c1, c2, c3, c4 = st.columns(4)
    def _card(col, val, label):
        col.markdown(
            f'<div class="stat-card"><div class="stat-val">{val}</div>'
            f'<div class="stat-label">{label}</div></div>',
            unsafe_allow_html=True,
        )
    _card(c1, summary["total_applications"], "Total Applications")
    _card(c2, summary["average_ats_score"],  "Avg ATS Score")
    _card(c3, summary["highest_ats_score"],  "Best ATS Score")
    applied   = sum(v for k, v in summary.get("applications_by_status", {}).items()
                    if k in ("applied", "interview", "offer"))
    _card(c4, applied, "Submitted")

    st.divider()

    # ATS trend chart
    if trend:
        import pandas as pd
        df = pd.DataFrame(trend)
        if not df.empty and "ats_score" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
            df = df.sort_values("created_at")
            st.markdown('<div class="section-hdr">📈 ATS Score Trend</div>',
                        unsafe_allow_html=True)
            st.line_chart(df.set_index("created_at")["ats_score"],
                          use_container_width=True)

    col_l, col_r = st.columns(2)

    # Skill gaps
    with col_l:
        st.markdown('<div class="section-hdr">🎯 Top Missing Skills</div>',
                    unsafe_allow_html=True)
        missing = summary.get("most_common_missing_skills", [])
        if missing:
            import pandas as pd
            df_miss = pd.DataFrame(missing)
            st.bar_chart(df_miss.set_index("skill")["count"],
                         use_container_width=True, height=280)
        else:
            st.info("No skill gaps tracked yet.")

    # Skill strengths
    with col_r:
        st.markdown('<div class="section-hdr">💪 Skill Strength Ranking</div>',
                    unsafe_allow_html=True)
        ranking = summary.get("skill_strength_ranking", [])
        if ranking:
            for i, s in enumerate(ranking[:10], 1):
                bar_w = min(100, s["frequency"] * 15)
                st.markdown(
                    f"**{i}. {s['name']}** `{s['category']}`  "
                    f"<span style='color:#4f46e5;font-weight:700'>"
                    f"{'▓' * min(s['frequency'],10)}</span> {s['frequency']}×",
                    unsafe_allow_html=True,
                )
        else:
            st.info("Upload resume and GitHub to build skill inventory.")

    # Status breakdown
    st.divider()
    st.markdown('<div class="section-hdr">📋 Applications by Status</div>',
                unsafe_allow_html=True)
    status_data = summary.get("applications_by_status", {})
    if status_data:
        import pandas as pd
        df_status = pd.DataFrame(
            list(status_data.items()), columns=["Status", "Count"]
        )
        st.bar_chart(df_status.set_index("Status")["Count"],
                     use_container_width=True, height=200)


# ═════════════════════════════════════════════════════════════════════════════
# SHARED: ATS Score Renderer
# ═════════════════════════════════════════════════════════════════════════════

def render_ats_score(result: dict, compact: bool = False) -> None:
    total   = result.get("total_score", 0)
    grade   = result.get("grade", "—")
    verdict = result.get("verdict", "")
    COLORS  = {
        "A+": "#16a34a", "A": "#16a34a", "B": "#4f46e5",
        "C":  "#ea580c", "D": "#dc2626", "F": "#dc2626",
    }
    color = COLORS.get(grade, "#6b7280")

    st.markdown('<div class="section-hdr">📊 ATS Analysis</div>',
                unsafe_allow_html=True)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(
            f'<div class="ats-big" style="color:{color}">{total}</div>'
            f'<div class="ats-sub">/100 · ATS Score</div>'
            f'<div style="text-align:center;margin-top:8px">'
            f'<span class="grade-tag" style="background:{color}22;color:{color}">'
            f'Grade {grade}</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"*{verdict}*")

    with col2:
        sub = {
            "Keywords":    result.get("keyword_score", 0),
            "Semantic":    result.get("semantic_score", 0),
            "Skills":      result.get("skill_score", 0),
            "Formatting":  result.get("format_score", 0),
        }
        for lbl, val in sub.items():
            bar_c = "#16a34a" if val >= 75 else "#ea580c" if val >= 55 else "#dc2626"
            st.markdown(
                f"**{lbl}** "
                f'<span style="float:right;color:{bar_c};font-weight:700">'
                f'{val:.0f}/100</span>',
                unsafe_allow_html=True,
            )
            st.progress(int(val) / 100)

    if not compact:
        st.divider()
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**✅ Matched Keywords**")
            kws = result.get("matched_keywords", [])
            if kws:
                pills = " ".join(
                    f'<span class="skill-pill">✓ {k}</span>'
                    for k in kws[:20]
                )
                st.markdown(pills, unsafe_allow_html=True)
            else:
                st.markdown("*None found*")

        with c2:
            st.markdown("**❌ Missing Keywords**")
            miss = result.get("missing_keywords", [])
            if miss:
                for kw in miss[:15]:
                    st.markdown(f"• {kw}")
            else:
                st.success("No critical keywords missing!")

        with c3:
            st.markdown("**💡 AI Suggestions**")
            for s in result.get("llm_improvements", []):
                st.markdown(f"• {s}")
            for iss in result.get("format_issues", []):
                st.warning(f"⚠️ {iss}")

        strengths = result.get("llm_strengths", [])
        gaps      = result.get("llm_improvements", [])
        if strengths:
            st.markdown("**💪 Strengths**")
            for s in strengths:
                st.markdown(f"✅ {s}")


# ═════════════════════════════════════════════════════════════════════════════
# SHARED: Application Row
# ═════════════════════════════════════════════════════════════════════════════

def _render_app_row(app: dict) -> None:
    score  = app.get("ats_score", 0)
    grade  = (app.get("ats_breakdown") or {}).get("grade", "—")
    color  = "#16a34a" if score >= 75 else "#ea580c" if score >= 55 else "#dc2626"
    title  = app.get("job_title") or "Untitled"
    comp   = app.get("company") or "—"
    date   = app.get("created_at","")[:10]
    status = app.get("status","draft")

    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    c1.markdown(f"**{title}** @ {comp}  \n<small style='color:#6b7280'>{date}</small>",
                unsafe_allow_html=True)
    c2.markdown(
        f'<span style="font-size:1.4rem;font-weight:800;color:{color}">{score}</span>',
        unsafe_allow_html=True
    )
    c3.markdown(f"Grade **{grade}**")
    c4.markdown(
        f'<span class="badge-{status}" style="padding:2px 8px;border-radius:999px;'
        f'font-size:.8rem;font-weight:600">{status.upper()}</span>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER
# ═════════════════════════════════════════════════════════════════════════════

def main():
    # Backend health check
    backend_ok = check_backend()

    # Sidebar
    with st.sidebar:
        st.markdown(f"## 🎓 InternAI")
        if is_logged_in():
            user = st.session_state.get("user", {})
            st.markdown(f"👤 *{user.get('email','')}*")
        st.divider()

        if not backend_ok:
            st.error("⚠️ Backend offline\nRun: `uvicorn main:app`")

        if is_logged_in():
            page = st.selectbox(
                "Navigate",
                ["🏠 Dashboard", "👤 Profile", "🚀 Optimize Job",
                 "📁 History", "📊 Analytics"],
                label_visibility="collapsed",
            )

            st.divider()

            # Quick system status
            api = get_api()
            try:
                health = api.get("/health/detailed")
                st.markdown("**System**")
                st.markdown(f"{'✅' if health.get('ollama')=='running' else '❌'} Ollama")
                st.markdown(f"{'✅' if health.get('model_available') else '❌'} LLM model")
                st.markdown(f"{'✅' if health.get('embedding_loaded') else '⚠️'} Embeddings")
            except Exception:
                st.markdown("⚠️ Cannot reach backend")

            st.divider()
            if st.button("🚪 Logout"):
                logout()
        else:
            page = "auth"

    # Route
    if not is_logged_in():
        page_auth()
    elif page == "🏠 Dashboard":
        page_dashboard()
    elif page == "👤 Profile":
        page_profile()
    elif page == "🚀 Optimize Job":
        page_optimize()
    elif page == "📁 History":
        page_history()
    elif page == "📊 Analytics":
        page_analytics()


if __name__ == "__main__":
    main()
