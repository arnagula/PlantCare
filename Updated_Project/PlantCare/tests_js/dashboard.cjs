const { JSDOM } = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');

async function testDashboard() {
  const html = fs.readFileSync('dashboard/index.html', 'utf8');
  const dom = new JSDOM(html, { url: 'https://plant.test/', runScripts: 'outside-only' });
  const w = dom.window;
  const calls = [];
  const timers = new Map();
  let now = 100;
  let offline = false;
  let snapshot = {
    status: 'ok',
    condition: 'thirsty',
    sample_time: '2026-11-12T15:00:00.000Z',
    fresh_for_s: 10,
    readings: { temperature_c: 23, humidity_pct: 60, light_lux: 1500, soil_pct: null, soil_raw: 0 },
  };
  try {
    w.AbortSignal = AbortSignal;
    w.performance.now = () => now;
    w.setInterval = (callback, delay) => timers.set(delay, callback);
    w.fetch = async (url, options) => {
      calls.push({ url, options });
      if (offline) throw new Error('offline');
      return { ok: true, json: async () => snapshot };
    };
    w.eval(fs.readFileSync('dashboard/app.js', 'utf8'));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, '/api/demo/telemetry');
    assert.equal(calls[0].options.method, 'GET');
    assert.equal(calls[0].options.credentials, 'omit');
    assert.equal(calls[0].options.headers, undefined);
    assert.equal(w.document.querySelectorAll('input, button, select, form').length, 0);
    assert.equal(w.document.getElementById('state').textContent, 'Thirsty');
    assert.match(w.document.getElementById('metrics').textContent, /Soil sensor: 0/);
    assert.match(w.document.getElementById('metrics').textContent, /Soil moisture: Unavailable/);
    now += 10001;
    timers.get(500)();
    assert.equal(w.document.getElementById('state').textContent, 'Unknown');
    assert.doesNotMatch(w.document.getElementById('metrics').textContent, /1500/);
    await timers.get(2000)();
    assert.equal(w.document.getElementById('state').textContent, 'Thirsty');
    snapshot = { status: 'stale', readings: null };
    await timers.get(2000)();
    assert.equal(w.document.getElementById('connection').textContent, 'No fresh measurements');
    offline = true;
    await timers.get(2000)();
    assert.equal(w.document.getElementById('connection').textContent, 'Telemetry connection unavailable');
    assert.ok(calls.every(call => call.url === '/api/demo/telemetry' && call.options.method === 'GET'));
    console.log('Dashboard DOM tests passed');
  } finally {
    w.close();
  }
}

testDashboard().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
