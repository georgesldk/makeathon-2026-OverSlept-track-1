"""Materialize recorded scientific fields; never infer missing source values."""
import json


def promote(kind, row):
    result = dict(row)
    source = json.loads(row['raw_json']) if row.get('raw_json') else {}
    def put(**values):
        result.update(values)
    if kind == 'hypotheses':
        put(family=source.get('family'), decided_by=source.get('decided_by'),
            unresolved_reason=source.get('unresolved_reason'), kingdom_flags=source.get('kingdom_flags'))
    elif kind == 'taxonomy':
        put(wfo_reason=(source.get('wfo') or {}).get('reason'),
            wcvp_reason=(source.get('wcvp') or {}).get('reason'),
            global_names_reason=(source.get('global_names') or {}).get('reason'),
            global_names_match_type=(source.get('global_names_view') or {}).get('match_type'))
    elif kind == 'decisions':
        put(lineages_strong=source.get('lineages_strong'), lineages_medium=source.get('lineages_medium'),
            passage_specific=source.get('passage_specific'), geography=source.get('geography'),
            other_accepted_names=source.get('other_accepted_names'))
    elif kind == 'evidence':
        detail = source.get('detail') or {}
        put(source_lineage=source.get('lineage') or source.get('family'), matched_text=source.get('matched_text'),
            match_type=source.get('match_type'), source_record_id=source.get('record'),
            candidate_full=source.get('candidate_full'), bridge=source.get('bridge'),
            layer=source.get('layer'), attributed_to=source.get('attributed_to'),
            lexicon=detail.get('lexicon'), lexicon_entry=detail.get('entry'), lexicon_citations=detail.get('cites'))
    elif kind == 'comparisons':
        put(batch=source.get('batch'), quotes_not_in_text=source.get('quotes_not_in_text'))
    elif kind == 'claims':
        put(mesh_not_found=source.get('mesh_not_found'), flags=source.get('flags'))
    elif kind == 'studies':
        text = source.get('text') or {}
        other_ids = source.get('other_ids') or {}
        put(text_locator=text.get('locator'), text_sha256=text.get('sha256'), text_kind=text.get('kind'),
            licence_note=text.get('licence_note'), doi=other_ids.get('doi'), pmid=other_ids.get('pmid'),
            pmcid=other_ids.get('pmcid'), nct=other_ids.get('nct'))
    elif kind == 'assessments':
        compatibility = source.get('compatibility') or {}
        validation = source.get('validation') or {}
        comparison = source.get('comparison') or {}
        safety = source.get('safety') or {}
        provenance = source.get('provenance') or {}
        put(**{f'{dest}_match': (compatibility.get(src) or {}).get('value') for dest, src in (
            ('species', 'species'), ('condition', 'condition'), ('action', 'therapeutic_action'),
            ('plant_part', 'plant_part'), ('preparation', 'preparation'), ('route', 'route'))})
        put(mismatches=source.get('mismatches'), unknowns=source.get('unknowns'),
            rules_applied=source.get('rules_applied'), modifiers=source.get('modifiers'),
            schema_ok=validation.get('schema_ok'), excerpts_checked=validation.get('excerpts_checked'),
            excerpts_failed=validation.get('excerpts_failed'), fields_voided=validation.get('fields_voided'),
            review_flag=comparison.get('flag_for_review'), code_model_agree=comparison.get('agree'),
            safety_flag=safety.get('flag'), safety_category=safety.get('category'),
            model_label=provenance.get('model'), prompt_version=provenance.get('prompt_version'),
            raw_response_file=provenance.get('raw_response_file'))
    return result
