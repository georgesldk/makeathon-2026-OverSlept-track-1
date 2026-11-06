// Read-only examples for Neo4j Browser. Run each query separately.
// Historical claims and model-produced assessments are not proof of efficacy.

// 1. Find entries by name (replace "carrot" as needed).
MATCH (e:HistoricalEntry)
WHERE toLower(coalesce(e.name, '')) CONTAINS 'carrot'
RETURN e.book AS book, e.entry_key AS entry_id, e.label AS chapter,
       e.name AS name, e.snapshot_id AS snapshot
ORDER BY book, name LIMIT 25;

// 2. Show claims and their original quotations for one entry.
MATCH (e:HistoricalEntry {book: 'culpeper', entry_key: 'carrots'})-[:HAS_CLAIM]->(c:HistoricalClaim)
RETURN c.source_claim_id AS claim_id, c.quote AS historical_quote,
       c.claim_text AS interpretation, c.kind AS kind, c.relation AS relation,
       c.plant_part AS plant_part, c.preparation AS preparation, c.route AS route,
       c.model_label AS extraction_label, c.dataset_id AS dataset_id
ORDER BY claim_id;

// 3. Show MeSH mappings and their recorded match qualities for a claim.
MATCH (c:HistoricalClaim {source_claim_id: 'culpeper:carrots:c05'})
      -[:HAS_MAPPING]->(mapping:ConceptMapping)-[:MAPS_TO]->(term:MedicalConcept)
RETURN c.source_claim_id AS claim_id, c.quote AS quotation,
       term.source_id AS mesh_id, term.name AS mesh_name,
       mapping.match AS mapping_quality, mapping.proposed AS proposed_term;

// 4. Show studies and their individual assessments for a claim. The result is
// not a claim of proven efficacy; check the original source and review status.
MATCH (c:HistoricalClaim {source_claim_id: 'culpeper:carrots:c05'})
      <-[:ABOUT_CLAIM]-(unit:ClaimPlantUnit)
MATCH (unit)-[:USES_HYPOTHESIS]->(h:IdentificationHypothesis)
MATCH (a:EvidenceAssessment)-[:ASSESSES_UNIT]->(unit)
MATCH (a)-[:ASSESSES_STUDY]->(study:Study)
OPTIONAL MATCH (a)-[:HAS_EXCERPT]->(x:EvidenceExcerpt)
RETURN c.source_claim_id AS claim_id, c.quote AS historical_quote,
       h.accepted_name AS candidate, unit.tier AS identification_tier,
       study.source_study_id AS study_id, study.title AS study_title,
       a.evidence_type AS study_type, a.finding AS finding,
       a.applicability AS applicability, a.badge AS recorded_badge,
       a.review_status AS review_status,
       collect(DISTINCT {field: x.field, text: x.text}) AS excerpts
ORDER BY study_id;

// 5. Inspect stored cross-book groupings as inferences, not proven equivalence.
MATCH (group:ClaimLink)-[:GROUPS_CLAIM]->(claim:HistoricalClaim)
WITH group, collect(DISTINCT claim.book) AS books, collect(DISTINCT claim.source_claim_id) AS claim_ids
WHERE size(books) > 1
RETURN group.species AS candidate_name, group.mesh_ui AS mesh_id,
       group.mesh_name AS mesh_name, group.both_A AS both_A, books, claim_ids
LIMIT 25;
