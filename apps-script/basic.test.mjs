import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createHash, createHmac} from 'node:crypto';

function app() {
  const properties = {WEBHOOK_KEY:'a'.repeat(64), OWNER_ID:'U'+'1'.repeat(32), BOT_ID:'U'+'2'.repeat(32), LINE_CHANNEL_ACCESS_TOKEN:'test-only'};
  const replies = [], cached = new Map();
  const context = vm.createContext({console:{log(){}},
    PropertiesService:{getScriptProperties:()=>({getProperty:k=>properties[k],setProperty:(k,v)=>{properties[k]=v;},getProperties:()=>({...properties})})},
    CacheService:{getScriptCache:()=>({get:k=>cached.get(k),put:(k,v)=>cached.set(k,v)})},
    LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock(){}})},
    HtmlService:{createHtmlOutput:text=>text}, ContentService:{createTextOutput:text=>text},
    Utilities:{Charset:{UTF_8:'UTF-8'},newBlob:value=>({getBytes:()=>[...Buffer.from(value,'utf8')]}),computeHmacSha256Signature:(value,key)=>[...createHmac('sha256',key).update(value).digest()],base64Encode:bytes=>Buffer.from(bytes).toString('base64'),DigestAlgorithm:{SHA_256:'sha256'},computeDigest:(_,value)=>[...createHash('sha256').update(value).digest()]},
    UrlFetchApp:{fetch:(_,request)=>{replies.push(JSON.parse(request.payload));return {getResponseCode:()=>200};}}
  });
  vm.runInContext(readFileSync(new URL('./Code.gs',import.meta.url),'utf8'),context);
  const event = (text,id='event-1',user=properties.OWNER_ID)=>({webhookEventId:id,type:'message',source:{type:'user',userId:user},message:{type:'text',text},replyToken:'b'.repeat(32)});
  const post = (events,key=properties.WEBHOOK_KEY,destination=properties.BOT_ID)=>context.doPost({parameter:{key},postData:{contents:JSON.stringify({destination,events})}});
  return {context,properties,replies,event,post};
}

test('private owner can save/query; redelivery never adds or replies twice',()=>{
  const a=app(); const e=a.event('記錄：交報告'); a.post([e]); a.post([e]);
  assert.equal(Object.keys(a.properties).filter(k=>k.startsWith('TODO_')).length,1);
  assert.equal(a.replies.length,1);
  a.post([a.event('查詢','query')]); assert.match(a.replies[1].messages[0].text,/交報告/);
});
test('wrong key, wrong bot, other user and group cannot mutate or send',()=>{
  const a=app(); a.post([a.event('記錄：fake')],'wrong'); a.post([a.event('記錄：fake')],undefined,'wrong');
  a.post([a.event('記錄：fake','other','U'+'3'.repeat(32))]);
  const e=a.event('記錄：fake');e.source.type='group';a.post([e]);
  assert.equal(a.replies.length,0); assert.equal(Object.keys(a.properties).filter(k=>k.startsWith('TODO_')).length,0);
});
test('empty/long tasks and unsupported chat do not write',()=>{
  const a=app(); ['記錄：','記錄：'+'字'.repeat(301),'你好'].forEach((s,i)=>a.post([a.event(s,'e'+i)]));
  assert.equal(a.replies.length,3); assert.equal(Object.keys(a.properties).filter(k=>k.startsWith('TODO_')).length,0);
});
test('query lists newest ten; capacity returns an explicit refusal',()=>{
  const a=app(); const tasks=Array.from({length:12},(_,i)=>({content:'task'+i}));
  const reply=a.context.todoReply_('查詢',tasks).answer; assert.match(reply,/最新 10 筆/); assert.doesNotMatch(reply,/task10/);
  assert.equal(a.context.todoReply_('記錄：new',Array(100).fill({})).content,undefined);
});

test('relay disabled by default preserves existing todo behavior',()=>{
  const a=app(); a.post([a.event('記錄：still local')]);
  assert.equal(a.replies.length,1);
  assert.equal(Object.keys(a.properties).filter(k=>k.startsWith('TODO_')).length,1);
});
test('relay rejects arbitrary destinations before making network calls',()=>{
  const a=app(); a.properties.LOCAL_RELAY_BASE='https://example.org';
  a.properties.LOCAL_RELAY_KEY='a'.repeat(64);
  const p={getProperty:k=>a.properties[k]};
  assert.equal(a.context.relayLocal_(a.event('hi'),a.properties.BOT_ID,p),'disabled');
  assert.equal(a.replies.length,0);
});

test('cloud todo remains in Apps Script when relay is enabled',()=>{
  const a=app(); a.properties.ENABLE_LOCAL_RELAY='1';
  a.properties.LOCAL_RELAY_BASE='https://test-only.trycloudflare.com';
  a.properties.LOCAL_RELAY_KEY='a'.repeat(64);
  a.post([a.event('記錄：cloud independent')]);
  assert.equal(Object.keys(a.properties).filter(k=>k.startsWith('TODO_')).length,1);
  assert.match(a.replies[0].messages[0].text,/cloud independent/);
});
test('offline preflight falls back before forwarding any event',()=>{
  const a=app(); a.properties.LOCAL_RELAY_BASE='https://test-only.trycloudflare.com';
  a.properties.LOCAL_RELAY_KEY='a'.repeat(64); let calls=0;
  a.context.UrlFetchApp.fetch=()=>{calls++; return {getResponseCode:()=>503};};
  assert.equal(a.context.relayLocal_(a.event('hi'),a.properties.BOT_ID,{getProperty:k=>a.properties[k]}),'disabled');
  assert.equal(calls,1);
});

test('signed registration updates only tunnel fields and rejects wrong signatures',()=>{
  const a=app();a.properties.LOCAL_RELAY_KEY='c'.repeat(64);
  const stamp=String(Math.floor(Date.now()/1000)),base='https://test-only.trycloudflare.com';
  const body={action:'registerLocalRelay',timestamp:stamp,base,signature:createHmac('sha256','c'.repeat(64)).update(stamp+'\n'+base).digest('base64')};
  const request=b=>({parameter:{key:a.properties.WEBHOOK_KEY},postData:{contents:JSON.stringify(b)}});
  assert.equal(a.context.doPost(request({...body,signature:'wrong'})),'invalid registration');
  assert.equal(a.properties.LOCAL_RELAY_BASE,undefined);
  assert.equal(a.context.doPost(request(body)),'relay registered');
  assert.equal(a.properties.LOCAL_RELAY_BASE,base);assert.equal(a.replies.length,0);
});
test('accepted relay never makes cloud todo or a second LINE reply',()=>{
  const a=app();Object.assign(a.properties,{ENABLE_LOCAL_RELAY:'1',LOCAL_RELAY_BASE:'https://test-only.trycloudflare.com',LOCAL_RELAY_KEY:'c'.repeat(64)});
  const calls=[];a.context.UrlFetchApp.fetch=(url,r)=>{calls.push({url,r});return {getResponseCode:()=>200,getContentText:()=>url.endsWith('/health')?'ok':'ok'};};
  a.post([a.event('解釋慣性')]);assert.equal(calls.length,2);
  assert.match(calls[1].url,/\/apps-script$/);assert.equal(calls[1].r.followRedirects,false);
  const forwarded=calls[1].r;
  assert.equal(forwarded.contentType,'application/json; charset=utf-8');
  const payload=Buffer.from(forwarded.payload);
  assert.equal(JSON.parse(payload.toString('utf8')).events[0].message.text,'解釋慣性');
  assert.equal(forwarded.headers['x-relay-signature'],createHmac('sha256','c'.repeat(64))
    .update(forwarded.headers['x-relay-time']+'\n').update(payload).digest('base64'));
  assert.equal(Object.keys(a.properties).filter(k=>k.startsWith('TODO_')).length,0);
});
test('offline photo receives explicit status; uncertain sent event never gets a second reply',()=>{
  const a=app();Object.assign(a.properties,{ENABLE_LOCAL_RELAY:'1',LOCAL_RELAY_BASE:'https://test-only.trycloudflare.com',LOCAL_RELAY_KEY:'c'.repeat(64)});
  const calls=[];a.context.UrlFetchApp.fetch=(url,r)=>{calls.push({url,r});return {getResponseCode:()=>url.endsWith('/health')?503:200};};
  const image=a.event('photo');image.message={type:'image',id:'image-test'};a.post([image]);
  assert.equal(calls.length,2);assert.match(JSON.parse(calls[1].r.payload).messages[0].text,/未連線/);
  calls.length=0;a.context.UrlFetchApp.fetch=(url,r)=>{calls.push({url,r});if(url.endsWith('/health'))return {getResponseCode:()=>200,getContentText:()=> 'ok'};throw new Error('unknown delivery');};
  a.post([a.event('解釋慣性','second')]);assert.equal(calls.length,2);
});

test('reply token is opaque: a non-hex LINE token is not silently dropped',()=>{
  const a=app();const e=a.event('查詢');e.replyToken='opaque_Test-token+/=';
  a.post([e]);assert.equal(a.replies.length,1);
  assert.equal(a.replies[0].replyToken,e.replyToken);
});
