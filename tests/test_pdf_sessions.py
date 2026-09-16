"""Regression cases for schedules which previously disappeared from the calendar."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from pdf_sessions import extract_sessions, names_for


def document(sid, rows=None, text='', **fields):
    return {'sport_id':sid,'sport':'測試','title':'正式賽程表.pdf',
            'url':'https://sport115.tycg.gov.tw/Upfile/test.pdf','pages':[text],
            'layout_pages':[text],'tables':[{'page':1,'tables':[rows]}] if rows else [],**fields}


def reg(sid,name,group):
    return {'sport_id':sid,'name':name,'group':group}


class PublishedSessionsTests(unittest.TestCase):
    def test_powerlifting_uses_competition_not_weigh_in_and_keeps_merged_dates(self):
        rows=[['10月17日','經典健力女子組47kg','08:00–09:30','10:00','經典健力女子組52kg','08:00–09:30','10:00'],
              [None,'經典健力男子組74kg','13:00–14:30','15:00','經典健力男子組59kg','13:00–14:30','15:00']]
        people=[reg('131','女甲','女子組經典健力'),reg('131','男甲','男子組經典健力'),reg('131','裝備甲','男子組裝備健力')]
        events=extract_sessions([document('131',rows)],people)
        self.assertEqual([e['time'] for e in events],['10:00','10:00','15:00','15:00'])
        self.assertTrue(all(e['date']=='2026-10-17' for e in events))
        self.assertEqual(events[0]['names'],['女甲'])
        self.assertEqual(events[2]['names'],['男甲'])

    def test_merged_time_is_a_session_start_not_an_individual_start(self):
        rows=[['10月13日','09:00','001','女子50公尺雙蹼預賽',''],[None,'','002','男子100公尺雙蹼預賽','']]
        people=[reg('327','女甲','女子組蹼泳'),reg('327','男甲','男子組蹼泳'),reg('327','潛水甲','女子組自由潛水')]
        events=extract_sessions([document('327',rows,'蹼泳')],people)
        self.assertEqual([e['time'] for e in events],['09:00','09:00'])
        self.assertTrue(all(e['time_scope']=='session' for e in events))
        self.assertEqual(events[1]['names'],['男甲'])

    def test_folk_sport_trailing_empty_columns_and_absent_disciplines(self):
        rows=[['10月21日','08:30–09:50','女子組','預賽','陀螺團體擲準賽','',None,None],
              [None,'11:10–12:10','女子組','決賽','陀螺團體擲準賽','',None,None],
              [None,'14:10–14:35','女子組','預賽','踢毽個人賽','',None,None]]
        events=extract_sessions([document('133',rows)],[reg('133','甲','女子組陀螺')])
        self.assertEqual(len(events),2)
        self.assertEqual(events[1]['result_state'],'conditional')
        self.assertTrue(events[1]['medal_event'])

    def test_direct_final_does_not_claim_pending_qualification(self):
        rows=[['10月19日','10:50–11:20','女子組','決賽','跳繩限時計次團體賽','']]
        [event]=extract_sessions([document('133',rows)],[reg('133','甲','女子組跳繩')])
        self.assertTrue(event['direct_final'])
        self.assertIsNone(event['advancement'])
        self.assertNotEqual(event['result_state'],'conditional')

    def test_dragon_b_final_is_not_a_medal_race(self):
        text='10月18日\n16 14:40 混合組 100M 決賽B 4\n18 15:00 混合組 100M 決賽A 4'
        events=extract_sessions([document('326',text=text)],[reg('326','甲','公開混合組')])
        self.assertEqual(len(events),2)
        self.assertNotIn('medal_event',events[0])
        self.assertTrue(events[1]['medal_event'])
        self.assertTrue(all(e['result_state']=='conditional' for e in events))

    def test_line_order_preserves_unicycle_dates(self):
        text='115年10月17日\n13:30–16:00 光電球場 獨輪車靜立持久賽決賽 女子組 場地C\n115年10月19日\n09:00–12:00 藝文中心 獨輪車團體花式競技決賽 混合組 藝文中心'
        people=[reg('329','女甲','女子組'),reg('329','團體甲','混合組')]
        events=extract_sessions([document('329',text=text)],people)
        self.assertEqual([e['date'] for e in events],['2026-10-17','2026-10-19'])

    def test_unknown_scan_hash_is_not_given_stale_transcribed_dates(self):
        events=extract_sessions([document('123',sha256='new-version')],[reg('123','甲','男子組')])
        self.assertEqual(events,[])

    def test_mixed_lifesaving_strokes_are_not_mixed_gender_team_entries(self):
        people=[reg('307','男甲','男子組'),reg('307','女甲','女子組'),reg('307','接力甲','男女混合組')]
        self.assertEqual(names_for(people,'307','男子組100公尺混合救生預賽'),['男甲'])

    def test_shifted_guoshu_item_column_keeps_last_days_and_pair_names(self):
        rows=[['10月21日','09:00–12:00',None,'長兵','男子組、女子組',''],
              ['10月22日','09:00–12:00',None,'對練','男女混合組','']]
        people=[reg('122','兵器甲','男子組兵器'),reg('122','對練甲','男女混合組對練')]
        events=extract_sessions([document('122',rows)],people)
        self.assertEqual([e['date'] for e in events],['2026-10-21','2026-10-22'])
        self.assertEqual(events[1]['names'],['對練甲'])

    def test_shooting_round_two_does_not_start_at_the_round_one_explanatory_mention(self):
        text='10月22日\n第一輪第5至12名進入第二輪\n08:00 1 男3甲\n第二輪 (4個場地)\n10:20 1 男12 男11 男10 男9'
        doc=document('208',text=text,title='射擊賽.pdf')
        events=extract_sessions([doc],[reg('208','甲','男子組')])
        self.assertEqual([(e['time'],e['phase']) for e in events],[('08:00','預賽'),('10:20','第二輪')])

    def test_aerobics_uses_published_item_names_and_skips_other_cities(self):
        doc=document('328',[['10月19日','11:00–12:00','混合團體組混雙組'],[None,'14:30–15:30','混合團體組三人組']],text='')
        doc['pages']+=['混合團體組 混雙組\n高雄市 甲、乙 3\n混合團體組 三人組\n臺北市 丙、丁、戊 1']
        doc['layout_pages']=doc['pages']
        events=extract_sessions([doc],[reg('328','甲','混合團體組'),reg('328','乙','混合團體組')])
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['names'],['甲','乙'])
        self.assertEqual(events[0]['names_basis'],'pdf_roster')


if __name__=='__main__':unittest.main()
