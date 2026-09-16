const test = require('node:test');
const assert = require('node:assert/strict');
const { matches, taipeiDay, statusInfo, scoreLabel, csvCell, safeUrl, buildScheduleItems, isPendingSchedule, timeScopeLabel, isMedalEvent, eventNames } = require('../site/app.js');

test('today follows Taiwan time at the midnight boundary', () => {
  assert.equal(taipeiDay(new Date('2026-09-14T15:59:59Z')), '2026-09-14');
  assert.equal(taipeiDay(new Date('2026-09-14T16:00:00Z')), '2026-09-15');
});
test('elapsed start time does not claim a match is live or completed', () => {
  const e = { date:'2026-09-14', time:'15:30', result_state:'pending' };
  assert.equal(statusInfo(e,new Date('2026-09-14T08:30:00Z')).text,'待官方更新');
  assert.equal(statusInfo(e,new Date('2026-09-14T06:30:00Z')).text,'賽程已排');
});
test('an unconfirmed final remains unconfirmed after the scheduled start', () => {
  const e = { date:'2026-10-18', time:'11:00', phase:'決賽', result_state:'conditional' };
  assert.equal(statusInfo(e,new Date('2026-10-19T00:00:00Z')).text,'晉級待確認');
});
test('preliminary rank is not displayed as final rank', () => {
  assert.equal(statusInfo({ round_rank:1, result_state:'result' }).text,'已有成績');
  assert.equal(statusInfo({ rank:2, phase:'決賽', result_state:'result' }).text,'最終第 2 名');
});
test('name and sport search accepts multiple terms and 台／臺 variants', () => {
  assert.ok(matches('王立淳 滑輪溜冰','王立淳 滑輪'));
  assert.ok(matches('臺東縣','台東'));
  assert.ok(!matches('王立淳 滑輪溜冰','王立淳 足球'));
});
test('head to head score is always rendered with Kaohsiung first', () => {
  assert.equal(scoreLabel({ opponent:'臺北市', score:'2:7', score_order:'高雄在後' }),'7 : 2');
  assert.equal(scoreLabel({ score:'18.320' }),'18.320');
});
test('CSV escapes quotes and spreadsheet formulas', () => {
  assert.equal(csvCell('=1+1'),'"\'=1+1"');
  assert.equal(csvCell('王"甲'),'"王""甲"');
});
test('source links only open official HTTPS pages', () => {
  assert.equal(safeUrl('javascript:alert(1)'),null);
  assert.equal(safeUrl('https://sport115.tycg.gov.tw.evil.example/'),null);
  assert.ok(safeUrl('https://sport115.tycg.gov.tw/Upfile/a.pdf#page=2'));
});

function calendarFixture() {
  return {
    events:[],entries:[],scheduled_sessions:[],
    registrations:[
      {sport_id:'303',name:'甲選手',group:'男子組競速溜冰'},
      {sport_id:'303',name:'乙選手',group:'女子組花式溜冰'},
      {sport_id:'303',name:'丙選手',group:'男子組溜冰曲棍球'}
    ],
    plans:[{id:'speed',sport_id:'303',sport:'滑輪溜冰',discipline:'滑輪溜冰-競速',
      start:'2026-09-14',end:'2026-09-16',end_note:'09/16（09/17 雨備）',source:'https://sport115.tycg.gov.tw/',venue:'測試場地'}]
  };
}
test('announced competition days remain visible with registration names and no invented start time',()=>{
  const snapshot=calendarFixture();
  const items=buildScheduleItems(snapshot);
  assert.deepEqual(items.map(e=>e.date),['2026-09-14','2026-09-15','2026-09-16']);
  for(const e of items){
    assert.ok(isPendingSchedule(e));
    assert.deepEqual(e.names,['甲選手']);
    assert.equal(e.time,null);
    assert.equal(e.advancement,null);
    assert.match(e.note,/不代表每位選手當天都會出賽/);
    assert.equal(statusInfo(e,new Date('2026-10-01T00:00:00Z')).text,'個別出賽待確認');
  }
  assert.equal(snapshot.events.length,0);
});
test('a known session time is retained while the Kaohsiung appearance remains unconfirmed',()=>{
  const snapshot=calendarFixture();
  snapshot.plans=[];
  snapshot.scheduled_sessions=[{id:'heat',sport_id:'303',sport:'滑輪溜冰',title:'滑輪溜冰男子組競速100公尺',date:'2026-09-15',time:'09:30',phase:'預賽',source:'https://sport115.tycg.gov.tw/'}];
  const [item]=buildScheduleItems(snapshot);
  assert.equal(item.time,'09:30');
  assert.equal(timeScopeLabel(item),'項目表定時間');
  assert.deepEqual(item.names,['甲選手']);
  assert.match(item.note,/實際出賽時間待公布／確認/);
});
test('a pending final does not mark the registration roster as qualified',()=>{
  const snapshot=calendarFixture();snapshot.plans=[];
  snapshot.scheduled_sessions=[{id:'final',sport_id:'303',sport:'滑輪溜冰',title:'滑輪溜冰女子組花式決賽',date:'2026-09-15',time:'10:00',phase:'決賽',source:'https://sport115.tycg.gov.tw/'}];
  const [item]=buildScheduleItems(snapshot);
  assert.deepEqual(item.names,['乙選手']);
  assert.equal(item.rank,null);
  assert.equal(item.advancement,null);
  assert.equal(statusInfo(item).text,'晉級待確認');
});
test('a published named appearance replaces its pending session without duplication',()=>{
  const snapshot=calendarFixture();snapshot.plans=[];
  const session={id:'heat',sport_id:'303',sport:'滑輪溜冰',title:'滑輪溜冰男子組競速100公尺',date:'2026-09-15',time:'09:30',phase:'預賽',pid:'race',source:'https://sport115.tycg.gov.tw/'};
  snapshot.scheduled_sessions=[session];
  snapshot.events=[{...session,id:'named',names:['甲選手'],names_basis:'entry_round',result_state:'pending'}];
  const items=buildScheduleItems(snapshot);
  assert.equal(items.length,1);
  assert.equal(items[0].id,'named');
  assert.ok(!isPendingSchedule(items[0]));
});
test('a published discipline schedule replaces the generic period even if not everyone competes that day',()=>{
  const snapshot=calendarFixture();snapshot.plans[0].end='2026-09-14';
  snapshot.registrations.push({sport_id:'303',name:'丁選手',group:'男子組競速溜冰'});
  snapshot.events=[{id:'known',sport_id:'303',sport:'滑輪溜冰',title:'競速100公尺',date:'2026-09-14',time:'08:00',names:['甲選手']}];
  assert.equal(buildScheduleItems(snapshot).length,1);
  assert.ok(!buildScheduleItems(snapshot).some(e=>e.schedule_scope==='period'));
});
test('a named preliminary does not hide an unannounced final of the same item on the same day',()=>{
  const snapshot=calendarFixture();snapshot.plans=[];
  const session={id:'final',pid:'same-item',sport_id:'303',sport:'滑輪溜冰',title:'男子組競速100公尺（決賽）',date:'2026-09-15',time:'11:30',phase:'決賽',source:'https://sport115.tycg.gov.tw/'};
  snapshot.scheduled_sessions=[session];
  snapshot.events=[{...session,id:'preliminary',time:'09:30',phase:'預賽',title:'男子組競速100公尺（預賽）',names:['甲選手']}];
  const items=buildScheduleItems(snapshot);
  assert.equal(items.length,2);
  assert.ok(items.some(e=>isPendingSchedule(e)&&e.phase==='決賽'&&e.time==='11:30'));
});
test('qualifier dates do not reuse the main-meet registration roster',()=>{
  const snapshot=calendarFixture();snapshot.plans[0].discipline='滑輪溜冰-資格賽';
  assert.deepEqual(buildScheduleItems(snapshot),[]);
});
test('undivided registrations still appear when the schedule separates indoor and outdoor events',()=>{
  const snapshot=calendarFixture();snapshot.registrations=[{sport_id:'306',name:'甲選手',group:'男子組'}];
  snapshot.plans=[{id:'indoor',sport_id:'306',sport:'拔河',discipline:'拔河-室內賽',start:'2026-10-17',end:'2026-10-18',source:'https://sport115.tycg.gov.tw/'}];
  const items=buildScheduleItems(snapshot);
  assert.equal(items.length,2);
  assert.deepEqual(items[0].names,['甲選手']);
});
test('a published event roster without Kaohsiung entries is not treated as an unpublished roster',()=>{
  const snapshot=calendarFixture();snapshot.plans=[];
  snapshot.scheduled_sessions=[{id:'absent',pid:'absent',sport_id:'303',sport:'滑輪溜冰',title:'女子組花式直排',date:'2026-09-15',time:'10:00',phase:'',source:'https://sport115.tycg.gov.tw/'}];
  snapshot.entries=[{pid:'absent',sport_id:'303',names:[],roster_published:true}];
  assert.deepEqual(buildScheduleItems(snapshot),[]);
  snapshot.entries[0].roster_published=false;
  assert.equal(buildScheduleItems(snapshot).length,1);
});
test('published PDF schedules suppress period placeholders only for their discipline',()=>{
  const snapshot=calendarFixture();
  snapshot.plans.push({...snapshot.plans[0],id:'art',discipline:'滑輪溜冰-花式'});
  snapshot.documents=[{sport_id:'303',title:'滑輪溜冰(競速)-賽程表.pdf'}];
  const items=buildScheduleItems(snapshot);
  assert.equal(items.length,3);
  assert.ok(items.every(e=>e.title.includes('花式')&&e.names.includes('乙選手')));
});
test('short and long programs on the same day remain distinct',()=>{
  const snapshot=calendarFixture();snapshot.plans=[];
  const item={id:'long',sport_id:'303',sport:'滑輪溜冰',pid:'art',date:'2026-09-16',time:'16:20',title:'女子組花式直排(長曲)',phase:'',source:'https://sport115.tycg.gov.tw/'};
  snapshot.scheduled_sessions=[item];
  snapshot.events=[{...item,id:'short',title:'女子組花式直排(短曲)',time:'10:00',names:['乙選手']}];
  assert.equal(buildScheduleItems(snapshot).length,2);
});
test('medal filters include verified untitled finals and bronze matches, not preliminary leaders',()=>{
  assert.ok(isMedalEvent({title:'5000公尺計分賽',medal_event:true}));
  assert.ok(isMedalEvent({phase:'銅牌賽'}));
  assert.ok(!isMedalEvent({phase:'準決賽',round_rank:1}));
  assert.ok(!isMedalEvent({title:'短曲',round_rank:1}));
});
test('searchable registration supplements do not overwrite confirmed participants',()=>{
  const event={names:['甲選手'],registered_names:['甲選手','乙選手']};
  assert.deepEqual(eventNames(event),['甲選手','乙選手']);
  assert.deepEqual(event.names,['甲選手']);
});
