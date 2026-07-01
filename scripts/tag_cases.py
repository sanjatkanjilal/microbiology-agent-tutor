#!/usr/bin/env python3
"""Heuristic first-pass tagging of data/cases/case_library.json.

Populates the `tags` array on every case following the schema documented
in README.md's "Adding tags to cases" section:

    "tags": [
      "organism:Staphylococcus aureus",
      "syndrome:skin and soft tissue infection",
      "host:immunocompetent adult",
      "host:healthcare worker"
    ]

This is a keyword/pattern-based FIRST PASS, not a verified ground truth.
It will miss things, over-tag some cases, and occasionally mis-tag edge
cases (e.g. an organism mentioned in the differential but not the actual
diagnosis). Treat it as a starting point for the "NLP tagging" workflow
already described in README.md, not a finished product — spot-check
before relying on it for anything high-stakes, and feel free to re-run
after tuning the keyword lists below.

Usage:
    python scripts/tag_cases.py            # writes data/cases/case_library.json in place
    python scripts/tag_cases.py --dry-run   # prints a sample of tags without writing
"""

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CASE_LIBRARY = REPO_ROOT / "data" / "cases" / "case_library.json"
ORGANISMS_JSON = REPO_ROOT / "data" / "cases" / "organisms.json"

# ─── Organism matching ──────────────────────────────────────────────────
# Reuse the curated organism list (data/cases/organisms.json) as the
# match dictionary — same list that powers the Setup screen dropdown.


def load_organism_labels():
    with open(ORGANISMS_JSON) as f:
        organisms = json.load(f)
    # Sort longest-label-first so "Mycobacterium avium complex" matches
    # before the shorter "Mycobacterium avium" would swallow it.
    return sorted((o["label"] for o in organisms), key=len, reverse=True)


def diagnosis_lead(diagnosis: str, n_sentences: int = 2) -> str:
    text = (diagnosis or "").replace("\n", " ")
    parts = re.split(r"(?<=[a-z0-9\)])\.\s+(?=[A-Z])", text)
    return ". ".join(parts[:n_sentences])


# Alternate names/old nomenclature that appear in diagnosis text but
# aren't the current preferred name used as the organisms.json label —
# map them to the label that IS in the dictionary so matching (and the
# dropdown) stays consistent instead of needing a duplicate entry.
ORGANISM_SYNONYMS = {
    "pneumocystis carinii": "Pneumocystis jirovecii",
    "flavobacterium oryzihabitans": "Pseudomonas oryzihabitans",
    "hpv": "Human papillomavirus (HPV)",
    "human papillomavirus": "Human papillomavirus (HPV)",
    "vzv": "Varicella-zoster virus (VZV)",
    "cmv": "Cytomegalovirus (CMV)",
    "ebv": "Epstein-Barr virus (EBV)",
    "hsv": "Herpes simplex virus (HSV)",
    "hiv": "Human immunodeficiency virus (HIV)",
    "rsv": "Respiratory syncytial virus (RSV)",
    # Reclassified/renamed genera — old case reports (pre-2016 or so)
    # use the old name; the curated dictionary uses the current one.
    "clostridium difficile": "Clostridioides difficile",
    "mycobacterium avium-intracellulare": "Mycobacterium avium complex",
    "mycobacterium avium intracellulare": "Mycobacterium avium complex",
    # Disease names that imply a specific organism/genus even when the
    # binomial name itself isn't spelled out in the same sentence
    # (e.g. "pulmonary histoplasmosis" without "Histoplasma capsulatum"
    # nearby). Where a disease can be caused by several species, this
    # maps to the most common one in this corpus — an approximation,
    # not a certainty.
    "cryptococcosis": "Cryptococcus neoformans",
    "cryptococcal": "Cryptococcus neoformans",
    "histoplasmosis": "Histoplasma capsulatum",
    "coccidioidomycosis": "Coccidioides immitis",
    "blastomycosis": "Blastomyces dermatitidis",
    "candidiasis": "Candida albicans",
    "aspergillosis": "Aspergillus fumigatus",
    "mucormycosis": "Rhizopus species",
    "zygomycosis": "Rhizopus species",
    "nocardiosis": "Nocardia species",
    "actinomycosis": "Actinomyces israelii",
    "toxoplasmosis": "Toxoplasma gondii",
    "cryptosporidiosis": "Cryptosporidium parvum",
    "echinococcosis": "Echinococcus granulosus",
    "schistosomiasis": "Schistosoma mansoni",
    "babesiosis": "Babesia microti",
    "tuberculosis": "Mycobacterium tuberculosis",
    "tuberculous": "Mycobacterium tuberculosis",
}

# A match found in a sentence containing one of these phrases describes
# a NEGATIVE finding or a ruled-out possibility, not the actual
# diagnosis — e.g. "PCR testing for cytomegalovirus (CMV) was negative."
ORGANISM_NEGATION_PHRASES = [
    "was negative", "were negative", "negative for", "ruled out",
    "excluded", "not detected", "no growth", "less likely",
]

_SENT_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def _sentence_containing(text: str, index: int) -> str:
    start = text.rfind(".", 0, index)
    start = start + 1 if start != -1 else 0
    end = text.find(".", index)
    end = end + 1 if end != -1 else len(text)
    return text[start:end]


def match_organisms(text: str, organism_labels: list) -> list:
    found = []
    text_lower = text.lower()

    def is_negated(idx: int) -> bool:
        sentence = _sentence_containing(text, idx).lower()
        return any(p in sentence for p in ORGANISM_NEGATION_PHRASES)

    for label in organism_labels:
        # Labels can have a parenthetical anywhere ("Cystoisospora
        # (Isospora) belli", "...(HIV)") — match on the label with ALL
        # parenthetical asides removed, not just a trailing one.
        base = re.sub(r"\s*\([^)]*\)\s*", " ", label).strip()
        base = re.sub(r"\s+", " ", base)
        if not base:
            continue
        idx = text_lower.find(base.lower())
        if idx != -1 and not is_negated(idx) and label not in found:
            found.append(label)

    for synonym, canonical_label in ORGANISM_SYNONYMS.items():
        idx = text_lower.find(synonym)
        if idx != -1 and not is_negated(idx) and canonical_label not in found:
            if canonical_label in organism_labels:
                found.append(canonical_label)

    return found


# ─── Syndrome matching ──────────────────────────────────────────────────
# (syndrome_tag, [keywords]) — a case can match multiple syndromes.
SYNDROME_KEYWORDS = [
    ("necrotizing fasciitis", ["necrotizing fasciitis"]),
    ("skin and soft tissue infection", [
        "cellulitis", "soft tissue infection", "skin lesion", "skin infection",
        "abscess", "folliculitis", "impetigo", "wound infection", "ulcer",
        "pyoderma", "furuncle", "carbuncle",
    ]),
    ("bacteremia / sepsis", [
        "bacteremia", "sepsis", "septic shock", "bloodstream infection", "septicemia",
    ]),
    ("endocarditis", ["endocarditis"]),
    ("pneumonia / pulmonary infection", [
        "pneumonia", "pulmonary infiltrate", "lung abscess", "pleural effusion",
        "respiratory failure", "pulmonary nodule",
    ]),
    ("tuberculosis", ["tuberculosis", "tuberculous"]),
    ("meningitis / encephalitis", [
        "meningitis", "encephalitis", "brain abscess", "cerebral abscess",
        "meningoencephalitis",
    ]),
    ("osteomyelitis / septic arthritis", [
        "osteomyelitis", "septic arthritis", "bone infection", "joint infection",
    ]),
    ("gastrointestinal infection", [
        "colitis", "gastroenteritis", "enteritis", "diarrhea", "intestinal infection",
        "peritonitis", "hepatic abscess", "liver abscess",
    ]),
    ("genitourinary infection", [
        "urinary tract infection", "pyelonephritis", "cystitis", "urethritis",
        "cervicitis", "prostatitis", "genital infection", "genital lesion",
    ]),
    ("lymphadenitis", ["lymphadenitis", "lymphadenopathy"]),
    ("ocular infection", ["keratitis", "endophthalmitis", "ocular infection", "eye infection"]),
    ("congenital / perinatal infection", [
        "congenital", "neonatal infection", "perinatal", "newborn infection",
    ]),
    ("disseminated / systemic infection", ["disseminated", "systemic infection"]),
    ("myositis", ["myositis", "pyomyositis"]),
    ("fever of unknown origin", ["fever of unknown origin", "fuo"]),
]


def match_syndromes(text: str) -> list:
    text_lower = text.lower()
    return [tag for tag, keywords in SYNDROME_KEYWORDS
            if any(kw in text_lower for kw in keywords)]


# ─── Host characteristic matching ───────────────────────────────────────
AGE_PATTERNS = [
    (re.compile(r"\bneonate\b|\bnewborn\b|\b\d{1,2}-day-old\b", re.I), "neonate"),
    (re.compile(r"\binfant\b|\b\d{1,2}-month-old\b", re.I), "infant"),
    (re.compile(r"\bchild\b|\btoddler\b|\bpediatric\b", re.I), "child"),
    (re.compile(r"\badolescent\b|\bteenager\b|\bteen\b", re.I), "adolescent"),
    (re.compile(r"\belderly\b|\bgeriatric\b|\bolder adult\b", re.I), "elderly adult"),
]

# "in his/her Xs" decade phrasing, e.g. "in his twenties" / "in her 60s"
DECADE_RE = re.compile(
    r"\bin (?:his|her|their) (twenties|thirties|forties|fifties|sixties|seventies|"
    r"eighties|nineties|\d0s)\b", re.I
)

IMMUNOCOMPROMISE_KEYWORDS = [
    "hiv", "human immunodeficiency virus", "transplant", "chemotherapy",
    "immunosuppress", "immunocompromised", "neutropenia", "neutropenic",
    "corticosteroid", "prednisone", "leukemia", "lymphoma", "malignancy",
    "chronic granulomatous disease", "asplenia", "splenectomy",
]

DIABETES_KEYWORDS = ["diabetes mellitus", "diabetic"]

EXPOSURE_KEYWORDS = [
    # "physician"/"nurse" deliberately excluded — in this corpus they
    # almost always describe who *treated* the patient, not the
    # patient's own occupation.
    ("healthcare worker", ["healthcare worker", "health care worker"]),
    ("animal contact", ["cat bite", "dog bite", "animal contact", "farm animal", "livestock"]),
    ("tick exposure", ["tick bite", "tick exposure"]),
    ("travel history", ["travel to", "recent travel", "returning traveler"]),
    ("injection drug use", ["injection drug use", "intravenous drug use", "iv drug use"]),
    ("occupational exposure", ["occupational exposure", "farmer", "veterinarian", "abattoir"]),
]

# "pregnant"/"pregnancy" without "gestation" — that word alone is too
# often about an infant's own birth history (gestational age at birth)
# rather than the patient currently being pregnant.
PREGNANCY_KEYWORDS = ["pregnant", "pregnancy"]

# Phrases that, if they appear shortly before a matched keyword, mean the
# keyword doesn't actually apply to the patient — either because it's
# negated ("no history of...") or because it's describing someone else
# (the patient's mother, in an infant case; the patient's spouse, etc).
NEGATION_WINDOW_CHARS = 45
NEGATION_PHRASES = [
    "no history of", "denied", "without a history of", "no known",
    "negative for", "no prior", "not have", "ruled out",
]
OTHER_PERSON_PHRASES = ["mother", "wife", "husband", "father", "sister", "brother", "grandmother", "grandfather"]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _is_negated_or_misattributed(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - NEGATION_WINDOW_CHARS):match_start].lower()
    if any(phrase in window for phrase in NEGATION_PHRASES):
        return True
    # Attribution context (e.g. "the infant's mother had...pregnancy")
    # can be a full clause earlier than a fixed window would catch, and
    # clinical narrative often introduces the subject once then carries
    # it across sentences without repeating it — check the current
    # sentence *and* the one before it.
    sentence_start = text.rfind(".", 0, match_start)
    sentence_start = sentence_start + 1 if sentence_start != -1 else 0
    prev_sentence_start = text.rfind(".", 0, max(0, sentence_start - 1))
    prev_sentence_start = prev_sentence_start + 1 if prev_sentence_start != -1 else 0
    context = _sentence_containing(text, match_start).lower()
    if prev_sentence_start < sentence_start:
        context += " " + text[prev_sentence_start:sentence_start].lower()
    if any(phrase in context for phrase in OTHER_PERSON_PHRASES):
        return True
    return False


def _find_unnegated(text: str, keywords: list) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        idx = text_lower.find(kw)
        while idx != -1:
            if not _is_negated_or_misattributed(text, idx):
                return True
            idx = text_lower.find(kw, idx + 1)
    return False


def match_host_tags(history_text: str) -> list:
    tags = []

    decade_match = DECADE_RE.search(history_text)
    matched_age = False
    for pattern, label in AGE_PATTERNS:
        if pattern.search(history_text):
            tags.append(label)
            matched_age = True
            break
    if not matched_age and decade_match:
        tags.append("adult")

    if _find_unnegated(history_text, IMMUNOCOMPROMISE_KEYWORDS):
        tags.append("immunocompromised")
    if _find_unnegated(history_text, DIABETES_KEYWORDS):
        tags.append("diabetes mellitus")
    if _find_unnegated(history_text, PREGNANCY_KEYWORDS):
        tags.append("pregnant")

    for label, keywords in EXPOSURE_KEYWORDS:
        if _find_unnegated(history_text, keywords):
            tags.append(label)

    return tags


def build_tags(case: dict, organism_labels: list) -> list:
    diag_lead = diagnosis_lead(case.get("diagnosis", ""))
    # Organism names are sometimes confirmed a sentence or two later than
    # the syndrome/diagnosis label itself (e.g. "Mycobacterium avium
    # complex pulmonary infection. The patient underwent bronchoscopy.
    # Culture grew Mycobacterium avium complex.") — use a slightly wider
    # window for organism matching specifically. Wider than this starts
    # picking up differential-diagnosis discussion and introduces wrong
    # answers, which is worse than a missed tag; 3 sentences is the
    # sweet spot found by testing against this corpus.
    diag_lead_for_organism = diagnosis_lead(case.get("diagnosis", ""), n_sentences=3)
    title = case.get("title", "") or ""
    history = case.get("history", "") or ""

    organisms = match_organisms(diag_lead_for_organism, organism_labels)
    syndromes = match_syndromes(f"{title} {diag_lead}")
    hosts = match_host_tags(history)

    tags = []
    tags += [f"organism:{o}" for o in organisms]
    tags += [f"syndrome:{s}" for s in syndromes]
    tags += [f"host:{h}" for h in hosts]
    return tags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Print a sample of results without writing case_library.json")
    args = parser.parse_args()

    organism_labels = load_organism_labels()

    with open(CASE_LIBRARY) as f:
        cases = json.load(f)

    tagged = 0
    for case in cases:
        case["tags"] = build_tags(case, organism_labels)
        if case["tags"]:
            tagged += 1

    print(f"Tagged {tagged}/{len(cases)} cases with at least one tag")

    if args.dry_run:
        for case in cases[:15]:
            print(f"\n{case['id']} — {case['title']}")
            print("  ", case["tags"])
        return

    with open(CASE_LIBRARY, "w") as f:
        json.dump(cases, f, indent=2)
    print(f"Wrote {CASE_LIBRARY}")


if __name__ == "__main__":
    main()
