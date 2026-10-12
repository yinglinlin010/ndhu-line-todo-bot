export function searchReply(answer, results) {
  const bubbles = results.slice(0, 3).map((result, index) => {
    const hostname = new URL(result.url).hostname;
    return {
      type: 'bubble', size: 'kilo',
      body: { type: 'box', layout: 'vertical', spacing: 'sm', contents: [
        { type: 'text', text: `[${index + 1}] ${result.title || hostname}`, weight: 'bold', size: 'sm', wrap: true, maxLines: 3 },
        { type: 'text', text: hostname, size: 'xs', color: '#777777', wrap: true },
        ...(result.published ? [{ type: 'text', text: new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', dateStyle: 'short' }).format(new Date(result.published)), size: 'xs', color: '#777777' }] : []),
        ...(result.snippet ? [{ type: 'text', text: result.snippet.slice(0, 100), size: 'xs', wrap: true, maxLines: 3 }] : []),
      ] },
      footer: { type: 'box', layout: 'vertical', contents: [{ type: 'button', style: 'link', height: 'sm', action: { type: 'uri', label: '查看來源', uri: result.url } }] },
    };
  });
  return [{ type: 'text', text: answer.replace(/https?:\/\/\S+/g, '').slice(0, 4000) }, { type: 'flex', altText: '搜尋結果：' + results.map(r => r.title).join('、').slice(0, 300), contents: { type: 'carousel', contents: bubbles } }];
}
