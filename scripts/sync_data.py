#!/usr/bin/env python3
"""Sync official public competition data. Never infer advancement from rank alone."""
from __future__ import annotations
import argparse, hashlib, json, math, re, sys, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from lxml import html

BASE = 'https://sport115.tycg.gov.tw'
ROOT = Path(__file__).resolve().parents[1]
CITY = '高雄市'
YEAR = 2026
SOURCES = {
 'roster': BASE + '/Module/SignupStats/Sta_Unit_Peoples_List.php?UID=014',
 'finals': BASE + '/Module/Score/Final_Query.php?UID=014',
 'plan': BASE + '/Module/Pages/Index.php?ID=425',
 'catalog': BASE + '/Module/SportItem/ALL_Index.php',
 'instant': BASE + '/Module/Score/Instant.php',
 'awards': BASE + '/Module/Score/Award_Data.php',
}

def clean(value):
    if hasattr(value, 'text_content'): value = value.text_content()
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value or ''))).strip()

def norm(value):
    return re.sub(r'[\s（）()\-－]', '', clean(value)).replace('臺', '台')

def key(*values):
    return hashlib.sha256('|'.join(str(v) for v in values).encode()).hexdigest()[:16]

def official_url(url, origin=BASE):
    url = urljoin(origin, url)
    s = urlsplit(url)
    if s.scheme not in ('http', 'https') or s.hostname != 'sport115.tycg.gov.tw':
        raise ValueError('Refusing non-official source URL')
    return urlunsplit(('https', s.netloc, quote(s.path, safe='/%:@'), quote(s.query, safe='=&%:+'), ''))

def cache_key(url):
    s = urlsplit(official_url(url))
    q = parse_qs(s.query)
    if s.path.endswith('InstantScore.php'): q = {k:v for k,v in q.items() if k == 'FID'}
    canonical = s.path + '?' + urlencode(sorted((k,v[0]) for k,v in q.items()))
    return hashlib.sha256(canonical.encode()).hexdigest()

def date_iso(value):
    value = clean(value)
    m = re.search(r'(\d{3,4})/(\d{1,2})/(\d{1,2})', value)
    if m:
        y,mo,d = map(int,m.groups()); y = y+1911 if y < 1911 else y
    else:
        m = re.search(r'(\d{1,2})[月/](\d{1,2})',value)
        if not m: return None
        mo,d = map(int,m.groups()); y=YEAR
    try: return datetime(y,mo,d).date().isoformat()
    except ValueError: return None

def name_lines(cell):
    result=[]
    for value in cell.xpath('.//text()'):
        # Reports use both <br> and several bib/name pairs in one text node.
        for part in re.split(r'[、,，;；\n]|(?<!\S)(?=\d{1,6}\s*[^\d\s])',value):
            name=re.sub(r'^\d+\s*', '', clean(part))
            if name and not re.fullmatch(r'.{2,4}[市縣]|選手|姓名',name):result.append(name)
    return list(dict.fromkeys(result))

def item_title(value):
    """Remove round suffixes, preserving discipline/weight class parentheses."""
    return norm(re.sub(r'[（(](?:預賽|複賽|準決賽|半決賽|決賽|短曲|長曲|\d+日)[)）]', '',clean(value)))

def is_team_event(event):
    return bool(re.search(r'團體賽|曲棍球|接力',event['title']))

def placement_stage(value):
    value=norm(re.sub(r'(?<=\d)[-－](?=\d)',',',clean(value)))
    if '敗部' in value:return '名次賽'
    if re.search(r'小組決賽|分組決賽',value):return '分組賽'
    if re.search(r'冠[、,]?亞|冠軍[賽戰]|金牌[賽戰]|爭?1[,、.及與和~～]2名|[一1][、,及與和][二2]名',value):return '決賽'
    if re.search(r'季[、,]?殿|季軍[賽戰]|銅牌[賽戰]|爭?3[,、.及與和~～]4名|[三3][、,及與和][四4]名',value):return '銅牌賽'
    if re.search(r'準決賽|半決賽',value):return '準決賽'
    if '決賽' in value:return '決賽'
    if '預賽' in value:return '預賽'
    if '複賽' in value:return '複賽'
    return ''

def table_grid(table):
    """Expand row/column spans before matching headers to athlete cells."""
    grid=[];spans={}
    for tr in table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr'):
        values={col:cell for col,(cell,left) in spans.items()}
        spans={col:(cell,left-1) for col,(cell,left) in spans.items() if left>1}
        col=0
        for cell in tr.xpath('./th|./td'):
            while col in values:col+=1
            width=max(1,int(cell.get('colspan','1')));height=max(1,int(cell.get('rowspan','1')))
            for offset in range(width):
                values[col+offset]=cell
                if height>1:spans[col+offset]=(cell,height-1)
            col+=width
        if values:grid.append((tr,[values.get(i) for i in range(max(values)+1)]))
    return grid

def score_table(table):
    grid=table_grid(table);header_rows=[row for tr,row in grid if tr.xpath('./th') and not tr.xpath('./td')]
    width=max((len(row) for row in header_rows),default=0)
    headers=[' '.join(dict.fromkeys(clean(row[i]) for row in header_rows if i<len(row) and clean(row[i]))) for i in range(width)]
    return headers,[row for tr,row in grid if tr.xpath('./td')]

def table_rows(doc, required):
    for t in doc.xpath('//table[not(.//table)]'):
        headers=[clean(th) for th in t.xpath('.//th')]
        if all(any(w in h for h in headers) for w in required): yield t

def cells(row): return row.xpath('./td')

def options(doc, name):
    return {o.get('value'): clean(o) for o in doc.xpath(f'//select[@name="{name}"]//option') if o.get('value')}

class Fetcher:
    def __init__(self, cache_dir, offline=False):
        self.cache_dir = Path(cache_dir); self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline=offline; self.memory={}; self.observed={}; self.errors=[]
    def get(self, url, max_age=0):
        url=official_url(url); cid=cache_key(url)
        if cid in self.memory: return self.memory[cid]
        p=self.cache_dir/(cid+'.html')
        cached = p.exists() and max_age > 0 and 0 <= time.time()-p.stat().st_mtime < max_age
        if self.offline or cached:
            if not p.exists(): raise RuntimeError('Offline fixture missing: '+url)
            raw=p.read_bytes(); observed=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()
        else:
            for attempt in range(3):
                try:
                    req=Request(url,headers={'User-Agent':'KaohsiungSport115/1.0 (public schedule reader)'})
                    with urlopen(req,timeout=40) as response:
                        if urlsplit(response.url).hostname != 'sport115.tycg.gov.tw': raise ValueError('Unexpected redirect')
                        raw=response.read(12_000_000)
                    if not raw or b'<html' not in raw.lower(): raise ValueError('Expected an HTML page')
                    p.write_bytes(raw); observed=datetime.now(timezone.utc).isoformat();time.sleep(.2);break
                except Exception:
                    if attempt==2: raise
                    time.sleep(1+attempt)
        doc=html.fromstring(raw.decode('utf-8-sig'))
        self.memory[cid]=doc;self.observed[url]=observed
        return doc
    def batch(self, urls, max_ages=None):
        urls=list(dict.fromkeys(urls))
        def one(url):
            try:return url,self.get(url,(max_ages or {}).get(url,0)),None
            except Exception as exc:return url,None,str(exc)
        with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(one,urls))
        out={}
        for url,doc,error in results:
            if error:self.errors.append({'url':url,'message':error})
            else:out[url]=doc
        return out

def paginated(fetcher, first_url, required):
    first=fetcher.get(first_url)
    tables=list(table_rows(first, required))
    if not tables: raise ValueError('Expected data table missing: '+first_url)
    rows=[r for t in tables for r in t.xpath('.//tr[td]')]
    m=re.search(r'共\s*([\d,]+)\s*筆',clean(first))
    expected=int(m.group(1).replace(',','')) if m else None
    links=[a.get('href') for a in first.xpath('//a[@href]') if '下一頁' in clean(a)]
    if links:
        parsed=urlsplit(urljoin(first_url,links[0]));q=parse_qs(parsed.query)
        field=next((k for k in q if k.startswith('pageNum_')),None)
        if not field or expected is None or not rows: raise ValueError('Unknown pagination format')
        total=math.ceil(expected/len(rows)); urls=[]
        for page in range(1,total):
            values={k:v[0] for k,v in q.items()};values[field]=str(page)
            urls.append(urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode(values),'')))
        pages=fetcher.batch(urls)
        if len(pages)!=len(urls):raise ValueError('Incomplete paginated source')
        for url in urls:
            for t in table_rows(pages[url],required):rows.extend(t.xpath('.//tr[td]'))
    if expected is not None and len(rows)!=expected:raise ValueError(f'Row count mismatch: expected {expected}, got {len(rows)}')
    return first,rows

def parse_roster(doc, rows, sport_map):
    groups=options(doc,'GID'); records=[]
    for row in rows:
        c=cells(row);v=[clean(x) for x in c]
        if len(v)<6 or v[1]!=CITY or v[3] not in ('隊員','隊長'):continue
        gid=next((gid for gid,label in groups.items() if label==v[5]),None)
        sid=gid[:3] if gid else next((sid for sid,sport in sport_map.items() if v[5].endswith(sport)),None)
        if not sid or sid not in sport_map:continue
        sport=sport_map[sid]; group=v[5][:-len(sport)] if v[5].endswith(sport) else v[5]
        records.append({'id':key(sid,group,v[2]),'athlete_id':key(sid,v[2]),'name':v[2], 'sport_id':sid,'sport':sport,'group':group,'role':v[3],'source':SOURCES['roster']})
    if not records: raise ValueError('No Kaohsiung athlete registrations found')
    return records

def parse_finals(rows, sport_map):
    results=[]
    for row in rows:
        c=cells(row);v=[clean(x) for x in c]
        if len(v)<10 or v[4]!=CITY:continue
        sid=next((sid for sid,label in sport_map.items() if label==v[1]),'')
        names=name_lines(c[6]);rank=int(v[9]) if v[9].isdigit() else None
        results.append({'id':key('final',v[5],v[3],v[6]),'sport_id':sid,'sport':v[1],'group':v[2],'date':date_iso(v[3]),'title':v[5], 'names':names,'rank':rank,'rank_text':v[9],'score':v[7],'note':v[8],'points':v[10] if len(v)>10 else '', 'source':SOURCES['finals']})
    return results

def parse_plan(doc,sport_map):
    result=[]
    for t in table_rows(doc,['種類','競賽場地','開始','結束']):
        for row in t.xpath('.//tr[td]'):
            v=[clean(x) for x in cells(row)]
            if len(v)<6:continue
            start,end=date_iso(v[4]),date_iso(v[5])
            if not start or not end:continue
            sport=v[1].split('-')[0];sid=next((sid for sid,label in sport_map.items() if label==sport),'')
            if not sid:raise ValueError('Unrecognized sport in date plan: '+sport)
            result.append({'id':key('plan',v[1]),'sport_id':sid,'sport':sport,'discipline':v[1],'venue':v[2],'address':v[3],'start':start,'end':end,'end_note':v[5], 'meeting_venue':v[6] if len(v)>6 else '', 'technical_meeting':v[7] if len(v)>7 else '', 'referee_meeting':v[8] if len(v)>8 else '', 'source':SOURCES['plan']})
    if len({x['sport_id'] for x in result})!=len(sport_map):raise ValueError('Date plan does not cover all official sports')
    return result

def parse_catalog(doc,sport_map):
    result=[]
    for li_index,li in enumerate(doc.xpath('//ul[contains(@class,"SportItemArea")]/li')):
        headings=li.xpath('.//h1|.//h2|.//h3')
        if not headings:continue
        sport=clean(headings[0]);sid=next((sid for sid,label in sport_map.items() if label==sport),None)
        if not sid:continue
        qualification=li_index<2 and sport in ('沙灘手球','五人制足球')
        for inp in li.xpath('.//input[@onclick]'):
            m=re.search(r"(?:window\.open\(|location\.href=)\s*['\"]([^'\"]+)",inp.get('onclick',''))
            if not m:continue
            url=official_url(m.group(1),SOURCES['catalog'])
            # The official catalog appends a fresh clock value, not a file revision.
            if '.pdf?' in url.lower():url=url.split('?')[0]
            result.append({'sport_id':sid,'sport':sport,'label':inp.get('value','文件'),'url':url,'qualification':qualification})
    if not result:raise ValueError('Official document catalog was not parsed')
    return result

def parse_schedule(doc,sid,sport,url):
    events=[]
    for t in table_rows(doc,['時間','項目','狀態']):
        preceding=t.xpath('preceding::a[starts-with(@name,"CompDate")][1]/@name')
        day=date_iso(preceding[0]) if preceding else None
        if not day:raise ValueError('Schedule date missing')
        for row in t.xpath('.//tr[td]'):
            c=cells(row)
            if len(c)!=3:continue
            tm,title=clean(c[0]),clean(c[1]);links=[]
            for a in c[2].xpath('.//a[@href]'):
                links.append({'label':clean(a),'url':official_url(a.get('href'),url)})
            report=next((a['url'] for a in links if 'InstantScore.php' in a['url']),None)
            q=parse_qs(urlsplit(report).query) if report else {}
            phase=placement_stage(title)
            events.append({'id':key(sid,day,tm,title),'sport_id':sid,'sport':sport,'date':day,'time':tm,'title':title,'phase':phase,'fid':q.get('FID',[None])[0],'pid':q.get('PID',[None])[0],'report':report,'source':url,'links':links})
    return events

def parse_award_groups(doc):
    groups=[]
    for table in table_rows(doc,['項目','應頒獎牌數']):
        for row in table.xpath('.//tr[td]'):
            values=[clean(c) for c in cells(row)]
            if len(values)>=2 and values[1].isdigit():groups.append({'title':values[0],'count':int(values[1])})
    return groups

def annotate_medal_sessions(schedule,documents,resources,award_groups=(),entries=()):
    """Use award links and the published PDF, never a preliminary placing."""
    for event in schedule:
        title=event['title'];phase=event['phase'];source=None;basis=''
        daily_team=bool(re.search(r'曲棍球|團體賽',title))
        award=next((a['url'] for a in event.get('links',[]) if 'Finals_Score.php' in a['url']),None)
        if phase in ('決賽','銅牌賽'):
            source=event['source'];basis='官方賽程標示'+phase
        elif award and not daily_team and phase not in ('預賽','複賽','準決賽') and '短曲' not in title:
            source=award;basis='此場次連結官方頒獎名單'
        if event['sport_id']=='303' and not phase:
            speed=next((d for d in documents if d['sport_id']=='303' and '競速' in d['title']),None)
            if speed and '競速' in title:
                label=norm(title.split('競速溜冰')[-1]).replace('美式接力','接力賽')
                gender='女子組' if '女子組' in title else '男子組'
                for page,text in enumerate(speed.get('pages',[]),1):
                    if re.sub(r'\s+','',gender+label+'-決賽') in re.sub(r'\s+','',clean(text)):
                        source=speed['url']+'#page='+str(page);basis='官方 PDF 將本項目列為決賽';break
            art=next((d for d in documents if d['sport_id']=='303' and '花式' in d['title']),None)
            if art and '花式' in title:
                if '基本型' in title and any('基本型頒獎' in norm(p) for p in art.get('pages',[])):
                    source=art['url'];basis='官方花式賽程列基本型比賽及頒獎'
                elif '(長曲)' in clean(title) and any('長曲比賽' in norm(p) and '頒獎' in p for p in art.get('pages',[])):
                    source=art['url'];basis='官方花式賽程最後競賽階段；最終名次採總成績';event['ranking_scope']='segment'
                elif '並排綜合型' in title:
                    technical=next((r['url'] for r in resources if r['sport_id']=='303' and r['label']=='技術手冊'),None)
                    if technical:
                        source=technical+'#page=12';basis='115 年技術手冊：基本型與自由型名次積分加總排名';event['ranking_scope']='aggregate'
        # Award totals enumerate complete item catalogs, not heats. Require one
        # scheduled stage for this exact item, with no qualifying/segment title.
        if not source and not phase and not daily_team and not re.search(r'短曲|長曲|練習|檢查',title):
            group=next((g for g in award_groups if norm(title).startswith(norm(g['title']))),None)
            group_entries=[e for e in entries if group and norm(e['title']).startswith(norm(group['title']))]
            same_item=[e for e in schedule if e['sport_id']==event['sport_id'] and item_title(e['title'])==item_title(title)]
            if group and group['count']==len(group_entries)>0 and len(same_item)==1 and any(item_title(e['title'])==item_title(title) for e in group_entries):
                source=SOURCES['awards'];basis='官方應頒獎牌項目數與完整項目清單相符，本項僅列一個競賽階段'
        if source:
            event.update(medal_event=True,medal_basis=basis,medal_source=source)
            if not phase and event.get('ranking_scope')!='segment':event['phase']='獎牌賽'
        if event.get('medal_event') and not daily_team:
            # A single-round medal item has no qualification round to wait for.
            event['direct_final']=not any(other['sport_id']==event['sport_id'] and item_title(other['title'])==item_title(title) and other['phase'] in ('預賽','複賽','準決賽') for other in schedule)

def parse_entry(doc,pid,sid,sport,url):
    event=options(doc,'PID').get(pid,'');names=[];appearances=[]
    tables=list(table_rows(doc,['姓名','日期']))
    published=any(cells(row) and clean(cells(row)[0]) and not re.search(r'查無|尚未|無資料',clean(cells(row)[0])) for t in tables for row in t.xpath('.//tr[td]'))
    for t in tables:
        labels=t.getparent().xpath('./span')
        if not any(CITY in clean(label) for label in labels):continue
        for row in t.xpath('.//tr[td]'):
            c=cells(row)
            if not c:continue
            for name in name_lines(c[0]):
                if name not in names:names.append(name)
                for a in row.xpath('.//a[contains(@href,"InstantScore.php")]'):
                    fid=parse_qs(urlsplit(a.get('href')).query).get('FID',[None])[0]
                    if fid:appearances.append({'name':name,'fid':fid,'text':clean(a)})
    group=doc.xpath('//select[@name="PID"]//option[@value=$pid]/ancestor::optgroup[1]/@label',pid=pid)
    return {'pid':pid,'sport_id':sid,'sport':sport,'title':sport+event,'group':clean(group[0]) if group else '', 'names':names,'appearances':appearances,'roster_published':bool(published),'source':url}

def reconcile_entry_groups(entries,registrations):
    """Some unpublished entry pages repeat the entire sport's registration list."""
    groups={}
    for row in registrations:groups.setdefault((row['sport_id'],norm(row['name'])),set()).add(norm(row['group']))
    for entry in entries:
        group=norm(entry.get('group'))
        if not group:continue
        original=entry['names'];appeared={a['name'] for a in entry['appearances']}
        entry['names']=[name for name in original if name in appeared or not groups.get((entry['sport_id'],norm(name))) or any(g.startswith(group) or group.startswith(g) for g in groups[(entry['sport_id'],norm(name))])]
        if entry['names']!=original:entry['roster_note']='依官方組別報名名單排除跨組名單；本輪出場紀錄優先。'

def parse_score(doc,event,url):
    """Return confirmed Kaohsiung rows and an explicit report coverage flag."""
    records=[]; recognized=False; incomplete=False
    for t in table_rows(doc,['序']):
        heads,body=score_table(t)
        # Team / head-to-head report: the two participants are separated by 對.
        if '勝隊' in heads or '勝方' in heads:
            recognized=True
            for c in body:
                v=[clean(x) for x in c]
                sep=next((i for i,x in enumerate(v) if x=='對'),None)
                if sep is None or sep<1 or sep+3>=len(c):continue
                left,right=sep-1,sep+1
                ix=left if CITY in v[left] else right if CITY in v[right] else None
                if ix is None:continue
                opponent=clean(c[right if ix==left else left]).split(' ')[0]
                winner=v[sep+2];score=v[sep+3];note=v[-1] if heads[-1]=='備註' else ''
                names=name_lines(c[ix]);tm=next((x for x in v[:left] if re.fullmatch(r'\d{1,2}:\d{2}',x)),event['time'])
                rec={**event,'id':key(event['id'],'match',v[2] if len(v)>2 else v[0]),'match_no':v[2],'time':tm,'time_scope':'match','names':names,'names_basis':'report','opponent':opponent,'score':score,'score_order':'高雄在前' if ix==left else '高雄在後','note':note,'round_rank':None,'rank':None,'advancement':None,'result_state':'won' if CITY in winner else ('lost' if winner else ('draw' if score and re.fullmatch(r'(\d+)[:：]\1',score) else 'pending')), 'source':url}
                stage=placement_stage(note)
                if stage in ('決賽','銅牌賽'):
                    rec.update(phase=stage,medal_event=True,medal_source=url,medal_basis='官方成績報告備註：'+note)
                records.append(rec)
        elif any('選手' in x for x in heads) and any('比賽單位' in x or x=='單位' for x in heads):
            recognized=True
            hmap={h:i for i,h in enumerate(heads)}
            unit=next(i for i,h in enumerate(heads) if '比賽單位' in h or h=='單位')
            ni=next(i for i,h in enumerate(heads) if '選手' in h)
            rank_indices=[i for i,h in enumerate(heads) if '名次' in h]
            final_advance=next((i for i,h in enumerate(heads) if '晉級決賽' in h),None)
            for c in body:
                v=[clean(x) for x in c]
                if len(v)!=len(heads):
                    if any(CITY in x for x in v):incomplete=True
                    continue
                if norm(v[unit])!=norm(CITY):continue
                names=name_lines(c[ni])
                if not names:incomplete=True;continue
                overall=next((i for i,h in enumerate(heads) if h in ('名次','決賽名次','總名次','總排名')),None)
                ri=overall if overall is not None and v[overall] else (rank_indices[0] if rank_indices else None)
                rtext=v[ri] if ri is not None else ''
                rank=int(rtext) if rtext.isdigit() else None
                advance='qualified' if final_advance is not None and v[final_advance].upper() in ('V','Y','Q','✓','✔','晉級') else ('not_qualified' if final_advance is not None and v[final_advance] in ('未晉級','不晉級','淘汰') else None)
                si=next((i for i,h in enumerate(heads) if (h.endswith('成績') or h in ('Total','總分','總成績')) and v[i]),hmap.get('成績'))
                score=v[si] if si is not None else ''
                tm=v[hmap['時間']] if '時間' in hmap and re.fullmatch(r'\d{1,2}:\d{2}',v[hmap['時間']]) else event['time']
                final_rank=rank if (event['phase']=='決賽' or event.get('medal_event')) and event.get('ranking_scope')!='segment' and ri==overall else None
                records.append({**event,'id':key(event['id'],'individual',v[ni]),'time':tm,'time_scope':'event','names':names,'names_basis':'report','opponent':'','score':score,'note':v[hmap['備註']] if '備註' in hmap else '', 'round_rank':rank,'round_rank_text':rtext, 'rank':final_rank,'rank_source':url if final_rank else None,'advancement':advance,'result_state':'result' if score or rtext else 'pending','source':url})
    return records,recognized and not incomplete

def collect_team_outcomes(doc):
    outcomes={}
    for t in table_rows(doc,['勝隊']):
        for row in t.xpath('.//tr[td]'):
            c=cells(row);v=[clean(x) for x in c]
            sep=next((i for i,x in enumerate(v) if x=='對'),None)
            if sep is None or sep+2>=len(c):continue
            unit=lambda ix: clean(c[ix].xpath('.//text()')[0]) if c[ix].xpath('.//text()') else ''
            a,b,w=unit(sep-1),unit(sep+1),unit(sep+2)
            if a and b and w in (a,b):outcomes[v[2]]={'winner':w,'loser':b if w==a else a}
    return outcomes

def parse_football_bracket(pages,source):
    rows=[];day=None
    for page in pages:
        if not re.search(r'\d{1,2}[：:]\d{2}',page):continue
        for line in unicodedata.normalize('NFKC',page).splitlines():
            line=clean(line)
            dm=re.search(r'(\d+)\s*月\s*(\d+)\s*日',line)
            if dm:day=date_iso(dm.group(1)+'/'+dm.group(2))
            m=re.match(r'^(\d+)\s+(\d{1,2}):(\d{2})\s+(.+?)\s*:\s*(.+?)\s+(女生|男生)(.*)$',line)
            if m and day:
                no,h,mi,left,right,gender,note=m.groups()
                def slot(value):
                    value=clean(value)
                    wm=re.fullmatch(r'(\d+)\s*(勝|敗)',value)
                    if wm:return {'match':wm.group(1),'outcome':'winner' if wm.group(2)=='勝' else 'loser'}
                    return {'team':re.sub(r'^\d+\s*','',value)}
                rows.append({'match_no':no,'date':day,'time':h.zfill(2)+':'+mi,'left':slot(left),'right':slot(right),'gender':'女子組' if gender=='女生' else '男子組','note':note,'source':source})
            elif rows and re.fullmatch(r'[一二三四五六七八九十、,季殿冠亞名軍]+',line):rows[-1]['note']=line
    for row in rows:
        row['phase']=placement_stage(row['note']) or ('名次賽' if row['note'] else '')
    for final in [r for r in rows if r['phase']=='決賽']:
        for slot in (final['left'],final['right']):
            if 'match' in slot:
                for row in rows:
                    if row['gender']==final['gender'] and row['match_no']==slot['match']:row['phase']='準決賽'
    return rows

def add_football_bracket(records,entries,schedule,report_docs,bracket):
    outcomes={'男子組':{},'女子組':{}}
    for event in schedule:
        if event['sport_id']!='216' or event.get('report') not in report_docs:continue
        gender='女子組' if '女子組' in event['title'] else '男子組'
        outcomes[gender].update(collect_team_outcomes(report_docs[event['report']]))
    for match in bracket:
        gender=match['gender'];pid='21602002' if gender=='女子組' else '21601001'
        old=next((r for r in records if r['sport_id']=='216' and r.get('match_no')==match['match_no'] and gender in r['title']),None)
        if old:
            old['phase']=match['phase'];old['bracket_source']=match['source']
            if match['phase'] in ('決賽','銅牌賽'):old.update(medal_event=True,medal_source=match['source'],medal_basis='官方對戰表：'+match['note'])
            if match['phase']=='準決賽' and old['result_state']=='won':
                old['advancement']='qualified';old['advancement_basis']='依官方對戰表與已公告勝隊判定'
            continue
        def resolve(slot):
            if 'team' in slot:return slot['team']
            return outcomes[gender].get(slot['match'],{}).get(slot['outcome'])
        left,right=resolve(match['left']),resolve(match['right'])
        if CITY not in (left,right):continue
        entry=next((e for e in entries if e['pid']==pid),None)
        names=entry['names'] if entry else []
        records.append({'id':key('football-bracket',gender,match['match_no']),'sport_id':'216','sport':'五人制足球','pid':pid,'fid':None,'match_no':match['match_no'],'date':match['date'],'time':match['time'],'time_scope':'match','title':'五人制足球'+gender+'團體賽','phase':match['phase'],'medal_event':match['phase'] in ('決賽','銅牌賽'),'medal_source':match['source'],'medal_basis':'官方對戰表：'+match['note'],'names':names,'names_basis':'team_entry','opponent':right if left==CITY else left,'score':'','note':match['note'],'rank':None,'round_rank':None,'advancement':'qualified' if match['phase']=='決賽' else None,'advancement_basis':'依官方對戰表與已公告勝隊判定','result_state':'pending','source':match['source'],'links':[],'bracket_source':match['source']})
    return records

def join_events(schedule, entries, report_docs):
    records=[];unrecognized=[]
    by_pid={x['pid']:x for x in entries}
    for event in schedule:
        entry=by_pid.get(event.get('pid'))
        if entry is None:
            title=item_title(event['title'])
            matches=[e for e in entries if e['sport_id']==event['sport_id'] and item_title(e['title'])==title]
            if len(matches)==1:entry=matches[0];event['pid']=entry['pid']
        parsed=[]
        report=report_docs.get(event.get('report'))
        if report is not None:
            parsed,recognized=parse_score(report,event,event['report'])
            if entry and is_team_event(event):
                for record in parsed:
                    record['registered_names']=entry['names'];record['registration_source']=entry['source']
                    if not record['names']:
                        record['names']=entry['names'];record['names_basis']='team_entry'
            records.extend(parsed)
            if recognized:
                # Entry-page appearances can be published before a report row.
                listed={n for r in parsed for n in r['names']}
                missing=[a['name'] for a in (entry or {}).get('appearances',[]) if a['fid']==event.get('fid') and a['name'] not in listed]
                if missing and not is_team_event(event):
                    extra={**event,'id':key(event['id'],'entry-appearance',','.join(missing)),'names':list(dict.fromkeys(missing)),'names_basis':'entry_round','time_scope':'event','score':'','rank':None,'round_rank':None,'advancement':None,'result_state':'pending','note':'官方本輪名單已列出；成績報告尚未列齊。','source':entry['source']}
                    records.append(extra);parsed.append(extra)
                if parsed and entry and not is_team_event(event) and (event['phase'] in ('','預賽','獎牌賽') or event.get('direct_final')):
                    missing=[n for n in entry['names'] if not any(n in r['names'] for r in parsed)]
                    if missing:parsed[0].update(registered_names=missing,registration_source=entry['source'])
                continue
            unrecognized.append(event['report'])
        if not entry or not entry['names']:continue
        # A team day's first start is never a Kaohsiung match time.
        team=event['sport_id']=='216' or '曲棍球' in event['title']
        final=event['phase'] in ('決賽','準決賽','複賽','銅牌賽') and not event.get('direct_final')
        known=[a['name'] for a in entry['appearances'] if event.get('fid') and a['fid']==event['fid']]
        confirmed_final=event['phase']=='決賽' and bool(known) and not event.get('direct_final')
        names=list(dict.fromkeys(known)) if known else entry['names']
        names=[n for n in names if not any(n in r['names'] for r in parsed)]
        if names:records.append({**event,'id':key(event['id'],'unparsed') if parsed else event['id'],'names':names,'names_basis':'entry_round' if known else ('team_entry' if team else 'registration'), 'time':None if team else event['time'],'session_time':event['time'],'time_scope':'session' if team else 'event','opponent':'','score':'','note':'','rank':None,'round_rank':None,'advancement':'qualified' if confirmed_final else None,'result_state':'conditional' if final and not known else 'pending','source':entry['source']})
    return records,unrecognized

def merge_pdf_events(records,pdf_events):
    for event in pdf_events:
        # Sharing a time and one athlete does not make two disciplines identical.
        same=next((r for r in records if r['sport_id']==event['sport_id'] and r['date']==event['date'] and r.get('time')==event['time'] and item_title(r['title'])==item_title(event['title']) and r.get('phase','')==event.get('phase','') and norm(r.get('opponent'))==norm(event.get('opponent')) and r.get('match_no','')==event.get('match_no','') and (not r.get('venue') or not event.get('venue') or r['venue']==event['venue'])),None)
        if same:
            if same.get('names_basis')=='report':
                same['registered_names']=list(dict.fromkeys(same.get('registered_names',[])+event['names']))
                same['registration_source']=event['source']
            else:same['names']=list(dict.fromkeys(same['names']+event['names']))
        else:records.append(event)

def attach_final_results(records,finals):
    for event in records:
        if not (event.get('medal_event') or event['phase']=='決賽') or event.get('ranking_scope')=='segment':continue
        matched=[f for f in finals if f['sport_id']==event['sport_id'] and f['date']==event['date'] and item_title(f['title'])==item_title(event['title']) and set(f['names'])&set(event['names'])]
        if len(matched)==1:
            final=matched[0]
            # Individual placeholder lists may contain several different ranks.
            if not is_team_event(event) and set(event['names'])!=set(final['names']):continue
            event.update(rank=final['rank'],rank_source=final['source'],result_state='result',final_id=final['id'])
            if final.get('score') and not event.get('score'):event['score']=final['score']

def annotate_hockey_matches(records,documents):
    """A team-day award link is not evidence that every match is a final."""
    doc=next((d for d in documents if d['sport_id']=='303' and '曲棍球' in d['title']),None)
    if not doc:return
    day=None
    for page,text in enumerate(doc.get('pages',[]),1):
        for raw in text.splitlines():
            line=clean(raw);compact=re.sub(r'\s+','',line)
            dm=re.search(r'(\d+)月(\d+)日',compact)
            if dm:day=date_iso(dm.group(1)+'/'+dm.group(2))
            match=re.search(r'\b60\s+([男女]子[長短]桿)\s+(\d+)\b',line)
            phase=placement_stage(line)
            if not day or not match or phase not in ('決賽','銅牌賽'):continue
            category,no=match.groups();gender='女子組' if category.startswith('女') else '男子組';stick='短桿' if '短桿' in category else '長桿'
            for event in records:
                if event['sport_id']=='303' and event['date']==day and event.get('match_no')==no and gender in event['title'] and stick in event['title']:
                    event.update(phase=phase,medal_event=True,medal_source=doc['url']+'#page='+str(page),medal_basis='官方曲棍球對戰表列'+phase)

def load_documents(resources,fetcher,previous=None):
    result=[]
    for resource in resources:
        if resource['label']!='賽程表':continue
        page=fetcher.get(resource['url'])
        for a in page.xpath('//a[contains(@href,"Upfile/CompSche")]'):
            url=official_url(a.get('href'),resource['url'])
            if any(x['url']==url for x in result):continue
            result.append({'id':key(url),'sport_id':resource['sport_id'],'sport':resource['sport'],'title':clean(a),'url':url})
    return result

def attach_athletes(registrations,entries,records,finals,sport_map):
    athletes={}
    def add(sid,name,group='',source=''):
        aid=key(sid,name)
        if aid not in athletes:athletes[aid]={'id':aid,'name':name,'sport_id':sid,'sport':sport_map.get(sid,sid),'groups':[],'sources':[],'event_ids':[],'final_ids':[],'entry_ids':[]}
        a=athletes[aid]
        if group and group not in a['groups']:a['groups'].append(group)
        if source and source not in a['sources']:a['sources'].append(source)
        return a
    for r in registrations:add(r['sport_id'],r['name'],r['group'],r['source'])
    for e in entries:
        for n in e['names']:add(e['sport_id'],n,source=e['source'])['entry_ids'].append(e['pid'])
    for e in records:
        for n in dict.fromkeys(e['names']+e.get('registered_names',[])):add(e['sport_id'],n,source=e['source'])['event_ids'].append(e['id'])
    for f in finals:
        for n in f['names']:add(f['sport_id'],n,f['group'],f['source'])['final_ids'].append(f['id'])
    return sorted(athletes.values(),key=lambda a:(a['sport_id'],a['name']))

def validate_snapshot(data):
    required=['sports','registrations','athletes','events','finals','plans','resources','meta']
    for k in required:
        if k not in data:raise ValueError('Missing section '+k)
    if len(data['sports'])<32 or not data['registrations']:raise ValueError('Incomplete competition catalog or registrations')
    for section in ('athletes','events','finals','plans'):
        ids=[x['id'] for x in data[section]]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate IDs in '+section)
    for event in data['events']:
        if not event['names'] and event.get('participation')!='no_registration':raise ValueError('Kaohsiung event without names')
        if event.get('participation')=='no_registration' and (event['names'] or any(r['sport_id']==event['sport_id'] for r in data['registrations'])):raise ValueError('Incorrect public-only schedule classification')
        datetime.fromisoformat(event['date'])
        if event.get('time') and not re.fullmatch(r'\d{2}:\d{2}',event['time']):raise ValueError('Invalid event time')
        if event.get('rank') and not (event['phase']=='決賽' or event.get('medal_event') and event.get('medal_source')):raise ValueError('A preliminary rank was treated as a final rank')
        if event.get('rank') and event.get('ranking_scope')=='segment':raise ValueError('A segment rank was treated as the overall result')
        if event.get('advancement')=='qualified' and not (event.get('advancement_basis') or event['names_basis'] in ('entry_round','report')):raise ValueError('Unsubstantiated advancement')
    return True

def write_snapshot(data,output):
    validate_snapshot(data);output.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(data,ensure_ascii=False,separators=(',',':'))
    for filename,text in [('snapshot.json',raw),('snapshot.js','window.SPORT115_DATA = '+raw.replace('</','<\\/')+';\n')]:
        tmp=output/(filename+'.tmp');tmp.write_text(text,encoding='utf-8');tmp.replace(output/filename)

def run(args):
    fetcher=Fetcher(args.cache_dir,args.offline)
    previous_path=args.output/'snapshot.json'
    previous=json.loads(previous_path.read_text()) if previous_path.exists() else None
    now=datetime.now(timezone.utc)
    refresh_reference=args.full or not previous or not previous['meta'].get('reference_checked_at') or (now-datetime.fromisoformat(previous['meta']['reference_checked_at'])).total_seconds()>86400
    print('Reading official score and schedule pages',flush=True)
    finals_doc,final_rows=paginated(fetcher,SOURCES['finals'],['種類','單位','姓名','名次'])
    sport_map=options(finals_doc,'LID')
    if len(sport_map)!=32:raise ValueError('Unexpected official sports catalog; review before publishing')
    finals=parse_finals(final_rows,sport_map)
    award_groups=parse_award_groups(fetcher.get(SOURCES['awards']))
    if refresh_reference:
        print('Reading all Kaohsiung registration pages and all sports references',flush=True)
        roster_doc,roster_rows=paginated(fetcher,SOURCES['roster'],['姓名','職稱','組別'])
        registrations=parse_roster(roster_doc,roster_rows,sport_map)
        plans=parse_plan(fetcher.get(SOURCES['plan']),sport_map)
        resources=parse_catalog(fetcher.get(SOURCES['catalog']),sport_map)
        docs=load_documents(resources,fetcher)
        reference_checked_at=min(fetcher.observed[u] for u in (SOURCES['roster'],SOURCES['plan'],SOURCES['catalog'])) if args.offline else now.isoformat()
    else:
        registrations=previous['registrations'];plans=previous['plans'];resources=previous['resources'];docs=previous.get('documents',[]);reference_checked_at=previous['meta']['reference_checked_at']
    instant=fetcher.get(SOURCES['instant'])
    schedule_urls={}
    for a in instant.xpath('//a[contains(@href,"Instant_List.php")]'):
        url=official_url(a.get('href'),SOURCES['instant']);sid=parse_qs(urlsplit(url).query).get('LID',[None])[0]
        if sid in sport_map:schedule_urls[sid]=BASE+'/Module/Score/Instant_List.php?LID='+sid
    if not schedule_urls:raise ValueError('No live schedule categories discovered')
    schedules=fetcher.batch(schedule_urls.values());schedule=[]
    if len(schedules)!=len(schedule_urls):raise ValueError('Schedule fetch was incomplete')
    for sid,url in schedule_urls.items():schedule.extend(parse_schedule(schedules[url],sid,sport_map[sid],url))
    # Refresh nearby rounds frequently; older and distant rounds are checked daily.
    # This prevents historical reports from delaying updates as the meet grows.
    today=now.astimezone(ZoneInfo('Asia/Taipei')).date()
    near_start=(today-timedelta(days=1)).isoformat();near_end=(today+timedelta(days=1)).isoformat()
    nearby=[e for e in schedule if near_start<=e['date']<=near_end]
    active_pids={e['pid'] for e in nearby if e['pid']}
    daily_age=0 if args.full else 86400
    entry_roots={sid:BASE+'/Module/Score/Entry_list.php?LID='+sid for sid in schedule_urls}
    entry_root_docs=fetcher.batch(entry_roots.values(),{url:daily_age for url in entry_roots.values()})
    if len(entry_root_docs)!=len(entry_roots):raise ValueError('Event catalog fetch was incomplete')
    entry_specs=[];entry_ages={}
    for sid,entry_url in entry_roots.items():
        for pid,label in options(entry_root_docs[entry_url],'PID').items():
            url=entry_url+'&PID='+pid
            entry_specs.append((sid,pid,url))
            by_title=any(e['sport_id']==sid and item_title(e['title'])==item_title(sport_map[sid]+label) for e in nearby)
            entry_ages[url]=0 if pid in active_pids or by_title else daily_age
    entry_pages=fetcher.batch([url for _,_,url in entry_specs],entry_ages)
    if len(entry_pages)!=len(entry_specs):raise ValueError('Event entry list fetch was incomplete')
    entries=[parse_entry(entry_pages[url],pid,sid,sport_map[sid],url) for sid,pid,url in entry_specs]
    reconcile_entry_groups(entries,registrations)
    report_ages={e['report']:0 if near_start<=e['date']<=near_end else daily_age for e in schedule if e['report']}
    reports=fetcher.batch(report_ages,report_ages)
    if fetcher.errors:raise ValueError('A source could not be fetched; keeping the previous complete snapshot')
    supplements=json.loads((args.output/'documents.json').read_text()) if (args.output/'documents.json').exists() else {'documents':[]}
    annotate_medal_sessions(schedule,supplements.get('documents',[]),resources,award_groups,entries)
    records,unrecognized=join_events(schedule,entries,reports)
    football_doc=next((d for d in supplements['documents'] if '38-3' in d.get('title','') and d['sport_id']=='216'),None)
    if football_doc:
        bracket=parse_football_bracket(football_doc['pages'],football_doc['url'])
        # Once the bracket is available, remove generic team-day entries.
        records=[r for r in records if r['sport_id']!='216' or r['names_basis']=='report']
        records=add_football_bracket(records,entries,schedule,reports,bracket)
    from pdf_events import extract_pdf_events
    pdf_events=extract_pdf_events(supplements.get('documents',[]),registrations,plans)
    merge_pdf_events(records,pdf_events)
    # Whitespace/compatibility variants must not create a second athlete identity.
    canonical={(r['sport_id'],norm(r['name'])):r['name'] for r in registrations}
    for collection in (entries,records,finals):
        for row in collection:
            for field in ('names','registered_names'):
                if field in row:row[field]=list(dict.fromkeys(canonical.get((row['sport_id'],norm(n)),n) for n in row[field]))
    annotate_hockey_matches(records,supplements.get('documents',[]))
    attach_final_results(records,finals)
    records.sort(key=lambda r:(r['date'],r.get('time') or '99:99',r['sport_id'],r['title'],r['id']))
    athletes=attach_athletes(registrations,entries,records,finals,sport_map)
    data={'schema_version':1,'sports':[{'id':sid,'name':name} for sid,name in sport_map.items()],'registrations':registrations,'athletes':athletes,'entries':entries,'events':records,'scheduled_sessions':schedule,'finals':finals,'plans':plans,'resources':resources,'documents':docs,
          'meta':{'checked_at':max(fetcher.observed.values()) if args.offline else datetime.now(timezone.utc).isoformat(),'reference_checked_at':reference_checked_at,'timezone':'Asia/Taipei','documents_checked_at':supplements.get('checked_at'),'schedule_sport_ids':list(schedule_urls),'pdf_event_count':len(pdf_events),'official_schedule_count':len(schedule),'unrecognized_reports':unrecognized,'source_count':len(fetcher.observed),'sources':SOURCES,'source_checks':fetcher.observed,'update_interval_minutes':10,'status':'ok','snapshot_note':'資料依官方已公開名單、賽程、成績與附件整理；精確場次與種類期間分開呈現。'}}
    write_snapshot(data,args.output)
    (args.output/'sync-status.json').write_text(json.dumps({'status':'ok','attempted_at':now.isoformat(),'last_success_at':now.isoformat()},ensure_ascii=False))
    print(json.dumps({'registrations':len(registrations),'athletes':len(athletes),'events':len(records),'finals':len(finals),'documents':len(docs),'unrecognized_reports':len(unrecognized)},ensure_ascii=False),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache-dir',type=Path,default=ROOT/'.cache');p.add_argument('--output',type=Path,default=ROOT/'site/data');p.add_argument('--offline',action='store_true');p.add_argument('--full',action='store_true');args=p.parse_args()
    try:run(args)
    except Exception as exc:
        print('SYNC FAILED: '+str(exc),file=sys.stderr)
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/'sync-status.json').write_text(json.dumps({'status':'error','attempted_at':datetime.now(timezone.utc).isoformat(),'message':'本次同步失敗，顯示上次成功取得的資料。'},ensure_ascii=False))
        raise SystemExit(1)

if __name__=='__main__':main()
