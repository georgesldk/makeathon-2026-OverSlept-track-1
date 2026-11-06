"""Optional read-only integration checks against the real local API and graph."""
import json
import os
import unittest
from urllib.parse import quote
from urllib.request import urlopen

from neo4j import GraphDatabase

ENABLED = os.environ.get('ETHNOTRACE_TEST_LIVE') == '1'


@unittest.skipUnless(ENABLED, 'Set ETHNOTRACE_TEST_LIVE=1 to test a running local API and Neo4j')
class LiveAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = GraphDatabase.driver(os.environ.get('NEO4J_URI', 'neo4j://127.0.0.1:7687'), auth=(os.environ.get('NEO4J_USER', 'neo4j'), os.environ['NEO4J_PASSWORD']))
        cls.database = os.environ.get('NEO4J_DATABASE', 'ethnotrace-clean')

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()

    def get(self, path):
        with urlopen('http://127.0.0.1:8787/api' + path, timeout=30) as response:
            return json.load(response)

    def cypher(self, q, **params):
        with self.driver.session(database=self.database, default_access_mode='READ') as session:
            return [r.data() for r in session.run(q, **params)]

    def find(self, name, book):
        data = self.get('/entries?q=' + quote(name) + '&book=' + book)
        item = next(x for x in data['items'] if x['name'] == name)
        return self.get('/entries/' + item['id'])

    def test_culpeper_carrots_and_real_historical_text(self):
        e = self.find('Carrots', 'culpeper')
        self.assertIn('Garden Carrots', e['introduction'])
        self.assertTrue(any(x['hypothesis'].get('accepted_name') == 'Daucus carota L.' and x['decision']['tier'] == 'A' for x in e['candidates']))
        actual = self.cypher('MATCH (e:HistoricalEntry {id:$id})-[:HAS_HYPOTHESIS]->(h) RETURN count(h) AS n', id=e['entry']['id'])[0]['n']
        self.assertEqual(len(e['candidates']), actual)

    def test_dioscorides_tier_a(self):
        e = self.find('μῆον', 'dioscorides')
        self.assertEqual(e['entry']['label'], '1.3')
        self.assertTrue(any(x['decision'] and x['decision']['tier'] == 'A' for x in e['candidates']))
        self.assertIn('μῆον', e['historical_text'])

    def test_multiple_different_candidates_remain_separate(self):
        e = self.get('/entries/' + self.cypher('MATCH (e:HistoricalEntry {book:"dioscorides",label:"1.117"}) RETURN e.id AS id')[0]['id'])
        names = {x['hypothesis'].get('accepted_name') for x in e['candidates'] if x['decision'] and x['decision']['tier'] in ('A', 'B')}
        self.assertGreaterEqual(len(names), 2)

    def test_mesh_mapping(self):
        e = self.find('Carrots', 'culpeper')
        c = next(x for x in e['claims'] if x['claim']['source_claim_id'] == 'culpeper:carrots:c05')
        self.assertTrue(any(x['name'] == 'Menstruation' and x['match'] == 'exact' for x in c['concepts']))
        self.assertIn('women', c['claim']['quote'])

    def test_real_catalogue_filters(self):
        path = '/entries?q=Carrots&book=culpeper&tier=A&family=Apiaceae&concept=Menstruation&research=1'
        results = self.get(path)['items']
        self.assertTrue(any(item['name'] == 'Carrots' for item in results))
        self.assertEqual(self.get('/entries?q=Carrots&family=Solanaceae')['items'], [])

    def test_claim_study_and_quote_are_same_as_graph(self):
        e = self.find('Carrots', 'culpeper')
        claim = next(x['claim'] for x in e['claims'] if x['claim']['source_claim_id'] == 'culpeper:carrots:c05')
        rows = self.get('/claims/' + claim['id'])['studies']
        expected = self.cypher('MATCH (:HistoricalClaim {id:$id})<-[:ABOUT_CLAIM]-(:ClaimPlantUnit)<-[:ASSESSES_UNIT]-(a:EvidenceAssessment)-[:ASSESSES_STUDY]->(s) RETURN a.id AS id, s.title AS title', id=claim['id'])
        self.assertEqual({r['assessment']['id'] for r in rows}, {r['id'] for r in expected})
        self.assertTrue(all(r['study']['title'] for r in rows))

    def test_missing_evidence_and_not_assessed(self):
        e = self.find('Bifoil', 'culpeper')
        self.assertFalse(any(x['decision'] and x['decision']['tier'] in ('A', 'B') for x in e['candidates']))
        self.assertEqual(e['claims'], [])

    def test_lsj_provenance(self):
        entry_id = self.cypher('MATCH (e:HistoricalEntry {book:"dioscorides", label:"1.1"}) RETURN e.id AS id')[0]['id']
        e = self.get('/entries/' + entry_id)
        h = next(x['hypothesis'] for x in e['candidates'] if x['hypothesis'].get('accepted_name') == 'Iris × florentina L.')
        rows = self.get('/candidates/' + h['id'])['evidence']
        self.assertTrue(any(v.get('lexicon') == 'LSJ' and v.get('lexicon_entry') == '*)=iris' and '1.1' in v.get('lexicon_citations', []) for v in rows))


if __name__ == '__main__':
    unittest.main()
