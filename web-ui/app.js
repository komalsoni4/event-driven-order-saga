const services = {
  order: 'http://localhost:8001',
  inventory: 'http://localhost:8002',
  payment: 'http://localhost:8003'
};
const apiKey = () => document.querySelector('#api-key').value.trim();
const adminHeaders = () => ({ 'X-Admin-API-Key': apiKey() });
let allOrders = [];
let selectedOrderId = null;
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
  document.querySelector('#kpi-stock').textContent = items.reduce((total, item) => total + item.available_qty, 0);
  document.querySelector('#stock-table').innerHTML = `<table class="data-table"><thead><tr><th>Product</th><th>Available</th><th>Reserved</th><th>Availability</th></tr></thead><tbody>${items.map(item => `<tr><td class="mono">${escapeHtml(item.sku)}</td><td>${item.available_qty}</td><td>${item.reserved_qty}</td><td><span class="status ${item.available_qty < 5 ? 'FAILED' : 'CONFIRMED'}">${item.available_qty < 5 ? 'Almost gone' : 'Available'}</span></td></tr>`).join('')}</tbody></table>`;
}
function renderOrders(items) {
  const search = document.querySelector('#order-search').value.toLowerCase();
  const filter = document.querySelector('#order-filter').value;
  const visible = items.filter(item => (filter === 'ALL' || item.status === filter) && (!search || item.customer_id.toLowerCase().includes(search) || item.order_id.toLowerCase().includes(search)));
  document.querySelector('#order-count').textContent = visible.length;
  document.querySelector('#kpi-total').textContent = items.length;
  document.querySelector('#kpi-complete').textContent = items.filter(item => item.status === 'CONFIRMED').length;
  document.querySelector('#kpi-failed').textContent = items.filter(item => item.status === 'FAILED').length;
  document.querySelector('#orders-table').innerHTML = visible.length ? `<table class="data-table"><thead><tr><th>Order</th><th>Customer</th><th>Total</th><th>Result</th><th>What happened</th></tr></thead><tbody>${visible.map(item => `<tr class="order-row ${selectedOrderId === item.order_id ? 'selected' : ''}" data-order-id="${escapeHtml(item.order_id)}"><td class="mono">${escapeHtml(item.order_id.slice(0, 8))}</td><td>${escapeHtml(item.customer_id)}</td><td>${money(item.amount_cents)}</td><td><span class="status ${item.status}">${friendlyStatus(item.status)}</span></td><td><div class="timeline">${item.history.map(entry => `<span>${friendlyStatus(entry.status)}</span>`).join('')}</div></td></tr>`).join('')}</tbody></table>` : '<p class="muted">No matching orders. Try another search or filter.</p>';
  document.querySelectorAll('.order-row').forEach(row => row.addEventListener('click', () => showOrderDetail(items.find(item => item.order_id === row.dataset.orderId))));
  if (selectedOrderId) showOrderDetail(items.find(item => item.order_id === selectedOrderId));
}
function renderPayments(items) {
  document.querySelector('#payments-table').innerHTML = items.length ? `<table class="data-table"><thead><tr><th>Payment</th><th>Order</th><th>Amount</th><th>Result</th><th>Note</th></tr></thead><tbody>${items.map(item => `<tr><td class="mono">${escapeHtml(item.payment_id.slice(0, 8))}</td><td class="mono">${escapeHtml(item.order_id.slice(0, 8))}</td><td>${money(item.amount_cents)}</td><td><span class="status ${item.status === 'COMPLETED' ? 'CONFIRMED' : 'FAILED'}">${item.status === 'COMPLETED' ? 'Accepted' : 'Declined'}</span></td><td>${escapeHtml(item.reason || 'Payment accepted')}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">No payments yet.</p>';
}

function friendlyStatus(status) {
  return { PENDING: 'In progress', INVENTORY_RESERVED: 'Stock held', CONFIRMED: 'Complete', FAILED: 'Not completed', INVENTORY_RELEASED: 'Stock returned' }[status] || status.replaceAll('_', ' ').toLowerCase();
}

function showOrderDetail(order) {
  if (!order) return;
  selectedOrderId = order.order_id;
  const detail = document.querySelector('#order-detail');
  const reason = order.failure_reason ? `<div class="detail-note"><strong>Why it stopped:</strong> ${escapeHtml(order.failure_reason.replaceAll('_', ' ').toLowerCase())}</div>` : '';
  detail.innerHTML = `<div class="panel-heading"><div><p class="eyebrow">ORDER DETAILS</p><h2>${escapeHtml(order.customer_id)}’s order</h2><p class="panel-help">Reference <span class="mono">${escapeHtml(order.order_id.slice(0, 12))}</span> · ${money(order.amount_cents)}</p></div><span class="status ${order.status}">${friendlyStatus(order.status)}</span></div><div class="journey">${order.history.map((entry, index) => `<div class="journey-step"><span class="journey-dot ${index === order.history.length - 1 ? 'current' : ''}">${index + 1}</span><div><strong>${friendlyStatus(entry.status)}</strong><small>${new Date(entry.at).toLocaleString()}</small></div></div>`).join('')}</div>${reason}`;
  document.querySelectorAll('.order-row').forEach(row => row.classList.toggle('selected', row.dataset.orderId === order.order_id));
  detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
    amount_cents: Math.round(Number(document.querySelector('#amount-dollars').value) * 100),
    force_payment_failure: document.querySelector('#force-failure').checked
  };
  try {
    const order = await getJson(`${services.order}/orders`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    document.querySelector('#order-result').className = 'result';
    document.querySelector('#order-result').innerHTML = `<strong>Order received</strong><p>We are checking stock and payment now.</p><div class="timeline">${order.history.map(entry => `<span>${friendlyStatus(entry.status)}</span>`).join('')}</div>`;
    notice('Order received; updating its progress');
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
document.querySelector('#order-search').addEventListener('input', () => renderOrders(allOrders));
document.querySelector('#order-filter').addEventListener('change', () => renderOrders(allOrders));
const scenarios = {
  success: { sku: 'SKU-1', quantity: 1, dollars: '10.00', failure: false },
  payment: { sku: 'SKU-1', quantity: 1, dollars: '20.00', failure: true },
  stock: { sku: 'SKU-5', quantity: 10, dollars: '10.00', failure: false }
};
document.querySelectorAll('[data-scenario]').forEach(button => button.addEventListener('click', () => {
  const scenario = scenarios[button.dataset.scenario];
  document.querySelector('#sku').value = scenario.sku;
  document.querySelector('#quantity').value = scenario.quantity;
  document.querySelector('#amount-dollars').value = scenario.dollars;
  document.querySelector('#force-failure').checked = scenario.failure;
  document.querySelectorAll('[data-scenario]').forEach(item => item.classList.toggle('active', item === button));
  notice(`${button.querySelector('strong').textContent} selected`);
}));
refreshData = async function refreshDashboard() {
  try {
    const [stock, orders, payments] = await Promise.all([
      getJson(`${services.inventory}/admin/stock`, { headers: adminHeaders() }),
      getJson(`${services.order}/admin/orders?limit=20`, { headers: adminHeaders() }),
      getJson(`${services.payment}/admin/payments?limit=20`, { headers: adminHeaders() })
    ]);
    allOrders = orders;
    renderStock(stock); renderOrders(allOrders); renderPayments(payments);
    document.querySelector('#last-refresh').textContent = `Updated ${new Date().toLocaleTimeString()}`;
    notice('Dashboard synchronized');
  } catch (error) { notice(`Could not load admin data: ${error.message}`, true); }
  await refreshHealth();
};
refreshData();
setInterval(refreshData, 15000);
