# Overlap judge test pairs (v1): review sheet

**Status:** draft labels proposed by Claude, awaiting your approval.

Each pair is a **proposed question** (what the pipeline would suggest) and a **published review** that already exists in PubMed. The label says whether that published review already answers the proposed question.

- **duplicate**: the published review already answers it, so the pipeline should reject the question.
- **different**: same topic, but one element (who, what, compared with what, or which outcome) makes it a new question, so the pipeline should keep it.

For each row, ask: *if this proposed question were written up as a new review, would a journal editor say it has already been done by this published review?* Tell me any label you disagree with.

## d1: DUPLICATE

**Proposed question:** Tranexamic acid plus drain clamping to reduce blood loss after primary total knee arthroplasty

- Population: adults undergoing primary total knee arthroplasty
- Intervention: tranexamic acid combined with temporary drain clamping
- Comparator: tranexamic acid alone, drain clamping alone, or no treatment
- Outcomes: transfusion, total blood loss, drain output, haemoglobin drop, deep vein thrombosis
- Study designs: randomised and non-randomised controlled studies

**Published review (2018):** [Tranexamic acid plus drain-clamping can reduce blood loss in total knee arthroplasty: A systematic review and meta-analysis.](https://pubmed.ncbi.nlm.nih.gov/29408472/)

**Why this label:** Same question as the earlier review (PMID 28658157) the candidate is modelled on.

---

## d2: DUPLICATE

**Proposed question:** Oral tranexamic acid for blood loss in total knee arthroplasty

- Population: adults undergoing total knee arthroplasty
- Intervention: oral tranexamic acid
- Comparator: placebo or no tranexamic acid
- Outcomes: total blood loss, haemoglobin reduction, transfusion, complications
- Study designs: randomised controlled trials

**Published review (2018):** [Oral tranexamic acid reduces blood loss in total-knee arthroplasty: A meta-analysis.](https://pubmed.ncbi.nlm.nih.gov/30407285/)

**Why this label:** Same PICO.

---

## d3: DUPLICATE

**Proposed question:** Probiotics for preventing necrotising enterocolitis in preterm infants

- Population: preterm infants
- Intervention: probiotic supplementation
- Comparator: placebo or no probiotic
- Outcomes: necrotising enterocolitis, all cause mortality, sepsis
- Study designs: randomised controlled trials

**Published review (2014):** [A meta-analysis of probiotics for preventing necrotizing enterocolitis in preterm neonates.](https://pubmed.ncbi.nlm.nih.gov/25098619/)

**Why this label:** Same PICO.

---

## d4: DUPLICATE

**Proposed question:** Probiotics for preventing necrotising enterocolitis in preterm infants

- Population: preterm infants
- Intervention: probiotic supplementation
- Comparator: placebo or no probiotic
- Outcomes: necrotising enterocolitis, all cause mortality, sepsis
- Study designs: randomised controlled trials

**Published review (2019):** [Probiotic strategies to prevent necrotizing enterocolitis in preterm infants: a meta-analysis.](https://pubmed.ncbi.nlm.nih.gov/31420743/)

**Why this label:** Same PICO, published later.

---

## d5: DUPLICATE

**Proposed question:** SGLT2 inhibitors in heart failure with preserved or mildly reduced ejection fraction

- Population: adults with heart failure and ejection fraction above 40%
- Intervention: SGLT2 inhibitors
- Comparator: placebo
- Outcomes: cardiovascular death, hospitalisation for heart failure
- Study designs: randomised controlled trials

**Published review (2023):** [SGLT2 inhibitors and cardiovascular outcomes in heart failure with mildly reduced and preserved ejection fraction: A systematic review and meta-analysis.](https://pubmed.ncbi.nlm.nih.gov/36914068/)

**Why this label:** Same population (HFpEF or HFmrEF), same outcomes.

---

## d6: DUPLICATE

**Proposed question:** Adjunctive corticosteroids for adults hospitalised with community acquired pneumonia

- Population: adults hospitalised with community acquired pneumonia
- Intervention: systemic corticosteroids added to usual care
- Comparator: placebo or usual care
- Outcomes: all cause mortality, mechanical ventilation, adverse events
- Study designs: randomised controlled trials

**Published review (2023):** [Efficacy and safety of corticosteroids for the treatment of community-acquired pneumonia: A systematic review and meta-analysis of randomized controlled trials.](https://pubmed.ncbi.nlm.nih.gov/38128217/)

**Why this label:** Same PICO.

---

## d7: DUPLICATE

**Proposed question:** Adjunctive corticosteroids for adults hospitalised with community acquired pneumonia

- Population: adults hospitalised with community acquired pneumonia
- Intervention: systemic corticosteroids added to usual care
- Comparator: placebo or usual care
- Outcomes: all cause mortality, mechanical ventilation, adverse events
- Study designs: randomised controlled trials

**Published review (2025):** [Corticosteroids for adult patients hospitalised with non-viral community-acquired pneumonia: a systematic review and meta-analysis.](https://pubmed.ncbi.nlm.nih.gov/40323455/)

**Why this label:** Same PICO, limited to non viral CAP: still the same question.

---

## d8: DUPLICATE

**Proposed question:** Melatonin or ramelteon for preventing delirium in hospitalised adults

- Population: adults admitted to hospital (medical, surgical or intensive care)
- Intervention: melatonin or ramelteon
- Comparator: placebo or usual care
- Outcomes: incidence of delirium
- Study designs: randomised controlled trials

**Published review (2020):** [Melatonin for delirium prevention in hospitalized patients: A systematic review and meta-analysis.](https://pubmed.ncbi.nlm.nih.gov/33348252/)

**Why this label:** Same PICO.

---

## d9: DUPLICATE

**Proposed question:** Melatonin for preventing delirium in critically ill adults

- Population: critically ill adults in intensive care
- Intervention: exogenous melatonin
- Comparator: placebo or usual care
- Outcomes: incidence and duration of delirium
- Study designs: randomised controlled trials

**Published review (2025):** [Melatonin and delirium in the intensive care units: a systematic review and meta-analysis of randomized controlled trials.](https://pubmed.ncbi.nlm.nih.gov/41051561/)

**Why this label:** Same PICO.

---

## d10: DUPLICATE

**Proposed question:** Corticosteroids for adults with sepsis or septic shock

- Population: adults with sepsis or septic shock
- Intervention: systemic corticosteroids
- Comparator: placebo or standard care
- Outcomes: mortality, shock reversal, adverse events
- Study designs: randomised controlled trials

**Published review (2024):** [Corticosteroids in Sepsis and Septic Shock: A Systematic Review, Pairwise, and Dose-Response Meta-Analysis.](https://pubmed.ncbi.nlm.nih.gov/38250247/)

**Why this label:** Same PICO.

---

## n1: DIFFERENT

**Proposed question:** Tranexamic acid plus drain clamping to reduce blood loss after primary total knee arthroplasty

- Population: adults undergoing primary total knee arthroplasty
- Intervention: tranexamic acid combined with temporary drain clamping
- Comparator: tranexamic acid alone, drain clamping alone, or no treatment
- Outcomes: transfusion, total blood loss, drain output, haemoglobin drop, deep vein thrombosis
- Study designs: randomised and non-randomised controlled studies

**Published review (2018):** [Oral tranexamic acid reduces blood loss in total-knee arthroplasty: A meta-analysis.](https://pubmed.ncbi.nlm.nih.gov/30407285/)

**Why this label:** Record is oral tranexamic acid without drain clamping: different intervention.

---

## n2: DIFFERENT

**Proposed question:** Oral tranexamic acid for blood loss in total knee arthroplasty

- Population: adults undergoing total knee arthroplasty
- Intervention: oral tranexamic acid
- Comparator: placebo or no tranexamic acid
- Outcomes: total blood loss, haemoglobin reduction, transfusion, complications
- Study designs: randomised controlled trials

**Published review (2025):** [Topical Versus Systemic Tranexamic Acid to Reduce Blood Loss After Total Knee and Total Hip Arthroplasty: A Systematic Review and Meta-Analysis.](https://pubmed.ncbi.nlm.nih.gov/40763214/)

**Why this label:** Record compares topical with systemic tranexamic acid, in knee and hip: different comparison.

---

## n3: DIFFERENT

**Proposed question:** Probiotics for preventing necrotising enterocolitis in term neonates with congenital heart disease

- Population: term neonates with congenital heart disease
- Intervention: probiotic supplementation
- Comparator: placebo or no probiotic
- Outcomes: necrotising enterocolitis, mortality
- Study designs: randomised controlled trials

**Published review (2014):** [A meta-analysis of probiotics for preventing necrotizing enterocolitis in preterm neonates.](https://pubmed.ncbi.nlm.nih.gov/25098619/)

**Why this label:** Record is preterm infants: different population.

---

## n4: DIFFERENT

**Proposed question:** Lactoferrin alone for preventing late onset sepsis in preterm infants

- Population: preterm infants
- Intervention: oral lactoferrin without probiotics
- Comparator: placebo
- Outcomes: late onset sepsis, mortality
- Study designs: randomised controlled trials

**Published review (2021):** [Probiotics for Preventing Necrotizing Enterocolitis in Preterm Infants: A Network Meta-Analysis.](https://pubmed.ncbi.nlm.nih.gov/33435456/)

**Why this label:** Record is probiotics for NEC: different intervention and outcome.

---

## n5: DIFFERENT

**Proposed question:** Dapagliflozin for kidney outcomes in adults with type 1 diabetes

- Population: adults with type 1 diabetes
- Intervention: dapagliflozin added to insulin
- Comparator: placebo with insulin
- Outcomes: eGFR decline, albuminuria, diabetic ketoacidosis
- Study designs: randomised controlled trials

**Published review (2023):** [SGLT2 inhibitors and cardiovascular outcomes in heart failure with mildly reduced and preserved ejection fraction: A systematic review and meta-analysis.](https://pubmed.ncbi.nlm.nih.gov/36914068/)

**Why this label:** Same drug class, different population and outcomes.

---

## n6: DIFFERENT

**Proposed question:** Adjunctive corticosteroids for adults hospitalised with community acquired pneumonia

- Population: adults hospitalised with community acquired pneumonia
- Intervention: systemic corticosteroids added to usual care
- Comparator: placebo or usual care
- Outcomes: all cause mortality, mechanical ventilation, adverse events
- Study designs: randomised controlled trials

**Published review (2024):** [Corticosteroids in Sepsis and Septic Shock: A Systematic Review, Pairwise, and Dose-Response Meta-Analysis.](https://pubmed.ncbi.nlm.nih.gov/38250247/)

**Why this label:** Record is sepsis and septic shock of any source: different population.

---

## n7: DIFFERENT

**Proposed question:** Adjunctive corticosteroids for children hospitalised with community acquired pneumonia

- Population: children under 18 hospitalised with community acquired pneumonia
- Intervention: systemic corticosteroids added to usual care
- Comparator: placebo or usual care
- Outcomes: treatment failure, length of stay, mortality
- Study designs: randomised controlled trials

**Published review (2023):** [Corticosteroids in Community-Acquired Bacterial Pneumonia: a Systematic Review, Pairwise and Dose-Response Meta-Analysis.](https://pubmed.ncbi.nlm.nih.gov/37076606/)

**Why this label:** Record is adults: different population.

---

## n8: DIFFERENT

**Proposed question:** Melatonin for preventing delirium in critically ill adults

- Population: critically ill adults in intensive care
- Intervention: exogenous melatonin
- Comparator: placebo or usual care
- Outcomes: incidence and duration of delirium
- Study designs: randomised controlled trials

**Published review (2025):** [Efficacy of Ramelteon, Suvorexant, and Lemborexant for Delirium Prevention in Hospitalized Patients: A Systematic Review and Meta-Analysis.](https://pubmed.ncbi.nlm.nih.gov/40511987/)

**Why this label:** Record is ramelteon, suvorexant and lemborexant, not melatonin: different intervention.

---

## n9: DIFFERENT

**Proposed question:** Melatonin for sleep quality in critically ill adults

- Population: critically ill adults in intensive care
- Intervention: exogenous melatonin
- Comparator: placebo or usual care
- Outcomes: sleep quality and duration
- Study designs: randomised controlled trials

**Published review (2025):** [Melatonin and delirium in the intensive care units: a systematic review and meta-analysis of randomized controlled trials.](https://pubmed.ncbi.nlm.nih.gov/41051561/)

**Why this label:** Record is delirium, not sleep: different outcome.

---

## n10: DIFFERENT

**Proposed question:** Vasopressin versus norepinephrine as first line vasopressor in septic shock

- Population: adults with septic shock
- Intervention: vasopressin as the first vasopressor
- Comparator: norepinephrine as the first vasopressor
- Outcomes: mortality, renal replacement therapy
- Study designs: randomised controlled trials

**Published review (2020):** [Norepinephrine vs Vasopressin: Which Vasopressor Should Be Discontinued First in Septic Shock? A Meta-Analysis.](https://pubmed.ncbi.nlm.nih.gov/31008869/)

**Why this label:** Record asks which vasopressor to stop first: different question.

---
