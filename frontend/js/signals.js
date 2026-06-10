
async function loadSignals() {
  try {
    const res  = await fetch(`${API}/api/signals`);
    const data = await res.json();

    const list  = document.getElementById('signalsList');
    const count = document.getElementById('signalCount');

    if (!data.length) {
      list.innerHTML = '<div class="loading-text">No active signals</div>';
      count.textContent = '0';
      return;
    }

    count.textContent = data.length;

    list.innerHTML = data.map(item => `
      <div class="signal-item">
        <div class="signal-item-header">
          <span class="signal-sym">${item.symbol.replace('USDT','')}</span>
          <span class="signal-date">${item.date}</span>
        </div>
        <div class="signal-price">$${formatPrice(item.price)}</div>
        <div class="signal-tags">
          ${item.signals.map(s => `
            <span class="sig-tag ${s.bias}">${s.type}</span>
          `).join('')}
        </div>
      </div>
    `).join('');

  } catch (e) {
    document.getElementById('signalsList').innerHTML =
      '<div class="loading-text">Failed to load signals</div>';
  }
}

function formatPrice(price) {
  if (price > 1000) return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price > 1)    return price.toFixed(4);
  return price.toFixed(6);
}