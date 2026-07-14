import dotenv from 'dotenv';
dotenv.config({ override: true });
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
const { callSitecore } = await import('../../src/sitecore/restClient.js');

const raw = await callSitecore({
  method: 'GET',
  path: '/sitecore/api/ssc/item/',
  query: {
    path: '/sitecore/content/EDS/ContentPublisherPhase2/CADescovy/Home/LivdelziApril7-1',
    database: 'master',
    includeStandardTemplateFields: 'true',
  },
});
const item = JSON.parse(raw).data;
console.log('content fields:', Object.keys(item).filter((k) => !k.startsWith('__')).join(', '));

const layout = item['__Final Renderings'] || item['__Renderings'] || '';
console.log('layout XML length:', layout.length);

const ids = [...new Set([...layout.matchAll(/ds="\{?([0-9A-Fa-f-]{36})\}?"/g)].map((m) => m[1]))];
console.log('datasource refs:', ids.length);
for (const id of ids.slice(0, 20)) {
  const r = JSON.parse(await callSitecore({ method: 'GET', path: `/sitecore/api/ssc/item/${id}`, query: { database: 'master' } }));
  console.log(' -', id, '->', r.status, r.data?.ItemName || '', '|', r.data?.ItemPath || '');
}
