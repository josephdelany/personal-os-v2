const escape = value => String(value).replace(/[&<>"']/g,c=>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function renderDataStatus(data) {
  const env=typeof data==='string'?JSON.parse(data):data;
  if (!env || typeof env!=='object' || Array.isArray(env)) throw new Error('Invalid data status');
  const gaps=Array.isArray(env.coverage_blindspots)?env.coverage_blindspots:[];
  let html='<h2>Data status</h2><p>Recent answers depend on recent records. You can still browse older dates when a source has stopped updating.</p>';
  html+='<h2>Older records reported by the backend</h2>';
  html+=gaps.length?'<ul>'+gaps.map(g=>`<li><strong>${escape(g.metric)}</strong> — latest recorded day: ${escape(g.last_day ?? 'not available')}</li>`).join('')+'</ul>'
    :'<p>No older-record warnings were returned. This does not establish that every source is connected or up to date.</p>';
  html+='<p class="muted">These checks cover selected metrics. An unlisted source may still be missing.</p><h2>Processing activity</h2><p class="muted">A successful job is not proof that new observations arrived.</p>';
  const jobs=Array.isArray(env.job_heartbeats)?env.job_heartbeats:[];
  html+=jobs.length?'<ul>'+jobs.map(j=>`<li>${escape(j.job)} — ${escape(j.status ?? 'status unavailable')}<br><span class="muted">Last run: ${escape(j.last ?? 'not available')}</span></li>`).join('')+'</ul>'
    :'<p>No processing activity was returned.</p>';
  return html;
}
