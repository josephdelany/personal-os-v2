"""Offline real-browser acceptance for the daily page. Run directly; no network or personal data.

Uses an installed Playwright and Chrome. Fixtures live in intercepted responses and never
touch a database. This does not prove production auth, RPC deployment or real-account saves.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp/personal-os-daily-mobile.png')
STUB = '''
const saved = JSON.parse(sessionStorage.getItem('fixtureSaved') || '[]');
const persist = () => sessionStorage.setItem('fixtureSaved', JSON.stringify(saved));
function day(p_day) {
  const pick = kind => ({entries: saved.filter(s => s.kind === kind && !saved.some(o => o.request.supersedes === s.request.entry_id)).map(s => s.request)});
  return {day: p_day || '2026-09-25', checkins: pick('checkin'), meals: {entries: pick('meal').entries.map(e => ({...e, nutrition: {status: 'pending', items: []}}))},
    workouts: pick('workout'),
    health: {daily_aggregates: p_day ? [] : [{metric: 'steps', label: 'Steps', value: 8123, unit: 'count', device: 'Watch'}],
      freshness: {last_received_at: p_day ? null : '2026-09-25T06:00:00-04:00'}},
    spending: {accounts: p_day ? [] : [{account_id: 'acct', entries: [
      {row_id: 'row-a', description: 'Fixture cafe', amount: -4.5, currency: 'USD',
       status: saved.some(s => s.kind === 'card_review' && s.request.row_id === 'row-a') ? 'distinct' : 'needs_review', candidate_ids: ['row-b']},
      {row_id: 'row-b', description: 'Fixture cafe', amount: -4.5, currency: 'USD', status: 'distinct'}]}]}, visits: {entries: [], processing_status: 'missing'}};
}
export function createClient() {
  let listener;
  return {
    auth: {
      getSession: async () => ({data: {session: sessionStorage.getItem('fixtureSignedIn') ? {} : null}}),
      onAuthStateChange: fn => { listener = fn; window.signInFixture = () => { sessionStorage.setItem('fixtureSignedIn', '1'); fn('SIGNED_IN', {}); }; },
      signOut: async () => { sessionStorage.removeItem('fixtureSignedIn'); listener('SIGNED_OUT', null); },
      signInWithOtp: async args => { window.signInRequest = args; return {error: null}; }
    },
    rpc: async (name, args) => {
      window.calls = JSON.parse(sessionStorage.getItem('fixtureCalls') || '[]').concat([{name, args}]);
      sessionStorage.setItem('fixtureCalls', JSON.stringify(window.calls));
      if (name === 'get_v0_day') return {data: day(args.p_day)};
      const kind = {save_v0_checkin: 'checkin', save_v0_meal: 'meal', save_v0_workout: 'workout', review_v0_card_row: 'card_review'}[name];
      if (kind) {
        if (window.dropNextSave) { window.dropNextSave = false; throw new Error('fixture network loss'); }
        saved.push({kind, request: args.p_request}); persist();
        return {data: kind === 'card_review' ? {status: 'saved', decision_id: args.p_request.decision_id}
          : {status: 'saved', entry_id: args.p_request.entry_id}};
      }
      return {error: {message: 'fixture unavailable'}};
    }
  };
}
'''


def main():
    from playwright.sync_api import sync_playwright, Error

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': 390, 'height': 844}, offline=True, service_workers='block')
        blocked, errors = [], []

        def route(request):
            url = request.request.url
            files = {'': ('index.html', 'text/html'), 'ask.mjs': ('ask.mjs', 'text/javascript'),
                     'daily.mjs': ('daily.mjs', 'text/javascript'), 'v0_client.mjs': ('v0_client.mjs', 'text/javascript'),
                     'manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json'),
                     'apple-touch-icon.png': ('apple-touch-icon.png', 'image/png'),
                     'icon-192.png': ('icon-192.png', 'image/png'), 'demo.mjs': ('demo.mjs', 'text/javascript'), 'icon-512.png': ('icon-512.png', 'image/png')}
            path = url[len('https://fixture.invalid/'):].split('?')[0]
            if url.startswith('https://fixture.invalid/') and path in files:
                name, kind = files[path]
                request.fulfill(body=(ROOT / 'app' / name).read_bytes(), content_type=kind)
            elif url == 'https://esm.sh/@supabase/supabase-js@2':
                request.fulfill(body=STUB, content_type='text/javascript')
            else:
                blocked.append(url)
                request.abort()

        context.route('**/*', route)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('https://fixture.invalid/')
        page.wait_for_function('typeof window.signInFixture === "function"')
        # ADR-0163/0174 refusal cases: fetch, navigation and a popup's first request all abort.
        assert page.evaluate("fetch('https://blocked.invalid/resource').then(()=>false,()=>true)")
        probe = context.new_page()
        try:
            probe.goto('https://blocked.invalid/navigation')
        except Error:
            pass
        else:
            raise AssertionError('unexpected external navigation')
        probe.close()
        with context.expect_page() as popup_event:
            page.evaluate("window.open('https://blocked.invalid/popup')")
        popup = popup_event.value
        try:
            popup.wait_for_load_state()
        except Error:
            pass
        popup.close()
        assert set(blocked) == {'https://blocked.invalid/resource', 'https://blocked.invalid/navigation',
                                'https://blocked.invalid/popup'}, blocked
        blocked.clear()
        assert context.cookies() == []
        assert not page.locator('#tabs').is_visible()
        manifest = page.evaluate("fetch(document.querySelector('link[rel=manifest]').href).then(r => r.json())")
        assert manifest['display'] == 'standalone' and manifest['start_url'] == './'
        assert page.evaluate("fetch('apple-touch-icon.png').then(r => r.ok)")
        page.locator('#email').fill('owner@example.invalid')
        page.locator('#sendlink').click()
        page.get_by_text('Check your inbox', exact=False).wait_for()
        assert page.evaluate('window.signInRequest.options.shouldCreateUser') is False
        page.evaluate('window.signInFixture()')

        # Today: stored values shown, empty domains labeled missing (not zero).
        page.get_by_text('No check-in logged.', exact=True).wait_for()
        today = page.locator('#today-view').inner_text()
        assert '8123' in today and 'No meals logged.' in today and 'No location data' in today

        # Add a morning check-in; a missing rating is refused client-side.
        page.locator('#tab-add').click()
        page.locator('#ci-period').select_option('morning')
        page.locator('.rating[data-key="sleep_quality"] button[data-v="7"]').click()
        page.locator('#form-checkin button[type=submit]').click()
        page.get_by_text('Choose a energy rating', exact=False).wait_for()
        page.locator('.rating[data-key="energy"] button[data-v="6"]').click()
        page.locator('#form-checkin button[type=submit]').click()
        page.get_by_text('Saved.', exact=True).wait_for()

        # Meal whose first send is lost: kept as unconfirmed, survives reload, retried identically.
        page.locator('[data-add="meal"]').click()
        page.locator('#meal-text').fill('Fixture meal, not personal data')
        page.evaluate('window.dropNextSave = true')
        page.locator('#form-meal button[type=submit]').click()
        page.get_by_text('Not confirmed.', exact=False).wait_for()
        assert page.locator('#pending').is_visible()
        first = page.evaluate("window.calls.filter(c => c.name === 'save_v0_meal')[0].args.p_request")
        page.reload()
        page.locator('#pending [data-retry]').wait_for()
        page.locator('#pending [data-retry]').click()
        page.get_by_text('Saved.', exact=True).wait_for()
        retried = page.evaluate("window.calls.filter(c => c.name === 'save_v0_meal').at(-1).args.p_request")
        assert retried == first, (retried, first)
        assert not page.locator('#pending').is_visible()

        # Workout set, then Today shows all three.
        page.locator('#tab-add').click()
        page.locator('[data-add="workout"]').click()
        page.locator('#wo-exercise').fill('Squat')
        page.locator('#wo-load').fill('185')
        page.locator('#wo-reps').fill('5')
        page.locator('#form-workout button[type=submit]').click()
        page.get_by_text('Saved.', exact=True).wait_for()
        page.locator('#tab-today').click()
        page.get_by_text('Squat', exact=False).wait_for()
        today = page.locator('#today-view').inner_text()
        assert 'sleep quality 7' in today and 'Fixture meal' in today and 'Nutrition not processed' in today

        # Correction: new identity, supersedes the original, original occurrence time kept.
        page.locator('#today-view [data-edit="checkin"]').click()
        assert page.locator('#editing').is_visible()
        page.locator('.rating[data-key="energy"] button[data-v="8"]').click()
        page.locator('#form-checkin button[type=submit]').click()
        page.get_by_text('Saved.', exact=True).wait_for()
        saves = page.evaluate("window.calls.filter(c => c.name === 'save_v0_checkin').map(c => c.args.p_request)")
        assert saves[-1]['supersedes'] == saves[0]['entry_id'] and saves[-1]['entry_id'] != saves[0]['entry_id']
        assert saves[-1]['occurred_at'] == saves[0]['occurred_at'] and saves[-1]['ratings']['energy'] == 8
        page.locator('#tab-today').click()
        page.wait_for_function("document.getElementById('today-view').innerText.includes('energy 8/10')")
        assert 'energy 6' not in page.locator('#today-view').inner_text()

        # Ambiguous card row: owner marks it separate; review request carries its own identity.
        page.locator('#today-view [data-review="distinct"][data-row="row-a"]').click()
        page.get_by_text('Saved.', exact=True).wait_for()
        review = page.evaluate("window.calls.filter(c => c.name === 'review_v0_card_row').at(-1).args.p_request")
        assert review['row_id'] == 'row-a' and review['action'] == 'distinct' and review['target_id'] is None
        page.wait_for_function("!document.querySelector('#today-view [data-row=\"row-a\"]')")

        # History of another day.
        page.locator('#tab-history').click()
        page.locator('#history-date').fill('2026-09-20')
        page.get_by_text('2026-09-20', exact=True).wait_for()
        assert 'No health data for this day.' in page.locator('#history-view').inner_text()

        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#tab-today').click()
        page.wait_for_function("document.getElementById('today-view').innerText.includes('energy 8/10')")
        page.evaluate("document.querySelector('main').insertAdjacentHTML('afterbegin','<p class=\"small muted\">OFFLINE TEST FIXTURES — NOT PERSONAL DATA</p>')")
        page.screenshot(path=str(SHOT), full_page=True)
        page.locator('#signout').click()
        assert page.locator('#auth').is_visible() and not page.locator('#tabs').is_visible()

        # Demo mode: no sign-in, no Supabase client, saves stay in memory and vanish on reload.
        calls_before = page.evaluate("JSON.parse(sessionStorage.getItem('fixtureCalls') || '[]').length")
        page.goto('https://fixture.invalid/?demo=1')
        page.get_by_text('Demo mode.', exact=False).wait_for()
        page.get_by_text('Steps (demo)', exact=True).wait_for()
        page.locator('#tab-add').click()
        page.locator('.rating[data-key="sleep_quality"] button[data-v="5"]').click()
        page.locator('.rating[data-key="energy"] button[data-v="5"]').click()
        page.locator('#ci-period').select_option('morning')
        page.locator('.rating[data-key="sleep_quality"] button[data-v="5"]').click()
        page.locator('.rating[data-key="energy"] button[data-v="5"]').click()
        page.locator('#form-checkin button[type=submit]').click()
        page.get_by_text('Saved.', exact=True).wait_for()
        page.locator('#tab-today').click()
        page.wait_for_function("document.getElementById('today-view').innerText.includes('energy 5/10')")
        assert page.evaluate("JSON.parse(sessionStorage.getItem('fixtureCalls') || '[]').length") == calls_before
        assert page.evaluate("localStorage.getItem('personal-os.pending.v1')") in (None, '[]')
        page.reload()
        page.get_by_text('No check-in logged.', exact=True).wait_for()
        assert not blocked, blocked
        assert not errors, errors
        context.close()
        browser.close()
    print('PASS: daily sign-in, Today, Add check-in/meal/set, unconfirmed save kept across reload and retried '
          'identically, correction supersedes, History, no horizontal scroll; offline fixtures only')


if __name__ == '__main__':
    main()
