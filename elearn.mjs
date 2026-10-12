import ical from 'node-ical';
import { randomBytes, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { dirname } from 'node:path';

const DAY = 86400000;
const HOME = 'https://elearn4.ndhu.edu.tw/moodle/calendar/view.php?view=upcoming';
const help = '指令：e學苑、同步e學苑、開啟提醒、關閉提醒。';
const dateFormat = new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const clean = value => String(value ?? '').replace(/[\r\n]+/g, ' ').slice(0, 250);

export function validateCalendarURL(value) {
  const url = new URL(value);
  if (url.origin !== 'https://elearn4.ndhu.edu.tw' || url.pathname !== '/moodle/calendar/export_execute.php' || url.username || url.password) throw Error('Invalid calendar URL');
  if (!url.searchParams.get('authtoken')) throw Error('Missing calendar token');
  return url.href;
}

export async function parseCalendar(text) {
  if (Buffer.byteLength(text) > 2 * 1024 * 1024 || !/^BEGIN:VCALENDAR\s*$/m.test(text) || !/^END:VCALENDAR\s*$/m.test(text)) throw Error('Invalid calendar response');
  const data = await ical.async.parseICS(text);
  return Object.values(data).filter(event => event.type === 'VEVENT' && event.status !== 'CANCELLED').map(event => {
    // Moodle assignment deadline events have DTSTART == DTEND. Preserve DTSTART
    // for other events rather than interpreting their ending time as a deadline.
    if (!(event.start instanceof Date) || !Number.isFinite(+event.start) || !event.uid || event.rrule) throw Error('Unsupported calendar event');
    return { uid: event.uid, title: clean(event.summary).slice(0, 180), course: clean((event.categories || []).join('、')).slice(0, 160), at: +event.start, allDay: event.datetype === 'date', link: HOME };
  }).sort((a, b) => a.at - b.at);
}

export function formatCalendar(events, now = Date.now(), title = '東華 e 學苑未來事件') {
  const upcoming = events.filter(event => event.at > now);
  if (!upcoming.length) return `${title}\n行事曆目前沒有未來事件。\n未列入行事曆的作業不會出現在這裡。`;
  const selected = upcoming.slice(0, 10);
  return `${title}（共 ${upcoming.length} 筆）\n\n` + selected.map((event, i) => `${i + 1}. ${event.title}\n${dateFormat.format(event.at)}${event.allDay ? '（全天事件）' : '（台灣時間）'}\n${event.course}`).join('\n\n')
    + `\n\n${HOME}\n依行事曆顯示，未確認繳交狀態。${upcoming.length > 10 ? '\n僅顯示最近 10 筆，完整內容請開啟行事曆。' : ''}`;
}

export function createElearn({ calendarURL, token, stateFile = './data/elearn.json', fetchImpl = fetch, now = Date.now, bindCode = randomBytes(6).toString('hex') }) {
  if (calendarURL) calendarURL = validateCalendarURL(calendarURL);
  const state = existsSync(stateFile) ? JSON.parse(readFileSync(stateFile, 'utf8')) : { ownerId: null, reminders: false, notices: {} };
  state.notices ||= {};
  const save = () => {
    mkdirSync(dirname(stateFile), { recursive: true });
    writeFileSync(stateFile + '.tmp', JSON.stringify(state), { mode: 0o600 });
    renameSync(stateFile + '.tmp', stateFile);
  };
  let cache = null, cacheAt = 0, loading = null, running = false;
  async function sync(force = false) {
    if (!calendarURL) throw Error('Calendar not configured');
    if (!force && cache && now() - cacheAt < 15 * 60000) return cache;
    if (loading) return loading;
    loading = (async () => {
      const response = await fetchImpl(calendarURL, { redirect: 'error', signal: AbortSignal.timeout(10000) });
      if (!response.ok) throw Error('Calendar fetch failed');
      if (Number(response.headers?.get('content-length')) > 2 * 1024 * 1024) throw Error('Calendar too large');
      const reader = response.body.getReader();
      const chunks = []; let size = 0;
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.length;
          if (size > 2 * 1024 * 1024) { await reader.cancel(); throw Error('Calendar too large'); }
          chunks.push(Buffer.from(value));
        }
      } finally { reader.releaseLock(); }
      const fresh = await parseCalendar(Buffer.concat(chunks).toString('utf8'));
      cache = fresh; cacheAt = now();
      return fresh;
    })();
    try { return await loading; } finally { loading = null; }
  }
  async function handle(command, event) {
    const binding = /^綁定e學苑\s+(\S+)$/i.exec(command);
    if (!binding && !['e學苑', 'E學苑', '同步e學苑', '開啟提醒', '關閉提醒'].includes(command)) return null;
    if (event.source?.type !== 'user' || !event.source.userId) return 'e學苑功能只在 LINE 個人聊天中使用。';
    const userId = event.source.userId;
    if (binding) {
      if (state.ownerId) return state.ownerId === userId ? `你已綁定 e學苑。${help}` : '此 e學苑已綁定其他使用者。';
      if (binding[1] !== bindCode) return '綁定碼不正確，請使用本機顯示的綁定碼。';
      if (!calendarURL) return '尚未設定 e學苑行事曆訂閱。';
      state.ownerId = userId; state.reminders = true; save();
      return '已綁定 e學苑並開啟提醒：每天上午 8 點摘要、事件前 24 小時內提醒一次。\n傳「e學苑」查看未來事件；傳「關閉提醒」停止推播。';
    }
    if (state.ownerId !== userId) return '尚未綁定此 LINE 帳號，請使用本機提供的綁定碼。';
    if (command === '關閉提醒' || command === '開啟提醒') {
      state.reminders = command === '開啟提醒'; save();
      return state.reminders ? '已開啟 e學苑提醒。' : '已關閉 e學苑推播，仍可傳「e學苑」查詢。';
    }
    try { return formatCalendar(await sync(command === '同步e學苑'), now()); }
    catch { return '暫時無法同步 e學苑，請稍後傳「同步e學苑」重試。若持續失敗，請重新取得行事曆訂閱網址。'; }
  }
  async function push(key, text) {
    if (state.notices[key]?.sent) return;
    state.notices[key] ||= { retryKey: randomUUID(), createdAt: now(), sent: false }; save();
    const notice = state.notices[key];
    // LINE retry keys are valid for 24 hours. Retain uncertain deliveries instead
    // of issuing a fresh key after that window and risking duplicate reminders.
    if (now() - notice.createdAt >= DAY) return;
    const response = await fetchImpl('https://api.line.me/v2/bot/message/push', {
      method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'X-Line-Retry-Key': notice.retryKey },
      body: JSON.stringify({ to: state.ownerId, messages: [{ type: 'text', text: text.slice(0, 4900) }] }), signal: AbortSignal.timeout(10000),
    });
    if (!response.ok && !(response.status === 409 && response.headers?.get('x-line-accepted-request-id'))) throw Error('LINE push failed');
    notice.sent = true; save();
  }
  async function tick() {
    if (running || !calendarURL || !state.ownerId || !state.reminders) return;
    running = true;
    try {
      const events = await sync(), current = now();
      const local = new Date(current + 8 * 3600000);
      const date = local.toISOString().slice(0, 10);
      if (local.getUTCHours() === 8) await push(`daily:${date}`, formatCalendar(events, current, '早安！e學苑待辦摘要'));
      for (const event of events.filter(e => !e.allDay && e.at > current && e.at - current <= DAY)) {
        await push(`due:${event.uid}:${event.at}`, formatCalendar([event], current, '提醒：這項事件將在 24 小時內到期'));
      }
    } catch { console.error('[e學苑] 同步或推播失敗，下次檢查重試。'); }
    finally { running = false; }
  }
  return { handle, sync, tick, bindCode: state.ownerId ? null : bindCode };
}
