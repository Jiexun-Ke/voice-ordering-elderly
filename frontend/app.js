import { createOrdering } from './ordering.js';

const copy = {
  en: {
    skip: 'Skip to menu options', brand: 'Menu helper', step: 'LET’S GET STARTED', headline: 'Let’s read <br />your menu.',
    intro: 'A little help with your next meal.<br />Choose how you’d like to open your menu.', options: 'Open a menu',
    scan: 'Scan QR code', scanHint: 'Use the code on your table', photo: 'Take menu photo', photoHint: 'Take a picture or choose a photo',
    link: 'Paste menu link', linkHint: 'Already have a link? Add it here', noMenu: 'Don’t have a menu handy?', sample: 'Try a sample menu',
    reassurance: 'Take your time. We’ll go one step at a time.', footer: 'A little easier. A little more independent.', help: 'Need a hand?', close: 'Close',
    linkIntro: 'Copy the restaurant’s menu link and paste it below.', linkLabel: 'Menu link', linkPlaceholder: 'https://restaurant.com/menu',
    saveLink: 'Use this link', invalidLink: 'Please enter a complete website link starting with https:// or http://.',
    linkSaved: 'Your menu link is ready.', analysisNotice: 'Reading and translating this menu will be available in the next step. For now, you can explore the sample menu.',
    photoIntro: 'Use a clear photo with the dish names and prices in view.', photoLabel: 'Choose a menu photo',
    photoReady: 'Your photo is ready.', photoError: 'Please choose a JPG, PNG, or WebP photo smaller than 10 MB.', photoAlt: 'Your selected menu photo',
    scanIntro: 'Point your camera at the QR code. Keep the whole code in view.', startCamera: 'Open camera',
    cameraFallback: 'This browser can’t scan QR codes here. Scan with your phone’s Camera app, then copy the menu link and paste it here.',
    cameraError: 'We couldn’t open your camera. Please check camera access, or paste your menu link instead.', cameraStarting: 'Opening camera…',
    scanning: 'Looking for a QR code…', cameraLabel: 'Live camera view for scanning a menu QR code', invalidQr: 'This code doesn’t contain a website link. Please try the menu’s QR code.',
    sampleTitle: 'Ah Seng Kopitiam', sampleBadge: 'SAMPLE MENU', sampleIntro: 'Have a look around. These dishes and prices are from our sample hawker menu.',
    sampleNote: 'This is a sample menu. Ordering and menu translation will be added next.', loading: 'Opening the sample menu…',
    loadError: 'The sample menu couldn’t load. Please try again.', retry: 'Try again', back: 'Back to menu options',
    helpTitle: 'Let’s take it one step at a time.', helpIntro: 'Choose the option that matches the menu you have.',
    helpSteps: ['A QR code on the table? Choose “Scan QR code”.', 'A printed menu? Choose “Take menu photo”.', 'A menu link in a message? Choose “Paste menu link”.'],
    listen: 'Read this aloud', stop: 'Stop reading', speechError: 'Reading aloud isn’t available here. You can follow the steps above.',
  },
  zh: {
    skip: '跳到菜单选项', brand: '菜单小帮手', step: '我们开始吧', headline: '一起看看<br />菜单吧。',
    intro: '点餐多一份帮助，用餐多一份轻松。<br />请选择打开菜单的方式。', options: '打开菜单',
    scan: '扫描二维码', scanHint: '扫描餐桌上的菜单二维码', photo: '拍摄菜单', photoHint: '拍一张照片，或从相册选择',
    link: '粘贴菜单链接', linkHint: '已有菜单链接？在这里添加', noMenu: '手边没有菜单？', sample: '试试示例菜单',
    reassurance: '不用着急，我们一步一步来。', footer: '轻松一点，自在一点。', help: '需要帮忙？', close: '关闭',
    linkIntro: '复制餐厅的菜单链接，然后粘贴到下方。', linkLabel: '菜单链接', linkPlaceholder: 'https://restaurant.com/menu',
    saveLink: '使用此链接', invalidLink: '请输入以 https:// 或 http:// 开头的完整网站链接。',
    linkSaved: '菜单链接已准备好。', analysisNotice: '读取和翻译菜单功能将在下一步加入。现在可以先试试示例菜单。',
    photoIntro: '请使用清晰的照片，确保能看清菜名和价格。', photoLabel: '选择菜单照片',
    photoReady: '菜单照片已准备好。', photoError: '请选择小于 10 MB 的 JPG、PNG 或 WebP 照片。', photoAlt: '您选择的菜单照片',
    scanIntro: '请将相机对准二维码，并确保整个二维码都在画面中。', startCamera: '打开相机',
    cameraFallback: '此浏览器暂时无法扫描二维码。请用手机相机扫描，然后复制菜单链接并粘贴到这里。',
    cameraError: '无法打开相机。请检查相机权限，或改用菜单链接。', cameraStarting: '正在打开相机……',
    scanning: '正在寻找二维码……', cameraLabel: '菜单二维码扫描相机画面', invalidQr: '这个二维码不含网站链接，请尝试扫描菜单的二维码。',
    sampleTitle: 'Ah Seng Kopitiam', sampleBadge: '示例菜单', sampleIntro: '先看看吧。以下菜品和价格来自我们的示例小贩菜单。',
    sampleNote: '这是一份示例菜单。点餐和菜单翻译功能将在之后加入。', loading: '正在打开示例菜单……',
    loadError: '暂时无法加载示例菜单，请重试。', retry: '重试', back: '返回菜单选项',
    helpTitle: '我们一步一步来。', helpIntro: '根据您手上的菜单，选择适合的方式。',
    helpSteps: ['餐桌上有二维码？请选择“扫描二维码”。', '手上有纸质菜单？请选择“拍摄菜单”。', '收到菜单链接？请选择“粘贴菜单链接”。'],
    listen: '朗读说明', stop: '停止朗读', speechError: '这里暂时无法朗读，您可以查看上面的说明。',
  },
};
let language = 'en';
try { language = localStorage.getItem('menu-helper-language') === 'zh' ? 'zh' : 'en'; } catch { /* Preferences are optional. */ }
const dialog = document.querySelector('#menu-dialog');
const content = document.querySelector('#dialog-content');
let stream = null;
let scanTimer = null;
let photoUrl = null;
let activePanel = null;
let panelVersion = 0;
const t = key => copy[language][key];
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const title = key => `<h2 id="dialog-title" tabindex="-1">${t(key)}</h2>`;
const sampleButton = () => `<button class="secondary-button" data-open="sample">${icon('menu')}${t('sample')}</button>`;
const ordering = createOrdering({ onHome: () => { document.querySelector('.sample-button')?.focus(); } });
function setLanguage(next) {
  language = next;
  document.documentElement.lang = next === 'zh' ? 'zh-Hans' : 'en';
  document.title = next === 'zh' ? '菜单小帮手 — 打开菜单' : 'Menu helper — Open your menu';
  document.querySelectorAll('[data-t]').forEach(el => { el.innerHTML = t(el.dataset.t); });
  document.querySelectorAll('[data-label]').forEach(el => el.setAttribute('aria-label', t(el.dataset.label)));
  document.querySelector('.brand').setAttribute('aria-label', t('brand'));
  document.querySelectorAll('[data-language]').forEach(el => { const active = el.dataset.language === next; el.classList.toggle('is-active', active); el.setAttribute('aria-pressed', String(active)); });
  try { localStorage.setItem('menu-helper-language', next); } catch { /* Continue without saving. */ }
  ordering.setLanguage(next);
}
function cleanup() {
  panelVersion++;
  clearTimeout(scanTimer);
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  if (photoUrl) URL.revokeObjectURL(photoUrl);
  photoUrl = null;
  window.speechSynthesis?.cancel();
}
function showPanel(panel) {
  cleanup();
  if (panel === 'sample') {
    if (dialog.open) dialog.close();
    activePanel = null;
    return ordering.open(language);
  }
  activePanel = panel;
  let ready;
  if (panel === 'link') {
    content.innerHTML = `${title('link')}<p>${t('linkIntro')}</p><form id="link-form" novalidate><label class="field-label" for="menu-url">${t('linkLabel')}</label><input class="text-input" id="menu-url" type="url" inputmode="url" autocomplete="url" placeholder="${t('linkPlaceholder')}" required aria-describedby="link-status" /><p id="link-status" role="status"></p><button class="primary-button" type="submit">${t('saveLink')}${icon('arrow')}</button></form>${sampleButton()}`;
  } else if (panel === 'photo') {
    content.innerHTML = `${title('photo')}<p>${t('photoIntro')}</p><label class="field-label" for="menu-photo">${t('photoLabel')}</label><input class="photo-input" id="menu-photo" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" /><div id="photo-result" aria-live="polite"></div>${sampleButton()}`;
  } else if (panel === 'scan') {
    content.innerHTML = `${title('scan')}<p>${t('scanIntro')}</p><div id="camera-container"></div><p id="camera-status" role="status"></p><button class="primary-button" id="start-camera">${icon('camera')}${t('startCamera')}</button><button class="secondary-button" data-open="link">${icon('link')}${t('link')}</button>`;
    if (!('BarcodeDetector' in window) || !navigator.mediaDevices?.getUserMedia) {
      document.querySelector('#camera-status').textContent = t('cameraFallback');
      document.querySelector('#start-camera').hidden = true;
    }
  } else if (panel === 'help') {
    content.innerHTML = `${title('helpTitle')}<p>${t('helpIntro')}</p><ol class="help-steps">${t('helpSteps').map(step => `<li>${step}</li>`).join('')}</ol><button class="primary-button" id="read-help">${icon('sound')}<span>${t('listen')}</span></button><p id="speech-status" role="status"></p>${sampleButton()}`;
  }
  if (!dialog.open) dialog.showModal();
  document.querySelector('#dialog-title')?.focus();
  return ready;
}
function parseMenuUrl(value) {
  const url = new URL(value.trim());
  if (!['https:', 'http:'].includes(url.protocol) || !url.hostname || url.username || url.password) throw new Error('Invalid URL');
  return url;
}
function acceptLink(url) {
  showPanel('link');
  document.querySelector('#menu-url').value = url.href;
  const status = document.querySelector('#link-status');
  status.className = 'notice';
  status.textContent = `${t('linkSaved')} ${t('analysisNotice')}`;
}
async function startCamera() {
  const version = panelVersion;
  const status = document.querySelector('#camera-status');
  const button = document.querySelector('#start-camera');
  button.disabled = true;
  status.textContent = t('cameraStarting');
  try {
    const formats = await BarcodeDetector.getSupportedFormats();
    if (!formats.includes('qr_code')) { status.textContent = t('cameraFallback'); button.hidden = true; return; }
    const camera = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
    if (version !== panelVersion) { camera.getTracks().forEach(track => track.stop()); return; }
    stream = camera;
    const video = document.createElement('video');
    video.className = 'camera-feed'; video.muted = true; video.playsInline = true; video.setAttribute('aria-label', t('cameraLabel')); video.srcObject = camera;
    document.querySelector('#camera-container').replaceChildren(video);
    await video.play();
    if (version !== panelVersion) return;
    status.textContent = t('scanning');
    button.hidden = true;
    const detector = new BarcodeDetector({ formats: ['qr_code'] });
    async function scan() {
      if (version !== panelVersion) return;
      try {
        const codes = await detector.detect(video);
        if (version !== panelVersion) return;
        if (codes.length) {
          try { acceptLink(parseMenuUrl(codes[0].rawValue)); return; }
          catch { status.textContent = t('invalidQr'); }
        }
      } catch { if (version === panelVersion) status.textContent = t('scanning'); }
      if (version === panelVersion) scanTimer = setTimeout(scan, 350);
    }
    scan();
  } catch {
    if (version === panelVersion) { stream?.getTracks().forEach(track => track.stop()); stream = null; status.textContent = t('cameraError'); button.disabled = false; }
  }
}
document.addEventListener('click', event => {
  const open = event.target.closest('[data-open]');
  if (open) Promise.resolve(showPanel(open.dataset.open)).catch(() => {});
  const lang = event.target.closest('[data-language]');
  if (lang) setLanguage(lang.dataset.language);
  if (event.target.closest('[data-close], #close-dialog')) dialog.close();
  if (event.target.closest('#help-button')) showPanel('help');
  if (event.target.closest('#start-camera')) startCamera();
  if (event.target.closest('#read-help')) {
    const button = document.querySelector('#read-help');
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) { document.querySelector('#speech-status').textContent = t('speechError'); return; }
    if (speechSynthesis.speaking || speechSynthesis.pending) { speechSynthesis.cancel(); button.querySelector('span').textContent = t('listen'); return; }
    const utterance = new SpeechSynthesisUtterance([t('helpIntro'), ...t('helpSteps')].join(' '));
    utterance.lang = language === 'zh' ? 'zh-CN' : 'en-SG'; utterance.rate = .85;
    button.querySelector('span').textContent = t('stop');
    utterance.onend = () => { button.querySelector('span').textContent = t('listen'); };
    utterance.onerror = event => { button.querySelector('span').textContent = t('listen'); if (!['canceled', 'interrupted'].includes(event.error) && activePanel === 'help') document.querySelector('#speech-status').textContent = t('speechError'); };
    speechSynthesis.speak(utterance);
  }
});
document.addEventListener('submit', event => {
  if (event.target.id !== 'link-form') return;
  event.preventDefault();
  const input = document.querySelector('#menu-url');
  try { acceptLink(parseMenuUrl(input.value)); }
  catch { const status = document.querySelector('#link-status'); status.className = 'error'; status.textContent = t('invalidLink'); input.setAttribute('aria-invalid', 'true'); input.focus(); }
});
document.addEventListener('change', event => {
  if (event.target.id !== 'menu-photo') return;
  const file = event.target.files[0];
  if (!file) return;
  if (photoUrl) URL.revokeObjectURL(photoUrl);
  photoUrl = null;
  const result = document.querySelector('#photo-result');
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) { result.innerHTML = `<p class="error">${t('photoError')}</p>`; return; }
  photoUrl = URL.createObjectURL(file);
  result.innerHTML = `<img class="photo-preview" alt="${t('photoAlt')}" /><p class="notice">${t('photoReady')} ${t('analysisNotice')}</p>`;
  result.querySelector('img').src = photoUrl;
  result.querySelector('img').onerror = () => { result.innerHTML = `<p class="error">${t('photoError')}</p>`; if (photoUrl) URL.revokeObjectURL(photoUrl); photoUrl = null; };
});
dialog.addEventListener('close', () => { activePanel = null; cleanup(); });
dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });
window.addEventListener('pagehide', cleanup);
document.addEventListener('visibilitychange', () => { if (document.hidden && activePanel === 'scan') dialog.close(); });
setLanguage(language);
window.addEventListener('popstate', () => {
  if (['menu','chat','order'].includes(location.hash.slice(1))) ordering.open(language, { fromHistory:true }).catch(() => {});
  else ordering.hide();
});
document.querySelector('.brand').addEventListener('click', event => {
  if (ordering.active) { event.preventDefault(); ordering.hide(); history.pushState({}, '', '/'); }
});
if (['menu','chat','order'].includes(location.hash.slice(1))) ordering.open(language, { fromHistory:true }).catch(() => {});
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  const target = ordering.active ? document.querySelector('#ordering-screen [role="tabpanel"]:not([hidden])') : document.querySelector('#main');
  target?.focus();
});

// Optional browser agent access uses the same visible sample-menu journey.
if (document.modelContext?.registerTool) {
  try {
    Promise.resolve(document.modelContext.registerTool({
      name: 'open_sample_menu',
      title: 'Open sample menu',
      description: 'Open the sample hawker menu on screen. Does not place an order.',
      inputSchema: { type: 'object', properties: { language: { type: 'string', enum: ['en', 'zh'] } }, additionalProperties: false },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      async execute(input) {
        if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => key !== 'language') || (input.language !== undefined && !['en', 'zh'].includes(input.language))) throw new Error('Use language en or zh.');
        if (input.language) setLanguage(input.language);
        await showPanel('sample');
        return { opened: true, ...ordering.snapshot(), language };
      },
    })).catch(() => {});
  } catch { /* Browsers without WebMCP use the normal buttons. */ }
}
