<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>SAUDE Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .chat-container { height: 500px; overflow-y: auto; }
    .user-message { background:#2563eb;color:#fff;align-self:flex-end;border-radius:1.5rem 1.5rem .5rem 1.5rem;padding:.75rem 1.25rem;max-width:70%;}
    .agent-message { background:#e5e7eb;color:#1f2937;border-radius:1.5rem 1.5rem 1.5rem .5rem;padding:.75rem 1.25rem;max-width:70%;}
  </style>
</head>
<body class="bg-gray-100 text-gray-800">
  <div class="max-w-7xl mx-auto p-4 md:p-8">
    <!-- Header -->
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-3xl font-bold text-gray-800">SAUDE MVP</h1>
      <nav class="flex space-x-6">
        <a href="#dashboard"    id="nav-dashboard"    class="text-gray-700 hover:text-blue-600 font-medium border-b-2 border-transparent">DASHBOARD</a>
        <a href="#pipelines"    id="nav-pipelines"    class="text-gray-700 hover:text-blue-600 font-medium border-b-2 border-transparent">PIPELINES</a>
        <a href="#chat"         id="nav-chat"         class="text-gray-700 hover:text-blue-600 font-medium border-b-2 border-transparent">CHATBOT</a>
        <a href="#architecture" id="nav-architecture" class="text-gray-700 hover:text-blue-600 font-medium border-b-2 border-transparent">ARCHITECTURE</a>
        <a href="#logs"         id="nav-logs"         class="text-gray-700 hover:text-blue-600 font-medium border-b-2 border-transparent">LOGS</a>
      </nav>
    </div>

    <div id="content-container">
      <!-- Dashboard -->
      <div id="tab-dashboard" class="tab-pane active">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-6 mb-8">
          <div class="bg-white rounded-lg shadow-sm p-6 text-center">
            <div class="text-sm text-gray-500">SUCCESS</div>
            <div id="kpi-success" class="text-3xl font-bold mt-2 text-green-600">—</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-6 text-center">
            <div class="text-sm text-gray-500">MTTR</div>
            <div id="kpi-mttr" class="text-3xl font-bold mt-2">—</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-6 text-center">
            <div class="text-sm text-gray-500">OPEN ALERTS</div>
            <div id="kpi-open" class="text-3xl font-bold mt-2 text-yellow-500">—</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-6 text-center">
            <div class="text-sm text-gray-500">FAILED RUNS</div>
            <div id="kpi-failed" class="text-3xl font-bold mt-2 text-red-600">—</div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div class="bg-white rounded-lg shadow-sm p-6">
            <h2 class="text-xl font-semibold mb-4">Products by Number of Resources</h2>
            <div class="relative w-full h-96"><canvas id="resourcesChart"></canvas></div>
            <div id="chartError" class="text-sm text-red-600 mt-3 hidden">Could not load resource summary.</div>
          </div>

          <div class="bg-white rounded-lg shadow-sm p-6">
            <h2 class="text-xl font-semibold mb-4">Last SRE Decisions</h2>
            <div class="overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Pipeline</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Category</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                  </tr>
                </thead>
                <tbody id="decisions-table-body" class="bg-white divide-y divide-gray-200"></tbody>
              </table>
              <div id="decisions-empty" class="text-sm text-gray-500 mt-3 hidden">No recent decisions.</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Pipelines -->
      <div id="tab-pipelines" class="tab-pane">
        <div class="bg-white rounded-lg shadow-sm">
          <div class="p-6 flex flex-col sm:flex-row justify-between items-center gap-4">
            <h3 class="text-xl font-semibold">Pipeline Events</h3>
            <div class="flex gap-2 sm:gap-3 items-center w-full sm:w-auto">
              <input id="pipelineFilter" placeholder="Filter by pipeline name"
                     class="px-4 py-2 border rounded-lg w-full sm:w-64" />
              <button onclick="loadFeed()" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Refresh</button>
            </div>
          </div>
          <div class="p-6">
            <div class="overflow-x-auto">
              <table id="pipelineFeed" class="min-w-full divide-y divide-gray-200">
                <thead>
                  <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time (UTC)</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Pipeline</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Category</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Why</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Run Id</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Durable</th>
                  </tr>
                </thead>
                <tbody></tbody>
              </table>
              <div id="emptyState" class="mt-4 text-center text-gray-500 hidden">No events yet.</div>
              <div id="feedError" class="mt-4 text-center text-red-600 hidden">Could not load pipeline feed.</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Chatbot -->
      <div id="tab-chat" class="tab-pane">
        <div class="bg-white rounded-lg shadow-sm p-6">
          <h2 class="text-xl font-semibold mb-4">Chat with Agent-Info</h2>
          <div id="chat-window" class="chat-container flex flex-col space-y-4 p-4 bg-gray-50 rounded-lg mb-4">
            <div class="flex"><div class="agent-message">How can I help? Try asking "list vms" or "triage".</div></div>
          </div>
          <form id="chat-form" class="flex items-center gap-4">
            <input type="text" id="chat-input" placeholder="Ask a question about your infra..."
                   class="flex-grow px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
            <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Send</button>
          </form>
        </div>
      </div>

      <!-- Architecture -->
      <div id="tab-architecture" class="tab-pane">
        <h2 class="text-3xl font-bold text-center mb-6 text-gray-800">SAUDE Architecture & Documentation</h2>
        <div class="bg-white rounded-lg shadow-sm p-6 md:p-10">
          <p>The SAUDE application is a lightweight web façade with serverless agents for triage and infra insights.</p>
          <div class="mt-8">
            <h3 class="text-2xl font-bold">Key Components</h3>
            <ul class="list-disc list-inside space-y-2">
              <li><strong class="text-blue-600">SAUDE Web App (Flask)</strong> — dashboard + webhook + AOAI classify.</li>
              <li><strong class="text-blue-600">Agent-SRE-Func</strong> — Durable Functions triage flows.</li>
              <li><strong class="text-blue-600">Agent-Info-Func</strong> — inventory/info via Resource Graph.</li>
              <li><strong class="text-blue-600">Azure Monitor</strong> — ADF failure alerts → webhook.</li>
              <li><strong class="text-blue-600">Azure Table Storage</strong> — transcripts & decisions.</li>
            </ul>
          </div>
          <div class="mt-8">
            <h3 class="text-2xl font-bold">Workflow</h3>
            <ol class="list-decimal list-inside space-y-2">
              <li>ADF pipeline fails → Azure Monitor alert.</li>
              <li>Action Group posts Common Alert Schema to <code>/alerts/adf</code>.</li>
              <li>AOAI classifies → retryable/FileNotFound → Agent-SRE; otherwise notify.</li>
              <li>Audit written to Table Storage; dashboard shows status.</li>
            </ol>
          </div>
        </div>
      </div>

      <!-- Logs -->
      <div id="tab-logs" class="tab-pane">
        <div class="bg-white rounded-lg shadow-sm">
          <div class="p-6 flex justify-between items-center">
            <h3 class="text-xl font-semibold">API Logs</h3>
            <button onclick="loadLogs()" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Refresh</button>
          </div>
          <div class="p-6">
            <div class="overflow-x-auto">
              <table id="api-logs-table" class="min-w-full divide-y divide-gray-200">
                <thead>
                  <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Endpoint</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Method</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status Code</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duration (ms)</th>
                  </tr>
                </thead>
                <tbody></tbody>
              </table>
              <div id="emptyLogsState" class="mt-4 text-center text-gray-500 hidden">No API logs yet.</div>
              <div id="logsError" class="mt-4 text-center text-red-600 hidden">Could not load logs.</div>
            </div>
          </div>
        </div>
      </div>
    </div> <!-- /content -->
  </div> <!-- /container -->

  <script>
    // ---------- helpers ----------
    function escapeHTML(s){return (s??"").toString()
      .replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");}

    // ---------- tabs ----------
    const tabs = {
      dashboard: document.getElementById('tab-dashboard'),
      pipelines: document.getElementById('tab-pipelines'),
      chat: document.getElementById('tab-chat'),
      architecture: document.getElementById('tab-architecture'),
      logs: document.getElementById('tab-logs')
    };
    const navs = {
      dashboard: document.getElementById('nav-dashboard'),
      pipelines: document.getElementById('nav-pipelines'),
      chat: document.getElementById('nav-chat'),
      architecture: document.getElementById('nav-architecture'),
      logs: document.getElementById('nav-logs')
    };
    function activateTab(tabName){
      for (const name in tabs){
        tabs[name].classList.remove('active');
        navs[name].classList.remove('border-blue-600','font-bold');
        navs[name].classList.add('border-transparent','font-medium');
      }
      tabs[tabName]?.classList.add('active');
      navs[tabName]?.classList.add('border-blue-600','font-bold');
      navs[tabName]?.classList.remove('border-transparent','font-medium');
    }
    const initialTab = (window.location.hash.substring(1) || 'dashboard');
    activateTab(initialTab);
    for (const name in navs){
      navs[name].addEventListener('click', (e)=>{
        e.preventDefault();
        window.location.hash = name;
        activateTab(name);
      });
    }

    // ---------- dashboard: resources chart + KPIs ----------
    let resourcesChart;
    async function loadDashboardData(){
      const apiBaseUrl = window.location.origin;
      try{
        const r = await fetch(`${apiBaseUrl}/api/resources/summary`);
        if(!r.ok) throw new Error(`status ${r.status}`);
        const data = await r.json();

        // KPIs (optional in your API; show placeholders if missing)
        document.getElementById('kpi-success').textContent = data.kpi_success ?? '—';
        document.getElementById('kpi-mttr').textContent    = data.kpi_mttr ?? '—';
        document.getElementById('kpi-open').textContent    = data.kpi_open_alerts ?? '—';
        document.getElementById('kpi-failed').textContent  = data.kpi_failed_runs ?? '—';

        const items = data.items || [];
        const labels = items.map(i=>i.product);
        const total  = items.map(i=>i.azure_total);
        const tf     = items.map(i=>i.created_by_terraform);

        const ctx = document.getElementById('resourcesChart').getContext('2d');
        if (resourcesChart) resourcesChart.destroy();
        resourcesChart = new Chart(ctx,{
          type:'bar',
          data:{
            labels,
            datasets:[
              {label:'Total Azure', data: total},
              {label:'Created by Terraform', data: tf}
            ]
          },
          options:{
            responsive:true, maintainAspectRatio:false,
            scales:{ x:{stacked:true}, y:{stacked:true} }
          }
        });
        document.getElementById('chartError').classList.add('hidden');
      }catch(e){
        console.error('resources/summary error:', e);
        document.getElementById('chartError').classList.remove('hidden');
      }
    }

    // ---------- dashboard: last decisions ----------
    async function loadLastDecisions(){
      const apiBaseUrl = window.location.origin;
      try{
        const r = await fetch(`${apiBaseUrl}/api/sre/actions?top=5`);
        if(!r.ok) throw new Error(`status ${r.status}`);
        const items = await r.json();

        const tbody = document.getElementById('decisions-table-body');
        tbody.innerHTML = '';
        if (!items.length){
          document.getElementById('decisions-empty').classList.remove('hidden');
          return;
        }
        document.getElementById('decisions-empty').classList.add('hidden');

        for(const it of items){
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${escapeHTML(it.ts || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(it.pipeline_name || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(it.category || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(it.action || '')}</td>
          `;
          tbody.appendChild(tr);
        }
      }catch(e){
        console.error('last decisions error:', e);
        // keep the widget quiet; optional: show a small error label
      }
    }

    // ---------- pipelines feed ----------
    async function loadFeed(){
      const apiBaseUrl = window.location.origin;
      const pipeline = document.getElementById('pipelineFilter').value.trim();
      const q = pipeline ? ('?pipeline=' + encodeURIComponent(pipeline)) : '';
      const tbody = document.querySelector('#pipelineFeed tbody');
      tbody.innerHTML = '';
      try{
        const res = await fetch(`${apiBaseUrl}/api/sre/actions` + q);
        if(!res.ok) throw new Error(`status ${res.status}`);
        const items = await res.json();

        if(!items.length){
          document.getElementById('emptyState').classList.remove('hidden');
          document.getElementById('feedError').classList.add('hidden');
          return;
        }
        document.getElementById('emptyState').classList.add('hidden');
        document.getElementById('feedError').classList.add('hidden');

        for(const it of items){
          const statusUrl = it.instance_id ? `${apiBaseUrl}/status/${encodeURIComponent(it.instance_id)}` : '';
          const why = escapeHTML((it.why || '').slice(0,120));
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">${escapeHTML(it.ts || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(it.pipeline_name || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(it.category || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(it.action || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(it.status || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500" title="${why}">${why}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(it.run_id || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm">
              ${statusUrl ? `<a href="${statusUrl}" target="_blank" class="text-blue-600 hover:text-blue-800">status</a>` : ''}
            </td>
          `;
          tbody.appendChild(tr);
        }
      }catch(e){
        console.error('pipeline feed error:', e);
        document.getElementById('feedError').classList.remove('hidden');
        document.getElementById('emptyState').classList.add('hidden');
      }
    }

    // ---------- logs ----------
    async function loadLogs(){
      const apiBaseUrl = window.location.origin;
      const tbody = document.querySelector('#api-logs-table tbody');
      tbody.innerHTML = '';
      try{
        const res = await fetch(`${apiBaseUrl}/api/logs/actions`);
        if(!res.ok) throw new Error(`status ${res.status}`);
        const data = await res.json();
        const items = Array.isArray(data) ? data : (data.items || []);
        if(!items.length){
          document.getElementById('emptyLogsState').classList.remove('hidden');
          document.getElementById('logsError').classList.add('hidden');
          return;
        }
        document.getElementById('emptyLogsState').classList.add('hidden');
        document.getElementById('logsError').classList.add('hidden');

        for (const log of items){
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${escapeHTML(log.createdAt || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(log.endpoint || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(log.method || '')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHTML(String(log.statusCode ?? ''))}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${log.durationMs != null ? escapeHTML(Number(log.durationMs).toFixed(2)) : ''}</td>
          `;
          tbody.appendChild(tr);
        }
      }catch(e){
        console.error('logs error:', e);
        document.getElementById('logsError').classList.remove('hidden');
        document.getElementById('emptyLogsState').classList.add('hidden');
      }
    }

    // ---------- chat ----------
    const chatForm   = document.getElementById('chat-form');
    const chatInput  = document.getElementById('chat-input');
    const chatWindow = document.getElementById('chat-window');

    chatForm.addEventListener('submit', async (e)=>{
      e.preventDefault();
      const userMessage = chatInput.value.trim();
      if(!userMessage) return;

      const userMsgDiv = document.createElement('div');
      userMsgDiv.className = 'flex justify-end';
      userMsgDiv.innerHTML = `<div class="user-message">${escapeHTML(userMessage)}</div>`;
      chatWindow.appendChild(userMsgDiv);
      chatWindow.scrollTop = chatWindow.scrollHeight;
      chatInput.value = '';

      try{
        const apiBaseUrl = window.location.origin;
        const resp = await fetch(`${apiBaseUrl}/chat`, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ message: userMessage })
        });
        const data = await resp.json();
        const agentMsgDiv = document.createElement('div');
        agentMsgDiv.className = 'flex';
        agentMsgDiv.innerHTML = `<div class="agent-message">${escapeHTML(String(data.reply ?? ''))}</div>`;
        chatWindow.appendChild(agentMsgDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
      }catch(err){
        const errDiv = document.createElement('div');
        errDiv.className = 'flex';
        errDiv.innerHTML = `<div class="agent-message text-red-500">Error: Could not connect to the agent.</div>`;
        chatWindow.appendChild(errDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
      }
    });

    // ---------- initial loads + refresh timers ----------
    loadDashboardData();
    loadLastDecisions();
    loadFeed();
    loadLogs();

    setInterval(loadLastDecisions, 30000);
    setInterval(loadFeed,        10000);
    setInterval(loadLogs,        10000);
  </script>
</body>
</html>