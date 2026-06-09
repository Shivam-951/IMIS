let priceChart = null;
let rsiChart   = null;
let macdChart  = null;

let priceSeries    = null;
let rsiSeries      = null;
let rsiOb          = null;
let rsiOs          = null;
let macdSeries     = null;
let macdSignalLine = null;
let macdHist       = null;

function initCharts() {
  const priceEl = document.getElementById('priceChart');
  const rsiEl   = document.getElementById('rsiChart');
  const macdEl  = document.getElementById('macdChart');

  if (!priceEl || !rsiEl || !macdEl) {
    console.error('Chart containers not found');
    return;
  }

  const chartOpts = {
    layout: { background: { color: 'transparent' }, textColor: '#7a7f96' },
    grid:   { vertLines: { color: '#1e2130' }, horzLines: { color: '#1e2130' } },
    crosshair: { mode: 1 },
    rightPriceScale: { borderColor: '#2a2d3a' },
    timeScale: { borderColor: '#2a2d3a', timeVisible: true },
    handleScroll: true,
    handleScale: true,
  };

  // Create charts first
  priceChart = LightweightCharts.createChart(priceEl, { ...chartOpts, height: 300 });
  rsiChart   = LightweightCharts.createChart(rsiEl,   { ...chartOpts, height: 160 });
  macdChart  = LightweightCharts.createChart(macdEl,  { ...chartOpts, height: 160 });

  // Then add series
  priceSeries = priceChart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: '#00d97e', downColor: '#ff4d6a',
    borderUpColor: '#00d97e', borderDownColor: '#ff4d6a',
    wickUpColor: '#00d97e', wickDownColor: '#ff4d6a',
  });

  rsiSeries = rsiChart.addSeries(LightweightCharts.LineSeries, { color: '#4d9fff', lineWidth: 2 });
  rsiOb     = rsiChart.addSeries(LightweightCharts.LineSeries, { color: '#ff4d6a', lineWidth: 1, lineStyle: 2 });
  rsiOs     = rsiChart.addSeries(LightweightCharts.LineSeries, { color: '#00d97e', lineWidth: 1, lineStyle: 2 });

  macdSeries     = macdChart.addSeries(LightweightCharts.LineSeries,    { color: '#4d9fff', lineWidth: 2 });
  macdSignalLine = macdChart.addSeries(LightweightCharts.LineSeries,    { color: '#ffaa00', lineWidth: 1 });
  macdHist       = macdChart.addSeries(LightweightCharts.HistogramSeries, {
    color: '#00d97e',
    priceFormat: { type: 'price', minMove: 0.0001 }
  });
}

async function loadChart(symbol, days) {
  try {
    const [chartRes, indRes] = await Promise.all([
      fetch(`${API}/api/chart/${symbol}?days=${days}`),
      fetch(`${API}/api/indicators/${symbol}?days=${days}`)
    ]);

    const chartData = await chartRes.json();
    const indData   = await indRes.json();

    // Candlestick
    const candles = chartData.data.map(d => ({
      time: d.date, open: d.open, high: d.high, low: d.low, close: d.close
    }));
    priceSeries.setData(candles);

    // RSI
    const rsiData = indData.data
      .filter(d => d.rsi !== null)
      .map(d => ({ time: d.date, value: d.rsi }));

    const obData = indData.data.map(d => ({ time: d.date, value: 70 }));
    const osData = indData.data.map(d => ({ time: d.date, value: 30 }));

    rsiSeries.setData(rsiData);
    rsiOb.setData(obData);
    rsiOs.setData(osData);

    // Latest RSI display
    if (rsiData.length) {
      const latest = rsiData[rsiData.length - 1].value;
      const el     = document.getElementById('rsiValue');
      el.textContent = latest.toFixed(2);
      el.style.color = latest < 30 ? '#00d97e' : latest > 70 ? '#ff4d6a' : '#e8eaf0';
    }

    // MACD
    const macdLineData = indData.data.map(d => ({ time: d.date, value: d.macd }));
    const macdSigData  = indData.data.map(d => ({ time: d.date, value: d.macd_signal }));
    const macdHistData = indData.data.map(d => ({
      time: d.date, value: d.macd_hist,
      color: d.macd_hist >= 0 ? '#00d97e' : '#ff4d6a'
    }));

    macdSeries.setData(macdLineData);
    macdSignalLine.setData(macdSigData);
    macdHist.setData(macdHistData);

    // Latest MACD display
    if (macdLineData.length) {
      const latest = macdLineData[macdLineData.length - 1].value;
      document.getElementById('macdValue').textContent = latest.toFixed(4);
    }

    // Fit charts
    priceChart.timeScale().fitContent();
    rsiChart.timeScale().fitContent();
    macdChart.timeScale().fitContent();

    document.getElementById('chartTitle').textContent =
      `${symbol.replace('USDT', '')} / USDT`;

  } catch (e) {
    console.error('Chart load error:', e);
  }
}