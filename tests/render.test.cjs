// Execute the complete page script against its real HTML IDs. This verifies
// rendering and filter handlers; it is not a substitute for browser layout QA.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function page(){
  const root=path.join(__dirname,'../site');
  const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
  const listeners={},elements=new Map();
  const noop=()=>{};
  for(const [,id] of html.matchAll(/\bid="([^"]+)"/g))elements.set(id,{
    id,innerHTML:'',textContent:'',value:'',dataset:{},listeners:{},
    classList:{toggle:noop,add:noop,remove:noop},setAttribute:noop,removeAttribute:noop,
    insertAdjacentHTML(_position,text){this.innerHTML+=text;},
    addEventListener(type,fn){this.listeners[type]=fn;},scrollIntoView:noop,
  });
  const document={documentElement:{dataset:{}},body:{classList:{add:noop,remove:noop}},hidden:true,
    getElementById(id){assert.ok(elements.has(id),`Missing HTML target ${id}`);return elements.get(id);},
    querySelectorAll(){return [];},querySelector(){return null;},
    addEventListener(type,fn){listeners[type]=fn;},
  };
  const context=vm.createContext({document,location:{protocol:'file:',hash:'#view=schedule'},
    window:{SPORT115_DATA:JSON.parse(fs.readFileSync(path.join(root,'data/snapshot.json'))),SPORT115_DOCUMENTS:{documents:[]}},
    URL,URLSearchParams,Intl,history:{replaceState:noop},requestAnimationFrame:noop,setInterval:noop,
  });
  vm.runInContext(fs.readFileSync(path.join(root,'app.js'),'utf8'),context);
  return {elements,listeners,change(id,value){const el=elements.get(id);el.value=value;el.listeners.change({target:el});}};
}

test('every requested official sport renders calendar cards and Kaohsiung names when available',()=>{
  const ui=page();
  for(const sid of ['208','212','133','132','131','126','125','124','123','122','121','120','329','328','327','306','307','309','310','314','325','326']){
    ui.change('sport-filter',sid);
    const html=ui.elements.get('results').innerHTML;
    assert.match(html,/class="event-card/,`${sid} has no rendered schedule`);
    if(sid==='126')assert.match(html,/目前官方公開資料未列高雄隊伍/);
    else assert.match(html,/class="name-button"/,`${sid} has no athlete name buttons`);
    assert.doesNotMatch(html,/undefined|NaN/);
  }
});

test('a date with no matches provides a working route to the sport calendar',()=>{
  const ui=page();ui.change('sport-filter','131');ui.change('date-picker','2026-09-16');
  assert.match(ui.elements.get('results').innerHTML,/sport-all-dates/);
  ui.listeners.click({target:{closest:()=>({dataset:{action:'sport-all-dates'}})}});
  assert.match(ui.elements.get('results').innerHTML,/class="event-card/);
});

test('medal filtering excludes the dragon boat B final and shows the A final',()=>{
  const ui=page();ui.change('sport-filter','326');ui.change('status-filter','final');
  assert.match(ui.elements.get('results').innerHTML,/決賽A/);
  assert.doesNotMatch(ui.elements.get('results').innerHTML,/決賽B/);
});
