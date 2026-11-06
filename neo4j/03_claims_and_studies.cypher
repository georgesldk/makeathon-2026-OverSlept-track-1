// OPTIONAL PARAMETERIZED TEMPLATES — execute each statement individually only
// after real claims/studies exist and their source formats have been verified.
// Schema creation does not create claims, studies, assessments, or findings.
// Every $... map below must contain only Neo4j scalar/list properties; retain
// structured source records as JSON strings. IDs and snapshots must be validated
// by the caller before running these statements.

// Historical claim with the quotation and extraction provenance in $claim.
MATCH (e:HistoricalEntry {id: $entry_id, snapshot_id: $snapshot_id})
WITH e WHERE $claim.id IS NOT NULL AND $claim.snapshot_id = $snapshot_id
MERGE (c:HistoricalClaim {id: $claim.id})
SET c += $claim
MERGE (e)-[:HAS_CLAIM]->(c)
RETURN c.id;

// Concept IDs include namespace and vocabulary version; $mapping carries match
// quality, method and review status. A concept is not an author's wording.
MATCH (c:HistoricalClaim {id: $claim_id, snapshot_id: $snapshot_id})
WITH c WHERE $concept.id IS NOT NULL AND $mapping.id IS NOT NULL AND $mapping.snapshot_id = $snapshot_id
MERGE (m:MedicalConcept {id: $concept.id}) SET m += $concept
MERGE (cm:ConceptMapping {id: $mapping.id}) SET cm += $mapping
MERGE (c)-[:HAS_MAPPING]->(cm) MERGE (cm)-[:MAPS_TO]->(m)
RETURN cm.id;

// A unit is one explicitly linked claim and plant hypothesis from the SAME entry.
// It does not assert that the candidate is the correct historical identification.
MATCH (e:HistoricalEntry {snapshot_id: $snapshot_id})-[:HAS_CLAIM]->(c:HistoricalClaim {id: $claim_id, snapshot_id: $snapshot_id})
MATCH (e)-[:HAS_HYPOTHESIS]->(h:IdentificationHypothesis {id: $hypothesis_id, snapshot_id: $snapshot_id})
WITH c, h WHERE $unit.id IS NOT NULL AND $unit.snapshot_id = $snapshot_id
MERGE (u:ClaimPlantUnit {id: $unit.id}) SET u += $unit
MERGE (u)-[:ABOUT_CLAIM]->(c) MERGE (u)-[:USES_HYPOTHESIS]->(h)
RETURN u.id;

// A recorded cross-book link is an inferred assertion, not remedy equivalence.
MATCH (a:HistoricalClaim {id: $from_id, snapshot_id: $snapshot_id}), (b:HistoricalClaim {id: $to_id, snapshot_id: $snapshot_id})
WITH a,b WHERE a.id <> b.id AND $link.id IS NOT NULL AND $link.snapshot_id = $snapshot_id
MERGE (l:ClaimLink {id: $link.id}) SET l += $link
MERGE (l)-[:FROM_CLAIM]->(a) MERGE (l)-[:TO_CLAIM]->(b)
RETURN l.id;

// Record a study independently of how applicable its results are to a claim.
WITH $study AS row WHERE row.id IS NOT NULL
MERGE (s:Study {id: row.id}) SET s += row
RETURN s.id;

// Assessment describes one source study against one claim + plant unit.
// finding and applicability are independent. Never infer efficacy from a link.
MATCH (u:ClaimPlantUnit {id: $unit_id, snapshot_id: $snapshot_id}), (s:Study {id: $study_id})
WITH u,s WHERE $assessment.id IS NOT NULL AND $assessment.snapshot_id = $snapshot_id
MERGE (a:EvidenceAssessment {id: $assessment.id}) SET a += $assessment
MERGE (a)-[:ASSESSES_UNIT]->(u) MERGE (a)-[:ASSESSES_STUDY]->(s)
RETURN a.id;

// Excerpt is tied to the assessment; text offsets and source locator belong in
// $excerpt and must be validated against the original source by the caller.
MATCH (a:EvidenceAssessment {id: $assessment_id, snapshot_id: $snapshot_id})
WITH a WHERE $excerpt.id IS NOT NULL AND $excerpt.snapshot_id = $snapshot_id
MERGE (x:EvidenceExcerpt {id: $excerpt.id}) SET x += $excerpt
MERGE (a)-[:HAS_EXCERPT]->(x)
RETURN x.id;
