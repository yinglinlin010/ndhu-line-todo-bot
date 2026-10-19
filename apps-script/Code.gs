/** Private, basic LINE todo fallback. Credentials belong in Script Properties.
 * Apps Script does not expose x-line-signature to doPost. This direct endpoint
 * therefore uses a separate secret URL key and accepts only its configured owner.
 * A signature-verifying gateway is required before general/public use.
 */
function doGet() {
  return HtmlService.createHtmlOutput('LINE todo fallback is running.');
}

function sameSecret_(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function doPost(e) {
  var properties = PropertiesService.getScriptProperties();
  var key = properties.getProperty('WEBHOOK_KEY');
  if (!/^[a-f0-9]{64}$/.test(key || '') || !sameSecret_((e.parameter || {}).key, key)) {
    return HtmlService.createHtmlOutput('ok');
  }
  if (!e.postData || !e.postData.contents || e.postData.contents.length > 100000) {
    return HtmlService.createHtmlOutput('ok');
  }
  var body;
  try { body = JSON.parse(e.postData.contents); } catch (_) {
    return HtmlService.createHtmlOutput('ok');
  }
  if (body.action === 'registerLocalRelay') return registerLocalRelay_(body, properties);
  var owner = properties.getProperty('OWNER_ID');
  var bot = properties.getProperty('BOT_ID');
  var token = properties.getProperty('LINE_CHANNEL_ACCESS_TOKEN');
  if (!owner || !bot || !token || body.destination !== bot || !Array.isArray(body.events)) {
    console.log('Webhook ignored: configuration or destination validation failed.');
    return HtmlService.createHtmlOutput('ok');
  }
  console.log('Webhook event count: ' + body.events.length);
  body.events.slice(0, 10).forEach(function (event) {
    if (event.type !== 'message' || !event.source || event.source.type !== 'user' ||
        event.source.userId !== owner || !event.message ||
        typeof event.replyToken !== 'string' || !/^[\x21-\x7e]{1,1024}$/.test(event.replyToken)) {
      console.log('Webhook event ignored: private source, message or reply token validation failed.');
      return;
    }
    var cloudTodo = event.message.type === 'text' && typeof event.message.text === 'string' &&
      (event.message.text.trim() === '查詢' || /^[記紀][錄録]\s*[:：]/.test(event.message.text.trim()));
    if (!cloudTodo && properties.getProperty('ENABLE_LOCAL_RELAY') === '1') {
      var relayed = relayLocal_(event, bot, properties);
      if (relayed === 'busy') {
        replyLine_(event.replyToken, '本機目前忙碌，這一題尚未排入處理，請稍後再問；雲端待辦仍可使用。', token);
        return;
      }
      if (relayed === 'disabled') {
        replyLine_(event.replyToken, '本機 AI 目前未連線，暫時無法回答問題或辨識照片。\n雲端待辦仍可使用：「記錄：事項」或「查詢」。', token);
        return;
      }
      // Unknown delivery must not fall through into a second store or reply.
      if (relayed !== 'disabled') return;
    }
    if (event.message.type !== 'text' || typeof event.message.text !== 'string') return;
    var lock = LockService.getScriptLock();
    if (!lock.tryLock(5000)) return;
    var answer;
    try {
      var id = event.webhookEventId || event.message.id;
      if (typeof id !== 'string' || !id || id.length > 200) return;
      var digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, id)
        .map(function (n) { return ('0' + ((n + 256) % 256).toString(16)).slice(-2); }).join('');
      var cache = CacheService.getScriptCache();
      if (cache.get(digest)) return;
      var tasks = Object.keys(properties.getProperties()).filter(function (k) { return k.indexOf('TODO_') === 0; })
        .map(function (k) { return JSON.parse(properties.getProperty(k)); })
        .sort(function (a, b) { return b.createdAt - a.createdAt || a.id.localeCompare(b.id); });
      var result = todoReply_(event.message.text, tasks);
      answer = result.answer;
      if (result.content) {
        var taskKey = 'TODO_' + digest;
        if (!properties.getProperty(taskKey)) {
          properties.setProperty(taskKey, JSON.stringify({id: digest, content: result.content, createdAt: Date.now()}));
        }
      }
      cache.put(digest, 'handled', 21600);
    } catch (_) {
      answer = '目前無法讀取或儲存待辦，請稍後再試。';
    } finally {
      lock.releaseLock();
    }
    if (answer) {
      replyLine_(event.replyToken, answer, token);
    }
  });
  return HtmlService.createHtmlOutput('ok');
}

function replyLine_(replyToken, answer, token) {
  try {
    var response = UrlFetchApp.fetch('https://api.line.me/v2/bot/message/reply', {
      method: 'post', contentType: 'application/json', followRedirects: false,
      headers: {Authorization: 'Bearer ' + token},
      payload: JSON.stringify({replyToken: replyToken, messages: [{type: 'text', text: answer}]}),
      muteHttpExceptions: true
    });
    console.log('LINE reply status: ' + response.getResponseCode());
  } catch (_) { console.log('LINE reply could not be confirmed.'); }
}

function registerLocalRelay_(body, properties) {
  var key = properties.getProperty('LOCAL_RELAY_KEY') || '';
  var stamp = String(body.timestamp || '');
  var base = String(body.base || '');
  if (!/^[a-f0-9]{64}$/.test(key) || !/^\d{10,12}$/.test(stamp) ||
      Math.abs(Date.now() / 1000 - Number(stamp)) > 60 ||
      !/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(base)) {
    return ContentService.createTextOutput('invalid registration');
  }
  var expected = Utilities.base64Encode(Utilities.computeHmacSha256Signature(stamp + '\n' + base, key));
  if (!sameSecret_(body.signature || '', expected)) return ContentService.createTextOutput('invalid registration');
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return ContentService.createTextOutput('registration busy');
  try {
    var previous = Number(properties.getProperty('LOCAL_RELAY_REGISTERED_AT') || '0');
    if (Number(stamp) < previous) return ContentService.createTextOutput('stale registration');
    properties.setProperty('LOCAL_RELAY_BASE', base);
    properties.setProperty('LOCAL_RELAY_REGISTERED_AT', stamp);
  } finally { lock.releaseLock(); }
  return ContentService.createTextOutput('relay registered');
}

/** Opt-in private relay. The URL must be an explicitly configured quick tunnel.
 * This authenticates Apps Script to Python, NOT the original LINE sender.
 * The secret webhook URL / owner-only restriction still applies upstream.
 */
function relayLocal_(event, bot, properties) {
  var base = properties.getProperty('LOCAL_RELAY_BASE') || '';
  var key = properties.getProperty('LOCAL_RELAY_KEY') || '';
  if (!/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(base) ||
      !/^[a-f0-9]{64}$/.test(key)) return 'disabled';
  if (!event.webhookEventId || !event.message ||
      ['text', 'image'].indexOf(event.message.type) < 0) return 'ignored';
  // Only fall back BEFORE sending an event, never after an uncertain delivery.
  try {
    var health = UrlFetchApp.fetch(base + '/health', {followRedirects: false, muteHttpExceptions: true});
    if (health.getResponseCode() !== 200 || health.getContentText().trim() !== 'ok') return 'disabled';
  } catch (_) { return 'disabled'; }
  var body = JSON.stringify({destination: bot, events: [event]});
  var stamp = String(Math.floor(Date.now() / 1000));
  var signature = Utilities.base64Encode(Utilities.computeHmacSha256Signature(stamp + '\n' + body, key, Utilities.Charset.UTF_8));
  try {
    var response = UrlFetchApp.fetch(base + '/apps-script', {
      method: 'post', contentType: 'application/json; charset=utf-8', followRedirects: false,
      headers: {'x-relay-time': stamp, 'x-relay-signature': signature},
      payload: Utilities.newBlob(body, 'application/json').getBytes(), muteHttpExceptions: true
    });
    console.log('Local relay status: ' + response.getResponseCode());
    if (response.getResponseCode() === 503 && response.getContentText().trim() === 'busy') return 'busy';
    return response.getResponseCode() === 200 ? 'accepted' : 'unconfirmed';
  } catch (_) {
    console.log('Local relay delivery unconfirmed; no duplicate fallback write.');
    return 'unconfirmed';
  }
}

function todoReply_(raw, tasks) {
  var command = raw.trim();
  if (command === '查詢') {
    if (!tasks.length) return {answer: '目前沒有待辦事項。\n輸入「記錄：待辦事項」新增一筆。'};
    var latest = tasks.slice(0, 10);
    return {answer: '你的雲端待辦（共 ' + tasks.length + ' 筆，顯示最新 ' + latest.length + ' 筆）：\n' +
      latest.map(function (t, i) { return (i + 1) + '. ' + t.content; }).join('\n')};
  }
  var match = /^[記紀][錄録]\s*[:：]([\s\S]*)$/.exec(command);
  if (!match) return {answer: '雲端基本待辦模式\n記錄：待辦事項\n查詢：請直接輸入「查詢」\nAI／搜尋／照片辨識需啟動電腦上的 Python bot。'};
  var content = match[1].trim();
  if (!content) return {answer: '請輸入要記錄的待辦事項。'};
  if (content.length > 300) return {answer: '待辦事項請縮短至 300 字以內。'};
  if (tasks.length >= 100) return {answer: '雲端待辦已達 100 筆上限，請先整理資料；本次未新增。'};
  return {answer: '已記錄：' + content + '。', content: content};
}

/** Safe editor-side check: no data write and no LINE message. */
function checkConfiguration() {
  var p = PropertiesService.getScriptProperties();
  if (!p.getProperty('LINE_CHANNEL_ACCESS_TOKEN') || !/^U[a-f0-9]{32}$/.test(p.getProperty('OWNER_ID') || '') ||
      !/^U[a-f0-9]{32}$/.test(p.getProperty('BOT_ID') || '') || !/^[a-f0-9]{64}$/.test(p.getProperty('WEBHOOK_KEY') || '')) {
    throw new Error('Missing or invalid private Script Properties.');
  }
  console.log('Private configuration is present. No data or credentials printed.');
}

/** Editor-side live connectivity check. No LINE send or Google data write. */
function testLocalRelay() {
  var p = PropertiesService.getScriptProperties();
  var base = p.getProperty('LOCAL_RELAY_BASE') || '';
  var key = p.getProperty('LOCAL_RELAY_KEY') || '';
  if (!/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(base) || !/^[a-f0-9]{64}$/.test(key)) {
    throw new Error('Private relay configuration is incomplete.');
  }
  var body = JSON.stringify({action: 'probe', destination: p.getProperty('BOT_ID'), events: []});
  var stamp = String(Math.floor(Date.now() / 1000));
  var signature = Utilities.base64Encode(Utilities.computeHmacSha256Signature(stamp + '\n' + body, key, Utilities.Charset.UTF_8));
  var r = UrlFetchApp.fetch(base + '/apps-script', {
    method: 'post', contentType: 'application/json; charset=utf-8', followRedirects: false,
    headers: {'x-relay-time': stamp, 'x-relay-signature': signature}, payload: Utilities.newBlob(body, 'application/json').getBytes(), muteHttpExceptions: true
  });
  if (r.getResponseCode() !== 200 || r.getContentText().trim() !== 'relay ready') {
    throw new Error('Local relay probe failed; HTTP ' + r.getResponseCode());
  }
  console.log('Authenticated Apps Script to local Python probe passed. No LINE message or Google data write.');
}

/** Synthetic relay diagnostic: invalid reply token cannot deliver a LINE message. */
function diagnoseLocalRelay() {
  var p = PropertiesService.getScriptProperties();
  var base = p.getProperty('LOCAL_RELAY_BASE');
  var h = UrlFetchApp.fetch(base + '/health', {followRedirects: false, muteHttpExceptions: true});
  console.log('Health HTTP: ' + h.getResponseCode() + '; body matches: ' + (h.getContentText().trim() === 'ok'));
  var event = {type: 'message', webhookEventId: 'synthetic-cloud-' + Utilities.getUuid(),
    replyToken: 'synthetic-invalid-reply-token', source: {type: 'user', userId: p.getProperty('OWNER_ID')},
    message: {type: 'text', id: 'synthetic', text: '用一句話解釋慣性'}};
  console.log('Synthetic relay result: ' + relayLocal_(event, p.getProperty('BOT_ID'), p));
}
