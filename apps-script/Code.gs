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
  var owner = properties.getProperty('OWNER_ID');
  var bot = properties.getProperty('BOT_ID');
  var token = properties.getProperty('LINE_CHANNEL_ACCESS_TOKEN');
  if (!owner || !bot || !token || body.destination !== bot || !Array.isArray(body.events)) {
    return HtmlService.createHtmlOutput('ok');
  }
  body.events.slice(0, 10).forEach(function (event) {
    if (event.type !== 'message' || !event.source || event.source.type !== 'user' ||
        event.source.userId !== owner || !event.message || event.message.type !== 'text' ||
        typeof event.message.text !== 'string' || !/^[a-f0-9]{32}$/.test(event.replyToken || '')) return;
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
      try {
        var response = UrlFetchApp.fetch('https://api.line.me/v2/bot/message/reply', {
          method: 'post', contentType: 'application/json',
          headers: {Authorization: 'Bearer ' + token},
          payload: JSON.stringify({replyToken: event.replyToken, messages: [{type: 'text', text: answer}]}),
          muteHttpExceptions: true
        });
        console.log('LINE reply status: ' + response.getResponseCode());
      } catch (_) { console.log('LINE reply could not be confirmed.'); }
    }
  });
  return HtmlService.createHtmlOutput('ok');
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
