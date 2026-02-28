"""
Skill Inventory Engine – extracts, categorizes, deduplicates, and ranks skills.
Aggregates across resume, LinkedIn, and GitHub sources.
"""

import re
from collections import Counter
from typing import Optional


# ── Skill Taxonomy ────────────────────────────────────────────────────────────

SKILL_TAXONOMY: dict[str, list[str]] = {
    "Programming": [
        "python", "r", "java", "scala", "javascript", "typescript",
        "c++", "c#", "go", "rust", "julia", "matlab", "bash", "shell",
    ],
    "AI/ML": [
        "machine learning", "deep learning", "nlp", "natural language processing",
        "computer vision", "reinforcement learning", "neural network", "transformer",
        "bert", "gpt", "llm", "large language model", "rag",
        "scikit-learn", "sklearn", "tensorflow", "pytorch", "keras",
        "xgboost", "lightgbm", "catboost", "random forest", "gradient boosting",
        "time series", "regression", "classification", "clustering",
        "feature engineering", "model deployment", "mlops", "mlflow", "wandb",
        "huggingface", "langchain", "sentence-transformers",
    ],
    "Data Engineering": [
        "sql", "postgresql", "mysql", "sqlite", "oracle",
        "mongodb", "cassandra", "neo4j", "redis", "elasticsearch",
        "spark", "hadoop", "hive", "kafka", "airflow", "dbt",
        "etl", "data pipeline", "data warehouse", "snowflake", "bigquery",
        "pandas", "numpy", "scipy", "polars",
    ],
    "Visualization": [
        "tableau", "power bi", "powerbi", "looker", "superset",
        "matplotlib", "seaborn", "plotly", "dash", "bokeh",
        "d3.js", "grafana",
    ],
    "DevOps": [
        "docker", "kubernetes", "git", "github", "gitlab", "ci/cd",
        "jenkins", "github actions", "linux", "bash", "terraform",
        "cloud", "aws", "azure", "gcp", "google cloud",
    ],
    "Frameworks": [
        "fastapi", "flask", "django", "streamlit", "gradio",
        "react", "node.js", "express", "spring boot",
    ],
    "Statistics": [
        "statistics", "probability", "bayesian", "hypothesis testing",
        "a/b testing", "experimental design", "regression analysis",
        "dimensionality reduction", "pca", "svd",
    ],
    "Soft Skills": [
        "communication", "teamwork", "leadership", "problem solving",
        "agile", "scrum", "project management", "critical thinking",
    ],
    "Languages": [
        "english", "french", "german", "spanish", "arabic", "hindi",
        "mandarin", "portuguese",
    ],
}

# Flatten for fast lookup
_SKILL_TO_CATEGORY: dict[str, str] = {}
for cat, skills in SKILL_TAXONOMY.items():
    for skill in skills:
        _SKILL_TO_CATEGORY[skill.lower()] = cat


# ── Main Extraction Functions ─────────────────────────────────────────────────

def extract_skills_from_text(text: str, source: str = "resume") -> list[dict]:
    """
    Rule-based skill extraction from text.
    Returns list of {name, category, source} dicts.
    """
    text_lower = text.lower()
    found: list[dict] = []

    for skill, category in _SKILL_TO_CATEGORY.items():
        # Match whole word(s)
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, text_lower):
            found.append({
                "name":     _canonical_name(skill),
                "category": category,
                "source":   source,
            })

    # Also catch things like "Python 3", "SQL Server", "scikit-learn"
    extra_patterns = [
        (r"\bscikit[-\s]learn\b",     "scikit-learn",     "AI/ML"),
        (r"\bpower\s+bi\b",           "Power BI",         "Visualization"),
        (r"\bnode\.?js\b",            "Node.js",          "Frameworks"),
        (r"\bci[/\-]cd\b",            "CI/CD",            "DevOps"),
        (r"\bml\b",                   "Machine Learning", "AI/ML"),
        (r"\bnlp\b",                  "NLP",              "AI/ML"),
        (r"\bllm\b",                  "LLM",              "AI/ML"),
        (r"\brag\b",                  "RAG",              "AI/ML"),
        (r"\baws\b",                  "AWS",              "DevOps"),
        (r"\bgcp\b",                  "GCP",              "DevOps"),
        (r"\br\b",                    "R",                "Programming"),
    ]
    existing_names = {s["name"].lower() for s in found}
    for pattern, name, category in extra_patterns:
        if re.search(pattern, text_lower) and name.lower() not in existing_names:
            found.append({"name": name, "category": category, "source": source})
            existing_names.add(name.lower())

    return found


def merge_skills(all_skill_lists: list[list[dict]]) -> list[dict]:
    """
    Deduplicate and merge skills from multiple sources.
    Returns ranked list with frequency and sources.
    """
    merged: dict[str, dict] = {}

    for skill_list in all_skill_lists:
        for skill in skill_list:
            name_lower = skill["name"].lower()
            if name_lower not in merged:
                merged[name_lower] = {
                    "name":      skill["name"],
                    "category":  skill.get("category", "Other"),
                    "frequency": 0,
                    "sources":   [],
                }
            merged[name_lower]["frequency"] += 1
            source = skill.get("source", "unknown")
            if source not in merged[name_lower]["sources"]:
                merged[name_lower]["sources"].append(source)

    # Sort by frequency desc
    return sorted(merged.values(), key=lambda x: x["frequency"], reverse=True)


def rank_skills(skills: list[dict]) -> list[dict]:
    """Add rank field and return top skills per category."""
    for i, skill in enumerate(skills, 1):
        skill["rank"] = i
    return skills


def get_skill_gap(user_skills: list[str], jd_text: str) -> list[str]:
    """Return skills mentioned in JD that the user doesn't have."""
    jd_skills = extract_skills_from_text(jd_text, source="jd")
    jd_names  = {s["name"].lower() for s in jd_skills}
    user_lower = {s.lower() for s in user_skills}
    return [s["name"] for s in jd_skills if s["name"].lower() not in user_lower]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _canonical_name(skill: str) -> str:
    """Return properly capitalized skill name."""
    overrides = {
        "python": "Python", "sql": "SQL", "r": "R", "java": "Java",
        "aws": "AWS", "gcp": "GCP", "nlp": "NLP", "ml": "ML",
        "llm": "LLM", "rag": "RAG", "etl": "ETL", "ci/cd": "CI/CD",
        "mlops": "MLOps", "pca": "PCA", "svd": "SVD",
        "pytorch": "PyTorch", "tensorflow": "TensorFlow", "bert": "BERT",
        "gpt": "GPT", "xgboost": "XGBoost", "lightgbm": "LightGBM",
        "fastapi": "FastAPI", "postgresql": "PostgreSQL", "mongodb": "MongoDB",
        "elasticsearch": "Elasticsearch", "airflow": "Airflow",
        "kubernetes": "Kubernetes", "docker": "Docker", "git": "Git",
        "github": "GitHub", "gitlab": "GitLab",
    }
    return overrides.get(skill.lower(), skill.title())
