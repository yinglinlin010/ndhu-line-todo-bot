import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createHash} from 'node:crypto';

function app() {
  const properties = {WEBHOOK_KEY:'a'.repeat(64), OWNER_ID:'U'+'1'.repeat(32), BOT_ID:'U'+'2'.repeat(32), LINE_CHANNEL_ACCESS_TOKEN:'test-only'};
  const replies = [], cached = new Map();
  const context = vm.createContext({console:{log(){}},
    PropertiesService:{getScriptProperties:()=>({getProperty:k=>properties[k],setProperty:(k,v)=>{properties[k]=v;},getProperties:()=>({...properties})})},
    CacheService:{getScriptCache:()=>({get:k=>cached.get(k),put:(k,v)=>cached.set(k,v)})},
    LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock(){}})},
    HtmlService:{createHtmlOutput:text=>text},
    Utilities:{DigestAlgorithm:{SHA_256:'sha256'},computeDigest:(_,value)=>[...createHash('sha256').update(value).digest()]},
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
