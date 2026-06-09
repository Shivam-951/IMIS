let allAlerts = [];
async function loadAlerts(){
    try{
        const res = await fetch(`${API}/api/alerts?limit=100`);
        allAlerts = await res.json();

        // Update badge 
        const badge = document.getElementById('alertBadge');
        if (badge) badge.textContent = allAlerts.length;

        renderAlerts(allAlerts);
    } catch (e) {
        document.getElementById('alertsList').innerHTML = 
        '<div class = "loading-text">Checking for new alerts...</div>';
        
    }
}

async function refreshAlerts() {
    document.getElementById('alertsList').innerHTML = 
    '<div class="loading-text">Checking for new alerts...</div>';
    try{
        await fetch(`${API}/api/alerts/check`);
        await loadAlerts();
    } catch (e) {
        console.error('Refresh error:', e);
    }
}

function renderAlerts(alerts){
    const list = document.getElementById('alertsList');
    if (!alerts.length){
        list.innerHTML = '<div class="loading-text">No alerts yet. Click Refresh to check.</div>';
    return;
    }
    list.innerHTML = alerts.map(a => `
        <div class="alert-item alert-${a.severity}">
      <div class="alert-left">
        <div class="alert-dot" style="background:${a.color}"></div>
        <div>
          <div class="alert-header">
            <span class="alert-symbol">${a.symbol.replace('USDT','')}</span>
            <span class="alert-type" style="color:${a.color}">${a.type}</span>
          </div>
          <div class="alert-message">${a.message}</div>
        </div>
      </div>
      <div class="alert-time">${a.timestamp}</div>
    </div>
        `).join('');
}

function filterAlertsBySeverity(sev){
    document.querySelectorAll('.sev-btn').forEach(btn => 
        btn.classList.toggle('active', btn.dataset.sev === sev)
    );
    const filtered = sev === 'all' ? allAlerts
        : allAlerts.filter(a => a.severity === sev);
    refreshAlerts(filtered);
}

document.querySelectorAll('.sev-btn').forEach(btn => {
    btn.addEventListener('click', () => filterAlertsBySeverity(btn.dataset.sev));
});