// Example read-only queries. Supply $snapshot_id, $book_id and $entry_key as parameters.
// The graph stores pipeline outputs as provisional assertions, including X candidates.
MATCH (s:PipelineSnapshot {id: $snapshot_id})-[:INCLUDES]->(e:HistoricalEntry {book: $book_id, entry_key: $entry_key})
OPTIONAL MATCH (e)-[:HAS_HYPOTHESIS]->(h:IdentificationHypothesis)
OPTIONAL MATCH (h)-[:HAS_DECISION]->(d:EligibilityDecision)
RETURN e.name, h.accepted_name, d.tier, d.rules, d.caveats, d.reasons
ORDER BY d.tier, h.accepted_name;

// Source rows are retained even if a safe candidate link could not be established.
MATCH (s:PipelineSnapshot {id: $snapshot_id})-[:INCLUDES]->(e:HistoricalEntry {book: $book_id, entry_key: $entry_key})-[:HAS_EVIDENCE]->(ev:EvidenceRecord)
OPTIONAL MATCH (ev)-[:RELATES_TO_HYPOTHESIS]->(h:IdentificationHypothesis)
RETURN ev.node, ev.original_candidate, ev.source, ev.grade, ev.raw_json, h.accepted_name
ORDER BY ev.line_number;

// Inspect unmatched or ambiguous links, not only visible candidates.
MATCH (s:PipelineSnapshot {id: $snapshot_id})-[:INCLUDES]->(e:HistoricalEntry)-[:HAS_EVIDENCE]->(ev:EvidenceRecord)
WHERE ev.hypothesis_link_status <> 'unique'
RETURN e.book, e.entry_key, ev.node, ev.hypothesis_link_status, ev.raw_json
LIMIT 100;

// Inspect resolved-name assertions from each backbone separately.
MATCH (s:PipelineSnapshot {id: $snapshot_id})-[:HAS_TAXONOMIC_RESOLUTION]->(t:TaxonomicResolution)
WHERE t.book = $book_id AND t.original_name = $scientific_name
RETURN t.original_name, t.agreement, t.wfo_json, t.wcvp_json, t.global_names_json, t.raw_json;

// Entries sharing an authority-specific record are candidate comparisons, not
// claims that the books identify the same plant or the remedies are equivalent.
MATCH (s:PipelineSnapshot {id: $snapshot_id})-[:INCLUDES]->(a:HistoricalEntry {book: 'culpeper'})-[:HAS_HYPOTHESIS]->(ha:IdentificationHypothesis)-[:HAS_NAME_RESOLUTION]->(ra:TaxonomicResolution)-[:RESOLVES_TO]->(taxon:Taxon)<-[:RESOLVES_TO]-(rb:TaxonomicResolution)<-[:HAS_NAME_RESOLUTION]-(hb:IdentificationHypothesis)<-[:HAS_HYPOTHESIS]-(b:HistoricalEntry {book: 'dioscorides'})<-[:INCLUDES]-(s)
WHERE taxon.authority = $authority AND taxon.release = $release
RETURN DISTINCT taxon.source_id, a.entry_key, a.name, b.entry_key, b.label,
       ha.accepted_name, hb.accepted_name;

// All independently reported study assessments for one claim + plant unit.
MATCH (u:ClaimPlantUnit {id: $unit_id, snapshot_id: $snapshot_id})<-[:ASSESSES_UNIT]-(a:EvidenceAssessment)-[:ASSESSES_STUDY]->(study:Study)
OPTIONAL MATCH (a)-[:HAS_EXCERPT]->(excerpt:EvidenceExcerpt)
RETURN study.id, study.title, a.finding, a.applicability, a.evidence_type,
       a.mismatches, a.unknowns, collect(excerpt.text) AS excerpts;

// Display the historical quote, assigned label and source used for each feature.
// These are stored model assessments, not independently verified observations.
MATCH (s:PipelineSnapshot {id: $snapshot_id})-[:INCLUDES]->(e:HistoricalEntry {book: $book_id, entry_key: $entry_key})-[:HAS_DESCRIPTION_COMPARISON]->(c:DescriptionComparison)-[:HAS_CANDIDATE_COMPARISON]->(candidate:CandidateDescription)
OPTIONAL MATCH (candidate)-[:HAS_SCORE]->(score:DescriptionScore)
RETURN candidate.accepted_name, candidate.verdict, candidate.congruence,
       c.model_version, score.feature, score.historical_quote, score.label,
       score.source, score.reason
ORDER BY candidate.accepted_name, score.feature;
