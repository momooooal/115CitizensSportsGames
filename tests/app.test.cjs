const test = require('node:test');
const assert = require('node:assert/strict');
const { matches, taipeiDay, statusInfo, scoreLabel, csvCell, safeUrl } = require('../site/app.js');

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
  assert.equal(statusInfo({ rank:2, phase:'決賽', result_state:'result' }).text,'決賽第 2 名');
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
