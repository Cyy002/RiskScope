// GUI input only; observe responses to those browser requests for diagnostics.
const { chromium } = require('/tmp/riskscope_pw_test/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const out = __dirname;
const creds = JSON.parse(fs.readFileSync('/tmp/riskscope_pw_test/.codex_m114_test_credentials.json', 'utf8'));
const results = [];
let browser;

async function runCase(page, label, message, expected) {
  await page.locator('#chat-message').fill(message);
  const responsePromise = page.waitForResponse(r =>
    r.url().endsWith('/chat') && r.request().method() === 'POST', { timeout: 165000 });
  const start = Date.now();
  await page.locator('#chat-send').click();
  const loadingShown = await page.locator('#chat-send').isDisabled();
  const response = await responsePromise;
  const data = await response.json();
  await page.waitForFunction(() => !document.querySelector('#chat-send').disabled,
    undefined, { timeout: 20000 });
  const bubbles = page.locator('#chat-transcript .item.spaced .item-desc');
  const text = await bubbles.last().innerText();
  const numbers = data.checks?.[0]?.numbers;
  const screenshot = `gui-${label}.png`;
  await page.screenshot({ path: path.join(out, screenshot), fullPage: true, mask: [page.locator('#token')] });
  const passed = response.status() === 200
    && Object.entries(expected.numbers).every(([k, v]) => numbers?.[k] === v)
    && expected.text.every(t => text.includes(t));
  const result = { case: label, elapsed_seconds: (Date.now() - start) / 1000,
    http_status: response.status(), loading_shown: loadingShown,
    session: data.session, numbers, accepted: data.user_supplied_accepted_this_turn,
    rejected: data.user_supplied_rejected_this_turn, unclaimed: data.unclaimed_change_intents,
    llm_diagnostic: data.llm_diagnostic, reply_source: data.reply_source,
    visible_reply: text, expected, passed, screenshot };
  results.push(result);
  fs.writeFileSync(path.join(out, 'gui-results.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify({ case: label, passed, elapsed_seconds: result.elapsed_seconds,
    http_status: result.http_status, reply_source: result.reply_source,
    extract: data.llm_diagnostic?.extract, reply: data.llm_diagnostic?.reply }));
  return result;
}

(async () => {
  browser = await chromium.launch({ channel: 'chrome', headless: false });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto('http://127.0.0.1:8001', { waitUntil: 'load' });
  await page.locator('#token').fill(creds.engineer);
  await page.locator('#login-button').click();
  await page.locator('#login').waitFor({ state: 'hidden' });
  await page.locator('button[data-page="chat"]').click();
  await page.locator('#chat-message').waitFor();
  await runCase(page, 'A',
    '電源24V，名目額定10A，實際持續可用8A。舊馬達8A，輔助負載3A。現在把馬達替換成11A，交期不能延後，請分析。',
    { numbers: { total_current_a: '14', total_power_w: '336', limit_current_a: '8' },
      text: ['14', '336', '40%', '75%'] });
  await runCase(page, 'C',
    '如果改用9A馬達，其他條件不變，重新分析。',
    { numbers: { total_current_a: '12', total_power_w: '288', limit_current_a: '8' },
      text: ['12', '288', '20%', '50%'] });
  // No extra inference: exercise the visible unavailable-extraction warning.
  await page.locator('#chat-local-llm').uncheck();
  await runCase(page, 'warning',
    '如果改用7.5A馬達，其他條件不變，重新分析。',
    { numbers: { total_current_a: '12', total_power_w: '288' },
      text: ['本次提出的條件尚未成功套用', '7.5A'] });
  if (results[0].session?.id !== results[1].session?.id) throw new Error('Session changed between A and C');
})().catch(e => {
  fs.writeFileSync(path.join(out, 'gui-error.txt'), String(e.message));
  console.error('GUI verification failed:', e.message);
  process.exitCode = 1;
}).finally(async () => { if (browser) await browser.close(); });
