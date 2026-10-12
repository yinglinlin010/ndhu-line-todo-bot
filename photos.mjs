import { load } from 'cheerio';
import sharp from 'sharp';
import ipaddr from 'ipaddr.js';
import { lookup } from 'node:dns/promises';
import { get } from 'node:https';
import { randomBytes } from 'node:crypto';
import { mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

export const publicIP = address => { try { return ipaddr.process(address).range() === 'unicast'; } catch { return false; } };

// Resolve and pin public addresses for each redirect. Never use browser cookies
// or fetch arbitrary URLs from the computer's private network.
export async function getPublic(url, { maxBytes = 3 * 1024 * 1024, signal, redirects = 3 } = {}) {
  url = new URL(url);
  if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443')) throw Error('Invalid public URL');
  const addresses = await lookup(url.hostname, { all: true });
  if (!addresses.length || addresses.some(a => !publicIP(a.address))) throw Error('Private address');
  const address = addresses[0];
  return new Promise((resolve, reject) => {
    const request = get(url, { signal, headers: { 'User-Agent': 'Mozilla/5.0', Accept: '*/*' }, lookup: (_hostname, options, callback) => options.all ? callback(null, [address]) : callback(null, address.address, address.family) }, response => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
        response.resume();
        if (!redirects || !response.headers.location) return reject(Error('Too many redirects'));
        getPublic(new URL(response.headers.location, url), { maxBytes, signal, redirects: redirects - 1 }).then(resolve, reject); return;
      }
      if (response.statusCode !== 200) { response.resume(); return reject(Error('Download failed')); }
      const chunks = []; let size = 0;
      response.on('data', chunk => { size += chunk.length; if (size > maxBytes) request.destroy(Error('Download too large')); else chunks.push(chunk); });
      response.on('error', reject);
      response.on('end', () => resolve({ body: Buffer.concat(chunks), type: response.headers['content-type'] || '', url: url.href }));
    });
    request.on('error', reject);
  });
}

export function photoSubject(raw, previous = '') {
  if (!/照片|圖片|相片|圖像/.test(raw) || /生成|畫一|畫個|繪製|辨識|分析圖片/.test(raw)) return null;
  let topic = raw.replace(/^(可以|能不能|請|麻煩|幫我|給我|傳給我|傳我|找一下|找|看看|看|我想看|我想要|我要|有沒有|來一張|來幾張|一張|幾張|張|的|一下|傳|送|我)+/g, '')
    .replace(/(?:的)?(?:照片|圖片|相片|圖像).*$/, '').trim();
  if (!topic || /^(他|她|它|這個|那個)$/.test(topic)) topic = previous.replace(/[？?！!]/g, '').replace(/的?(評價|介紹|資料|消息).*$/, '').trim();
  return topic;
}

export function imageCandidates(html, pageURL, subject) {
  const $ = load(html);
  const candidates = [];
  const add = (value, label, priority = 0) => {
    if (!value) return;
    try {
      const url = new URL(value, pageURL);
      if (url.protocol === 'https:' && !/logo|icon|banner|favicon|\.svg(?:\?|$)/i.test(url.pathname)) candidates.push({ url: url.href, label, priority });
    } catch { /* Ignore malformed image attributes. */ }
  };
  add($('meta[property="og:image"]').attr('content'), $('title').text(), 2);
  $('main img, article img, #page img, .mcont img, img').each((_i, element) => {
    const img = $(element), label = img.attr('alt') || img.attr('title') || '';
    add(img.attr('data-src') || img.attr('src'), label, label.includes(subject) ? 5 : 1);
  });
  return [...new Map(candidates.sort((a, b) => b.priority - a.priority).map(c => [c.url, c])).values()].slice(0, 8);
}

export function createPhotos({ publicBaseURL, cacheDir = './data/photos', download = getPublic } = {}) {
  if (publicBaseURL && new URL(publicBaseURL).protocol !== 'https:') throw Error('Photo base URL must use HTTPS');
  const memo = new Map();
  async function handle(raw, previous = '') {
    const subject = photoSubject(raw, previous);
    if (subject === null) return null;
    if (!subject) return '你想看誰或哪個地方的照片？直接說名稱就可以。';
    if (!publicBaseURL) return '圖片傳送連線還沒準備好，我先保留文字搜尋功能。';
    if (memo.has(subject)) return memo.get(subject);
    const signal = AbortSignal.timeout(25000);
    try {
      const search = new URL('https://lite.duckduckgo.com/lite/'); search.searchParams.set('q', subject + ' 照片');
      const html = (await download(search.href, { signal })).body.toString('utf8');
      const $ = load(html);
      const pages = $('.result-link').toArray().slice(0, 3).map(e => {
        const href = new URL($(e).attr('href'), 'https://duckduckgo.com');
        return { url: href.searchParams.get('uddg') || href.href, title: $(e).text() };
      });
      const name = /大學\s*([\u4e00-\u9fff]{2,4})(?:老師|教授)/.exec(subject)?.[1];
      for (const page of pages) {
        if (name && !page.title.includes(name)) continue;
        try {
          const response = await download(page.url, { signal });
          const pageHTML = response.body.toString('utf8');
          if (name && !load(pageHTML)('title').text().includes(name)) continue;
          for (const candidate of imageCandidates(pageHTML, response.url || page.url, name || subject)) {
            try {
              const image = await download(candidate.url, { signal, maxBytes: 5 * 1024 * 1024 });
              const pipeline = sharp(image.body, { limitInputPixels: 20000000 });
              const info = await pipeline.metadata();
              if (!['jpeg', 'png', 'webp', 'avif'].includes(info.format) || info.width < 100 || info.height < 100) continue;
              mkdirSync(cacheDir, { recursive: true });
              if (readdirSync(cacheDir).length >= 400) throw Error('Photo cache full');
              const id = randomBytes(16).toString('hex');
              const original = await pipeline.clone().rotate().resize({ width: 1280, height: 1280, fit: 'inside', withoutEnlargement: true }).jpeg({ quality: 82 }).toBuffer();
              const preview = await pipeline.clone().rotate().resize({ width: 320, height: 320, fit: 'inside', withoutEnlargement: true }).jpeg({ quality: 75 }).toBuffer();
              writeFileSync(join(cacheDir, id + '.jpg'), original, { mode: 0o600 });
              writeFileSync(join(cacheDir, id + '-preview.jpg'), preview, { mode: 0o600 });
              const base = publicBaseURL.replace(/\/$/, '');
              const messages = [{ type: 'text', text: `找到與「${subject}」相關的照片。\n來源：${page.title}\n${page.url}`.slice(0, 2000) }, { type: 'image', originalContentUrl: `${base}/photos/${id}.jpg`, previewImageUrl: `${base}/photos/${id}-preview.jpg` }];
              if (memo.size >= 100) memo.delete(memo.keys().next().value);
              memo.set(subject, messages); return messages;
            } catch { if (signal.aborted) throw Error('Timed out'); }
          }
        } catch { if (signal.aborted) break; }
      }
      return `這次沒找到能傳送的「${subject}」照片。你可以補充地點或全名，我再找一次。`;
    } catch { return '圖片搜尋暫時沒成功，請稍後再試。'; }
  }
  function serve(req, res) {
    const match = /^\/photos\/([a-f0-9]{32}(?:-preview)?\.jpg)$/.exec(req.url);
    if (!match || req.method !== 'GET') return false;
    const file = join(cacheDir, match[1]);
    if (!existsSync(file)) { res.writeHead(404); res.end('not found'); return true; }
    res.writeHead(200, { 'Content-Type': 'image/jpeg', 'Cache-Control': 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff' }); res.end(readFileSync(file)); return true;
  }
  return { handle, serve, subject: photoSubject };
}
