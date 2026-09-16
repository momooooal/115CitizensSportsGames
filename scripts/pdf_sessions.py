"""Import published PDF sessions even before individual start lists exist.

Each parser follows a verified official layout. A session start is not an
individual start time, and a registration is never evidence of qualification.
"""
import re
from sync_data import clean, norm, key, date_iso, CITY, placement_stage

DISCIPLINES = {
    '120': ['格鬥柔術', '寢技', '對打', '演武'],
    '122': ['掛技擂台', '拳術', '兵器', '對練'],
    '131': ['經典健力', '裝備健力'],
    '132': ['古典形體', '健美', '形體', '比基尼'],
    '133': ['跳繩', '扯鈴', '陀螺', '踢毽'],
    '309': ['高爾夫', '爭奪'], '327': ['自由潛水', '蹼泳'],
    '328': ['單人', '混合團體'],
}


def compact(value):
    return re.sub(r'\s+', '', clean(value))


def times(value):
    pattern=r'(?<!\d)([0-2]?\d):([0-5]\d)'
    found=re.findall(pattern,clean(value)) or re.findall(pattern,compact(value))
    return [f'{int(h):02d}:{m}' for h,m in found if int(h)<24]


def day(value):
    return date_iso(compact(value))


def pages(doc):
    for i, text in enumerate(doc.get('layout_pages') or doc.get('pages', []), 1):
        yield i, '\n'.join(clean(line) for line in text.splitlines())


def tables(doc):
    for p in doc.get('tables', []):
        for table in p['tables']:
            yield p['page'], [[clean(v) for v in row] for row in table]


def names_for(registrations, sid, label):
    rows = [r for r in registrations if r['sport_id']==sid]
    label = compact(label).replace('男生', '男子').replace('女生', '女子')
    words = DISCIPLINES.get(sid, [])
    selected = next((w for w in words if w in label), None)
    if selected:
        rows = [r for r in rows if selected in r['group']]
    if re.search(r'男女混合|混合(?:組|團體)',label) and any('混合' in r['group'] for r in rows):
        rows = [r for r in rows if '混合' in r['group']]
    elif '男子' in label and '女子' not in label and any(re.search('男子|女子',r['group']) for r in rows):
        rows = [r for r in rows if '男子' in r['group']]
    elif '女子' in label and '男子' not in label and any(re.search('男子|女子',r['group']) for r in rows):
        rows = [r for r in rows if '女子' in r['group']]
    return list(dict.fromkeys(r['name'] for r in rows))


def session(doc, page, date, time, title, registrations, *, label=None, names=None,
            phase=None, conditional=False, medal=False, note='', scope='event',
            opponent='', no='', venue='', direct=False, public=False):
    from pdf_events import make
    exact = names is not None
    names = names if exact else names_for(registrations, doc['sport_id'], label or title)
    if not date or not names and not public:
        return None
    event = make(doc, page, date, time, title, names, opponent, no=no,
                 basis='pdf_roster' if exact else 'group_registration')
    event['id']=key(event['id'],no,venue)
    event.update(time_scope=scope, note=note, venue=venue)
    if not exact:
        event.update(schedule_scope='session', result_state='entry_pending')
        event['note'] += ('；' if note else '')+'名單為高雄相關組別報名選手，個別項目／級別及實際出賽時間待公布／確認。'
    if phase is not None:
        event['phase']=phase
        for field in ('medal_event','medal_source','medal_basis'):
            event.pop(field, None)
    if medal or event['phase'] in ('決賽','銅牌賽','獎牌賽'):
        event.update(medal_event=True, medal_source=event['source'], medal_basis='官方 PDF 的賽程或名次說明')
    if direct:
        event['direct_final']=True
    if conditional:
        event['result_state']='conditional'
    if public:
        event.update(participation='no_registration', result_state='official_schedule', schedule_scope='official')
        event['note']='官方已排賽程；目前公開報名名單及賽程均未列高雄隊伍。'
    return event


def tabular_sessions(doc, registrations):
    """Date columns with merged cells; only competition rows are imported."""
    out=[];sid=doc['sport_id']
    for page, rows in tables(doc):
        current=None;start=None
        for r in rows:
            if sid=='131' and len(r)==7:
                current=day(r[0]) or current
                for title_col,time_col,court in [(1,3,'A 比賽台'),(4,6,'B 比賽台')]:
                    if '健力' in r[title_col] and times(r[time_col]):
                        out.append(session(doc,page,current,times(r[time_col])[0],r[title_col],registrations,venue=court,note='比賽時間（非過磅時間）'))
            elif sid=='133' and len(r)>=6:
                current=day(r[0]) or current
                if r[3] not in ('預賽','決賽') or not times(r[1]):continue
                has_heat=any(len(other)>=5 and other[2]==r[2] and other[4]==r[4] and other[3]=='預賽' for _,table in tables(doc) for other in table)
                out.append(session(doc,page,current,times(r[1])[0],r[2]+r[4]+r[3],registrations,note='項目時段 '+r[1],conditional=r[3]=='決賽' and has_heat,direct=r[3]=='決賽' and not has_heat))
            elif sid=='327' and len(r)==5:
                current=day(r[0]) or current
                if times(r[1]):start=times(r[1])[0]
                if not r[2].isdigit():continue
                title=('自由潛水' if '自由潛水' in doc['pages'][page-1] else '蹼泳')+'｜'+r[3]
                out.append(session(doc,page,current,start,title,registrations,scope='session',no=r[2],conditional='決賽' in r[3],note='本時段依項次順序進行；未公布每位選手的個別開始時間。'))
            elif sid=='121' and len(r)>=6:
                current=day(r[2]) or current
                if not times(r[3]):continue
                for col in (4,5):
                    if not re.search('預賽|淘汰賽|決賽',r[col]):continue
                    title=r[col]
                    phase='預賽／淘汰賽／決賽' if '預賽' in title and '決賽' in title else '淘汰賽／決賽' if '決賽' in title else '預賽'
                    out.append(session(doc,page,current,times(r[3])[0],title,registrations,phase=phase,medal='決賽' in title,conditional='決賽' in title and '預賽' not in title,scope='session',note='時段 '+r[3],venue='甲場地' if col==4 else '乙場地'))
            elif sid=='122' and len(r)>=5:
                current=day(r[0]) or current
                if not times(r[1]):continue
                title=r[2] or (r[3] if page==1 else '')
                if page==1 and title in ('內家拳','北拳','南拳','奇兵','長兵','短兵','對練'):
                    category='拳術' if '拳' in title else '對練' if title=='對練' else '兵器'
                    out.append(session(doc,page,current,times(r[1])[0],title+'（男、女子組）',registrations,label=category,scope='session',medal=True,note='比賽時段 '+r[1]+'；同日該項比賽後頒獎。'))
                elif page==2 and re.search('初賽|複賽|準決賽|決賽',title):
                    phase=title.replace('/','／')
                    medal='決賽' in title.replace('準決賽','')
                    out.append(session(doc,page,current,times(r[1])[0],'掛技擂台｜'+title,registrations,phase=phase,medal=medal,conditional='初賽' not in title,scope='session',note='比賽時段 '+r[1]))
            elif sid=='132' and len(r)==4:
                current=day(r[0]) or current
                if times(r[1]):start=times(r[1])[0]
                if r[3] not in ('預賽','決賽'):continue
                out.append(session(doc,page,current,start,r[2]+r[3],registrations,conditional=r[3]=='決賽',scope='session',note='此組 '+str(start)+' 開始，依序進行預賽、決賽；決賽未另訂開始時間。'))
    return [e for e in out if e]


def combat_sessions(doc, registrations):
    out=[]
    if doc['sport_id']=='120':
        for page,rows in tables(doc):
            if page==1:continue
            text=clean(doc['pages'][page-1]);current=day(text)
            category='格鬥柔術' if '格鬥柔術' in text else '寢技' if '寢技' in text else '對打'
            # Keep each published time block, with all weight classes in it.
            # These are expressly pre-draw estimates, not individual starts.
            for r in rows:
                if len(r)!=4 or not times(r[0]):continue
                for gender,token in [('男子','男'),('女子','女'),('混合','混')]:
                    cells=' '.join(r[1:])
                    labels=re.findall(token+r'([+-]\d+kg)\s+(R[12]|SF|BR|F)\b',cells)
                    for phase,codes in [('預賽',('R1','R2')),('準決賽',('SF',)),('銅牌賽',('BR',)),('決賽',('F',))]:
                        weights=list(dict.fromkeys(w for w,c in labels if c in codes))
                        if weights:out.append(session(doc,page,current,times(r[0])[0],gender+category+'｜'+'、'.join(weights)+' '+phase,registrations,conditional=phase!='預賽',scope='session',note='官方抽籤前預估時段 '+r[0]+'；10/14 抽籤後依正式對戰表更新。'))
                    if re.search(token+r'(?:創意|傳統)\s*演',cells):
                        title=gender+('創意演武' if '創意' in text else '傳統演武')
                        out.append(session(doc,page,current,times(r[0])[0],title,registrations,label='演武',scope='session',note='官方抽籤前預估時段 '+r[0]+'；場內依序進行。'))
    else:
        for page,raw in enumerate(doc['pages'],1):
            text='\n'.join(clean(line) for line in raw.splitlines())
            current=None;start=None;phase=None
            for line in text.splitlines():
                if day(line):current=day(line);phase=None
                m=re.search(r'(預賽、複賽|準決賽、決賽)[:：](\d{1,2}:\d{2})',line)
                if m:phase=m[1];start=times(m[2])[0]
                if phase and re.search(r'自由式[男女]生組',line):
                    title=re.search(r'自由式[男女]生組.+',line).group(0).replace('男生','男子').replace('女生','女子')+' '+phase
                    out.append(session(doc,page,current,start,title,registrations,phase=phase,medal='決賽' in phase,conditional='準決賽' in phase,scope='session'))
    return [e for e in out if e]


def sequential_sessions(doc, registrations):
    out=[];sid=doc['sport_id']
    if sid=='314':
        for page,rows in tables(doc):
            current=None;start=None;labels=[]
            def flush(phase=''):
                if not labels:return
                title='、'.join(labels)+(('｜'+phase) if phase else '')
                out.append(session(doc,page,current,start,title,registrations,phase=phase,medal='決賽' in phase,conditional=phase=='決賽',scope='session',note='同時段依序進行；個別出場順序待公布。'))
                labels.clear()
            for r in rows:
                if day(r[0]):flush();current=day(r[0]);continue
                if len(r)!=2:continue
                if times(r[0]):flush();start=times(r[0])[0]
                if re.search('彩排|練習|抽選|午休|頒獎',r[1]):continue
                if re.search('初複|決賽',r[1]) and r[1].startswith('('):flush(r[1].strip('()'));continue
                if '14歲' in compact(r[1]):labels.append(r[1])
            flush()
    elif sid=='325':
        for page,text in pages(doc):
            current=None
            for line in text.splitlines():
                if day(line):current=day(line)
                m=re.match(r'^(\d+)\s+(\d{2}:\d{2})\s+(.+?)\s+(直接準決賽|直接決賽|準決賽|初賽|決賽|排序賽)\b',line)
                if not m:continue
                no,start,title,phase=m.groups()
                out.append(session(doc,page,current,start,title+' '+phase,registrations,no=no,direct=phase=='直接決賽',conditional=phase in ('準決賽','決賽'),phase=phase.replace('直接','')))
    elif sid=='329':
        for page,text in pages(doc):
            current=None
            for line in text.splitlines():
                if day(line):current=day(line)
                m=re.match(r'^(\d{2}:\d{2})[–－-](\d{2}:\d{2})\s+(\S+)\s+獨輪車(.+?)\s+((?:男子組|女子組|混合組)[、女子組]*)\s+(.*)',line)
                if not m:continue
                start,end,venue,title,group,note=m.groups()
                conditional='決賽' in title and any(w in title for w in ('100','50','400'))
                out.append(session(doc,page,current,start,group+title,registrations,conditional=conditional,direct=not conditional,scope='session',venue=venue,note='時段 '+start+'–'+end+'；'+note))
    return [e for e in out if e]


def rescue_sessions(doc, registrations):
    out=[]
    for page,text in pages(doc):
        current=day(text)
        # Both columns share a block start; the numbered items then run in order.
        starts=re.findall(r'(上午|下午).*?檢錄[,，](\d{1,2}:\d{2})\s*比賽',text)
        clock={period:f'{int(t.split(":")[0])+(12 if period=="下午" else 0):02d}:{t.split(":")[1]}' for period,t in starts}
        for no,title in re.findall(r'(\d+)\.\s*((?:女子|男子|男女混合)組.*?(?:預賽|決賽))',text):
            final=title.endswith('決賽');start=clock.get('下午' if final else '上午')
            if start:out.append(session(doc,page,current,start,title,registrations,conditional=final,scope='session',no=no,note='上午／下午時段依項次順序比賽；未另訂每項開始時間。'))
    return [e for e in out if e]


def simple_sessions(doc, registrations):
    out=[];sid=doc['sport_id']
    if sid=='125':
        for page,rows in tables(doc):
            current=None
            for r in rows:
                if len(r)<3:continue
                current=day(r[0]) or current
                m=re.search(r'(\d{2})(\d{2})-(比賽開始|各組個人|團體|混雙|個人)',compact(r[1]))
                if not m:continue
                start=m[1]+':'+m[2];title=r[2] if m[3]=='比賽開始' else re.sub(r'^.*?\d{4}-','',compact(r[1]))+'｜'+r[2]
                phase='資格賽' if '資格賽' in title else '淘汰賽' if '個人挑戰' in title else '淘汰賽／獎牌賽'
                out.append(session(doc,page,current,start,title,registrations,phase=phase,medal='獎牌賽' in title,conditional=phase!='資格賽',scope='session'))
    elif sid=='310':
        for page,text in pages(doc):
            current=None
            for line in text.splitlines():
                if day(line):current=day(line)
                m=re.match(r'^(\d{2}:\d{2})\s+(\S+賽)\s+(.+)',line)
                if m and '模擬' not in m[2]:out.append(session(doc,page,current,m[1],m[2],registrations,venue=m[3]))
    elif sid=='328':
        # The start-order tables identify exact athletes and absent Kaohsiung items.
        rosters={};title=None
        for page,text in pages(doc):
            if page==1:continue
            for line in text.splitlines():
                if re.fullmatch(r'(?:女子單人組|男子單人組|混合團體組\s*(?:混雙組|三人組|五人組|有氧舞蹈組))',line):title=compact(line);rosters[title]=[]
                if CITY in line and title:
                    rosters[title]=[n for n in re.split(r'[、\s]+',re.sub(r'\s+\d+$','',line.split(CITY,1)[1]).strip()) if n]
        for page,rows in tables(doc):
            if page!=1:continue
            current=None
            for r in rows:
                if len(r)!=3:continue
                current=day(r[0]) or current;title=compact(r[2])
                if title in rosters and rosters[title] and times(r[1]):out.append(session(doc,page,current,times(r[1])[0],r[2],registrations,names=rosters[title],note='項目時段 '+r[1]+'；依官方出場順序進行。',medal=True))
    return [e for e in out if e]


def dragon_sessions(doc, registrations):
    out=[]
    for page,text in pages(doc):
        current=day(text)
        if not current:continue
        for line in text.splitlines():
            m=re.match(r'^(\d+)\s+(\d{2}:\d{2})\s+(公開組|混合組)\s+(\d+M)\s+(預賽\d+|準決賽\d+|決賽[AB]|計時決賽)',line)
            if not m:continue
            no,start,group,distance,stage=m.groups()
            # 公開混合組 is the registration category, not a choice of just one race group.
            phase='名次賽' if stage=='決賽B' else '決賽' if stage in ('決賽A','計時決賽') else placement_stage(stage)
            out.append(session(doc,page,current,start,group+distance+' '+stage,registrations,no=no,phase=phase,conditional=not stage.startswith('預賽') and stage!='計時決賽',direct=stage=='計時決賽',note='組別／航道名單待公布，尚未確認高雄編在哪一場。'))
    return [e for e in out if e]


def gateball_sessions(doc, registrations):
    out=[];page_table={}
    for page,rows in tables(doc):
        if page>2:continue
        labels=re.findall(r'比賽項目[:：](.*?)地點',clean(doc['pages'][page-1]))
        index=page_table.get(page,0);page_table[page]=index+1
        if index>=len(labels):continue
        items=labels[index].strip().split('、');current=None
        for r in rows:
            if len(r)!=5:continue
            current=day(r[0]) or current
            if not times(r[1]) or not r[2].isdigit():continue
            # The PDF calls the entire knockout bracket 決賽. Only the last
            # round contains the championship / bronze / placement matches.
            final=r[3]=='決賽';medal=final and r[2]=='10'
            phase='名次／獎牌賽' if medal else '淘汰賽' if final else '預賽'
            for title in items:
                out.append(session(doc,page,current,times(r[1])[0],title+'｜'+phase,registrations,no=r[2],phase=phase,medal=medal,conditional=final,note='第 '+r[2]+' 輪，時段 '+compact(r[1])+'；個別場地及出場名單依對戰表。'))
    return [e for e in out if e]


def tug_sessions(doc, registrations):
    if '場次' not in doc['title']:return []
    out=[];eligible=set()
    def category(page,r):
        match=re.search(r'[男女混]\d+',compact(r[2]))
        return ('室內' if '室內' in doc['pages'][page-1] else '室外')+(match[0] if match else '')
    for page,rows in tables(doc):
        for r in rows:
            if len(r)==10 and r[0].isdigit() and CITY in r[4]:eligible.add(category(page,r))
    for page,rows in tables(doc):
        current=day(doc['pages'][page-1]);start=None
        court=next((compact(r[0]) for r in rows if '河' in r[0]),'')
        for r in rows:
            if len(r)!=10 or not r[0].isdigit():continue
            if times(r[1]):start=times(r[1])[0]
            cat=category(page,r)
            if cat not in eligible:continue
            named=CITY in r[4]
            if not named and re.search(r'[市縣]',r[4]):continue
            title=cat.replace('男','男子組').replace('女','女子組')+'公斤級'
            phase='預賽' if named else placement_stage(r[4]) or '複賽'
            opponent=next((v for v in re.split('[—–－-]',r[4]) if v and v!=CITY),'') if named else ''
            out.append(session(doc,page,current,start,title+' '+phase,registrations,phase=phase,conditional=not named,scope='session',opponent=opponent,no=r[0],venue=court,note=('時段 '+start+' 起依場次順序比賽；' if start else '本場未另列開始時間，依場次順序進行；')+r[4]))
    return [e for e in out if e]


def disc_sessions(doc, registrations):
    out=[];golf='高爾夫' in doc['title']
    for page,rows in tables(doc):
        current=None
        for r in rows:
            current=day(r[0]) or current
            if golf and len(r)==3 and times(r[0]):
                title='高爾夫｜'+r[1]+' '+r[2]
                # Use this row's stage, not an earlier-round reference in its opponents.
                stage=r[2]
                phase='銅牌賽' if '三、四' in stage else '決賽' if '一、二' in stage else '名次賽' if re.search('五、六|七、八',stage) else placement_stage(stage)
                out.append(session(doc,page,current,times(r[0])[0],title,registrations,phase=phase,conditional='預賽' not in stage,note='本場高雄參賽組別及名單依官方分組／晉級公告。'))
            elif not golf and len(r)==9 and times(r[2].replace('l','1')):
                start=times(r[2].replace('l','1'))[0];pair=r[4:6];named=any(CITY in v for v in pair)
                if not named and any(re.search('[縣市]',v) for v in pair):continue
                phase='銅牌賽' if '3.4' in r[8] else '決賽' if '1.2' in r[8] else '名次賽' if re.search('[57]\\.[68]',r[8]) else '預賽' if named else '複賽'
                other=next((re.search(r'[^\s\dA-D]+[市縣]',v).group(0) for v in pair if CITY not in v and re.search(r'[^\s\dA-D]+[市縣]',v)),'') if named else ''
                out.append(session(doc,page,current,start,'爭奪賽｜'+phase,registrations,phase=phase,conditional=not named,opponent=other,no=r[1],venue=r[3].replace('l','1'),note='對戰表：'+' — '.join(pair)))
    return [e for e in out if e]


def petanque_sessions(doc, registrations):
    out=[]
    if '輪序表' in doc['title']:
        prepared=[];discipline='';groups=set()
        for page,rows in tables(doc):
            text=clean(doc['pages'][page-1])
            if '雙人賽輪序表' in compact(text):discipline='雙人賽'
            if '三人賽輪序表' in compact(text):discipline='三人賽'
            current=day(text);start=None;gender='';stage='';time_idx=None
            for r in rows:
                if not r[0].isdigit():continue
                ti=next((i for i,v in enumerate(r) if times(v)),None)
                if ti is not None:time_idx=ti;start=times(r[ti])[0]
                g=next((v for v in r if re.search('[男女]子組',v)),None)
                if g:
                    gender='男子組' if '男子' in g else '女子組'
                    if '預賽' in g:stage='預賽'
                    if '八強' in g:stage='八強'
                new_stage=next((v for v in r if re.fullmatch('五到八|四強|八強|季軍戰|冠軍戰|爭第[五七]名',v)),None)
                if new_stage:stage=new_stage
                code=next((v for v in r if re.match('[A-D]【',v)),'')
                named=any(CITY in v for v in r)
                if named and code:groups.add((discipline,gender,code[0]))
                prepared.append((page,current,start,discipline,gender,stage,code,r,named))
        for page,current,start,discipline,gender,stage,code,r,named in prepared:
            if not start or not gender:continue
            if code and (discipline,gender,code[0]) not in groups:continue
            if not named and any(re.search('[市縣]',v) for v in r) and not code:continue
            # Known other teams' initial games do not involve Kaohsiung.
            if not named and sum(bool(re.search('[市縣]',v)) for v in r)>=2:continue
            phase={'冠軍戰':'決賽','季軍戰':'銅牌賽','四強':'準決賽','五到八':'名次賽','爭第五名':'名次賽','爭第七名':'名次賽','八強':'複賽'}.get(stage,stage)
            cities=[re.search(r'([^\s\d]+[市縣])',v).group(1) for v in r if re.search(r'([^\s\d]+[市縣])',v)]
            other=next((v for v in cities if v!=CITY),'') if named else ''
            out.append(session(doc,page,current,start,gender+discipline+' '+stage,registrations,no=r[0],opponent=other,phase=phase,conditional=not named,note='依官方輪序表出場。'+('後續出場取決於前輪結果。' if not named else '')))
    elif '射擊賽' in doc['title']:
        text=doc['pages'][0];current=day(text)
        shooters={}
        # Named first-round shooting entries; later placeholders are not names.
        for line in text.splitlines():
            if not times(line):continue
            for r in registrations:
                if r['sport_id']=='208' and r['name'] in compact(line):
                    shooters.setdefault(r['group'],[]).append(r['name'])
                    out.append(session(doc,1,current,times(line)[0],r['group']+'射擊賽第一輪',registrations,names=[r['name']],phase='預賽',note='官方預計出場時間。'))
        sections=re.split(r'第二輪\s*\([^)]*場地\)',text,maxsplit=1)
        second=sections[1] if len(sections)==2 else ''
        for line in second.splitlines():
            m=re.match(r'^\s*(\d{2}:\d{2})\s+\d+\s+([男女])\d+',line)
            if m:
                gender=m[2]+'子組'
                e=session(doc,1,current,m[1],gender+'射擊賽第二輪',registrations,names=shooters.get(gender,[]),phase='第二輪',conditional=True,note='第一輪第 5–12 名依名次編組，實際是否出場及所在組別待成績確認。')
                if e:e['names_basis']='registration'
                out.append(e)
        # Read the bracket's aligned time row from the layout text.
        for page,text in pages(doc):
            if page!=2:continue
            gender=None
            for line in text.splitlines():
                if '男子組' in line:gender='男子組'
                if '女子組' in line:gender='女子組'
                if gender and '預計時間' in line:
                    clock=times(line)
                    if len(clock)>=14:
                        for label,index in [('複賽',6),('準決賽',8),('銅牌賽',10),('決賽',12)]:
                            e=session(doc,page,current,clock[index],gender+'射擊賽'+label,registrations,names=shooters.get(gender,[]),phase=label,conditional=True,note='官方預計時間；依前輪成績決定出場名單。')
                            if e:e['names_basis']='registration'
                            out.append(e)
    return [e for e in out if e]


def canoe_sessions(doc, registrations):
    out=[];public=not any(r['sport_id']=='126' for r in registrations)
    for page,rows in tables(doc):
        if page not in (2,3):continue
        current=None
        # Each table is headed by its own day; unlike the document-wide range.
        headings=re.findall(r'10\s*月\s*(\d+)\s*日\s*\(星期',clean(doc['pages'][page-1]))
        page_tables=[t for p,t in tables(doc) if p==page and any(any('場次' in c for c in r) for r in t)]
        try:current=f'2026-10-{int(headings[page_tables.index(rows)]):02d}'
        except (ValueError,IndexError):continue
        for r in rows:
            if len(r)<6 or not r[0].isdigit() or not times(r[1]):continue
            title=' '.join(r[2:]);phase=placement_stage(title)
            if re.search('[57]-[678]',title):phase='名次賽'
            if not public and CITY not in title and re.search('[市縣]',title):continue
            out.append(session(doc,page,current,times(r[1])[0],title,registrations,no=r[0],phase=phase,public=public))
    return [e for e in out if e]


def kendo_sessions(doc, registrations):
    # This official PDF consists solely of scanned images. These reviewed rows
    # are valid only for these exact bytes; a replacement scan must be reviewed.
    if doc.get('sha256')!='4e28de77a11145a9dcfe0daa88fd64a15e77ad855b44410a9ee641d789b4e52c':return []
    out=[]
    male_refs={11:[3,4],12:[9,5],13:[6,10],14:[7,8],15:[1,5],16:[2,6],17:[3,4],18:[7,8],19:[9,15],20:[10,16],21:[13,17],22:[12,18],23:[14,19],24:[11,20],25:[11,12],26:[13,14],27:[21,23],28:[22,24],29:[25,27],30:[26,28],31:[25,26],32:[27,28],33:[29,30],34:[29,30],35:[31,34],36:[31,35]}
    female_refs={5:[1],6:[2],7:[3],8:[4],9:[1,8],10:[2,7],11:[3,6],12:[4,5],13:[5,6],14:[7,8],15:[9,10],16:[11,12],17:[13,15],18:[16,14],19:[13,14],20:[15,16],21:[17,18],22:[17,18],23:[19,22],24:[19,23]}
    grids=[
        (1,'男子組團體得分賽',7,'彰化縣',male_refs,18,[(7,'10:00'),(14,'11:30'),(18,'13:30'),(22,'16:30'),(23,'17:00'),(26,'17:30')],19,[(27,'08:30'),(28,'08:30'),(29,'09:30'),(30,'09:30'),(31,'10:30'),(32,'11:00'),(33,'11:30'),(34,'12:00'),(35,'12:30'),(36,'13:00')]),
        (2,'女子組團體得分賽',3,'嘉義縣',female_refs,18,[(3,'12:30'),(7,'14:30'),(10,'15:30'),(11,'16:00'),(14,'18:00')],19,[(15,'09:00'),(16,'09:00'),(17,'10:00'),(18,'10:00'),(19,'10:30'),(20,'11:00'),(21,'11:30'),(22,'12:00'),(23,'12:30'),(24,'13:00')]),
        (3,'男子組團體過關賽',7,'臺北市',male_refs,19,[(7,'15:00'),(14,'16:30')],20,[(18,'09:30'),(22,'11:30'),(23,'12:00'),(26,'12:30'),(27,'13:30'),(28,'13:30'),(29,'14:30'),(30,'14:30'),(31,'15:30'),(32,'16:00'),(33,'16:30'),(34,'17:00'),(35,'17:30'),(36,'18:00')]),
        (4,'女子組團體過關賽',7,'',female_refs,20,[(7,'08:30'),(10,'10:00'),(14,'13:00')],20,[(15,'14:00'),(17,'15:00'),(18,'15:00'),(19,'15:30'),(20,'16:00'),(21,'16:30'),(22,'17:00'),(23,'17:30'),(24,'18:00')]),
    ]
    for page,title,seed,opponent,refs,d1,rows1,d2,rows2 in grids:
        reachable={seed}
        for no,deps in refs.items():
            if no>seed and any(n in reachable for n in deps):reachable.add(no)
        for d,rows in [(d1,rows1),(d2,rows2)]:
            for no,start in rows:
                if no not in reachable:continue
                male='男子' in title
                phase='決賽' if no==(36 if male else 24) else '銅牌順位賽' if no==(35 if male else 23) else '名次賽' if no in ([32,33,34] if male else [20,21,22]) else '預賽' if no==seed else '後續輪次'
                note='官方掃描賽程所列高雄場次。' if no==seed else '須依前輪勝敗決定是否出場；敗部加賽未另公布時間。'
                if page==4 and no==7:note+='對手為第 03 場勝隊。'
                out.append(session(doc,page,f'2026-10-{d}',start,title+' '+phase,registrations,phase=phase,medal=phase=='銅牌順位賽',conditional=no!=seed,no=str(no),opponent=opponent if no==seed else '',note=note))
    for gender in ('男子','女子'):
        out.append(session(doc,9,'2026-10-21','08:30',gender+'組個人賽',registrations,scope='session',note='10/20 抽籤，10/21 08:30 起依序比賽；個別選手出場時間待公布。'))
    return [e for e in out if e]


def extract_sessions(documents, registrations):
    out=[]
    for doc in documents:
        if re.search('資格賽|練習時間',doc['title']):continue
        sid=doc['sport_id']
        if sid in ('131','133','327','121','122','132'):out.extend(tabular_sessions(doc,registrations))
        elif sid in ('120','124'):out.extend(combat_sessions(doc,registrations))
        elif sid in ('314','325','329'):out.extend(sequential_sessions(doc,registrations))
        elif sid=='307':out.extend(rescue_sessions(doc,registrations))
        elif sid in ('125','310','328'):out.extend(simple_sessions(doc,registrations))
        elif sid=='326':out.extend(dragon_sessions(doc,registrations))
        elif sid=='212':out.extend(gateball_sessions(doc,registrations))
        elif sid=='306':out.extend(tug_sessions(doc,registrations))
        elif sid=='309':out.extend(disc_sessions(doc,registrations))
        elif sid=='208':out.extend(petanque_sessions(doc,registrations))
        elif sid=='126':out.extend(canoe_sessions(doc,registrations))
        elif sid=='123':out.extend(kendo_sessions(doc,registrations))
    return out
