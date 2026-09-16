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
from sync_data import parse_score, parse_entry, join_events, validate_snapshot, Fetcher, cache_key, annotate_medal_sessions, merge_pdf_events, parse_football_bracket, reconcile_entry_groups
from pdf_events import extract_pdf_events
from update import update


def event(phase='預賽'):
    return {'id': 'fixture', 'date': '2026-10-18', 'time': '08:00',
            'sport_id': '303', 'sport': '滑輪溜冰', 'title': '測試用項目',
            'phase': phase, 'fid': 'fixture', 'pid': 'fixture',
            'report': None, 'source': 'https://sport115.tycg.gov.tw/', 'links': []}


class ScoreInterpretation(unittest.TestCase):
    def test_distinguishes_unpublished_roster_from_published_roster_without_kaohsiung(self):
        template='<div><span>臺北市</span><table><tr><th>姓名</th><th>日期</th></tr>{}</table></div>'
        empty=parse_entry(html.fromstring(template.format('')),'item','303','滑輪溜冰','https://sport115.tycg.gov.tw/')
        published=parse_entry(html.fromstring(template.format('<tr><td>測試選手</td></tr>')),'item','303','滑輪溜冰','https://sport115.tycg.gov.tw/')
        self.assertFalse(empty['roster_published'])
        self.assertTrue(published['roster_published'])
        self.assertEqual(published['names'],[])

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

    def test_award_link_identifies_a_medal_race_without_final_in_its_name(self):
        e=event('');e['title']='滑輪溜冰男子組競速溜冰5000公尺計分賽'
        e['links']=[{'label':'頒獎名單','url':'https://sport115.tycg.gov.tw/Module/Score/Finals_Score.php?FID=fixture'}]
        annotate_medal_sessions([e],[],[])
        self.assertTrue(e['medal_event'])
        doc=html.fromstring('<table><tr><th>序</th><th>比賽單位</th><th>選手</th><th>成績</th><th>名次</th></tr><tr><td>1</td><td>高雄市</td><td>測試選手甲</td><td>12</td><td>2</td></tr></table>')
        rows,_=parse_score(doc,e,e['source']);self.assertEqual(rows[0]['rank'],2)
        e['phase']='預賽';e.pop('medal_event');annotate_medal_sessions([e],[],[])
        rows,_=parse_score(doc,e,e['source']);self.assertIsNone(rows[0]['rank'])

    def test_merged_city_cells_and_multiple_names_keep_all_athletes(self):
        doc=html.fromstring('''<table><tr><th>序</th><th>比賽單位</th><th>選手</th><th>名次</th></tr>
        <tr><td>1</td><td rowspan="2">高雄市</td><td>101 測試選手甲 102 測試選手乙</td><td>1</td></tr>
        <tr><td>2</td><td>103 測試選手丙</td><td>2</td></tr></table>''')
        rows,recognized=parse_score(doc,event(),event()['source'])
        self.assertTrue(recognized)
        self.assertEqual([n for r in rows for n in r['names']],['測試選手甲','測試選手乙','測試選手丙'])
        self.assertTrue(all(r['rank'] is None for r in rows))

    def test_incomplete_report_retains_confirmed_entry_and_missing_registration(self):
        e=event();e['report']=e['source']
        doc=html.fromstring('<table><tr><th>序</th><th>比賽單位</th><th>選手</th><th>名次</th></tr><tr><td>1</td><td>臺北市</td><td>測試選手外縣市</td><td>1</td></tr></table>')
        entry={'pid':'fixture','sport_id':'303','title':e['title'],'names':['測試選手甲','測試選手乙'],'appearances':[{'name':'測試選手甲','fid':'fixture'}],'source':e['source']}
        rows,_=join_events([e],[entry],{e['report']:doc})
        self.assertEqual(rows[0]['names'],['測試選手甲'])
        self.assertEqual(rows[0]['registered_names'],['測試選手乙'])
        self.assertIsNone(rows[0]['rank'])
        self.assertIsNone(rows[0]['advancement'])

    def test_pdf_merge_preserves_distinct_items_and_teammates(self):
        a={**event(), 'title':'男子雙人賽','names':['測試選手甲'],'names_basis':'pdf_roster'}
        records=[a]
        merge_pdf_events(records,[{**a,'id':'different','title':'男女混合雙人賽','names':['測試選手甲','測試選手乙']}])
        self.assertEqual(len(records),2)
        merge_pdf_events(records,[{**a,'id':'same','names':['測試選手甲','測試選手丙']}])
        self.assertEqual(len(records),2)
        self.assertIn('測試選手丙',records[0]['names'])

    def test_long_program_rank_remains_segment_rank(self):
        e={**event(''),'medal_event':True,'ranking_scope':'segment'}
        doc=html.fromstring('<table><tr><th>序</th><th>比賽單位</th><th>選手</th><th>Total</th><th>名次</th></tr><tr><td>1</td><td>高雄市</td><td>測試選手甲</td><td>14.14</td><td>1</td></tr></table>')
        rows,_=parse_score(doc,e,e['source'])
        self.assertEqual(rows[0]['score'],'14.14')
        self.assertEqual(rows[0]['round_rank'],1)
        self.assertIsNone(rows[0]['rank'])

    def test_official_championship_and_bronze_wording_with_punctuation(self):
        rows=parse_football_bracket(['9 月 14 日\n15 13:20 13敗 : 14敗 女生 季、殿軍\n16 15:30 13勝 : 14勝 女生 冠、亞軍'],event()['source'])
        self.assertEqual([r['phase'] for r in rows],['銅牌賽','決賽'])

    def test_award_catalog_requires_complete_items_and_one_stage(self):
        a={**event(''),'sport_id':'313','title':'龍獅運動男女混合組南獅自選'}
        b={**a,'id':'b','title':'龍獅運動男女混合組南獅規定'}
        groups=[{'title':'龍獅運動男女混合組南獅','count':2}]
        entries=[{'title':e['title']} for e in (a,b)]
        annotate_medal_sessions([a,b],[],[],groups,entries)
        self.assertTrue(a['medal_event']);self.assertTrue(b['direct_final'])
        a={**event(''),'sport_id':'313','title':a['title']}
        annotate_medal_sessions([a],[],[],groups,entries[:1])
        self.assertFalse(a.get('medal_event',False))

    def test_repeated_entry_list_respects_registered_group_and_confirmed_appearances(self):
        entries=[{'sport_id':'313','group':'男女混合組北獅','names':['測試選手甲','測試選手乙'],'appearances':[{'name':'測試選手乙','fid':'fixture'}]}]
        registrations=[{'sport_id':'313','group':'男女混合組南獅','name':n} for n in ('測試選手甲','測試選手乙')]
        reconcile_entry_groups(entries,registrations)
        self.assertEqual(entries[0]['names'],['測試選手乙'])


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

    def test_official_pdf_footnotes_and_paired_rosters_do_not_lose_names(self):
        # Small frozen excerpts of the observed PDFs; later schedule revisions
        # must not make this parser regression depend on a live athlete/date.
        names=['徐嘉宏','蔡森茂','李淑凌','陳吳玉霞']
        wood={'sport_id':'205','sport':'木球','title':'木球賽程表.pdf','url':'https://sport115.tycg.gov.tw/fixture-wood.pdf','pages':['10月19日 桿數賽男子組 第一輪'],'tables':[{'page':1,'tables':[[['場次','時間','單位','號碼','姓名']]+[[str(i),'11:30','高雄市','1193','※'+n] for i,n in enumerate(names,1)]]}]}
        pair={'sport_id':'134','sport':'太極拳','title':'太極拳賽程表.pdf','url':'https://sport115.tycg.gov.tw/fixture-pair.pdf','pages':['']*29+['男子指定推手對練'],'tables':[{'page':1,'tables':[]},{'page':2,'tables':[[['10月21日','08:00~11:00','男子指定推手對練初賽'],[None,'11:00~12:00','決賽']]]},{'page':30,'tables':[[['縣市','姓名','出場順序'],['高雄市','張權龍 / 陳冠魁','2']]]}]}
        registrations=[{'sport_id':'205','name':n} for n in names]
        rows=extract_pdf_events([wood,pair],registrations,[{'sport_id':'205','start':'2026-10-19'}])
        woodball={n for e in rows if e['sport_id']=='205' for n in e['names']}
        self.assertTrue({'徐嘉宏','蔡森茂','李淑凌','陳吳玉霞'}<=woodball)
        paired=[e for e in rows if '男子指定推手對練初賽' in e['title']]
        self.assertEqual(len(paired),1)
        self.assertEqual(set(paired[0]['names']),{'張權龍','陳冠魁'})
        self.assertEqual((paired[0]['date'],paired[0]['time']),('2026-10-21','08:00'))

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
