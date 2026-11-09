const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');
const OUT = process.argv[2];
const tok = JSON.parse(execSync('podman exec riskscope-portable cat /app/runtime/demo_credentials.json').toString()).engineer;
(async () => {
  const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 1500 });
  await p.goto('http://127.0.0.1:8100/'); await p.type('#token', tok); await p.click('#login-button');
  await p.waitForFunction(() => document.querySelector('#identity').textContent.includes('工程師'), { timeout: 20000 });
  await p.click('#nav button[data-page="chat"]'); await p.waitForSelector('#chat-message');
  const msgs = ['電源24V，名目額定10A，實際可用8A，馬達11A，輔助3A，電流夠嗎？', '只將馬達改成9A，其餘完全不變。', '電源額定一直是10A，實際可用一直是8A，我只修改馬達。'];
  const log = [];
  for (let i = 0; i < msgs.length; i++) {
    await p.type('#chat-message', msgs[i]); await p.click('#chat-send');
    await p.waitForFunction(n => document.querySelectorAll('.chat-agent').length >= n && !document.querySelector('#chat-send').disabled, { timeout: 240000 }, i + 1);
    await new Promise(r => setTimeout(r, 800));
    await p.screenshot({ path: `${OUT}/gui_turn${i + 1}.png`, fullPage: true });
    const last = await p.$$eval('.chat-agent', els => els[els.length - 1].innerText);
    log.push({ turn: i + 1, badge: /本機 LLM 轉述/.test(last) ? 'LLM_ACCEPTED' : (/確定性模板/.test(last) ? 'DETERMINISTIC_TEMPLATE' : '?'), has14A: /14\s*A/.test(last), has12A: /12\s*A/.test(last), falseNameplateChange: /額定[^。\n]{0,6}由\s*10\s*A[^。\n]{0,6}(改|換)/.test(last) });
  }
  console.log(JSON.stringify(log, null, 1)); await b.close();
})().catch(e => { console.error('GUI FAIL', e.message); process.exit(1); });
