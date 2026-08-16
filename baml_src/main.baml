// BAML schema for extracting compliance rules from PDFs

generator python_client {
  output_type "python/pydantic"
  output_dir "../"
  version "0.225.0"
}

client<llm> Claude {
  provider anthropic
  options {
    model claude-sonnet-4
    api_key env.ANTHROPIC_API_KEY
    temperature 0
  }
}

client<llm> Fireworks {
  provider openai
  options {
    model "accounts/fireworks/models/deepseek-v4-flash-0731"
    base_url "https://api.fireworks.ai/inference/v1"
    api_key env.FIREWORKS_API_KEY
    temperature 0
    max_tokens 32000  // Increased for detailed structured extraction
  }
}

enum Modality {
  SHALL
  MUST
  SHOULD
  IMPERATIVE
  DESCRIPTIVE
}

enum Verifiability {
  OBSERVABLE
  MEASURABLE
  DOCUMENTARY
  PROCESS_ONLY
}

enum ObservableKind {
  PHOTO
  VIDEO
  MEASUREMENT
  DOCUMENT
}

class Observable {
  name string @description("Snake_case identifier for this observable, e.g. 'vents_unobstructed'")
  kind ObservableKind @description("PHOTO for visual checks, MEASUREMENT for tape measure/instruments, DOCUMENT for screenshots/records")
  target string @description("What to capture, e.g. 'the HVAC intake vents'")
  method string @description("How to capture it, e.g. 'Take clear photos showing full vent and surrounding area'")
  instrument string? @description("Required tool, e.g. 'tape measure', 'multimeter'. Null if just photo/visual")
  accepts string @description("Acceptance criterion: what must be visible/true in the evidence, e.g. 'vents are unobstructed by cables or infrastructure'")
}

class ComplianceRule {
  id string @description("Unique ID for this rule, e.g. 'HVAC.1', 'HVAC.2'")
  subject_type string @description("What this rule applies to, e.g. 'hvac_vent', 'hvac_controller'")
  predicate string @description("What property must hold, e.g. 'unobstructed', 'ip_enabled'")
  modality Modality @description("IMPERATIVE for commands (Verify/Ensure), MUST for explicit requirements")
  verifiability Verifiability @description("OBSERVABLE for photos, MEASURABLE for instruments, DOCUMENTARY for records")
  observables Observable[] @description("List of things that must be observed/captured to verify compliance")
  citation_span string @description("Exact verbatim quote from source document that this rule interprets")
  confidence float? @description("0.0-1.0, how confident you are this interpretation is correct. Default 0.9 if omitted")
  notes string? @description("Any caveats, ambiguities, or important context")
}

function ExtractRules(document_text: string, doc_name: string) -> ComplianceRule[] {
  client Fireworks

  prompt #"
    You are a compliance analyst. You turn written standards into structured,
    field-verifiable rules. Your output is executed by a technician on site who
    has never read the source document: every rule must be satisfiable using only
    the evidence you name.

    {{ _.role("user") }}
    <document name="{{ doc_name }}">
    {{ document_text }}
    </document>

    Extract every verifiable obligation from the document above.

    <what_counts_as_a_rule>
    Emit a rule when the document tells someone to do, check, install, confirm, or
    maintain something a person could verify on site.

    Do NOT emit a rule for scope statements, definitions, revision history, purpose
    sections, or bare cross-references to other documents.

    One rule per obligation:
    - If one obligation needs several pieces of evidence (a photo AND a
      measurement), that is ONE rule with multiple observables. Do not split it.
    - If one paragraph states two independent obligations, emit two rules.
    - If an obligation has no capturable evidence at all, still emit it with
      verifiability PROCESS_ONLY and an empty observables list.
    </what_counts_as_a_rule>

    <field_rules>
    id: "<SECTION>.<N>" — SECTION is a short uppercase topic token (HVAC, POWER,
      RACK, NET, SEC), N counts from 1 within that section.
    subject_type: the thing being regulated, singular, lowercase_with_underscores.
      "hvac_vent" — not "HVAC Vents", not "vents".
    predicate: the property that must hold, lowercase_with_underscores, stated
      positively: "unobstructed", "labeled", "grounded". Never a check verb
      ("verify_vents") and never a repeat of the subject.
    modality: pick from the document's own wording, not from how important it feels:
      "shall" -> SHALL
      "must" / "is required to" -> MUST
      "should" / "recommended" -> SHOULD
      bare command ("Verify...", "Ensure...", "Photograph...") -> IMPERATIVE
      statement of fact carrying no obligation -> DESCRIPTIVE
    verifiability: pick the strongest that applies, in this order:
      MEASURABLE   — any observable needs an instrument or yields a number
      DOCUMENTARY  — evidence is a record, screenshot, log, or certificate
      OBSERVABLE   — a photo or video settles it
      PROCESS_ONLY — nothing can be captured
    citation_span: copy the sentence(s) from the document CHARACTER FOR CHARACTER.
      Do not paraphrase, fix typos, normalize whitespace, stitch together distant
      sentences, or insert ellipses. It must be findable by exact string search of
      the document text above.
    confidence: 0.9 when the text is explicit; 0.6-0.8 when you inferred the
      subject, the threshold, or the evidence; below 0.6 when genuinely ambiguous.
      Always provide this value.
    notes: only for a real ambiguity, a missing threshold, or a dependency on an
      external document. Omit otherwise — do not restate the rule here.
    </field_rules>

    <observable_rules>
    - name: lowercase_with_underscores, unique within the rule
    - kind: PHOTO for still visual proof | VIDEO only when motion or sequence
      matters | MEASUREMENT for readings and dimensions | DOCUMENT for
      screenshots, logs, certificates, and records
    - target: the exact physical thing or screen to capture
    - method: a concrete instruction including framing or position where it
      matters — "photograph the full vent face straight on from ~1m"
    - instrument: name the tool for MEASUREMENT and DOCUMENT observables
      ("tape measure", "multimeter", "BMS console"). Omit for PHOTO and VIDEO.
    - accepts: the pass/fail test, written so two inspectors would agree. Include
      the numeric threshold and unit whenever the document states one.
    </observable_rules>

    <constraints>
    - Never invent a requirement, threshold, unit, or instrument the document does
      not support. Under-specify and flag it in notes rather than guess.
    - Emit only the fields defined in the schema below. Do not add fields such as
      section, page, severity, category, source, rationale, or reasoning.
    - Return the array and nothing else: no prose, no markdown fences, no preamble.
    - If the document states no verifiable obligations, return [].
    </constraints>

    {{ ctx.output_format }}
  "#
}
