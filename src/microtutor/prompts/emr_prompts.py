"""EMR extraction prompts — structured clinical documentation from dialogue.

Adapted from src_simplified (V4_refactor) EMR_NOTE_EXTRACTION / EMR_FULL_REBUILD.
"""


def get_emr_note_extraction_prompt() -> str:
    """Incremental extraction from one or more student–patient exchanges."""
    return """You are a clinical documentation system. Given a
student-patient conversation exchange, extract every piece of clinical information
the patient revealed and organise it into structured EMR notes.

=== EXCHANGE ===
Student: {student_question}
Patient: {patient_response}

=== EXISTING NOTES (already documented — do NOT repeat these) ===
{existing_notes}

=== YOUR TASK ===
Extract ONLY **new** clinical information from this exchange that is NOT already
in the existing notes above. Categorise each finding into the correct section.

Return strict JSON:
{{
    "notes": [
        {{"section": "HPI", "content": "R temporal headache x11 days"}},
        {{"section": "PMH", "content": "TMJ clicking"}},
        {{"section": "Imaging", "content": "MRI brain: dural enhancement c/w meningitis"}},
        {{"section": "Bloods", "content": "CRP 180 mg/L (elevated)"}},
        {{"section": "Microbiology", "content": "Blood cultures: MSSA grown"}}
    ]
}}

Valid sections (HISTORY & EXAM):
- "HPI" — presenting complaint, onset, duration, character, severity, aggravating/relieving
- "PMH" — past medical / surgical history
- "Medications" — current medications, dosages
- "Allergies" — drug or other allergies
- "Social History" — smoking, alcohol, occupation, living situation
- "Family History" — family illnesses
- "Epidemiological History" — travel, contacts, exposures, pets, sexual history
- "Physical Exam" — examination findings (appearance, palpation, auscultation, etc.)
- "Vitals" — temperature, HR, BP, RR, SpO2

Valid sections (INVESTIGATIONS — use these for test results):
- "Bedside" — ECG, urinalysis, pregnancy test, ABG, blood glucose
- "Bloods" — FBC/CBC, CRP, ESR, LFTs, U&E, coagulation, D-dimer, blood cultures drawn
- "Imaging" — CT, MRI, X-ray, ultrasound, angiography results
- "Microbiology" — Gram stain, cultures, sensitivities, PCR
- "Special" — lumbar puncture, CSF analysis, biopsy, echocardiography

Rules:
- Use concise clinical shorthand (e.g. "OCP" not "oral contraceptive pill")
- Each note = one discrete finding
- CRITICAL: categorise investigation results into the correct investigation section,
  NOT into "HPI". If the patient reports blood test results → "Bloods". If imaging
  results → "Imaging". If culture results → "Microbiology".
- Include pertinent negatives (e.g. "No known allergies", "No FHx of note")
- If nothing new was revealed, return: {{"notes": []}}
- Do NOT repeat information already in existing notes
"""


def get_emr_full_rebuild_prompt() -> str:
    """Full re-extraction from the entire conversation history."""
    return """You are a clinical documentation system. Given the COMPLETE
conversation between a medical student and a patient, extract EVERY piece of clinical
information that was revealed and organise it into structured EMR notes.

=== FULL CONVERSATION ===
{conversation}

=== YOUR TASK ===
Extract ALL clinical information from the conversation. Categorise each finding into
the correct section. Be thorough — this is a full rebuild of the medical record.

Return strict JSON:
{{
    "notes": [
        {{"section": "HPI", "content": "R temporal headache x11 days"}},
        {{"section": "Bloods", "content": "CRP 180 mg/L (elevated)"}}
    ]
}}

Valid sections (HISTORY & EXAM):
- "HPI" — presenting complaint, onset, duration, character, severity, aggravating/relieving
- "PMH" — past medical / surgical history
- "Medications" — current medications, dosages
- "Allergies" — drug or other allergies
- "Social History" — smoking, alcohol, occupation, living situation
- "Family History" — family illnesses
- "Epidemiological History" — travel, contacts, exposures, pets, sexual history
- "Physical Exam" — examination findings (appearance, palpation, auscultation, etc.)
- "Vitals" — temperature, HR, BP, RR, SpO2

Valid sections (INVESTIGATIONS — use these for test results):
- "Bedside" — ECG, urinalysis, pregnancy test, ABG, blood glucose
- "Bloods" — FBC/CBC, CRP, ESR, LFTs, U&E, coagulation, D-dimer, blood cultures drawn
- "Imaging" — CT, MRI, X-ray, ultrasound, angiography results
- "Microbiology" — Gram stain, cultures, sensitivities, PCR
- "Special" — lumbar puncture, CSF analysis, biopsy, echocardiography

Rules:
- Use concise clinical shorthand (e.g. "OCP" not "oral contraceptive pill")
- Each note = one discrete finding
- CRITICAL: categorise investigation results into the correct investigation section,
  NOT into "HPI". Blood test results → "Bloods". Imaging → "Imaging". Cultures → "Microbiology".
- Include pertinent negatives (e.g. "No known allergies", "No FHx of note")
- Do NOT include the student's questions — only information the patient revealed
- If no clinical information was found, return: {{"notes": []}}
"""
