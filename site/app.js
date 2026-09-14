/* Static GitHub Pages app. Public JSON is refreshed without a third-party proxy. */
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalize = value => String(value ?? '').normalize('NFKC').toLocaleLowerCase().replace(/臺/g, '台').replace(/\s+/g, '');
  const matches = (value, query) => query.trim().split(/\s+/).filter(Boolean).every(term => normalize(value).includes(normalize(term)));
  const taipeiDay = (date = new Date()) => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
  const shortDate = day => day ? `${Number(day.slice(5,7))}/${Number(day.slice(8,10))}` : '日期待確認';
  const weekday = day => day ? new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',weekday:'short'}).format(new Date(`${day}T12:00:00+08:00`)) : '';
  const prettyStamp = value => value ? new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)) : '未取得';
  const safeUrl = value => { try {const u=new URL(value); return u.protocol==='https:' && u.hostname==='sport115.tycg.gov.tw' ? u.href : null;} catch {return null;} };
  const sourceLink = (url,label) => safeUrl(url) ? `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : '';
  const scoreLabel = event => {
    if (event.opponent && event.score_order === '高雄在後' && /^\d+[:：]\d+$/.test(event.score || '')) return event.score.split(/[:：]/).reverse().join(' : ');
    return String(event.score || '').replace(/^([0-9]+)[:：]([0-9]+)$/, '$1 : $2');
  };
  const statusInfo = (event, now=new Date()) => {
    if (event.rank) return {text:`決賽第 ${event.rank} 名`,tone:event.rank===1?'gold':event.rank===2?'silver':event.rank===3?'bronze':'confirmed'};
    if (event.advancement==='qualified') return {text:'已確認晉級決賽',tone:'confirmed'};
    if (event.advancement==='not_qualified') return {text:'官方註記未晉級',tone:''};
    if (event.result_state==='won') return {text:'高雄獲勝',tone:'confirmed'};
    if (event.result_state==='lost') return {text:'本場落敗',tone:''};
    if (event.result_state==='draw') return {text:'本場平手',tone:''};
    if (event.result_state==='result') return {text:'已有成績',tone:'confirmed'};
    if (event.result_state==='conditional') return {text:'晉級待確認',tone:'pending'};
    if (event.date < taipeiDay(now) || (event.time && new Date(`${event.date}T${event.time}:00+08:00`) < now)) return {text:'待官方更新',tone:'pending'};
    return {text:'賽程已排',tone:''};
  };
  const csvCell = value => '"' + String(value ?? '').replace(/^[=+@-]/, c=>"'"+c).replace(/"/g,'""') + '"';
  if (typeof module !== 'undefined' && module.exports) {module.exports={matches,taipeiDay,statusInfo,scoreLabel,csvCell,safeUrl};return;}
  const $ = id => document.getElementById(id);
  const downloadMode=location.protocol==='file:' || document.documentElement.dataset.preview==='true';
  const nameBasisLabel={team_entry:'隊伍報名名單',team_registration:'隊伍報名名單',registration:'項目報名選手',report:'成績報告所列選手',entry_round:'本輪名單',pdf_roster:'官方賽程所列選手'};
  let data=window.SPORT115_DATA;
  let docs=window.SPORT115_DOCUMENTS || {documents:[]};
  let state={view:'schedule',query:'',sport:'',status:'',day:taipeiDay(),page:1};
  let currentItems=[];
  let refreshBusy=false;
  let lastFocus=null;
  const pageSize=48;
  let athleteMap=new Map();
  let eventMap=new Map();
  let finalMap=new Map();
  function indexData(){
    athleteMap=new Map(data.athletes.map(a=>[`${a.sport_id}|${a.name}`,a]));
    eventMap=new Map(data.events.map(e=>[e.id,e]));finalMap=new Map(data.finals.map(f=>[f.id,f]));
  }
  function namesMarkup(names,sportId,basis='') {
    const buttons=names.map(name=>{const athlete=athleteMap.get(`${sportId}|${name}`);return athlete?`<button type="button" class="name-button" data-athlete="${esc(athlete.id)}">${esc(name)}</button>`:`<span>${esc(name)}</span>`;});
    const note=basis==='team_entry'||basis==='team_registration'?'隊伍報名名單；實際出賽以大會紀錄為準':basis==='registration'?'項目報名選手':basis==='report'?'成績報告所列選手':basis==='entry_round'?'本輪名單':basis==='pdf_roster'?'官方賽程所列選手':'';
    if(names.length<=4) return `<div class="names">${buttons.join('')}</div>${note?`<p class="small" style="margin-top:7px">${esc(note)}</p>`:''}`;
    const queryMatches=state.query && names.some(n=>matches(n,state.query));
    return `<div class="names">${buttons.slice(0,3).join('')}</div><details class="roster-details" ${queryMatches?'open':''}><summary>完整名單 · ${names.length} 位選手</summary><div class="names">${buttons.join('')}</div><p>${esc(note)}</p></details>`;
  }
  function venueFor(event){
    const candidates=data.plans.filter(p=>p.sport_id===event.sport_id && p.start<=event.date && p.end>=event.date);
    if(candidates.length<=1)return candidates[0]?.venue || '';
    return candidates.find(p=>p.discipline.split('-')[1] && event.title.includes(p.discipline.split('-')[1]))?.venue || '';
  }
  function eventCard(event, compact=false) {
    const info=statusInfo(event);
    const title=event.title.startsWith(event.sport)?event.title.slice(event.sport.length):event.title;
    const timeScope=event.time_scope==='event'?'項目開始':event.time_scope==='match'?'表定時間':'個別時間待確認';
    const venue=event.venue || venueFor(event);
    const detail=event.result_state==='conditional'?'以下為此項目報名名單，尚未確認誰進入本輪。':event.advancement_basis || '';
    const result=scoreLabel(event);
    return `<article class="event-card"><div class="event-time"><strong>${esc(event.time || '待定')}</strong><span>${esc(timeScope)}</span>${compact?`<span>${shortDate(event.date)} ${weekday(event.date)}</span>`:''}</div><div class="event-main"><div class="event-meta"><span class="sport-tag">${esc(event.sport)}</span>${event.phase?`<span>／ ${esc(event.phase)}</span>`:''}${event.match_no?`<span>第 ${esc(event.match_no)} 場</span>`:''}</div><h3>${esc(title)}</h3>${event.opponent?`<p style="margin-top:5px"><strong>高雄市</strong> <span class="small">vs</span> ${esc(event.opponent)}</p>`:''}${detail?`<p class="small" style="margin-top:7px">${esc(detail)}</p>`:''}${namesMarkup(event.names,event.sport_id,event.names_basis)}<div class="event-bottom">${venue?`<span>場地：${esc(venue)}</span>`:''}${event.note?`<span>${esc(event.note)}</span>`:''}</div></div><div class="event-state"><span class="pill ${info.tone}">${esc(info.text)}</span>${result?`<span class="score">${esc(result)}</span>`:''}${event.opponent&&result?'<span class="small">比分：高雄在前</span>':''}${event.round_rank&&!event.rank?`<span class="small">本輪第 ${event.round_rank} 名</span>`:''}${event.phase==='決賽' && !event.rank?'<span class="small">決賽名次尚待公告</span>':''}${sourceLink(event.report || event.source, event.pdf_page?'官方賽程 PDF':'查看官方依據')}${event.bracket_source && event.bracket_source!==event.source?sourceLink(event.bracket_source,'對戰表'):''}</div></article>`;
  }
  function finalCard(final){
    const tone=final.rank===1?'gold':final.rank===2?'silver':final.rank===3?'bronze':'';
    const badge=final.rank===1?'金牌':final.rank===2?'銀牌':final.rank===3?'銅牌':'最終名次';
    return `<article class="event-card"><div class="event-time"><strong>${shortDate(final.date)}</strong><span>${weekday(final.date)}</span></div><div class="event-main"><div class="event-meta"><span class="sport-tag">${esc(final.sport)}</span><span>官方決賽成績表</span></div><h3>${esc(final.title.replace(final.sport,''))}</h3>${namesMarkup(final.names,final.sport_id,'report')}${final.note?`<p class="small">${esc(final.note)}</p>`:''}</div><div class="event-state"><span class="pill ${tone}">${badge}</span><strong class="score">${final.rank?`第 ${final.rank} 名`:esc(final.rank_text||'名次待確認')}</strong>${final.score?`<span>${esc(final.score)}</span>`:''}${sourceLink(final.source,'官方最終成績')}</div></article>`;
  }
  function inQuery(event){return (!state.sport||event.sport_id===state.sport) && matches([event.title,event.sport,...(event.names||[]),event.opponent||''].join(' '),state.query);}
  function byStatus(event){
    if(state.status==='result')return ['won','lost','draw','result'].includes(event.result_state)||Boolean(event.rank);
    if(state.status==='final')return event.phase==='決賽';
    if(state.status==='pending')return ['pending','conditional'].includes(event.result_state);
    return true;
  }
  function athleteMatches(athlete){
    const details=athlete.entry_ids.map(pid=>data.entries.find(e=>e.pid===pid)?.title || '').join(' ');
    return (!state.sport || athlete.sport_id===state.sport) && matches([athlete.name,athlete.sport,...athlete.groups,details].join(' '),state.query);
  }
  function chooseItems(){
    if(state.view==='schedule')return data.events.filter(e=>inQuery(e)&&byStatus(e)&&(!state.day||e.date===state.day));
    if(state.view==='athletes')return data.athletes.filter(athleteMatches);
    if(state.view==='finals')return data.finals.filter(f=>inQuery(f)&&(!state.day||f.date===state.day)).sort((a,b)=>b.date.localeCompare(a.date)||(a.rank||99)-(b.rank||99));
    return data.sports.filter(s=>(!state.sport||s.id===state.sport) && matches(s.name+' '+data.athletes.filter(a=>a.sport_id===s.id).map(a=>a.name).join(' '),state.query)).sort((a,b)=>{
      const getEnd=s=>data.plans.filter(p=>p.sport_id===s.id).reduce((value,p)=>p.end>value?p.end:value,'');
      const ae=getEnd(a),be=getEnd(b),today=taipeiDay();return Number(ae<today)-Number(be<today)||ae.localeCompare(be);
    });
  }
  function athleteCard(a){
    const events=a.event_ids.map(id=>eventMap.get(id)).filter(Boolean);
    const next=events.filter(e=>e.date>=taipeiDay()&&e.result_state!=='conditional').sort((a,b)=>a.date.localeCompare(b.date)||(a.time||'99').localeCompare(b.time||'99'))[0];
    const finals=a.final_ids.map(id=>finalMap.get(id)).filter(Boolean);
    const best=finals.filter(f=>f.rank).sort((a,b)=>a.rank-b.rank)[0];
    return `<article class="athlete-card"><p class="sport-tag small">${esc(a.sport)}</p><h3><button class="name-button" type="button" data-athlete="${a.id}">${esc(a.name)}</button></h3><p class="small">${esc(a.groups.join('、'))}</p><p>${next?`${shortDate(next.date)} ${weekday(next.date)} <strong>${esc(next.time||'時間待確認')}</strong>`:events.length?'已整理場次請點姓名查看':'查看種類期間與官方詳細賽程'}</p><div class="event-bottom"><span>${events.length} 筆已對應場次</span>${best?`<span class="pill ${best.rank===1?'gold':best.rank===2?'silver':best.rank===3?'bronze':''}">最佳第 ${best.rank} 名</span>`:''}</div></article>`;
  }
  function sportCard(s, periodOnly=false){
    const athletes=data.athletes.filter(a=>a.sport_id===s.id);
    let plans=data.plans.filter(p=>p.sport_id===s.id);
    if(periodOnly && state.day)plans=plans.filter(p=>p.start<=state.day && p.end>=state.day);
    const resources=data.resources.filter(r=>r.sport_id===s.id && !r.qualification);
    const uniqueResources=[...new Map(resources.map(r=>[r.label+'|'+r.url,r])).values()];
    const attachments=data.documents.filter(d=>d.sport_id===s.id);
    return `<article class="sport-card"><div class="event-meta"><span>${periodOnly?'種類期間參考':'115 全民運'}</span><span>${athletes.length} 筆選手登錄</span></div><h3>${esc(s.name)}</h3>${plans.map(p=>`<p class="range">${shortDate(p.start)}${p.start!==p.end?' – '+shortDate(p.end):''}</p><p class="small">${esc(p.discipline)}${p.end_note.includes('雨備')?` · ${esc(p.end_note)}`:''}</p><p class="small">${esc(p.venue)}</p>`).join('')}<p class="small">以上為種類比賽期間，不代表每位選手每天出賽。</p>${athletes.length?namesMarkup(athletes.map(a=>a.name),s.id):'<p class="small">本次高雄公開報名資料未列選手。</p>'}<div class="link-row"><button class="button subtle" data-sport-athletes="${s.id}" type="button">查此種類選手</button><button class="button subtle" data-sport-schedule="${s.id}" type="button">查已對應場次</button></div><div class="link-row">${uniqueResources.map(r=>sourceLink(r.url,r.label)).join('')}</div>${attachments.length?`<details class="doc-list"><summary>官方詳細賽程 · ${attachments.length} 份附件</summary>${attachments.map(d=>`<div class="doc-item"><p>${esc(d.title)}</p><div class="link-row"><button type="button" class="text-button" data-document="${d.id}">站內查看</button>${sourceLink(d.url,'PDF 原檔')}</div></div>`).join('')}</details>`:''}</article>`;
  }
  function empty(message,detail='') {return `<div class="empty"><h3>${esc(message)}</h3><p>${esc(detail)}</p><button class="button subtle" type="button" data-action="reset">清除篩選，查看全部</button></div>`;}
  function renderDates(){
    $('date-controls').hidden=!['schedule','finals'].includes(state.view);
    $('date-picker').value=state.day;
    const dates=[...new Set([...data.events.map(e=>e.date),...data.finals.map(f=>f.date),...data.plans.flatMap(p=>[p.start,p.end]),taipeiDay(),...(state.day?[state.day]:[])])].sort();
    $('date-strip').innerHTML=dates.map(day=>`<button class="date-day ${day===state.day?'selected':''}" data-date="${day}" type="button" aria-pressed="${day===state.day}"><span>${weekday(day)}${day===taipeiDay()?' · 今天':''}</span><strong>${shortDate(day)}</strong></button>`).join('');
  }
  function renderStats(){
    const dayEvents=data.events.filter(e=>e.date===taipeiDay() && e.result_state!=='conditional');
    const counts=[1,2,3].map(rank=>data.finals.filter(f=>f.rank===rank).length);
    $('stats').innerHTML=`<div class="stat"><div class="stat-label">今天已對應場次</div><div class="stat-value">${dayEvents.length}</div><div class="stat-sub">另有 ${data.events.filter(e=>e.date===taipeiDay()&&e.result_state==='conditional').length} 筆晉級待確認</div></div><div class="stat"><div class="stat-label">高雄選手登錄</div><div class="stat-value">${data.athletes.length}</div><div class="stat-sub">同名跨種類分列</div></div><div class="stat"><div class="stat-label">官方已公告獎牌</div><div class="breakdown"><span>金 <b>${counts[0]}</b></span><span>銀 <b>${counts[1]}</b></span><span>銅 <b>${counts[2]}</b></span></div><div class="stat-sub">團體項目每項計 1 面</div></div><div class="stat"><div class="stat-label">競賽資料涵蓋</div><div class="stat-value">${data.sports.length}<span style="font-size:16px;font-weight:500"> 種</span></div><div class="stat-sub">${data.documents.length} 份官方賽程附件</div></div>`;
  }
  function render(){
    document.querySelectorAll('[data-view]').forEach(b=>{const active=b.dataset.view===state.view;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    $('status-filter-wrap').hidden=state.view!=='schedule';
    $('search').value=state.query;$('sport-filter').value=state.sport;$('status-filter').value=state.status;
    renderDates();currentItems=chooseItems();
    const title={schedule:state.day?`${shortDate(state.day)} ${weekday(state.day)} · 比賽日程`:'全部比賽日程',athletes:'高雄選手名單',finals:'決賽與名次',sports:'全部競賽種類'};
    $('result-title').textContent=title[state.view];
    $('result-summary').textContent=state.view==='sports'?`${currentItems.length} 種 · 依種類結束日期排列，已結束項目列於後方`:state.view==='athletes'?`${currentItems.length} 筆選手登錄 · 點姓名查看個人賽程與成績`:state.view==='finals'?`${currentItems.length} 筆最終成績 · 團體成績每項計 1 筆`:`${currentItems.length} 筆場次 · 時間皆為臺灣時間`;
    let content='';
    if(state.view==='schedule'){
      let lastDay='';
      content=currentItems.map(event=>{let header='';if(event.date!==lastDay){lastDay=event.date;header=`<h3 class="day-heading">${shortDate(event.date)} ${weekday(event.date)} <span>${event.date.slice(0,4)}</span></h3>`;}return header+eventCard(event);}).join('');
      if(!currentItems.length)content=empty('這個條件下沒有已對應的選手場次','可換日期或種類查詢。未列出場次不代表沒有比賽，其他資訊可查看下方官方賽程。');
      if(state.query){
        const people=data.athletes.filter(athleteMatches);
        if(people.length)content=`<div class="coverage"><p>找到 ${people.length} 筆選手登錄 · 點姓名查看全部日期的個人賽程</p><div class="names">${people.slice(0,6).map(a=>`<button class="name-button" type="button" data-athlete="${a.id}">${esc(a.name)}<span class="small">（${esc(a.sport)}）</span></button>`).join('')}</div>${people.length>6?'<button class="text-button" type="button" data-view="athletes">查看全部符合的選手</button>':''}</div>`+content;
      }
      if(!state.status){
        const related=data.sports.filter(s=>(!state.sport||s.id===state.sport) && data.athletes.some(a=>a.sport_id===s.id&&matches(a.name+' '+s.name,state.query)) && data.plans.some(p=>p.sport_id===s.id&&(!state.day||(p.start<=state.day&&p.end>=state.day))));
        if(related.length)content+=`<h3 class="day-heading">其他種類與完整賽程</h3><p class="coverage">部分賽程仍以 PDF 公告。下方保留完整附件及高雄名單；未完成個人場次對應的資料，請以附件中的組別、項目與出場順序確認。</p><div class="sport-grid">${related.map(s=>sportCard(s,true)).join('')}</div>`;
      }
    }else if(state.view==='athletes'){
      const pages=Math.max(1,Math.ceil(currentItems.length/pageSize));state.page=Math.min(state.page,pages);
      content=currentItems.length?`<div class="athlete-grid">${currentItems.slice((state.page-1)*pageSize,state.page*pageSize).map(athleteCard).join('')}</div>`:empty('找不到這位選手','可先只輸入姓氏，或清除競賽種類篩選。');
      if(pages>1)content+=`<div class="pagination"><button class="button subtle" data-page="${state.page-1}" ${state.page===1?'disabled':''}>上一頁</button><span>${state.page} / ${pages}</span><button class="button subtle" data-page="${state.page+1}" ${state.page===pages?'disabled':''}>下一頁</button></div>`;
    }else if(state.view==='finals'){
      const qualified=data.events.filter(e=>e.advancement==='qualified' && inQuery(e) && (!state.day||e.date===state.day) && !data.finals.some(f=>f.sport_id===e.sport_id && f.names.some(n=>e.names.includes(n)) && normalize(e.title).includes(normalize(f.title))));
      content=`<p class="coverage">「最終成績」包含官方決賽成績表所列名次；團體項目第 3 名以後，不代表參加過冠軍戰。「已確認晉級」只採官方標記、出場名單或可核對的對戰表。</p>`;
      if(qualified.length)content+=`<h3 class="day-heading">已確認晉級決賽</h3>${qualified.map(e=>eventCard(e,true)).join('')}`;
      content+=currentItems.length?`<h3 class="day-heading">已公告最終名次</h3>${currentItems.map(finalCard).join('')}`:empty('尚無符合條件的最終成績','沒有成績不等於未晉級。可查看上方已確認晉級的場次，或切回比賽日程。');
    }else content=currentItems.length?`<div class="sport-grid">${currentItems.map(s=>sportCard(s)).join('')}</div>`:empty('沒有符合條件的競賽種類');
    $('results').innerHTML=content;$('results').setAttribute('aria-busy','false');
    $('export').hidden=state.view==='sports';
    $('export').textContent=state.view==='finals'?'匯出最終名次 CSV ↓':'匯出目前結果 CSV ↓';
    try{const params=new URLSearchParams();params.set('view',state.view);if(state.day)params.set('date',state.day);if(state.query)params.set('q',state.query);if(state.sport)params.set('sport',state.sport);if(state.status)params.set('status',state.status);history.replaceState(null,'','#'+params);}catch{}
  }
  function openDialog(title,content){lastFocus=document.activeElement;$('dialog-title').textContent=title;$('dialog-content').innerHTML=content;if(!$('athlete-dialog').open)$('athlete-dialog').showModal();$('athlete-dialog').scrollTop=0;document.body.classList.add('modal-open');}
  function showAthlete(id){
    const a=data.athletes.find(a=>a.id===id);if(!a)return;
    const events=a.event_ids.map(id=>eventMap.get(id)).filter(Boolean);
    const finals=a.final_ids.map(id=>finalMap.get(id)).filter(Boolean);
    const plans=data.plans.filter(p=>p.sport_id===a.sport_id);
    const attachments=data.documents.filter(d=>d.sport_id===a.sport_id);
    let content=`<div class="detail-list"><p><strong>${esc(a.sport)}</strong> · ${esc(a.groups.join('、'))}</p><p class="small">高雄市代表隊 · 以下場次與成績依官方公開資料整理。</p></div>`;
    if(finals.length)content+=`<h3 class="day-heading">最終成績</h3>${finals.map(finalCard).join('')}`;
    content+=`<h3 class="day-heading">已對應的比賽場次 <span>${events.length} 筆</span></h3>${events.length?events.map(e=>eventCard(e,true)).join(''):'<div class="empty">尚無可精確對應此選手的場次。請查看下方完整賽程附件。</div>'}`;
    content+=`<h3 class="day-heading">種類比賽期間</h3><p class="small">此處為整個種類的期間，不是這位選手每天都要出賽。</p>${plans.map(p=>`<p style="margin-top:8px">${esc(p.discipline)}：${shortDate(p.start)} – ${shortDate(p.end)}</p>`).join('')}<h3 class="day-heading">官方詳細賽程</h3>${attachments.map(d=>`<div class="doc-item"><p>${esc(d.title)}</p><div class="link-row"><button class="text-button" data-document="${d.id}" type="button">站內查看</button>${sourceLink(d.url,'PDF 原檔')}</div></div>`).join('')}<div class="link-row">${a.sources.slice(0,3).map(url=>sourceLink(url,'官方名單／成績')).join('')}</div>`;
    openDialog(a.name,content);
  }
  function showDocument(id){
    const meta=data.documents.find(d=>d.id===id);const doc=docs.documents.find(d=>d.id===id);
    if(!meta)return;
    let content=`<p>${sourceLink(meta.url,'開啟官方 PDF 原始排版')}</p><p class="coverage">以下為附件文字，原始表格的合併儲存格或對戰線可能無法完整呈現。確認個別場次時，可開啟上方 PDF 核對。</p>`;
    if(doc?.searchable)content+=`<label class="document-search"><span>搜尋附件內的姓名、日期或項目</span><input id="document-search" type="search" placeholder="輸入關鍵字，篩選含關鍵字的頁面" data-document-search="${id}"></label><div id="document-pages">${doc.pages.map((p,i)=>`<details class="pdf-page" data-page-text="${i}" ${doc.pages.length===1?'open':''}><summary>第 ${i+1} 頁</summary><pre>${esc(p)}</pre>${sourceLink(meta.url+'#page='+(i+1),'查看這一頁原檔')}</details>`).join('')}</div>`;
    else content+='<div class="empty">這份附件為影像或尚無文字內容，請開啟官方 PDF 查看。</div>';
    openDialog(meta.title,content);
  }
  function reset(){state={...state,query:'',sport:'',status:'',day:'',page:1};render();}
  function scrollDate(){document.querySelector('.date-day.selected')?.scrollIntoView({block:'nearest',inline:'center'});}
  function updateNotice(status){
    const notice=$('data-notice');
    if(downloadMode){notice.textContent=`你正在查看下載版，資料截至 ${prettyStamp(data.meta.checked_at)}。放到 GitHub 並啟用更新流程後，才會自動同步。`;notice.hidden=false;return;}
    const age=Date.now()-new Date(data.meta.checked_at).getTime();
    if(status?.status==='error'){notice.textContent='最近一次資料同步失敗，目前保留上次成功的內容；請以各場次的官方連結核對。';notice.hidden=false;}
    else if(age>45*60*1000){notice.textContent=`這份資料已超過 45 分鐘未更新（截至 ${prettyStamp(data.meta.checked_at)}）。目前結果可能有延遲，請開啟官方依據核對。`;notice.hidden=false;}
    else if(data.meta.unrecognized_reports?.length){notice.textContent='部分成績報告的格式改變，暫時需點選官方依據查看。';notice.hidden=false;}
    else notice.hidden=true;
  }
  async function refresh(manual=false){
    if(refreshBusy)return;
    if(downloadMode){if(manual){$('updated-at').textContent='下載版不會自行取得新的官方資料';updateNotice();}return;}
    refreshBusy=true;$('refresh').disabled=true;
    const oldStamp=data.meta.checked_at;
    try{
      const response=await fetch(`./data/snapshot.json?t=${Date.now()}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const fresh=await response.json();if(fresh.schema_version!==1||!Array.isArray(fresh.events)||!Array.isArray(fresh.athletes))throw new Error('Invalid snapshot');
      data=fresh;indexData();renderStats();render();
      let syncStatus=null;try{const r=await fetch(`./data/sync-status.json?t=${Date.now()}`,{cache:'no-store'});if(r.ok)syncStatus=await r.json();}catch{}
      if(manual || (data.meta.documents_checked_at && docs.checked_at!==data.meta.documents_checked_at)){try{const r=await fetch(`./data/documents.json?t=${Date.now()}`,{cache:'no-store'});if(r.ok){const d=await r.json();if(Array.isArray(d.documents))docs=d;}}catch{}}
      $('updated-at').textContent=`資料更新 ${prettyStamp(data.meta.checked_at)}${manual&&oldStamp===data.meta.checked_at?' · 目前沒有新版本':''}`;updateNotice(syncStatus);
    }catch(error){
      $('data-notice').hidden=false;$('data-notice').textContent='目前無法讀取新版資料，已保留畫面上的內容。請稍後再試，或開啟官方依據查看。';
    }finally{refreshBusy=false;$('refresh').disabled=false;}
  }
  function exportCSV(){
    let rows=[];
    if(state.view==='schedule')rows=[['日期','時間','時間性質','種類','項目','階段','選手姓名','名單性質','對手','狀態','本輪名次','決賽名次','成績（高雄在前）','官方依據'],...currentItems.map(e=>[e.date,e.time||'待確認',e.time_scope==='event'?'項目開始':e.time_scope==='match'?'表定時間':'個別時間待確認',e.sport,e.title,e.phase,e.names.join('、'),e.result_state==='conditional'?'報名名單，晉級待確認':nameBasisLabel[e.names_basis]||'官方名單',e.opponent,statusInfo(e).text,e.round_rank||'',e.rank||'',scoreLabel(e),e.source])];
    else if(state.view==='athletes')rows=[['姓名','種類','組別','已對應場次','最終成績筆數','官方名單'],...currentItems.map(a=>[a.name,a.sport,a.groups.join('、'),a.event_ids.length,a.final_ids.length,a.sources[0]])];
    else rows=[['日期','種類','項目','選手姓名','最終名次','成績','官方依據'],...currentItems.map(f=>[f.date,f.sport,f.title,f.names.join('、'),f.rank_text,f.score,f.source])];
    const blob=new Blob(['\uFEFF'+rows.map(r=>r.map(csvCell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8;'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`sport115-高雄-${state.view}-${state.day||'全部'}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  if(!data?.events || !data?.athletes){$('results').innerHTML=empty('資料檔案尚未載入','請確認網站檔案已完整上傳，包含 site/data 資料夾。');$('updated-at').textContent='資料載入失敗';$('results').setAttribute('aria-busy','false');return;}
  try{const p=new URLSearchParams(location.hash.slice(1));if(['schedule','athletes','finals','sports'].includes(p.get('view')))state.view=p.get('view');const day=p.get('date')||'';if(/^2026-\d{2}-\d{2}$/.test(day)&&!Number.isNaN(Date.parse(day))&&new Date(day).toISOString().slice(0,10)===day)state.day=day;else if(location.hash)state.day='';if(data.sports.some(s=>s.id===p.get('sport')))state.sport=p.get('sport');state.query=p.get('q')||'';if(['result','final','pending'].includes(p.get('status')))state.status=p.get('status');}catch{}
  indexData();
  $('sport-filter').innerHTML='<option value="">全部種類</option>'+data.sports.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
  $('source-notes').innerHTML=`<p>比賽日程、最終成績及前後一天內的逐場報告與出場名單，預設每 10 分鐘擷取一次；其他日期資料、PDF 與全市報名名單每日檢查一次。網頁每分鐘檢查已發布的新資料。排程可能延遲，請以顯示的資料時間判斷。</p><p style="margin-top:8px">「檢查更新」讀取最近已同步的版本，不會直接觸發官網爬取。已知賽程開始後仍無成績，顯示「待官方更新」，不推測正在比賽或已遭淘汰。</p><p style="margin-top:8px">個人項目的「項目開始」是該項目的表定時間；個別選手上場仍可能依檢錄與賽序調整。官網 HTML、官方 PDF 與對戰表無法確實對應的資料，保留在種類頁的附件中，不補造時間、名字或名次。</p><p style="margin-top:8px">本次整理：${data.registrations.length} 筆選手報名人次、${data.documents.length} 份賽程 PDF。相同姓名跨種類分列，本站無法用公開姓名辨識所有同名者。${sourceLink(data.meta.sources.roster,'報名來源')} ${sourceLink(data.meta.sources.finals,'名次來源')}</p>`;
  $('updated-at').textContent='資料更新 '+prettyStamp(data.meta.checked_at);
  $('source-notes').insertAdjacentHTML('afterbegin','<p style="margin-bottom:8px">啟用 GitHub 更新流程後，定時擷取期間為 2026 年 9–10 月；賽會結束後保留查詢，也可手動更新。</p>');
  renderStats();render();updateNotice();
  requestAnimationFrame(scrollDate);
  $('search').addEventListener('input',e=>{state.query=e.target.value;state.page=1;render();});
  $('sport-filter').addEventListener('change',e=>{state.sport=e.target.value;state.page=1;render();});
  $('status-filter').addEventListener('change',e=>{state.status=e.target.value;render();});
  $('date-picker').addEventListener('change',e=>{state.day=e.target.value;render();scrollDate();});
  $('today').addEventListener('click',()=>{state.day=taipeiDay();render();scrollDate();});
  $('all-dates').addEventListener('click',()=>{state.day='';render();});
  $('clear').addEventListener('click',()=>{state.query='';state.sport='';state.status='';state.page=1;render();});
  $('refresh').addEventListener('click',()=>refresh(true));$('export').addEventListener('click',exportCSV);
  $('close-dialog').addEventListener('click',()=>$('athlete-dialog').close());
  $('athlete-dialog').addEventListener('close',()=>{document.body.classList.remove('modal-open');if(lastFocus?.isConnected)lastFocus.focus();});
  document.addEventListener('input',e=>{if(e.target.id!=='document-search')return;const doc=docs.documents.find(d=>d.id===e.target.dataset.documentSearch);if(!doc)return;document.querySelectorAll('[data-page-text]').forEach(el=>{const show=matches(doc.pages[Number(el.dataset.pageText)],e.target.value);el.hidden=!show;if(e.target.value&&show)el.open=true;});});
  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.view){state.view=b.dataset.view;state.status='';state.page=1;if(state.view==='finals')state.day='';render();}
    if(b.dataset.date){state.day=b.dataset.date;render();scrollDate();}
    if(b.dataset.athlete)showAthlete(b.dataset.athlete);
    if(b.dataset.document)showDocument(b.dataset.document);
    if(b.dataset.sportAthletes){state.view='athletes';state.sport=b.dataset.sportAthletes;state.query='';state.page=1;render();$('result-title').scrollIntoView({block:'start'});}
    if(b.dataset.sportSchedule){state.view='schedule';state.sport=b.dataset.sportSchedule;state.query='';state.day='';state.status='';render();$('result-title').scrollIntoView({block:'start'});}
    if(b.dataset.action==='reset')reset();
    if(b.dataset.page){state.page=Number(b.dataset.page);render();$('result-title').scrollIntoView({block:'start'});}
  });
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  setInterval(()=>{if(!document.hidden)refresh();},60000);
  if(!downloadMode)refresh();
})();
