// Copyright (C) 2026 Pilipala
// SPDX-License-Identifier: GPL-3.0-only
'use strict';

(function () {
  const API_BASE = '/api/ai-console';
  const CSRF_HEADERS = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'MarcoAiConsole',
  };

  const state = {
    plat: 'all',
    daysMode: '30',
    sessionExpiresAt: null,
    latestTokens: [],
    sessionHistory: [],
    ttlTimer: null,
    toastTimer: null,
  };

  const $ = (id) => document.getElementById(id);

  function showToast(msg) {
    const el = $('toast');
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 2200);
  }

  function showError(id, msg) {
    const el = $(id);
    if (!msg) {
      el.hidden = true;
      el.textContent = '';
    } else {
      el.textContent = msg;
      el.hidden = false;
    }
  }

  async function apiGet(path) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  }

  async function apiPost(path, body) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: CSRF_HEADERS,
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  }

  function formatDateTime(isoOrEpoch) {
    if (!isoOrEpoch) return '永久有效';
    const d = typeof isoOrEpoch === 'number' ? new Date(isoOrEpoch * 1000) : new Date(isoOrEpoch);
    if (Number.isNaN(d.getTime())) return '—';
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function platLabel(plat) {
    switch (plat) {
      case 'ios': return 'iOS / iPadOS';
      case 'windows': return 'Windows';
      case 'android': return 'Android 手机';
      default: return '三端通用';
    }
  }

  async function copyText(text, successMsg) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        showToast(successMsg || '已复制到剪贴板');
        return;
      }
    } catch {
      // Fallback below.
    }
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.className = 'sr-copy-buffer';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(successMsg || '已复制到剪贴板');
  }

  function updateSessionTtl() {
    const ttlEl = $('session-ttl');
    if (!state.sessionExpiresAt) {
      ttlEl.textContent = '';
      return;
    }
    const remain = state.sessionExpiresAt - Math.floor(Date.now() / 1000);
    if (remain <= 0) {
      clearInterval(state.ttlTimer);
      setView('login');
      showError('login-error', '登录会话已过期，请重新验证密码与动态码');
      return;
    }
    const h = Math.floor(remain / 3600);
    const m = Math.floor((remain % 3600) / 60);
    ttlEl.textContent = h > 0 ? `会话剩余 ${h}h ${m}m` : `会话剩余 ${Math.max(1, m)}m`;
  }

  function updateKeyBadge(pubkeyPrefix, keyMatchesOfficial) {
    const badge = $('key-badge');
    if (keyMatchesOfficial) {
      badge.className = 'badge';
      badge.textContent = `官方公钥就绪 · ${pubkeyPrefix}…`;
    } else {
      badge.className = 'badge badge-warn';
      badge.textContent = `非官方公钥 · ${pubkeyPrefix}…`;
    }
  }

  function setView(mode, info = {}) {
    $('unconfigured-card').hidden = mode !== 'unconfigured';
    $('login-card').hidden = mode !== 'login';
    $('workbench').hidden = mode !== 'workbench';
    $('session-bar').hidden = mode !== 'workbench';

    if (mode === 'unconfigured') {
      const list = $('missing-list');
      list.textContent = '';
      for (const name of info.missingSecrets || []) {
        const li = document.createElement('li');
        li.textContent = name;
        list.appendChild(li);
      }
    }
    if (mode === 'workbench') {
      state.sessionExpiresAt = info.expiresAt || null;
      updateKeyBadge(info.pubkeyPrefix || '', Boolean(info.keyMatchesOfficial));
      clearInterval(state.ttlTimer);
      updateSessionTtl();
      state.ttlTimer = setInterval(updateSessionTtl, 30000);
    } else {
      clearInterval(state.ttlTimer);
      state.latestTokens = [];
      state.sessionHistory = [];
      renderTokenOutput();
      renderHistory();
    }
  }

  async function bootstrap() {
    const { ok, data } = await apiGet('/status');
    if (!ok) {
      setView('login');
      showError('login-error', '无法连接后端签发服务，请稍后刷新重试');
      return;
    }
    if (!data.configured) {
      setView('unconfigured', data);
      return;
    }
    if (data.authenticated) {
      setView('workbench', data);
    } else {
      setView('login', data);
      $('password-input').focus();
    }
  }

  function syncPlatformUi() {
    for (const btn of $('plat-group').querySelectorAll('.pill')) {
      btn.classList.toggle('is-active', btn.dataset.plat === state.plat);
    }
    $('min-vc-field').hidden = state.plat !== 'android';
    if (state.plat !== 'android') {
      $('min-vc-input').value = '0';
    }
  }

  function syncDaysUi() {
    for (const btn of $('days-group').querySelectorAll('.pill')) {
      btn.classList.toggle('is-active', btn.dataset.days === state.daysMode);
    }
    $('custom-days-wrap').hidden = state.daysMode !== 'custom';
  }

  function getSelectedDays() {
    if (state.daysMode === 'custom') {
      return parseInt($('custom-days-input').value, 10);
    }
    return parseInt(state.daysMode, 10);
  }

  function buildShareCopy(item) {
    const c = item.claims;
    const expStr = c.exp > 0 ? formatDateTime(c.exp) : '永久有效';
    const perms = c.exp_oauth ? '自备 API + 订阅 OAuth' : '自备 API';
    return [
      'Marco Movie「AI 观影实验室」内测解锁口令',
      `适用端：${platLabel(c.plat)} ｜ 有效期：${expStr} ｜ 权限：${perms}`,
      '',
      item.token,
      '',
      '使用方式：打开 App → 设置 → 通用 → AI 观影实验室 → 粘贴上方口令即可离线解锁。',
    ].join('\n');
  }

  function renderTokenOutput() {
    const list = $('token-list');
    const empty = $('output-empty');
    const batchActions = $('batch-actions');
    const summary = $('output-summary');
    list.textContent = '';

    if (!state.latestTokens.length) {
      list.hidden = true;
      batchActions.hidden = true;
      empty.hidden = false;
      summary.textContent = '点击左侧按钮由服务端 Ed25519 实时签名';
      return;
    }

    empty.hidden = true;
    list.hidden = false;
    batchActions.hidden = state.latestTokens.length < 2;
    summary.textContent = `已签发 ${state.latestTokens.length} 枚官方 Ed25519 签名口令`;

    for (const item of state.latestTokens) {
      const c = item.claims;
      const box = document.createElement('div');
      box.className = 'token-item';

      const meta = document.createElement('div');
      meta.className = 'token-meta';

      const addPill = (txt, cls) => {
        const s = document.createElement('span');
        s.className = cls ? `meta-pill ${cls}` : 'meta-pill';
        s.textContent = txt;
        meta.appendChild(s);
      };
      addPill(platLabel(c.plat));
      addPill(c.exp > 0 ? `至 ${formatDateTime(c.exp)}` : '永久有效');
      addPill(`tag: ${c.tag}`);
      if (c.exp_oauth) addPill('含订阅 OAuth', 'oauth');
      if (c.shared) addPill('频道共享');
      if (c.min_vc) addPill(`min_vc >= ${c.min_vc}`);

      const code = document.createElement('code');
      code.className = 'token-code';
      code.textContent = item.token;

      const actions = document.createElement('div');
      actions.className = 'btn-row';

      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = 'btn btn-primary btn-sm';
      copyBtn.textContent = '一键复制口令';
      copyBtn.addEventListener('click', () => copyText(item.token, '已复制纯口令'));

      const shareBtn = document.createElement('button');
      shareBtn.type = 'button';
      shareBtn.className = 'btn btn-ghost btn-sm';
      shareBtn.textContent = '复制群发话术';
      shareBtn.addEventListener('click', () => copyText(buildShareCopy(item), '已复制群发话术'));

      actions.appendChild(copyBtn);
      actions.appendChild(shareBtn);

      box.appendChild(meta);
      box.appendChild(code);
      box.appendChild(actions);
      list.appendChild(box);
    }
  }

  function renderHistory() {
    const box = $('history-box');
    const ul = $('history-list');
    ul.textContent = '';
    if (!state.sessionHistory.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    for (const h of state.sessionHistory) {
      const li = document.createElement('li');
      li.textContent = `${h.time} | ${h.plat} | ${h.exp} | ${h.tag}${h.oauth ? ' | OAuth' : ''} | ${h.tail}`;
      ul.appendChild(li);
    }
  }

  function renderVerifyResult(result) {
    const box = $('verify-result');
    box.textContent = '';
    box.hidden = false;
    box.className = `verify-result ${result.valid ? 'is-valid' : 'is-invalid'}`;

    const title = document.createElement('strong');
    title.textContent = result.valid ? `✅ ${result.message}` : `❌ ${result.message}`;
    box.appendChild(title);

    if (result.claims) {
      const c = result.claims;
      const grid = document.createElement('div');
      grid.className = 'verify-grid';
      const pairs = [
        ['签名校验', result.signatureValid ? '通过（官方 Ed25519）' : '失败'],
        ['适用平台', `${platLabel(c.plat)} (${c.plat || 'all'})`],
        ['批次标签', c.tag || '—'],
        ['签发时间', c.iat ? formatDateTime(c.iat) : '—'],
        ['过期时间', c.exp > 0 ? `${formatDateTime(c.exp)}${result.expired ? '（已过期）' : ''}` : '永久有效'],
        ['订阅 OAuth 权限', c.exp_oauth ? '允许' : '未开启'],
        ['口令类型', c.shared ? '频道共享' : '个人专属'],
        ['随机 Nonce', c.n || '—'],
      ];
      if (c.min_vc) pairs.push(['最低版本码', String(c.min_vc)]);
      for (const [k, v] of pairs) {
        const kv = document.createElement('div');
        kv.className = 'verify-kv';
        const span = document.createElement('span');
        span.textContent = k;
        const val = document.createElement('strong');
        val.textContent = v;
        kv.appendChild(span);
        kv.appendChild(val);
        grid.appendChild(kv);
      }
      box.appendChild(grid);
    }
  }

  // Event wiring
  $('toggle-pw-btn').addEventListener('click', () => {
    const inp = $('password-input');
    const isPw = inp.type === 'password';
    inp.type = isPw ? 'text' : 'password';
    $('toggle-pw-btn').textContent = isPw ? '隐藏' : '显示';
  });

  $('totp-input').addEventListener('input', (e) => {
    e.target.value = e.target.value.replace(/\D+/g, '').slice(0, 6);
  });

  $('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    showError('login-error', '');
    const password = $('password-input').value;
    const totp = $('totp-input').value.trim();
    const shortSession = $('short-session-check').checked;
    if (!password) {
      showError('login-error', '请输入管理员密码');
      return;
    }
    if (!/^\d{6}$/.test(totp)) {
      showError('login-error', '请输入 6 位数字动态验证码');
      return;
    }
    const btn = $('login-submit');
    btn.disabled = true;
    btn.textContent = '验证中…';
    try {
      const { ok, data } = await apiPost('/login', { password, totp, shortSession });
      if (!ok) {
        showError('login-error', data.message || '登录验证失败');
        $('totp-input').value = '';
        $('totp-input').focus();
        return;
      }
      $('password-input').value = '';
      $('totp-input').value = '';
      setView('workbench', data);
      showToast('已通过双因素验证');
    } finally {
      btn.disabled = false;
      btn.textContent = '验证并进入控制台';
    }
  });

  $('logout-btn').addEventListener('click', async () => {
    await apiPost('/logout', {});
    setView('login');
    showToast('已安全退出并清除会话');
  });

  for (const tabBtn of document.querySelectorAll('.tab')) {
    tabBtn.addEventListener('click', () => {
      const target = tabBtn.dataset.tab;
      for (const b of document.querySelectorAll('.tab')) {
        const active = b.dataset.tab === target;
        b.classList.toggle('is-active', active);
        b.setAttribute('aria-selected', active ? 'true' : 'false');
      }
      $('panel-issue').hidden = target !== 'issue';
      $('panel-verify').hidden = target !== 'verify';
    });
  }

  for (const btn of $('plat-group').querySelectorAll('.pill')) {
    btn.addEventListener('click', () => {
      state.plat = btn.dataset.plat;
      syncPlatformUi();
    });
  }

  for (const btn of $('days-group').querySelectorAll('.pill')) {
    btn.addEventListener('click', () => {
      state.daysMode = btn.dataset.days;
      syncDaysUi();
    });
  }

  const PRESETS = {
    owner: { plat: 'all', daysMode: '0', tag: 'PILIPALA', count: 1, expOAuth: true, shared: false },
    'ios-beta': { plat: 'ios', daysMode: '30', tag: 'ios-beta', count: 1, expOAuth: true, shared: false },
    channel: { plat: 'all', daysMode: '7', tag: 'channel', count: 1, expOAuth: false, shared: true },
    personal: { plat: 'all', daysMode: '30', tag: 'beta', count: 1, expOAuth: false, shared: false },
  };

  for (const chip of document.querySelectorAll('.preset-chip')) {
    chip.addEventListener('click', () => {
      const p = PRESETS[chip.dataset.preset];
      if (!p) return;
      state.plat = p.plat;
      state.daysMode = p.daysMode;
      $('tag-input').value = p.tag;
      $('count-input').value = String(p.count);
      $('exp-oauth-check').checked = p.expOAuth;
      $('shared-check').checked = p.shared;
      syncPlatformUi();
      syncDaysUi();
      showToast('已套用快捷预设');
    });
  }

  $('issue-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    showError('issue-error', '');
    const days = getSelectedDays();
    const tag = $('tag-input').value.trim();
    const count = parseInt($('count-input').value, 10);
    const minVc = state.plat === 'android' ? parseInt($('min-vc-input').value || '0', 10) : 0;
    const expOAuth = $('exp-oauth-check').checked;
    const shared = $('shared-check').checked;

    const btn = $('issue-submit');
    btn.disabled = true;
    btn.textContent = '服务端签名中…';
    try {
      const { ok, status, data } = await apiPost('/issue', {
        plat: state.plat,
        days,
        tag,
        count,
        minVc,
        expOAuth,
        shared,
      });
      if (status === 401) {
        setView('login');
        showError('login-error', data.message || '会话已失效，请重新登录');
        return;
      }
      if (!ok) {
        showError('issue-error', data.message || '签发失败');
        return;
      }
      state.latestTokens = data.tokens || [];
      const nowStr = new Date().toLocaleTimeString('zh-CN', { hour12: false });
      for (const item of state.latestTokens) {
        const c = item.claims;
        state.sessionHistory.unshift({
          time: nowStr,
          plat: c.plat,
          exp: c.exp > 0 ? `${days}d` : '永久',
          tag: c.tag,
          oauth: Boolean(c.exp_oauth),
          tail: `…${item.token.slice(-6)}`,
        });
      }
      state.sessionHistory = state.sessionHistory.slice(0, 30);
      renderTokenOutput();
      renderHistory();
      showToast(`已生成 ${state.latestTokens.length} 枚签名口令`);
    } finally {
      btn.disabled = false;
      btn.textContent = '生成签名口令';
    }
  });

  $('copy-all-btn').addEventListener('click', () => {
    if (!state.latestTokens.length) return;
    copyText(state.latestTokens.map((t) => t.token).join('\n'), `已复制全部 ${state.latestTokens.length} 枚口令`);
  });

  $('download-txt-btn').addEventListener('click', () => {
    if (!state.latestTokens.length) return;
    const content = state.latestTokens.map((t) => t.token).join('\n') + '\n';
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `marco-ai-passcodes-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  $('clear-history-btn').addEventListener('click', () => {
    state.sessionHistory = [];
    renderHistory();
  });

  $('verify-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    showError('verify-error', '');
    const tokenText = $('verify-input').value.trim();
    const platform = $('verify-plat-select').value;
    if (!tokenText) {
      showError('verify-error', '请粘贴待验证的口令或文案');
      return;
    }
    const btn = $('verify-submit');
    btn.disabled = true;
    btn.textContent = '验签中…';
    try {
      const { ok, status, data } = await apiPost('/verify', { tokenText, platform });
      if (status === 401) {
        setView('login');
        showError('login-error', data.message || '会话已失效，请重新登录');
        return;
      }
      if (!ok) {
        showError('verify-error', data.message || '验签请求失败');
        return;
      }
      renderVerifyResult(data.result);
    } finally {
      btn.disabled = false;
      btn.textContent = '开始验签';
    }
  });

  syncPlatformUi();
  syncDaysUi();
  bootstrap();
})();
