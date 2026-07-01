#!/usr/bin/env python3
"""Extract candidate pathogen names from data/cases/case_library.json.

This is a *candidate generator*, not a fully automated pipeline: it scans
each case's `diagnosis` field (the organism name is almost always in the
first sentence or two — see README.md's "Adding tags" section)
and prints ranked genus+species matches plus known viral pathogen keyword
hits, deduplicated with occurrence counts.

The output is meant to be reviewed by a human (or an LLM) and merged into
the curated, hand-reviewed list at data/cases/organisms.json, which is
what the frontend's pathogen dropdown actually loads. Re-run this whenever
new cases are added to case_library.json to see what's new.

Usage:
    python scripts/extract_organism_candidates.py
"""

import json
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CASE_LIBRARY = REPO_ROOT / "data" / "cases" / "case_library.json"

# Genus + species/adjective pattern, e.g. "Mycobacterium marinum"
BINOMIAL_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+((?:sp\.|spp\.|species)|[a-z][a-z\-]{2,})\b")

# Common words that look like a capitalized "genus" at the start of a
# clause but aren't organism names — filters out obvious false positives.
STOPWORDS = {
    "the", "this", "a", "an", "in", "of", "patient", "disseminated", "line",
    "group", "tick", "severe", "acute", "chronic", "multiple", "recurrent",
    "fatal", "invasive", "primary", "secondary", "probable", "possible",
    "culture", "due", "with",
}

# Viral pathogens rarely fit the binomial pattern above (e.g. "Epstein-Barr
# virus", "West Nile virus") — matched by keyword instead.
VIRUS_KEYWORDS = [
    "Epstein-Barr virus", "Epstein Barr virus", "cytomegalovirus",
    "herpes simplex virus", "varicella-zoster virus", "varicella zoster virus",
    "West Nile virus", "human immunodeficiency virus", "hepatitis A",
    "hepatitis B", "hepatitis C", "hepatitis E", "influenza", "adenovirus",
    "norovirus", "rotavirus", "parainfluenza", "enterovirus", "coxsackievirus",
    "echovirus", "rabies virus", "measles", "mumps", "rubella", "parvovirus",
    "human papillomavirus", "molluscum contagiosum virus", "poxvirus",
    "monkeypox", "smallpox", "vaccinia", "coronavirus", "SARS-CoV-2",
    "dengue virus", "chikungunya", "Zika virus", "hantavirus",
    "human herpesvirus", "HHV-6", "HHV-8",
    "human T-cell lymphotropic virus", "JC virus", "BK virus",
    "lymphocytic choriomeningitis virus", "Powassan virus",
    "eastern equine encephalitis", "western equine encephalitis",
    "St. Louis encephalitis", "La Crosse virus",
]


def diagnosis_lead(diagnosis: str, n_sentences: int = 2) -> str:
    """Return the first `n_sentences` of a diagnosis field."""
    text = diagnosis.replace("\n", " ")
    parts = re.split(r"(?<=[a-z0-9\)])\.\s+(?=[A-Z])", text)
    return ". ".join(parts[:n_sentences])


def main():
    with open(CASE_LIBRARY) as f:
        cases = json.load(f)

    binomial_counts = Counter()
    virus_counts = Counter()

    for case in cases:
        lead = diagnosis_lead(case.get("diagnosis", "") or "")

        for match in BINOMIAL_RE.finditer(lead):
            genus, species = match.groups()
            if genus.lower() in STOPWORDS:
                continue
            binomial_counts[f"{genus} {species}"] += 1

        for keyword in VIRUS_KEYWORDS:
            if keyword.lower() in lead.lower():
                virus_counts[keyword] += 1

    print(f"Scanned {len(cases)} cases\n")
    print(f"=== Binomial-pattern candidates ({len(binomial_counts)} unique) ===")
    print("(Includes false positives — lab/procedure terms, disease names, etc. "
          "Review before merging into data/cases/organisms.json.)\n")
    for name, count in binomial_counts.most_common():
        print(f"{count}\t{name}")

    print(f"\n=== Viral keyword hits ({len(virus_counts)} unique) ===\n")
    for name, count in virus_counts.most_common():
        print(f"{count}\t{name}")


if __name__ == "__main__":
    main()
