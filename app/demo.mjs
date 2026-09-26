// In-memory demo server for ?demo=1. Nothing leaves the browser tab and nothing is stored;
// the example rows are labeled fixtures, never personal data (RULE-01).
export function createDemoRpc() {
  const saved = [];
  const kinds = {save_v0_checkin: 'checkin', save_v0_meal: 'meal', save_v0_workout: 'workout',
    review_v0_card_row: 'card_review'};
  const current = kind => saved.filter(s => s.kind === kind &&
    !saved.some(o => o.request.supersedes === s.request.entry_id)).map(s => s.request);
  const reviewed = row => saved.some(s => s.kind === 'card_review' && s.request.row_id === row);
  function day(p_day) {
    const today = !p_day;
    return {
      day: p_day || new Date().toLocaleDateString('en-CA'),
      checkins: {entries: today ? current('checkin') : []},
      meals: {entries: today ? current('meal').map(e => ({...e, nutrition: {status: 'pending', items: []}})) : []},
      workouts: {entries: today ? current('workout') : []},
      health: today ? {daily_aggregates: [{metric: 'steps', label: 'Steps (demo)', value: 6400, unit: 'count', device: 'Demo watch'}],
        freshness: {last_received_at: new Date().toISOString()}} : {daily_aggregates: [], freshness: {}},
      spending: {accounts: today ? [{account_id: 'demo', entries: [
        {row_id: 'demo-a', description: 'Demo coffee', amount: -4.5, currency: 'USD',
          status: reviewed('demo-a') ? 'distinct' : 'needs_review', candidate_ids: ['demo-b']},
        {row_id: 'demo-b', description: 'Demo coffee', amount: -4.5, currency: 'USD', status: 'distinct'}]}] : []},
      visits: {entries: [], processing_status: 'missing'}
    };
  }
  return async (name, args) => {
    await new Promise(r => setTimeout(r, 150));
    if (name === 'get_v0_day') return {data: day(args?.p_day)};
    const kind = kinds[name];
    if (kind) {
      saved.push({kind, request: args.p_request});
      return {data: kind === 'card_review' ? {status: 'saved', decision_id: args.p_request.decision_id}
        : {status: 'saved', entry_id: args.p_request.entry_id}};
    }
    if (name === 'ask') return {data: {answer_text: 'Demo mode: Ask needs the real database.', tier: 'INSUFFICIENT'}};
    return {error: {message: 'demo'}};
  };
}
