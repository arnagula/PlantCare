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
  const liveSnapshot = {
    mode: 'live',
    status: 'ok',
    condition: 'thirsty',
    sample_time: '2026-11-12T15:00:00.000Z',
    fresh_for_s: 10,
    readings: { temperature_c: 23, humidity_pct: 60, light_lux: 1500, soil_pct: null, soil_raw: 0 },
    thresholds: {
      temperature_c: { low: 16, high: 27 },
      humidity_pct: { low: 50, high: null },
      light_lux: { low: 1100, high: null },
      soil_pct: { low: null, high: null },
    },
  };
  const metricCard = key => w.document.getElementById('card-' + key);
  const card = key => {
    const found = metricCard(key);
    assert.ok(found, 'missing card ' + key);
    return {
      value: [...found.querySelectorAll('.value span')].map(el => el.textContent).join(' '),
      missing: found.querySelector('.value').classList.contains('missing'),
      pill: found.querySelector('.pill').textContent,
      ideal: found.querySelector('.bar-scale .ideal').textContent,
    };
  };
  const detail = () => {
    const panel = w.document.getElementById('detail');
    return {
      metric: panel.dataset.metric,
      title: panel.querySelector('.detail-title').textContent,
      pill: panel.querySelector('.pill').textContent,
      stats: Object.fromEntries([...panel.querySelectorAll('.stat')].map(row =>
        [row.querySelector('dt').textContent, row.querySelector('dd').textContent])),
      chart: panel.querySelector('.chart'),
    };
  };
  let snapshot = liveSnapshot;
  try {
    w.AbortSignal = AbortSignal;
    w.performance.now = () => now;
    w.setInterval = (callback, delay) => timers.set(delay, callback);
    let respond = null;
    w.fetch = async (url, options) => {
      calls.push({ url, options });
      if (offline) throw new Error('offline');
      if (respond) return respond(url, options);
      return { ok: true, json: async () => snapshot };
    };
    w.eval(fs.readFileSync('dashboard/app.js', 'utf8'));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, '/api/demo/telemetry?mode=live');
    assert.equal(calls[0].options.method, 'GET');
    assert.equal(calls[0].options.credentials, 'omit');
    assert.equal(calls[0].options.headers, undefined);
    // The only controls are the mode toggle and the four metric cards; there are no watering controls.
    assert.equal(w.document.querySelectorAll('input, select, form, textarea').length, 0);
    const buttons = [...w.document.querySelectorAll('#modeToggle button')];
    assert.deepEqual(buttons.map(b => b.dataset.mode), ['live', 'simulated']);
    assert.deepEqual(
      [...w.document.querySelectorAll('button')].map(b => b.dataset.mode || b.dataset.metric),
      ['live', 'simulated', 'soil_pct', 'light_lux', 'temperature_c', 'humidity_pct'],
    );
    for (const control of w.document.querySelectorAll('button, a, [role="button"]')) {
      assert.doesNotMatch(control.textContent, /water|\barm|pump/i, 'no watering controls: ' + control.textContent);
    }
    assert.deepEqual(buttons.map(b => b.getAttribute('aria-pressed')), ['true', 'false']);
    assert.equal(w.document.getElementById('modeBanner').textContent, 'Live plant');
    assert.equal(w.document.getElementById('connection').textContent, 'Online');
    assert.match(w.document.getElementById('sample').textContent, /^Last updated: \d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2} (AM|PM)$/);
    assert.equal(w.document.getElementById('connection').dataset.status, 'ok');
    assert.equal(w.document.getElementById('state').textContent, 'Needs water');
    assert.equal(w.document.getElementById('stateIcon').textContent, '💧');
    assert.equal(w.document.body.dataset.health, 'attention', 'hero turns amber when the plant needs something');
    assert.equal(w.document.getElementById('advice').textContent,
      'Soil moisture is below the ideal range. Water until the soil is evenly moist.');
    assert.equal(w.document.body.dataset.mode, 'live');
    assert.equal(w.document.getElementById('simBadge').hidden, true);
    assert.deepEqual(
      [...w.document.querySelectorAll('#metrics .label')].map(el => el.textContent),
      ['Soil moisture', 'Light', 'Temperature', 'Humidity'],
    );
    assert.deepEqual(card('temperature_c'), { value: '23 °C', missing: false, pill: 'Good', ideal: 'Ideal 16–27 °C' });
    assert.deepEqual(card('humidity_pct'), { value: '60 % RH', missing: false, pill: 'Good', ideal: 'Ideal ≥ 50 % RH' });
    assert.deepEqual(card('light_lux'), { value: '1.5k lux', missing: false, pill: 'Good', ideal: 'Ideal ≥ 1100 lux' });
    assert.deepEqual(card('soil_pct'), { value: '—', missing: true, pill: 'Not calibrated', ideal: 'Not calibrated yet' });
    assert.equal(metricCard('soil_raw'), null, 'raw soil sensor value is not shown');

    // Bars: ideal zone and marker are placed on each metric's scale.
    const temp = metricCard('temperature_c');
    assert.equal(temp.querySelector('.bar-zone').style.left, '40%');      // 16 of 0–40
    assert.equal(temp.querySelector('.bar-zone').style.width, '27.5%');   // 16–27
    assert.equal(temp.querySelector('.bar-marker').style.left, '57.5%');  // 23
    assert.equal(temp.querySelector('.bar-marker').dataset.outside, 'false');
    assert.deepEqual([...temp.querySelectorAll('.bar-scale span')].map(el => el.textContent), ['0', 'Ideal 16–27 °C', '40']);
    assert.deepEqual([...metricCard('humidity_pct').querySelectorAll('.bar-scale span')].map(el => el.textContent),
      ['0%', 'Ideal ≥ 50 % RH', '100%']);
    assert.equal(metricCard('light_lux').querySelector('.bar-zone').style.width, '63.33%'); // 1100 to end
    assert.equal(metricCard('soil_pct').querySelector('.bar-zone'), null, 'no zone while soil is uncalibrated');
    assert.equal(metricCard('soil_pct').querySelector('.bar-marker'), null, 'no marker without a value');

    // Detail panel: soil moisture by default; clicking a card selects it.
    assert.equal(detail().metric, 'soil_pct');
    assert.equal(metricCard('soil_pct').getAttribute('aria-selected'), 'true');
    assert.match(detail().chart.textContent, /Waiting for soil calibration/);
    metricCard('temperature_c').click();
    assert.equal(detail().metric, 'temperature_c');
    assert.equal(detail().title, 'Temperature');
    assert.equal(metricCard('temperature_c').getAttribute('aria-selected'), 'true');
    assert.equal(metricCard('soil_pct').getAttribute('aria-selected'), 'false');
    assert.deepEqual(detail().stats, {
      Current: '23 °C', Average: '23 °C', Lowest: '23 °C', Highest: '23 °C',
      'Time in ideal range': '100%', 'Ideal range': '16–27 °C',
    });
    assert.equal(detail().chart.querySelectorAll('.chart-threshold').length, 2);
    assert.equal(detail().chart.querySelectorAll('.chart-zone').length, 1);
    assert.ok(detail().chart.querySelectorAll('.chart-grid').length >= 2, 'value axis gridlines');
    assert.equal([...detail().chart.querySelectorAll('.chart-axis')].filter(t => /[AP]M$/.test(t.textContent)).length, 3, 'time axis labels');
    // Arrow keys move the selection like tabs.
    temp.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    assert.equal(detail().metric, 'humidity_pct');
    assert.equal(w.document.activeElement.id, 'card-humidity_pct');
    metricCard('temperature_c').click();
    metricCard('temperature_c').focus();

    // History: one point per new sample, never per repeated fetch.
    assert.equal(detail().chart.querySelector('.chart-line'), null);
    assert.equal(temp.querySelector('.spark-line'), null);
    await timers.get(2000)();
    assert.equal(detail().chart.querySelector('.chart-line'), null, 'same sample_time adds no point');
    snapshot = { ...snapshot, sample_time: '2026-11-12T15:01:00.000Z', readings: { ...snapshot.readings, temperature_c: 30 } };
    await timers.get(2000)();
    assert.equal(detail().chart.querySelector('.chart-line').getAttribute('points').split(' ').length, 2);
    assert.equal(metricCard('temperature_c').querySelector('.spark-line').getAttribute('points').split(' ').length, 2);
    assert.equal(metricCard('temperature_c').querySelector('.spark-axis'), null, 'sparklines have no axis labels');
    assert.equal(metricCard('temperature_c').querySelectorAll('.spark-threshold').length, 2, 'dotted lines at 16 and 27');
    const yLabels = [...detail().chart.querySelectorAll('.chart-axis-end')].map(el => el.textContent);
    assert.equal(yLabels.length, 2, 'detail graph labels its y-axis min and max');
    assert.ok(Number(yLabels[0]) <= 16 && Number(yLabels[1]) >= 30, 'axis covers the readings and thresholds: ' + yLabels);
    assert.equal(detail().chart.querySelector('.chart-unit').textContent, '°C');
    assert.equal(metricCard('temperature_c').querySelector('.bar-marker').dataset.outside, 'true', '30 °C is above 27');
    assert.equal(card('temperature_c').pill, 'Too warm');
    assert.deepEqual(detail().stats, {
      Current: '30 °C', Average: '26.5 °C', Lowest: '23 °C', Highest: '30 °C',
      'Time in ideal range': '50%', 'Ideal range': '16–27 °C',
    });
    assert.equal(w.document.activeElement, metricCard('temperature_c'), 'focus survives the refresh');
    snapshot = liveSnapshot;
    now += 10001;
    timers.get(500)();
    assert.equal(w.document.getElementById('state').textContent, 'Status unavailable');
    assert.doesNotMatch(w.document.getElementById('metrics').textContent, /1500/);
    await timers.get(2000)();
    assert.equal(w.document.getElementById('state').textContent, 'Needs water');
    snapshot = { mode: 'live', status: 'stale', readings: null };
    await timers.get(2000)();
    assert.equal(w.document.getElementById('connection').textContent, 'Offline');
    assert.equal(w.document.getElementById('connection').dataset.status, 'stale');
    offline = true;
    await timers.get(2000)();
    assert.equal(w.document.getElementById('connection').textContent, 'Connection error');
    assert.equal(w.document.getElementById('connection').dataset.status, 'error');
    offline = false;
    snapshot = liveSnapshot;

    // Switching to Simulation clears live readings and polls the simulated mode at once.
    let release;
    respond = () => new Promise(resolve => { release = resolve; });
    calls.length = 0;
    buttons[1].click();
    assert.deepEqual(buttons.map(b => b.getAttribute('aria-pressed')), ['false', 'true']);
    assert.match(detail().chart.textContent, /Collecting data/, 'switching modes clears the history');
    assert.equal(detail().metric, 'temperature_c', 'selection is kept across modes');
    assert.equal(w.document.getElementById('modeBanner').textContent, 'Simulated plant');
    assert.equal(w.document.getElementById('connection').dataset.status, 'waiting');
    assert.equal(w.document.body.dataset.health, 'unknown');
    assert.equal(w.document.getElementById('state').textContent, 'Status unavailable');
    assert.equal(card('temperature_c').missing, true);
    assert.equal(card('temperature_c').ideal, '', 'live thresholds must not carry over to simulation');
    assert.equal(card('temperature_c').pill, 'No data');
    assert.equal(w.document.body.dataset.mode, 'simulated');
    assert.equal(w.document.getElementById('simBadge').hidden, false);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, '/api/demo/telemetry?mode=simulated');
    assert.equal(calls[0].options.signal.aborted, false);

    // Switching back aborts that request; its late reply must not render.
    const simulatedCall = calls[0];
    respond = null;
    buttons[0].click();
    assert.equal(simulatedCall.options.signal.aborted, true);
    assert.equal(calls.at(-1).url, '/api/demo/telemetry?mode=live');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(w.document.getElementById('state').textContent, 'Needs water');
    release({ ok: true, json: async () => ({ ...snapshot, mode: 'simulated', condition: 'happy' }) });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(w.document.getElementById('state').textContent, 'Needs water');

    // A response labelled with the wrong mode is never shown.
    buttons[1].click();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(w.document.getElementById('state').textContent, 'Status unavailable');
    assert.equal(w.document.getElementById('connection').textContent, 'Connection error');
    snapshot = {
      ...snapshot, mode: 'simulated', condition: 'happy',
      readings: { ...snapshot.readings, soil_pct: 55 },
      thresholds: { ...snapshot.thresholds, soil_pct: { low: 30, high: 80 } },
    };
    await timers.get(2000)();
    assert.equal(w.document.getElementById('state').textContent, 'Healthy');
    assert.equal(w.document.getElementById('stateIcon').textContent, '😊');
    assert.equal(w.document.body.dataset.health, 'good');
    assert.deepEqual(card('soil_pct'), { value: '55 %', missing: false, pill: 'Good', ideal: 'Ideal 30–80 %' });
    assert.equal(w.document.getElementById('connection').textContent, 'Online');
    assert.equal(w.document.getElementById('connection').title, 'Receiving simulated measurements');

    // Uncalibrated soil still counts as online; invalid readings show a partial-data badge.
    snapshot = { ...snapshot, status: 'uncalibrated' };
    await timers.get(2000)();
    assert.equal(w.document.getElementById('connection').textContent, 'Online');
    snapshot = { ...snapshot, status: 'invalid' };
    await timers.get(2000)();
    assert.equal(w.document.getElementById('connection').textContent, 'Partial data');
    assert.equal(w.document.getElementById('connection').dataset.status, 'partial');
    if (process.env.TZ === 'UTC') {
      assert.equal(w.document.getElementById('sample').textContent, 'Last updated: 2026-11-12 3:00:00 PM');
    }

    assert.ok(calls.every(call => call.url.startsWith('/api/demo/telemetry?mode=') && call.options.method === 'GET'));
    console.log('Dashboard DOM tests passed');
  } finally {
    w.close();
  }
}

testDashboard().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
