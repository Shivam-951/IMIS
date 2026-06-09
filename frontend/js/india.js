const API_INDIA = 'http://127.0.0.1:8000';

let indiaData        = [];
let currentIndiaTicker = null;
let currentIndiaDays   = 30;
let indiaPriceChart    = null;
let indiaRsiChart      = null;
let indiaMacdChart     = null;
let indiaPriceSeries   = null;
let indiaRsiSeries     = null;
let indiaRsiOb         = null;
let indiaRsiOs         = null;
let indiaMacdSeries    = null;
let indiaMacdSig       = null;
let indiaMacdHist      = null;


function encodeTicker(ticker) {
  return ticker
    .replace('=', '__')
    .replace('.NS', '_NS')
    .replace('^', '_CARET_');
}


function initIndiaCharts() {
  const opts = {
    layout: { background: { color: 'transparent' }, textColor: '#7a7f96' },
    grid:   { vertLines: { color: '#1e2130' }, horzLines: { color: '#1e2130' } },
    crosshair: { mode: 1 },
    rightPriceScale: { borderColor: '#2a2d3a' },
    timeScale: { borderColor: '#2a2d3a', timeVisible: true },
  };

  indiaPriceChart = LightweightCharts.createChart(
    document.getElementById('indiaPriceChart'), { ...opts, height: 300 }
  );
  indiaPriceSeries = indiaPriceChart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: '#00d97e', downColor: '#ff4d6a',
    borderUpColor: '#00d97e', borderDownColor: '#ff4d6a',
    wickUpColor: '#00d97e', wickDownColor: '#ff4d6a',
  });

  indiaRsiChart  = LightweightCharts.createChart(
    document.getElementById('indiaRsiChart'), { ...opts, height: 160 }
  );
  indiaRsiSeries = indiaRsiChart.addSeries(LightweightCharts.LineSeries, { color: '#4d9fff', lineWidth: 2 });
  indiaRsiOb     = indiaRsiChart.addSeries(LightweightCharts.LineSeries, { color: '#ff4d6a', lineWidth: 1, lineStyle: 2 });
  indiaRsiOs     = indiaRsiChart.addSeries(LightweightCharts.LineSeries, { color: '#00d97e', lineWidth: 1, lineStyle: 2 });

  indiaMacdChart  = LightweightCharts.createChart(
    document.getElementById('indiaMacdChart'), { ...opts, height: 160 }
  );
  indiaMacdSeries = indiaMacdChart.addSeries(LightweightCharts.LineSeries,      { color: '#4d9fff', lineWidth: 2 });
  indiaMacdSig    = indiaMacdChart.addSeries(LightweightCharts.LineSeries,      { color: '#ffaa00', lineWidth: 1 });
  indiaMacdHist   = indiaMacdChart.addSeries(LightweightCharts.HistogramSeries, {
    color: '#00d97e', priceFormat: { type: 'price', minMove: 0.0001 }
  });
}


async function loadIndiaChart(ticker, days) {
  try {
    const encoded = encodeTicker(ticker);
    const [chartRes, indRes] = await Promise.all([
      fetch(`${API_INDIA}/api/india/chart/${encoded}?days=${days}`),
      fetch(`${API_INDIA}/api/india/indicators/${encoded}?days=${days}`)
    ]);

    const chartData = await chartRes.json();
    const indData   = await indRes.json();

    const candles = chartData.data.map(d => ({
      time: d.date, open: d.open, high: d.high, low: d.low, close: d.close
    }));
    indiaPriceSeries.setData(candles);

    const rsiData = indData.data.filter(d => d.rsi !== null).map(d => ({ time: d.date, value: d.rsi }));
    indiaRsiSeries.setData(rsiData);
    indiaRsiOb.setData(indData.data.map(d => ({ time: d.date, value: 70 })));
    indiaRsiOs.setData(indData.data.map(d => ({ time: d.date, value: 30 })));

    if (rsiData.length) {
      const latest = rsiData[rsiData.length - 1].value;
      const el     = document.getElementById('indiaRsiValue');
      el.textContent = latest.toFixed(2);
      el.style.color = latest < 30 ? '#00d97e' : latest > 70 ? '#ff4d6a' : '#e8eaf0';
    }

    indiaMacdSeries.setData(indData.data.map(d => ({ time: d.date, value: d.macd })));
    indiaMacdSig.setData(indData.data.map(d => ({ time: d.date, value: d.macd_signal })));
    indiaMacdHist.setData(indData.data.map(d => ({
      time: d.date, value: d.macd_hist,
      color: d.macd_hist >= 0 ? '#00d97e' : '#ff4d6a'
    })));

    if (indData.data.length) {
      const latest = indData.data[indData.data.length - 1].macd;
      document.getElementById('indiaMacdValue').textContent = latest?.toFixed(4) || '—';
    }

    indiaPriceChart.timeScale().fitContent();
    indiaRsiChart.timeScale().fitContent();
    indiaMacdChart.timeScale().fitContent();

    const name = chartData.name || ticker;
    document.getElementById('indiaChartTitle').textContent = name;

  } catch (e) {
    console.error('India chart error:', e);
  }
}


function renderIndiaCards(data) {
  const grid = document.getElementById('indiaCardsGrid');

  grid.innerHTML = data.map(item => `
    <div class="card" onclick="selectIndiaTicker('${item.ticker}')">
      <div class="card-category">${item.category}</div>
      <div class="card-symbol">${item.name}</div>
      <div class="card-price">
        ${item.price > 1000
          ? item.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })
          : item.price.toFixed(4)}
      </div>
      <div class="card-return ${item.return_1d >= 0 ? 'up' : 'down'}">
        ${item.return_1d >= 0 ? '▲' : '▼'} ${Math.abs(item.return_1d).toFixed(2)}%
      </div>

      <div class="score-bar-wrap">
        <div class="score-bar" style="width:${item.score}%; background:${item.color}"></div>
      </div>

      <div class="score-row">
        <span class="score-num" style="color:${item.color}">${item.score}</span>
        <span class="score-label">${item.label}</span>
        <span class="score-action" style="color:${item.color}">${item.action}</span>
      </div>

      <div class="card-rsi">RSI ${item.rsi}</div>
    </div>
  `).join('');
}


function renderIndiaOverview(data) {
  const el = document.getElementById('indiaOverview');
  el.innerHTML = data.map(item => `
    <div class="overview-item" onclick="selectIndiaTicker('${item.ticker}')"
         style="cursor:pointer">
      <div>
        <div class="overview-name">${item.name}</div>
        <div class="overview-price">
          ${item.price > 1000
            ? item.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })
            : item.price.toFixed(4)}
        </div>
      </div>
      <div style="text-align:right">
        <div class="overview-ret ${item.return_1d >= 0 ? 'up' : 'down'}">
          ${item.return_1d >= 0 ? '▲' : '▼'} ${Math.abs(item.return_1d).toFixed(2)}%
        </div>
        <div style="font-size:11px; color:${item.color}">${item.score} ${item.action}</div>
      </div>
    </div>
  `).join('');
}


async function loadIndiaSummary() {
  try {
    const res  = await fetch(`${API_INDIA}/api/india/summary`);
    indiaData  = await res.json();

    renderIndiaCards(indiaData);
    renderIndiaOverview(indiaData);

    // Auto-select first ticker
    if (indiaData.length && !currentIndiaTicker) {
      selectIndiaTicker(indiaData[0].ticker);
    }

  } catch (e) {
    console.error('India summary error:', e);
  }
}


function selectIndiaTicker(ticker) {
  currentIndiaTicker = ticker;
  document.querySelectorAll('#indiaCardsGrid .card').forEach(card => {
    card.classList.toggle('active', card.onclick?.toString().includes(ticker));
  });
  loadIndiaChart(ticker, currentIndiaDays);
}


function filterIndiaByCategory(cat) {
  const filtered = cat === 'all' ? indiaData : indiaData.filter(d => d.category === cat);
  renderIndiaCards(filtered);

  document.querySelectorAll('.cat-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.cat === cat);
  });
}


// Wire up category buttons
document.querySelectorAll('.cat-btn').forEach(btn => {
  btn.addEventListener('click', () => filterIndiaByCategory(btn.dataset.cat));
});

// Wire up india days buttons
document.querySelectorAll('.india-days-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    currentIndiaDays = parseInt(btn.dataset.days);
    document.querySelectorAll('.india-days-btn').forEach(b =>
      b.classList.toggle('active', parseInt(b.dataset.days) === currentIndiaDays)
    );
    if (currentIndiaTicker) loadIndiaChart(currentIndiaTicker, currentIndiaDays);
  });
});