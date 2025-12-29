This is a sophisticated project. Building a linter for Anki cards is a great way to ensure quality, but adding the layer of Ancient Greek (a highly inflected language with complex diacritics) adds significant technical constraints.

Below is a detailed specification for the application, structured to help you build or prototype it effectively.

### **Application Name:** Anki-Hoplite (Working Title)

**Purpose:** A middleware application to ingest, validate, clean, and analyze Ancient Greek Anki cards before they are committed to the main deck.

-----

### **1. High-Level Architecture**

The application acts as a staging area. It does not replace Anki but serves as a gatekeeper.

**Data Flow:**

1.  **Input:** Raw card data (CSV, JSON, or clipboard paste).
2.  **Processing (The Engine):**
      * Normalization (Unicode/Diacritics).
      * NLP Analysis (Lemmatization).
      * Rule-based Linting.
3.  **Reference Check:** Querying existing Anki collection (via **deck export files**) and the Core 500 list.
4.  **Output:** A "Diff" report requiring user approval before final export/sync to Anki.

**Anki Integration Approach (Export-Based):**

Since development occurs in GitHub Codespaces without access to a running Anki instance, the application uses **deck export files** instead of AnkiConnect:

1.  **Export from Anki Desktop:**
    *   In Anki, select the deck (e.g., "Unified Greek")
    *   File → Export → "Notes in Plain Text (.txt)"
    *   Ensure "Include HTML and media references" is checked
    *   Save as `Unified-Greek.txt`

2.  **Check into Repository:**
    *   The export file is committed to `resources/Unified-Greek.txt`
    *   This allows the linter to run in any environment (local, codespace, CI/CD)
    *   Trade-off: Must manually update the export when deck changes significantly

3.  **Update Workflow:**
    *   Periodically re-export the deck when you've added substantial new cards
    *   Commit the updated export file
    *   The linter will detect duplicates against the latest deck state

**Why Export Files vs AnkiConnect:**
*   **Portability:** Works in GitHub Codespaces, CI/CD, without running Anki
*   **Reproducibility:** Export file can be version controlled
*   **Simplicity:** No network calls, localhost dependencies, or plugin management
*   **Trade-off:** Requires manual export updates (acceptable for prototype)

[Image of data processing pipeline flow diagram]

-----

### **2. Functional Specifications**

#### **Feature A: Smart Duplicate Detection (The "Lemma" Problem)**

Standard string matching fails in Greek because `λύω` (I loose) and `λύεις` (you loose) look different but represent the same concept.

  * **Requirement:** The system must identify "Semantic Duplicates" rather than just exact string duplicates.
  * **Logic:**
    1.  **Normalization:** Convert all text to Unicode normalization form C (NFC) to handle polytonic Greek consistently. Strip punctuation.
    2.  **Lemmatization:** Use an NLP library (like CLTK - Classics Language Toolkit) to extract the *lemma* (root form) of the Greek word on the card.
    3.  **Comparison:**
          * *Direct Match:* Is the exact Greek string already in the deck?
          * *Lemma Match:* Do you already have a card for this lemma? (e.g., You are adding `ἔλυσα` (aorist), but you already have `λύω` (present)).
          * *Warning Level:*
              * **High:** Exact duplicate.
              * **Medium:** Same lemma, different inflection (User may genuinely want this for grammar practice).
              * **Low:** Same English definition found on a different Greek word.

#### **Feature B: Tag & Label Hygiene**

Imported decks often contain "junk tags" (e.g., `ch_1`, `import_2023`, `vocab_easy`) that clutter the browser.

  * **Requirement:** Enforce a strict "Allowlist" for tags.
  * **Logic:**
      * User defines a `schema.json` containing allowed tags (e.g., `noun`, `verb`, `aorist`, `thucydides`).
      * **The Cleaner:**
          * If a tag is in the *Allowlist*: Keep it.
          * If a tag is in the *Blocklist*: Delete silently.
          * If a tag is *Unknown*: Flag for manual review (Keep/Delete/Rename).
  * **Auto-Tagging:** Automatically add tags based on the text (e.g., if the front contains `ὁ`, tag as `noun`, `masculine`).

#### **Feature C: Cloze Context Validator**

Cloze cards are useless if the context doesn't narrow down the answer.

  * *Bad:* `___ was a general.` (Could be anyone).

  * *Good:* `Pericles said that ___ was a general.`

  * **Requirement:** Flag cards with high ambiguity.

  * **Heuristics:**

    1.  **Ratio Check:** If the Cloze deletion removes \>50% of the total characters in the field, flag as "Low Context."
    2.  **Stop Word Check:** If the text *outside* the cloze consists only of high-frequency Greek stop words (καί, δέ, ὁ, τόν), flag as "Ambiguous."
    3.  **Minimum Length:** If the total field length is \< 15 characters, flag for review.

#### **Feature D: Core 500 Progress Tracker**

  * **Requirement:** Visualize coverage of the "Top 500" Ancient Greek words.
  * **Data Source:** A static JSON/CSV list of the Top 500 lemmas.
  * **Logic:**
    1.  Scan the current Anki Collection (via deck export file).
    2.  Lemmatize the "Front" field of every card.
    3.  Match against the Top 500 list.
    4.  **On New Import:** Highlight if the new card covers a "New" word from the Top 500 (High Priority) or a word already "Mastered" (Low Priority).

-----

### **3. Data Structure Proposal**

To handle the complexity of Greek, your internal data representation for a "Pending Card" should look like this:

```json
{
  "raw_front": "τοὺς Ἕλληνας",
  "raw_back": "the Greeks (accusative)",
  "derived_data": {
    "normalized_text": "τους ελληνες",
    "lemma": "Ἕλλην",
    "part_of_speech": "noun",
    "is_stop_word": false
  },
  "lint_status": {
    "duplicate_found": true,
    "duplicate_type": "lemma_match",
    "existing_card_id": 14985201,
    "context_score": 0.8,
    "is_core_vocab": true
  }
}
```

-----

### **4. Technical Stack Recommendations**

Since you are dealing with NLP and data processing, Python is the optimal choice here.

| Component | Recommendation | Why? |
| :--- | :--- | :--- |
| **Language** | **Python 3.10+** | Best ecosystem for text processing and Anki interaction. |
| **Greek NLP** | **CLTK (Classical Language Toolkit)** | The gold standard for lemmatizing Ancient Greek. Handles polytonic accents natively. |
| **Anki Interface** | **Deck Export Files (.txt)** | Tab-separated export format with metadata headers. No network dependencies. |
| **UI** | **CLI (prototype)** | Command-line interface for CSV input/output. Future: Streamlit or Textual. |

-----

### **5. Handling Polytonic Greek (Crucial Warning)**

Ancient Greek in digital formats is messy. You must handle **Unicode Normalization**.

  * **Precomposed characters:** `ά` (one character).
  * **Combining characters:** `α` + `´` (two characters).
  * **The Rule:** Always normalize inputs to **NFC** (Normalization Form C) immediately upon ingestion, or your duplicate detector will fail on visually identical words.

### **Next Step**

Would you like me to write a **Python script prototype** that uses `CLTK` to demonstrate how to lemmatize a Greek word and check it against a dummy "Core 500" list?