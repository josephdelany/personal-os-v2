// Stored backend answers only: no client-side metric calculations or model calls.
const escape = value => String(value).replace(/[&<>"']/g, c =>
  ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));

const evidenceLabels = {
  DESCRIPTIVE: 'A description of your recorded data, not an explanation of its cause.',
  INSUFFICIENT: 'There is not enough evidence to answer reliably.',
  CANDIDATE: 'An exploratory association. It has not been confirmed.',
  PROMOTED: 'A promising association that still needs confirmation.',
  CONFIRMED_OBSERVATIONAL: 'Supported by observational evidence; this does not establish cause.',
  EXPERIMENTAL: 'Evidence from an experiment; see the study details and limitations.'
};

export function renderAnswer(envelope) {
  const env = typeof envelope === 'string' ? JSON.parse(envelope) : envelope;
  if (!env || typeof env !== 'object' || Array.isArray(env)) throw new Error('Invalid answer');
  const answer = env.answer_text || env.refusal;
  if (typeof answer !== 'string' || !answer.trim()) throw new Error('Missing answer');
  let html = `<p>${escape(answer)}</p>`;
  if (env.tier) html += `<p class="evidence"><strong>${escape(env.tier)}</strong><br>${escape(evidenceLabels[env.tier] || 'Review the source details before interpreting this answer.')}</p>`;
  if (Array.isArray(env.range) && env.range.length===2)
    html += `<p class="muted">Records from ${escape(env.range[0])} to ${escape(env.range[1])}</p>`;
  if (env.as_of) html += `<p class="muted">As of ${escape(env.as_of)}</p>`;
  if (env.would_raise_it) html += `<p>${escape(env.would_raise_it)}</p>`;
  const result=env.result;
  if (result && typeof result==='object' && !Array.isArray(result)) {
    const labels={unit:'Unit',n:'Observations used',n_days:'Days in the requested period',
      last_day:'Latest recorded day',source:'Source',caveat:'Limitations',note:'About this result'};
    const fields=Object.entries(labels).filter(([key]) => result[key] !== undefined && result[key] !== null
      && ['string','number'].includes(typeof result[key]));
    if (fields.length) html+=`<dl>${fields.map(([key,label]) => `<dt>${label}</dt><dd>${escape(result[key])}</dd>`).join('')}</dl>`;
  }
  // Preserve units, coverage, source IDs and uncertainty from the stored envelope.
  html += `<details><summary>Data and sources behind this answer</summary><pre>${escape(JSON.stringify(env, null, 2))}</pre></details>`;
  return html;
}

export function mountAsk({form, input, date, button, output, rpc, timeoutMs = 30000}) {
  let generation = 0;
  let busy = false;
  const reset = () => {
    generation += 1;
    busy = false;
    button.disabled = false;
    output.innerHTML = '';
    input.value = '';
  };
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || busy) return;
    const request = ++generation;
    busy = true;
    button.disabled = true;
    output.textContent = 'Checking your recorded data…';
    let timer;
    try {
      const {data, error} = await Promise.race([
        rpc('ask', {p_question: question, p_as_of: date.value || null}),
        new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('timeout')), timeoutMs); })
      ]);
      if (request !== generation) return;
      if (error) throw new Error('Request failed');
      output.innerHTML = renderAnswer(data);
    } catch (error) {
      if (request === generation) output.textContent = error?.message === 'timeout'
        ? 'The answer is taking too long. Your question may still have been saved. You can try again; no retry was sent automatically.'
        : 'Your answer is unavailable. Check your connection and sign-in, then try again. This does not mean your records are empty.';
    } finally {
      clearTimeout(timer);
      if (request === generation) {
        busy = false;
        button.disabled = false;
      }
    }
  });
  return {reset};
}
