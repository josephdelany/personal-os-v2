"""Offline real-browser acceptance. Run directly; no network or personal data.

Uses an installed Playwright and Chrome. Fixtures remain in intercepted browser
responses and never touch a database. This does not prove production auth or RPCs.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
STUB = '''
export function createClient() {
  let listener;
  return {
    auth: {
      getSession: async () => ({data:{session:null}}),
      onAuthStateChange: fn => { listener=fn; window.signInFixture=()=>fn('SIGNED_IN',{}); },
      signOut: async () => listener('SIGNED_OUT',null),
      signInWithOtp: async args => {window.signInRequest=args; return {error:null};}
    },
    rpc: async (name,args) => {
      if(name==='get_day') return {data:{day:'fixture day'}};
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
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width':390,'height':844})
        errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        def route(request):
            url=request.request.url
            if url=='https://fixture.invalid/':
                request.fulfill(body=(ROOT/'app/index.html').read_text(),content_type='text/html')
            elif url=='https://fixture.invalid/ask.mjs':
                request.fulfill(body=(ROOT/'app/ask.mjs').read_text(),content_type='text/javascript')
            elif url.startswith('https://esm.sh/'):
                request.fulfill(body=STUB,content_type='text/javascript')
            else:
                request.abort()
        page.route('**/*',route)
        page.goto('https://fixture.invalid/')
        page.wait_for_function('typeof window.signInFixture === "function"')
        assert not page.locator('#ask-panel').is_visible()
        page.locator('#email').fill('owner@example.invalid')
        page.locator('#sendlink').click()
        page.get_by_text('Check your inbox for the sign-in link.',exact=False).wait_for()
        assert page.evaluate('window.signInRequest.options.shouldCreateUser') is False
        assert page.locator('#sendlink').is_enabled()
        page.evaluate('window.signInFixture()')
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
        page.locator('#signout').click()
        assert not page.locator('#ask-panel').is_visible()
        assert not page.locator('#app').is_visible()
        assert page.locator('#question').input_value()==''
        assert not errors,errors
        browser.close()
    print('PASS: mobile browser sign-in state, Ask, evidence, failure recovery, sign-out; offline fixtures only')


if __name__=='__main__':
    main()
