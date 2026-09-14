"""Checks for errors that would misstate attendance, advancement or final rank."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sync_data import parse_score, join_events, validate_snapshot, Fetcher, cache_key
from update import update


def event(phase='預賽'):
    return {'id': 'fixture', 'date': '2026-10-18', 'time': '08:00',
            'sport_id': '303', 'sport': '滑輪溜冰', 'title': '測試用項目',
            'phase': phase, 'fid': 'fixture', 'pid': 'fixture',
            'report': None, 'source': 'https://sport115.tycg.gov.tw/', 'links': []}


class ScoreInterpretation(unittest.TestCase):
    def test_historical_cache_keeps_original_timestamp_but_live_requests_refresh(self):
        url = 'https://sport115.tycg.gov.tw/Module/Score/InstantScore.php?FID=fixture'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / (cache_key(url) + '.html')
            path.write_text('<html><body>previous report</body></html>')
            original_time = path.stat().st_mtime
            reader = Fetcher(temporary)
            with patch('sync_data.urlopen', side_effect=RuntimeError('network unavailable')) as network, patch('sync_data.time.sleep'):
                self.assertIn('previous report', reader.get(url, 86400).text_content())
                network.assert_not_called()
                self.assertEqual(path.stat().st_mtime, original_time)
                with self.assertRaises(RuntimeError):
                    Fetcher(temporary).get(url, 0)

    def individual(self, advancement='', phase='預賽'):
        # Synthetic fixture only; this is never published as competition data.
        doc = html.fromstring(f'''<table><tr><th>序</th><th>時間</th><th>比賽單位</th>
        <th>選手</th><th>預賽成績</th><th>名次</th><th>晉級決賽</th></tr>
        <tr><td>1</td><td>10:10</td><td>高雄市</td><td>測試選手甲</td>
        <td>10.01</td><td>1</td><td>{advancement}</td></tr></table>''')
        rows, recognized = parse_score(doc, event(phase), 'https://sport115.tycg.gov.tw/')
        self.assertTrue(recognized)
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_preliminary_first_place_is_not_championship_or_qualification(self):
        row = self.individual()
        self.assertEqual(row['round_rank'], 1)
        self.assertIsNone(row['rank'])
        self.assertIsNone(row['advancement'])

    def test_explicit_qualification_marker_required(self):
        self.assertEqual(self.individual('V')['advancement'], 'qualified')
        self.assertEqual(self.individual('未晉級')['advancement'], 'not_qualified')
        self.assertEqual(self.individual(phase='決賽')['rank'], 1)

    def test_registration_is_not_a_final_appearance(self):
        e = event('決賽')
        entry = {'pid': 'fixture', 'sport_id': '303', 'title': e['title'],
                 'names': ['測試選手甲'], 'appearances': [], 'source': e['source']}
        rows, _ = join_events([e], [entry], {})
        self.assertEqual(rows[0]['result_state'], 'conditional')
        self.assertIsNone(rows[0]['advancement'])
        entry['appearances'] = [{'name': '測試選手甲', 'fid': 'fixture'}]
        rows, _ = join_events([e], [entry], {})
        self.assertEqual(rows[0]['advancement'], 'qualified')

    def test_team_uses_its_match_time_and_preserves_score_order(self):
        doc = html.fromstring('''<table><tr><th>序</th><th>時間</th><th>場次</th>
        <th colspan="3">比賽單位 選手</th><th>勝隊</th><th>成績</th><th>備註</th></tr>
        <tr><td>1</td><td>13:00</td><td>6</td><td>金門縣<br>測試選手乙</td>
        <td>對</td><td>高雄市<br>01 測試選手甲</td><td>高雄市</td><td>2:7</td><td></td></tr></table>''')
        rows, recognized = parse_score(doc, event(), 'https://sport115.tycg.gov.tw/')
        self.assertTrue(recognized)
        self.assertEqual(rows[0]['time'], '13:00')
        self.assertEqual(rows[0]['names'], ['測試選手甲'])
        self.assertEqual(rows[0]['score_order'], '高雄在後')
        self.assertEqual(rows[0]['result_state'], 'won')
        self.assertIsNone(rows[0]['rank'])


class PublishedData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'site/data/snapshot.json').read_text(encoding='utf-8'))
        cls.docs = json.loads((ROOT / 'site/data/documents.json').read_text(encoding='utf-8'))

    def test_complete_links_and_distinct_identifiers(self):
        d = self.data
        self.assertTrue(validate_snapshot(d))
        athletes = {(a['sport_id'], a['name']): a for a in d['athletes']}
        events = {e['id'] for e in d['events']}
        finals = {e['id'] for e in d['finals']}
        entries = {e['pid'] for e in d['entries']}
        for a in d['athletes']:
            self.assertTrue(set(a['event_ids']) <= events)
            self.assertTrue(set(a['final_ids']) <= finals)
            self.assertTrue(set(a['entry_ids']) <= entries)
        for e in d['events']:
            for name in e['names']:
                self.assertIn(e['id'], athletes[(e['sport_id'], name)]['event_ids'])
            if e['result_state'] == 'conditional':
                self.assertIsNone(e.get('rank'))
                self.assertNotEqual(e.get('advancement'), 'qualified')

    def test_all_catalog_attachments_have_saved_content(self):
        self.assertEqual({d['url'] for d in self.data['documents']},
                         {d['url'] for d in self.docs['documents']})
        for document in self.docs['documents']:
            self.assertEqual(document['page_count'], len(document['pages']))
            self.assertTrue(document['url'].startswith('https://sport115.tycg.gov.tw/'))

    def test_published_registration_contains_only_needed_fields(self):
        self.assertTrue(self.data['registrations'])
        for registration in self.data['registrations']:
            self.assertTrue(set(registration) <= {'id', 'athlete_id', 'name', 'sport_id', 'sport', 'group', 'role', 'source'})
            self.assertIn(registration['role'], ('隊員', '隊長'))
        for a in self.data['athletes']:
            self.assertNotIn('測試選手', a['name'])

    def test_local_scripts_styles_and_dom_targets_exist(self):
        page = html.fromstring((ROOT / 'site/index.html').read_text(encoding='utf-8'))
        for ref in page.xpath('//script/@src | //link[@rel="stylesheet"]/@href'):
            self.assertTrue((ROOT / 'site' / ref).is_file(), ref)
        ids = page.xpath('//*[@id]/@id')
        self.assertEqual(len(ids), len(set(ids)))
        script = (ROOT / 'site/app.js').read_text(encoding='utf-8')
        for identifier in re.findall(r"\$\('([^']+)'\)", script):
            self.assertIn(identifier, ids)

    def test_failed_update_retains_all_previous_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            original = json.dumps(self.data, ensure_ascii=False)
            (folder / 'snapshot.json').write_text(original, encoding='utf-8')
            (folder / 'documents.json').write_text('previous documents', encoding='utf-8')
            with patch('update.subprocess.run', side_effect=subprocess.CalledProcessError(1, ['fixture'])):
                self.assertEqual(update(folder, folder / 'cache'), 1)
            self.assertEqual((folder / 'snapshot.json').read_text(encoding='utf-8'), original)
            self.assertEqual((folder / 'documents.json').read_text(encoding='utf-8'), 'previous documents')
            self.assertEqual(json.loads((folder / 'sync-status.json').read_text())['status'], 'error')


if __name__ == '__main__':
    unittest.main()
