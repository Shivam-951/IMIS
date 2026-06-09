const API = 'http://127.0.0.1:8000';

let currentSymbol = 'BTCUSDT';
let currentDays   = 30;

async function loadSummary() {
  try {
    const [summaryRes, scoresRes, intelRes, sentimentRes] = await Promise.all([
      fetch(`${API}/api/summary`),
      fetch(`${API}/api/scores`),
      fetch(`${API}/api/intelligence`),
      fetch(`${API}/api/sentiment`)
    ]);

    const summaryData  = await summaryRes.json();
    const scoresData   = await scoresRes.json();
    const intelData    = await intelRes.json();
    const sentimentData = await sentimentRes.json();

    // Map by symbol
    const scoresMap    = {};
    const intelMap     = {};
    const sentimentMap = {};

    scoresData.forEach(s   => scoresMap[s.symbol]      = s);
    intelData.forEach(i    => intelMap[i.symbol]        = i);
    sentimentData.forEach(s => sentimentMap[s.ticker]   = s);

    const grid = document.getElementById('cardsGrid');
    grid.innerHTML = summaryData.map(item => {
      const s        = scoresMap[item.symbol]    || {};
      const intel    = intelMap[item.symbol]     || {};
      const sentiment = sentimentMap[item.symbol] || {};
      const score      = s.score || 0;
      const scoreColor = s.color || '#7a7f96';

      return `
        <div class="card ${item.symbol === currentSymbol ? 'active' : ''}"
             onclick="selectSymbol('${item.symbol}')">

          <div class="card-symbol">${item.symbol.replace('USDT','')}/USDT</div>
          <div class="card-price">$${formatPrice(item.price)}</div>
          <div class="card-return ${item.return_1d >= 0 ? 'up' : 'down'}">
            ${item.return_1d >= 0 ? '▲' : '▼'} ${Math.abs(item.return_1d).toFixed(2)}%
          </div>

          <div class="score-bar-wrap">
            <div class="score-bar" style="width:${score}%; background:${scoreColor}"></div>
          </div>

          <div class="score-row">
            <span class="score-num" style="color:${scoreColor}">${score}</span>
            <span class="score-label">${s.label || ''}</span>
            <span class="score-action" style="color:${scoreColor}">${s.action || ''}</span>
          </div>

          <div class="intel-row">
            <span class="intel-tag" style="color:${intel.trend_color || '#7a7f96'}">
              ${intel.trend || '—'}
            </span>
            <span class="intel-tag" style="color:${intel.momentum_color || '#7a7f96'}">
              ${intel.momentum || '—'}
            </span>
            <span class="intel-tag" style="color:${intel.volatility_color || '#7a7f96'}">
              Vol:${intel.volatility || '—'}
            </span>
          </div>

          <div class="sentiment-row">
            <span class="sentiment-badge"
                  style="color:${sentiment.color || '#7a7f96'}">
              ${sentiment.emoji || '—'} ${sentiment.label || 'No Data'}
            </span>
            <span class="sentiment-count">
              ${sentiment.article_count ? `${sentiment.article_count} articles` : ''}
            </span>
          </div>

          <div class="card-rsi">RSI ${item.rsi}</div>
        </div>
      `;
    }).join('');

    const lastDate = summaryData[0]?.date || '';
    document.getElementById('lastUpdate').textContent = `Updated ${lastDate}`;

  } catch (e) {
    console.error('Summary error:', e);
  }
}

function selectSymbol(symbol) {
  currentSymbol = symbol;

  // Update symbol bar
  document.querySelectorAll('.sym-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.symbol === symbol);
  });

  // Update cards
  document.querySelectorAll('.card').forEach(card => {
    card.classList.toggle('active', card.onclick?.toString().includes(symbol));
  });

  loadChart(symbol, currentDays);
}

function selectDays(days) {
  currentDays = days;
  document.querySelectorAll('.days-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.days) === days);
  });
  loadChart(currentSymbol, days);
}

// Wire up symbol bar buttons
document.querySelectorAll('.sym-btn').forEach(btn => {
  btn.addEventListener('click', () => selectSymbol(btn.dataset.symbol));
});

// Wire up days buttons
document.querySelectorAll('.days-btn').forEach(btn => {
  btn.addEventListener('click', () => selectDays(parseInt(btn.dataset.days)));
});


// Tab Switching 
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;

    document.querySelectorAll('.tab-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.tab === tab)
    );
    document.querySelectorAll('.tab-content').forEach(c =>
      c.classList.toggle('active', c.id === `tab-${tab}`)
    );

    if (tab === 'india' && indiaData.length === 0) {
      loadIndiaSummary();
      initIndiaCharts();
    }

    if (tab === 'alerts') {
      loadAlerts();
    }
  });
});


// Boot
async function init() {
  initCharts();
  await loadSummary();
  await loadChart(currentSymbol, currentDays);
  await loadSignals();
}

init();