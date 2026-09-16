const services = {
  order: 'http://localhost:8001',
  inventory: 'http://localhost:8002',
  payment: 'http://localhost:8003'
};
const apiKey = () => document.querySelector('#api-key').value.trim();
const adminHeaders = () => ({ 'X-Admin-API-Key': apiKey() });
const notice = (message, error = false) => {
  const node = document.querySelector('#notice');
  node.textContent = message;
  node.style.color = error ? '#a33d2e' : '';
};
const money = cents => `$${(cents / 100).toFixed(2)}`;
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function setHealth(id, online) {
  const node = document.querySelector(`#${id}-health`);
  node.textContent = online ? 'online' : 'offline';
  node.previousElementSibling.classList.toggle('ok', online);
}

async function refreshHealth() {
  await Promise.all(Object.entries(services).map(async ([name, base]) => {
    try { await getJson(`${base}/health`); setHealth(name, true); }
    catch { setHealth(name, false); }
  }));
}

function renderStock(items) {
  document.querySelector('#stock-table').innerHTML = `<table class="data-table"><thead><tr><th>SKU</th><th>Available</th><th>Reserved</th><th>Signal</th></tr></thead><tbody>${items.map(item => `<tr><td class="mono">${escapeHtml(item.sku)}</td><td>${item.available_qty}</td><td>${item.reserved_qty}</td><td><span class="status ${item.available_qty < 5 ? 'FAILED' : 'CONFIRMED'}">${item.available_qty < 5 ? 'low' : 'ready'}</span></td></tr>`).join('')}</tbody></table>`;
}
function renderOrders(items) {
  document.querySelector('#order-count').textContent = items.length;
  document.querySelector('#orders-table').innerHTML = items.length ? `<table class="data-table"><thead><tr><th>Order</th><th>Customer</th><th>Amount</th><th>Status</th><th>Flow</th></tr></thead><tbody>${items.map(item => `<tr><td class="mono">${escapeHtml(item.order_id.slice(0, 8))}</td><td>${escapeHtml(item.customer_id)}</td><td>${money(item.amount_cents)}</td><td><span class="status ${item.status}">${item.status}</span></td><td><div class="timeline">${item.history.map(entry => `<span>${entry.status}</span>`).join('')}</div></td></tr>`).join('')}</tbody></table>` : '<p class="muted">No orders yet.</p>';
}
function renderPayments(items) {
  document.querySelector('#payments-table').innerHTML = items.length ? `<table class="data-table"><thead><tr><th>Payment</th><th>Order</th><th>Amount</th><th>Decision</th><th>Reason</th></tr></thead><tbody>${items.map(item => `<tr><td class="mono">${escapeHtml(item.payment_id.slice(0, 8))}</td><td class="mono">${escapeHtml(item.order_id.slice(0, 8))}</td><td>${money(item.amount_cents)}</td><td><span class="status ${item.status === 'COMPLETED' ? 'CONFIRMED' : 'FAILED'}">${item.status}</span></td><td>${escapeHtml(item.reason || '-')}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">No payments yet.</p>';
}

async function refreshData() {
  try {
    const [stock, orders, payments] = await Promise.all([
      getJson(`${services.inventory}/admin/stock`, { headers: adminHeaders() }),
      getJson(`${services.order}/admin/orders?limit=20`, { headers: adminHeaders() }),
      getJson(`${services.payment}/admin/payments?limit=20`, { headers: adminHeaders() })
    ]);
    renderStock(stock); renderOrders(orders); renderPayments(payments);
    document.querySelector('#last-refresh').textContent = `Updated ${new Date().toLocaleTimeString()}`;
    notice('Dashboard synchronized');
  } catch (error) { notice(`Could not load admin data: ${error.message}`, true); }
  await refreshHealth();
}

async function createOrder(event) {
  event.preventDefault();
  const body = {
    customer_id: document.querySelector('#customer-id').value,
    items: [{ sku: document.querySelector('#sku').value, qty: Number(document.querySelector('#quantity').value) }],
    amount_cents: Number(document.querySelector('#amount').value),
    force_payment_failure: document.querySelector('#force-failure').checked
  };
  try {
    const order = await getJson(`${services.order}/orders`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    document.querySelector('#order-result').className = 'result';
    document.querySelector('#order-result').innerHTML = `<strong>${escapeHtml(order.order_id.slice(0, 8))}</strong><div class="timeline">${order.history.map(entry => `<span>${entry.status}</span>`).join('')}</div>`;
    notice('Order accepted; refreshing workflow data');
    setTimeout(refreshData, 900);
  } catch (error) { notice(`Order failed: ${error.message}`, true); }
}

document.querySelector('#api-key').value = localStorage.getItem('saga-admin-key') || 'local-admin-key';
document.querySelector('#api-key').addEventListener('change', event => localStorage.setItem('saga-admin-key', event.target.value));
document.querySelector('#refresh').addEventListener('click', refreshData);
document.querySelector('#reset-stock').addEventListener('click', async () => {
  try { await getJson(`${services.inventory}/admin/reset-stock`, { method: 'POST', headers: adminHeaders() }); notice('Demo stock reset'); refreshData(); }
  catch (error) { notice(`Reset failed: ${error.message}`, true); }
});
document.querySelector('#order-form').addEventListener('submit', createOrder);
refreshData();
setInterval(refreshData, 15000);
