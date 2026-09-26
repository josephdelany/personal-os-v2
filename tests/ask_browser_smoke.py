"""Offline real-browser acceptance. Run directly; no network or personal data.

Uses an installed Playwright and Chrome. Fixtures remain in intercepted browser
responses and never touch a database. This does not prove production auth or RPCs.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUB = '''
export function createClient() {
  let listener;
  return {
    auth: {
      getSession: async () => ({data:{session:null}}),
      onAuthStateChange: fn => { listener=fn; window.signInFixture=()=>fn('SIGNED_IN',{});
        window.refreshFixture=()=>fn('TOKEN_REFRESHED',{}); },
      signOut: async () => listener('SIGNED_OUT',null),
      signInWithOtp: async args => {window.signInRequest=args; return {error:null};}
    },
    rpc: async (name,args) => {
      if(name==='get_trust') {
        if(window.failStatus) throw new Error('fixture unavailable');
        return {data:{coverage_blindspots:[{metric:'steps',last_day:'2026-08-21'}],
          job_heartbeats:[{job:'import',status:'success',last:'2026-09-24'}]}};
      }
      if(name==='get_timeline') {
        window.timelineArgs=args;
        return new Promise(resolve => {window.finishTimeline=(entries=[])=>resolve({data:{day:args.p_day,n:entries.length,entries}});});
      }
      if(name==='get_day') return {data:{day:'fixture day',coverage:window.fixtureCoverage}};
      if(name==='ask') {
        window.lastQuestion=args;
        if(args.p_question==='fail') throw new Error('fixture network failure');
        return {data:{answer_text:'Fixture answer, not personal data.',tier:'INSUFFICIENT',
          would_raise_it:'Record observations.',result:{unit:'h',value:null}}};
      }
      return {error:{message:'fixture unavailable'}};
    }
  };
}
'''


def main():
    from playwright.sync_api import sync_playwright, Error

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width':390,'height':844},
                                      offline=True, service_workers='block')
        assert context.cookies()==[]
        blocked=[]
        errors=[]
        def route(request):
            url=request.request.url
            if url=='https://fixture.invalid/':
                request.fulfill(body=(ROOT/'app/explore.html').read_text(),content_type='text/html')
            elif url=='https://fixture.invalid/ask.mjs':
                request.fulfill(body=(ROOT/'app/ask.mjs').read_text(),content_type='text/javascript')
            elif url=='https://fixture.invalid/data-status.mjs':
                request.fulfill(body=(ROOT/'app/data-status.mjs').read_text(),content_type='text/javascript')
            elif url=='https://esm.sh/@supabase/supabase-js@2':
                request.fulfill(body=STUB,content_type='text/javascript')
            else:
                blocked.append(url)
                request.abort()
        context.route('**/*',route)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('https://fixture.invalid/')
        page.wait_for_function('typeof window.signInFixture === "function"')
        # Exercise refusals through the real browser, including a popup's first
        # request (page-only routing would miss it). Reserved invalid hosts only.
        assert page.evaluate("fetch('https://blocked.invalid/resource').then(()=>false,()=>true)")
        probe=context.new_page()
        try:
            probe.goto('https://blocked.invalid/navigation')
        except Error:
            pass
        else:
            raise AssertionError('unexpected external navigation')
        probe.close()
        with context.expect_page() as popup_event:
            page.evaluate("window.open('https://blocked.invalid/popup')")
        popup=popup_event.value
        try:
            popup.wait_for_load_state()
        except Error:
            pass
        popup.close()
        assert set(blocked)=={'https://blocked.invalid/resource',
                              'https://blocked.invalid/navigation','https://blocked.invalid/popup'}
        assert not page.locator('#ask-panel').is_visible()
        page.locator('#email').fill('owner@example.invalid')
        page.locator('#sendlink').click()
        page.get_by_text('Check your inbox for the sign-in link.',exact=False).wait_for()
        assert page.evaluate('window.signInRequest.options.shouldCreateUser') is False
        assert page.locator('#sendlink').is_enabled()
        page.evaluate('window.signInFixture()')
        page.get_by_role('button',name='How is my sleep?',exact=True).click()
        assert page.locator('#question').input_value()=='how is my sleep'
        assert page.evaluate('window.lastQuestion === undefined')
        page.locator('#question').fill('how is my sleep')
        page.locator('#ask-submit').click()
        page.get_by_text('Fixture answer, not personal data.',exact=True).wait_for()
        assert page.evaluate('window.lastQuestion.p_as_of') is None
        assert page.locator('#ask-answer').inner_text().count('INSUFFICIENT')>=1
        page.locator('#ask-answer summary').click()
        assert '"value": null' in page.locator('#ask-answer pre').inner_text()
        page.locator('#question').fill('fail')
        page.locator('#ask-submit').click()
        page.get_by_text('Your answer is unavailable.',exact=False).wait_for()
        assert page.locator('#ask-submit').is_enabled()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#tab-trust').click()
        page.get_by_text('latest recorded day: 2026-08-21',exact=False).wait_for()
        assert page.locator('#app').inner_text().count('2026-08-21')==1
        assert 'not proof that new observations arrived' in page.locator('#app').inner_text()
        page.evaluate('window.failStatus=true')
        page.locator('#tab-trust').click()
        page.locator('#retry-view').wait_for()
        assert 'does not mean they are empty' in page.locator('#app').inner_text()
        page.evaluate('window.failStatus=false')
        page.locator('#retry-view').click()
        page.get_by_text('latest recorded day: 2026-08-21',exact=False).wait_for()
        page.locator('#day').fill('2026-08-21')
        page.locator('#tab-timeline').click()
        page.wait_for_function('typeof window.finishTimeline === "function"')
        assert page.evaluate('window.timelineArgs.p_day')=='2026-08-21'
        page.locator('#tab-trust').click()
        page.get_by_text('latest recorded day: 2026-08-21',exact=False).wait_for()
        page.evaluate('window.finishTimeline()')
        page.wait_for_timeout(50)
        assert page.locator('#tab-trust').get_attribute('aria-current')=='page'
        assert page.locator('#app').get_by_role('heading',name='Data status',exact=True).is_visible()
        page.evaluate('delete window.finishTimeline')
        page.locator('#tab-timeline').click()
        page.wait_for_function('typeof window.finishTimeline === "function"')
        page.evaluate("window.finishTimeline([{at:'08:30',kind:'note',text:'Browser fixture — not personal history'}])")
        page.get_by_text('Browser fixture — not personal history',exact=False).wait_for()
        assert '2026-08-21' in page.locator('#app').inner_text()
        page.evaluate('delete window.finishTimeline')
        page.locator('#tab-timeline').click()
        page.wait_for_function('typeof window.finishTimeline === "function"')
        page.evaluate('window.finishTimeline()')
        page.get_by_text('nothing recorded this day',exact=True).wait_for()
        page.locator('#load').click()
        page.get_by_text('Count unavailable captured',exact=False).wait_for()
        assert '0 captured' not in page.locator('#app').inner_text()
        page.evaluate('window.fixtureCoverage={captures:0,atoms:0}')
        page.locator('#load').click()
        page.get_by_text('0 captured · 0 facts',exact=False).wait_for()
        page.locator('#tab-trust').click()
        page.get_by_text('latest recorded day: 2026-08-21',exact=False).wait_for()
        page.evaluate('window.refreshFixture()')
        page.wait_for_timeout(50)
        assert page.locator('#app').get_by_role('heading',name='Data status',exact=True).is_visible()
        page.evaluate("document.body.insertAdjacentHTML('afterbegin','<p>OFFLINE TEST FIXTURES — NOT PERSONAL DATA</p>')")
        page.screenshot(path='/tmp/personal-os-usability-mobile.png',full_page=True)
        page.locator('#signout').click()
        assert not page.locator('#ask-panel').is_visible()
        assert not page.locator('#app').is_visible()
        assert page.locator('#question').input_value()==''
        assert not errors,errors
        context.close()
        browser.close()
    print('PASS: mobile browser sign-in state, Ask, evidence, failure recovery, sign-out; offline fixtures only')


if __name__=='__main__':
    main()
