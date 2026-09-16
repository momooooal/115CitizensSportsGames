"""Conservative extraction of dated, named official PDF schedule rows.

Only supported observed table layouts are converted. Other PDFs remain fully
available in the document viewer. Dates are never copied across unrelated tables.
"""
import re
from sync_data import clean,norm,key,date_iso,CITY,placement_stage

def make(doc,page,day,tm,title,names,opponent='',group='',no='',basis='pdf_roster'):
    phase=placement_stage(title)
    record={'id':key('pdf',doc['url'],page,day,tm,title,','.join(names),opponent),'sport_id':doc['sport_id'],'sport':doc['sport'],'date':day,'time':tm,'time_scope':'match','title':doc['sport']+title,'phase':phase, 'names':list(dict.fromkeys(names)),'names_basis':basis,'opponent':opponent,'score':'','score_order':'','note':'','rank':None,'round_rank':None,'advancement':None,'result_state':'pending','source':doc['url']+'#page='+str(page),'links':[],'pdf_page':page,'match_no':no,'group':group}
    if phase in ('決賽','銅牌賽'):record.update(medal_event=True,medal_source=record['source'],medal_basis='官方 PDF 標示'+phase)
    return record

def group_names(registrations,sid,gender):
    return list(dict.fromkeys(r['name'] for r in registrations if r['sport_id']==sid and (not gender or gender in r['group'])))

def read_day(raw,month):
    compact=re.sub(r'\s+','',clean(raw))
    if compact.isdigit() and 1<=int(compact)<=31:return f'2026-{month:02d}-{int(compact):02d}'
    return date_iso(compact)

def taichi_events(doc,registrations):
    slots=[];events=[]
    first=next((p for p in doc.get('tables',[]) if p['page']==1),None)
    if not first:return events
    for table in first['tables']:
        day=None;last_slots={}
        for raw in table:
            row=[clean(c) for c in raw]
            if len(row)<4:continue
            day=read_day(row[0],10) or day
            times=re.findall(r'\d{1,2}:\d{2}',row[1])
            if not day or len(times)!=2:continue
            for col in (2,3):
                label=row[col]
                match=re.match(r'(.+?)\(([男女])\)',label)
                if match:
                    slot={'date':day,'time':times[0],'end':times[1],'label':match.group(1),'gender':match.group(2),'court':'甲場地' if col==2 else '乙場地','final_time':None}
                    slots.append(slot);last_slots[col]=slot
                elif label=='決賽' and col in last_slots:last_slots[col]['final_time']=times[0]
    for page in doc.get('tables',[]):
        if page['page']<3:continue
        text=clean(doc['pages'][page['page']-1]);title_match=re.search(r'([男女])子套路-\s*(.+?)\s*縣市',text)
        if not title_match:continue
        gender,title=title_match.groups()
        def same_form(label,title):
            aliases={'五十四式劍':'54式傳統太極劍','三十二式刀':'32式太極刀'}
            return norm(label) in norm(title) or (label in aliases and norm(aliases[label]) in norm(title))
        slot=next((s for s in slots if s['gender']==gender and same_form(s['label'],title)),None)
        if not slot:continue
        names=[];orders=[]
        for table in page['tables']:
            for row in table:
                if len(row)>=3 and clean(row[0])==CITY:
                    names.append(clean(row[1]));orders.append(clean(row[1])+' 第'+clean(row[2])+'位')
        if not names:continue
        record=make(doc,page['page'],slot['date'],slot['time'],gender+'子組套路'+title,names)
        record['time_scope']='event';record['note']=slot['court']+' · 項目時段 '+slot['time']+'–'+slot['end']+' · 出場順序：'+'、'.join(orders)
        record['links']=[{'label':'項目時間表','url':doc['url']+'#page=1'}];events.append(record)
        if slot['final_time']:
            final={**record,'id':key(record['id'],'conditional-final'),'time':slot['final_time'],'phase':'決賽','medal_event':True,'medal_source':doc['url']+'#page=1','medal_basis':'官方套路時段表列決賽','result_state':'conditional','note':slot['court']+' · 決賽出場名單待公布','names_basis':'registration'};events.append(final)
    second=next((p for p in doc.get('tables',[]) if p['page']==2),None)
    if not second:return events
    push_names=list(dict.fromkeys(r['name'] for r in registrations if r['sport_id']=='134' and '推手' in r['group'] and '對練' not in r['group']))
    pairs={}
    for page in doc.get('tables',[]):
        text=clean(doc['pages'][page['page']-1])
        gender='男子' if '男子指定推手對練' in text else '女子' if '女子指定推手對練' in text else None
        if not gender:continue
        for table in page['tables']:
            for row in table:
                if len(row)>=3 and clean(row[0])==CITY:
                    pairs[gender]=([clean(n) for n in re.split(r'[/／、]',clean(row[1])) if clean(n)],clean(row[2]),page['page'])
    for table in second['tables']:
        day=None;gender=None
        for raw in table:
            row=[clean(c) for c in raw]
            if len(row)<3:continue
            day=read_day(row[0],10) or day
            times=re.findall(r'\d{1,2}:\d{2}',row[1]);label=row[2]
            if not day or len(times)!=2 or not re.search(r'賽',label) or '練習' in label:continue
            if '指定推手對練' in label:gender='男子' if '男子' in label else '女子'
            if gender and gender in pairs:
                names,order,page=pairs[gender];final=label=='決賽'
                rec=make(doc,page,day,times[0],gender+'指定推手對練'+('決賽' if final else '初賽'),names)
                rec.update(time_scope='event',note='丙場地 · 項目時段 '+times[0]+'–'+times[1]+(' · 決賽名單待公布' if final else ' · 第'+order+'組'),links=[{'label':'項目時間表','url':doc['url']+'#page=2'}])
                if final:rec.update(result_state='conditional',names_basis='registration')
                events.append(rec)
            elif push_names and '定步' in label:
                rec=make(doc,2,day,times[0],'推手｜'+label,push_names,basis='group_registration')
                rec.update(schedule_scope='session',time_scope='event',result_state='conditional' if '決賽' in label else 'entry_pending',note='丙、丁場地 · 項目時段 '+times[0]+'–'+times[1]+'；以下為推手報名名單，個人場次及實際出賽時間待公布／確認。')
                events.append(rec)
    return events

def softball_events(doc,registrations):
    gender='女子' if '女子' in doc['title'] else '男子' if '男子' in doc['title'] else ''
    if not gender:return []
    names=group_names(registrations,'211',gender);events=[]
    for p in doc.get('tables',[]):
        for table in p['tables']:
            day=None;courts={1:'A 場',3:'B 場'}
            for raw in table:
                row=[clean(c) for c in raw]
                if len(row)<5:continue
                dm=re.fullmatch(r'10/(\d{1,2})',row[0])
                if dm:
                    day=read_day(row[0],10)
                    courts={1:row[1] or 'A 場',3:row[3] or 'B 場'}
                    continue
                tm=re.match(r'^(\d{1,2}:\d{2})[~～-]',row[0])
                if not day or not tm:continue
                for start,court in courts.items():
                    left,right=row[start:start+2]
                    if CITY not in left+right:continue
                    other=right if CITY in left else left
                    city=re.search(r'(?:臺|台|新|桃|高|南|嘉|屏|苗|彰|雲|宜|花|基|金|連|澎)[^\s()]{1,3}[市縣]',other)
                    if not city:continue
                    e=make(doc,p['page'],day,tm.group(1),gender+'組團體賽（分組排名賽）',names,city.group(0),gender,basis='team_registration');e['note']=court+' · '+row[0];events.append(e)
    return events

def extract_pdf_events(documents,registrations,plans):
    events=[]
    for doc in documents:
        sid=doc['sport_id']
        if sid not in ('210','213','209','214','205','134','211') or '資格' in doc['title']:continue
        if sid=='134':events.extend(taichi_events(doc,registrations));continue
        if sid=='211':events.extend(softball_events(doc,registrations));continue
        months={int(p['start'][5:7]) for p in plans if p['sport_id']==sid}
        if len(months)!=1:continue
        month=next(iter(months));last_page_day=None
        for page_data in doc.get('tables',[]):
            pi=page_data['page'];text=clean(doc['pages'][pi-1]);prefix=text[:350]
            # A heading date can carry to the immediately following continuation
            # page only for the observed woodball booklet layout.
            page_dates=re.findall(r'10\s*月\s*\d+\s*日',text if sid=='205' else prefix)
            page_day=read_day(page_dates[0],month) if page_dates else None
            if sid=='205':
                if page_day:last_page_day=page_day
                else:page_day=last_page_day
            for table in page_data['tables']:
                current_day=page_day;heads=None;date_idx=None;time_idx=None
                if sid=='205':
                    prepared=[];previous=None
                    for raw in table:
                        values=list(raw)
                        if previous and len(values)>2 and values[0] is None and values[1] is None:
                            values[0:2]=previous[0:2]
                            for ix in range(2,len(values)):
                                if values[ix] is None and ix<len(previous) and re.fullmatch(r'.{2,3}[市縣]',clean(previous[ix])):values[ix]=previous[ix]
                        prepared.append(values);previous=values
                    table=prepared
                rows=[[clean(c) for c in row] for row in table]
                for row in rows:
                    compact=[re.sub(r'\s+','',v) for v in row]
                    if any('時間' in v for v in compact):
                        heads=compact;time_idx=next(i for i,v in enumerate(compact) if '時間' in v);date_idx=next((i for i,v in enumerate(compact) if '日期' in v),None);continue
                    # Standalone full-width date headings (e.g. korfball).
                    if row and len([v for v in row if v])==1:
                        maybe=read_day(next(v for v in row if v),month)
                        if maybe:current_day=maybe
                    if date_idx is not None and len(row)>date_idx and row[date_idx]:
                        current_day=read_day(row[date_idx],month) or current_day
                    if time_idx is None or len(row)<=time_idx:continue
                    tm=re.fullmatch(r'(\d{1,2}):(\d{2})',row[time_idx])
                    if not tm or not current_day or not any(CITY in c for c in row):continue
                    time_value=tm.group(1).zfill(2)+':'+tm.group(2)
                    if sid in ('210','213','209','214'):
                        city_cells=[(i,re.search(r'(?:臺|台|新|桃|高|南|嘉|屏|苗|彰|雲|宜|花|基|金|連|澎)[^\s]{1,3}[市縣]',v)) for i,v in enumerate(row)]
                        cities=[(i,m.group(0)) for i,m in city_cells if m]
                        if len(cities)!=2:continue
                        group_cell=next((v for v in row if re.search(r'男|女|混合',v)),None)
                        if group_cell:gender='男子' if '男' in group_cell and '女' not in group_cell else '女子' if '女' in group_cell and '男' not in group_cell else '男女混合'
                        elif sid=='209':gender='男女混合'
                        elif '男子組' in prefix and '女子組' not in prefix:gender='男子'
                        elif '女子組' in prefix and '男子組' not in prefix:gender='女子'
                        else:continue
                        names=group_names(registrations,sid,gender)
                        if not names:continue
                        opponent=next((name for _,name in cities if name!=CITY),'')
                        title=(gender+'組' if gender!='男女混合' else '男女混合組')+'團體賽'
                        if group_cell:title+=' · '+group_cell
                        no_idx=next((i for i,v in enumerate(heads or []) if '場次' in v),None)
                        no=row[no_idx] if no_idx is not None and no_idx<len(row) else ''
                        events.append(make(doc,pi,current_day,time_value,title,names,opponent,gender,no,'team_registration'))
                    elif sid=='205':
                        names=[]
                        for i,value in enumerate(row):
                            if CITY not in value:continue
                            suffix=clean(value.split(CITY,1)[1])
                            def name_key(value):return norm(re.sub(r'^[※＊*†‡\s]+','',clean(value)))
                            if suffix:names.extend([r['name'] for r in registrations if r['sport_id']==sid and norm(r['name'])==name_key(suffix)])
                            elif i+2<len(row):
                                names.extend([r['name'] for r in registrations if r['sport_id']==sid and norm(r['name']) in [name_key(n) for n in re.split(r'[\s/／、]+',row[i+2])]])
                        if not names:continue
                        before=' '.join(v for r in rows[:3] for v in r)
                        label=next((v for r in rows[:3] for v in r if re.search(r'(桿數賽|球道賽).*(男|女)',v)),None)
                        if not label:
                            m=re.search(r'((?:桿數賽|球道賽)[男女]子組\s*第[一二三四五六七八九十]輪)',text)
                            label=m.group(1) if m else '個人賽（詳見賽程）'
                        label=label.split('賽程表')[-1].strip()
                        events.append(make(doc,pi,current_day,time_value,label,names,no=row[0]))
    # Equal rows can appear in both a summary and a detailed PDF.
    unique={}
    for e in events:
        signature=(e['sport_id'],e['date'],e['time'],e['title'],e['phase'],e['opponent'],e.get('match_no',''))
        if signature in unique:
            unique[signature]['names']=list(dict.fromkeys(unique[signature]['names']+e['names']))
        else:unique[signature]=e
    return list(unique.values())
