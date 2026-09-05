import { BackendOrder, canCancelLine, defaultOptions, isMenuItemAvailable, kitchenStatusClass, kitchenStatusLabel, requestJSON } from './backend-client.js';
import { createBackendVoice } from './backend-voice.js';

const words = {
  en: { menu:'Menu', chat:'Chat', order:'Order', back:'Open another menu', demo:'Sample menu · Demo ordering', restaurant:'Ah Seng Kopitiam', welcome:'What would you like?', menuHint:'Choose something you like, or ask our helper.', food:'Food', drinks:'Drinks', add:'Add', listen:'Listen', stop:'Stop', viewOrder:'View order', yourOrder:'Your order', reviewHint:'Check your choices before confirming.', empty:'Your order is empty', emptyHint:'Find something you like in the menu, or ask the helper.', browse:'Browse the menu', total:'Total', change:'Change', remove:'Remove', readOrder:'Read my order aloud', confirm:'Confirm demo order', notSent:'This is a demo. No order is sent to a restaurant.', helpTitle:'How can I help?', helpHint:'Ask about the sample menu or tell me what you’d like.', helper:'Menu helper', greeting:'Hello! I can show you the sample menu and help build your order. Try “one kopi, less sweet”, or choose a suggestion below.', showFood:'Show food', showDrinks:'Show drinks', under5:'Under $5', review:'Review order', speak:'Tap to speak', speaking:'Done speaking', placeholder:'Or type a message…', send:'Send', typeLabel:'Your message', voiceHint:'Speak, check the words, then press Send.', noVoice:'Voice input isn’t available in this browser. You can type your message below.', voiceError:'Voice input couldn’t start. Check microphone access, or type your message.', voiceNetwork:'The browser’s voice service is unavailable. Please type your message instead.', heard:'Check what I heard. You can edit it before sending.', hearing:'Listening… take your time.', speechError:'Audio isn’t available here. You can read the text on screen.', added:'Added to your order', removed:'Removed from your order', updated:'Your choices have been updated.', inOrder:'in your order', quantity:'Quantity', options:'Your preferences', save:'Save changes', cancel:'Cancel', sweetness:'Sweetness', temperature:'Temperature', chilli:'Chilli', normal:'Normal', less:'Less sweet', none:'No added sugar', hot:'Hot', iced:'Iced', regular:'As served', no:'No chilli', little:'Less chilli', itemError:'Please choose a quantity from 1 to 20.', confirmed:'Demo order confirmed', confirmedHint:'You’ve tried the full flow. This order stays in this browser and hasn’t been sent anywhere.', newOrder:'Start a new demo order', done:'Done', clear:'Start over', waiting:'Opening your menu…', loadError:'We couldn’t open the sample menu.', retry:'Try again', choicesTitle:'Change your choices', confirmTitle:'Ready to confirm?', confirmHint:'Please review this sample order. Confirming only completes the demo.', yesConfirm:'Yes, confirm demo', keepEditing:'Keep editing', readbackEmpty:'Your order is empty.', photos:'Photos are illustrative.', credits:'Photo credits', sources:'Illustrative photo sources', fallback:'I can help with this sample menu. Try “show drinks”, “under $5”, or “one kopi, less sweet”. For more choices, use the Menu tab.', uncertain:'This sample menu doesn’t provide reliable ingredient, allergen, or dietary details. Please ask the restaurant staff.', reviewReply:'Here is your order so far. Open Order to change your choices or confirm the demo.', removeReply:'Open Order and use Remove beside the dish you want to remove.', editReply:'Open Order and press Change beside the dish to update its quantity or preferences.', thanks:'Your demo order is confirmed. Nothing has been sent to a restaurant.', chooseOptions:'Choose your preferences below. These are sample choices for the demo.', close:'Close', minus:'Decrease quantity of', plus:'Increase quantity of', addedChat:'Added', countLabel:'items', listReply:'Here are some choices from the sample menu:', infoNote:'Descriptions are examples for this demo.', startAgain:'A fresh demo order is ready. What would you like?', savedTab:'Your order is shared across all three tabs.' },
  zh: { menu:'菜单', chat:'聊天', order:'订单', back:'打开其他菜单', demo:'示例菜单 · 体验点餐', restaurant:'Ah Seng Kopitiam', welcome:'想吃点什么？', menuHint:'选一道喜欢的菜，或问问菜单小帮手。', food:'食物', drinks:'饮料', add:'添加', listen:'朗读', stop:'停止', viewOrder:'查看订单', yourOrder:'您的订单', reviewHint:'确认前，请检查您的选择。', empty:'订单还是空的', emptyHint:'先看看菜单，或请小帮手帮忙。', browse:'浏览菜单', total:'总计', change:'修改', remove:'删除', readOrder:'朗读我的订单', confirm:'确认示例订单', notSent:'这是体验版，不会向餐厅发送订单。', helpTitle:'有什么可以帮您？', helpHint:'问问菜单有什么，或告诉我您想点什么。', helper:'菜单小帮手', greeting:'您好！我可以介绍示例菜单，帮您选择餐点。试着说“我要一杯咖啡，少糖”，或点击下面的问题。', showFood:'看看食物', showDrinks:'看看饮料', under5:'少于 $5', review:'查看订单', speak:'点击说话', speaking:'说好了', placeholder:'也可以在这里输入……', send:'发送', typeLabel:'您的消息', voiceHint:'说完后先检查文字，再按发送。', noVoice:'此浏览器暂不支持语音输入，请在下方打字。', voiceError:'无法启动语音输入。请检查麦克风权限，或改用打字。', voiceNetwork:'浏览器的语音服务暂不可用，请改用打字。', heard:'请检查识别出的文字，可以修改后再发送。', hearing:'正在聆听……您慢慢说。', speechError:'这里暂时无法朗读，请查看屏幕上的文字。', added:'已加入订单', removed:'已从订单中删除', updated:'已更新您的选择。', inOrder:'已加入订单', quantity:'数量', options:'您的偏好', save:'保存修改', cancel:'取消', sweetness:'甜度', temperature:'温度', chilli:'辣椒', normal:'正常', less:'少糖', none:'不额外加糖', hot:'热', iced:'冰', regular:'正常做法', no:'不加辣椒', little:'少辣椒', itemError:'请选择 1 到 20 的数量。', confirmed:'示例订单已确认', confirmedHint:'您已体验完整流程。这份订单仅在此浏览器中，不会发送给餐厅。', newOrder:'开始新的体验订单', done:'完成', clear:'重新开始', waiting:'正在打开菜单……', loadError:'暂时无法打开示例菜单。', retry:'重试', choicesTitle:'修改您的选择', confirmTitle:'准备好确认了吗？', confirmHint:'请检查这份示例订单。确认只会完成体验流程。', yesConfirm:'是的，确认示例订单', keepEditing:'继续修改', readbackEmpty:'您的订单还是空的。', photos:'图片仅供参考。', credits:'图片来源', sources:'参考图片来源', fallback:'我可以帮您查看示例菜单。试试“看看饮料”“少于5”或“我要一杯咖啡，少糖”。更多选择请打开菜单。', uncertain:'示例菜单没有提供可靠的成分、过敏原或饮食需求信息，请向餐厅工作人员确认。', reviewReply:'这是您目前的订单。打开订单页即可修改选择或确认体验订单。', removeReply:'请打开订单，点击对应菜品旁的删除按钮。', editReply:'请打开订单，点击对应菜品旁的修改按钮。', thanks:'您的示例订单已确认，不会向餐厅发送。', chooseOptions:'请选择偏好。以下是体验版中的示例选项。', close:'关闭', minus:'减少数量：', plus:'增加数量：', addedChat:'已添加', countLabel:'份', listReply:'以下是示例菜单中的一些选择：', infoNote:'菜品介绍是体验版中的示例说明。', startAgain:'新的示例订单已准备好，您想吃点什么？', savedTab:'菜单、聊天和订单会保留同一份选择。' },
};
Object.assign(words.en, {
  startingVoice:'Starting microphone…', startingHint:'Allow microphone access if asked. Wait for “Listening” before speaking.', cancelVoice:'Cancel microphone', processingVoice:'Turning speech into text…', processingHint:'Please wait. Your message has not been sent.', retryVoice:'Try voice again', voiceProblem:'Voice input needs attention', useTyping:'Use typing instead',
  voiceHint:'Tap to speak → say your message → Done speaking → check the words → Send.',
  voiceNetwork:'The browser couldn’t reach its speech service. You can type below, or try this page in Chrome with microphone access allowed.',
  noSpeech:'No words were detected. Try again and wait for “Listening” before speaking, or type below.',
  voiceDenied:'Microphone access wasn’t allowed. Allow it in your browser’s site settings and try again, or type below.',
  noMicrophone:'We couldn’t hear your microphone. Check that a working microphone is selected, or type below.',
  voiceTimeout:'Speech input didn’t respond in time. You can try again or type below.',
  voiceLanguage:'This browser’s speech service doesn’t support the selected language. Change language or type below.',
  voiceReview:'Check any words below before pressing Send.', helloReply:'Hello! What would you like to eat or drink? You can ask “show drinks” or say “one kopi, less sweet”.',
});
Object.assign(words.zh, {
  startingVoice:'正在启动麦克风……', startingHint:'如有提示，请允许使用麦克风。看到“正在聆听”后再说话。', cancelVoice:'取消语音输入', processingVoice:'正在转成文字……', processingHint:'请稍等，您的消息还没有发送。', retryVoice:'重试语音输入', voiceProblem:'语音输入遇到问题', useTyping:'改用打字',
  voiceHint:'点击说话 → 说出消息 → 点击“说好了” → 检查文字 → 发送。',
  voiceNetwork:'浏览器无法连接语音服务。请在下方打字，或用 Chrome 打开此页面并允许麦克风权限。',
  noSpeech:'没有识别到文字。请重试，看到“正在聆听”后再说话，也可以在下方打字。',
  voiceDenied:'麦克风权限未获允许。请在浏览器的网站设置中允许使用麦克风后重试，或改用打字。',
  noMicrophone:'无法收到麦克风声音。请检查是否选择了可用的麦克风，或改用打字。',
  voiceTimeout:'语音输入等待超时。您可以重试，或在下方打字。',
  voiceLanguage:'此浏览器的语音服务不支持所选语言。请更换语言，或改用打字。',
  voiceReview:'发送前，请检查下方已有的文字。', helloReply:'您好！您想吃点什么，或喝点什么？可以问“看看饮料”，或说“我要一杯咖啡，少糖”。',
});
const photos = {
  CHICKEN_RICE: { url:'https://img.wongnai.com/p/1920x0/2024/05/12/ef53342dea494572971e66cf282547de.jpg', source:'https://www.wongnai.com/reviews/60ba2c1f85b44a23b78be6ec1590bb4e', credit:'Wongnai' },
  NASI_LEMAK: { url:'https://www.marinabaysands.com/guides/singapore-foodie-guide/guide-to-singapore-local-food/_jcr_content/root/container/table_copy_copy_1485/1-1/image_1021437342.coreimg.jpeg/1730792647535/nasi-lemak.jpeg', source:'https://www.marinabaysands.com/guides/singapore-foodie-guide/guide-to-singapore-local-food.html', credit:'Marina Bay Sands' },
  KOPI: { url:'https://www.alliancecoffee.sg/wp-content/uploads/2020/04/old-school-singapore-kopi-cup-1024x889.jpg', source:'https://www.alliancecoffee.sg/how-to-make-kopi/', credit:'Alliance Coffee' },
};
Object.assign(words.en, {
  demo:'Sample menu · Local kitchen demo', restaurant:'Kopitiam sample menu',
  helpHint:'Order in English or Singlish. The helper will ask about missing choices.',
  notSent:'Connected to the local backend. Kitchen submission is simulated.',
  confirmedHint:'The local demo kitchen received your order. No real restaurant receives it.',
  confirmHint:'Review your order and choose dine-in or takeaway. This sends it to the local demo kitchen.',
  chooseOptions:'Choose your preferences. Prices follow the ordering menu.',
  noVoice:'Microphone recording isn’t supported here. You can type below.',
  backendVoiceOffline:'The speech backend is offline. You can type while the service reconnects.',
  backendVoiceUnavailable:'The speech model isn’t ready. Please try again shortly, or type below.',
  backendVoiceError:'The speech backend couldn’t process this recording. Please try again or type below.',
  processingHint:'Your recording is being transcribed. This may take a moment. Your message has not been sent.',
  voiceTimeout:'The speech backend took too long to respond. Please try again or type below.',
  recordingHint:'Say your message, then press Done speaking. Words appear after transcription.',
  voiceReady:'Voice ready', voiceChecking:'Checking voice…', voiceOffline:'Voice unavailable · typing works', checkServices:'Check connection', saving:'Updating your order…', retryConnection:'Retry connection',
  dineIn:'Eat here', takeaway:'Takeaway', serviceType:'Where will you eat?', confirmedLine:'Confirmed with demo kitchen', pendingHint:'Please answer the question in Chat to finish this choice.',
  milk_type:'Milk', strength:'Strength', spice:'Chilli', noodle_type:'Noodle type', soup_style:'Soup or dry',
  condensed_milk:'Condensed milk', evaporated_milk:'Evaporated milk', black:'No milk', less_sweet:'Less sweet', no_sugar:'No sugar', extra_sweet:'Extra sweet', strong:'Strong', weak:'Weak',
  no_chilli:'No chilli', less_chilli:'Less chilli', normal_chilli:'Normal chilli', extra_chilli:'Extra chilli', yellow_noodle:'Yellow noodle', kway_teow:'Kway teow', bee_hoon:'Bee hoon', instant_noodle:'Instant noodle', soup:'Soup', dry:'Dry',
});
Object.assign(words.zh, {
  demo:'示例菜单 · 本地厨房体验', restaurant:'咖啡店示例菜单', helpHint:'请用英语或 Singlish 点餐。小帮手会询问缺少的选择。',
  notSent:'已连接本地后端，厨房接单仅供体验。', confirmedHint:'本地模拟厨房已收到订单，不会发送给真实餐厅。', confirmHint:'请检查订单，并选择堂食或打包。确认后会发送给本地模拟厨房。', chooseOptions:'请选择偏好，价格以点餐菜单为准。',
  noVoice:'这里暂不支持麦克风录音，请在下方打字。', backendVoiceOffline:'语音后端未连接。等待恢复时，您可以先打字。', backendVoiceUnavailable:'语音模型尚未就绪，请稍后重试，或改用打字。', backendVoiceError:'语音后端无法处理这段录音，请重试或打字。',
  processingHint:'正在转写您的录音，请稍等。您的消息还没有发送。', voiceTimeout:'语音后端响应超时，请重试或改用打字。', recordingHint:'请说出消息，再点击“说好了”。转写完成后会显示文字。',
  voiceReady:'语音已就绪', voiceChecking:'正在检查语音……', voiceOffline:'语音未就绪，可先打字', checkServices:'检查连接', saving:'正在更新订单……', retryConnection:'重新连接',
  dineIn:'堂食', takeaway:'打包', serviceType:'用餐方式', confirmedLine:'模拟厨房已确认', pendingHint:'请到聊天页回答问题，完成这项选择。',
  milk_type:'奶的种类', strength:'浓度', spice:'辣椒', noodle_type:'面条种类', soup_style:'汤面或干面', condensed_milk:'炼乳', evaporated_milk:'淡奶', black:'不加奶', less_sweet:'少糖', no_sugar:'无糖', extra_sweet:'多糖', strong:'浓', weak:'淡',
  no_chilli:'不加辣椒', less_chilli:'少辣椒', normal_chilli:'正常辣椒', extra_chilli:'多辣椒', yellow_noodle:'黄面', kway_teow:'粿条', bee_hoon:'米粉', instant_noodle:'快熟面', soup:'汤面', dry:'干面',
});
Object.assign(words.en, {
  outOfStock:'Out of stock',
  stockLeft:'{count} left', stockChanged:'The menu has been refreshed. Please try again.',
  cancellationUnavailable:'Cancellation is unavailable after preparation starts.',
});
Object.assign(words.zh, {
  outOfStock:'已售罄', stockLeft:'剩余 {count} 份',
  stockChanged:'菜单已刷新，请重试。', cancellationUnavailable:'开始制作后无法取消。',
});
const esc = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const svg = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const money = cents => `$${(cents/100).toFixed(2)}`;

export function createOrdering({ onHome }) {
  const root = document.querySelector('#ordering-screen');
  const choiceDialog = document.createElement('dialog'); choiceDialog.className='choice-dialog'; choiceDialog.setAttribute('aria-labelledby','choice-title'); document.body.append(choiceDialog);
  let language='en', active=false, currentTab='menu', category='Food', items=[], order=null, loading=null, error=false;
  let messages=[], draft='', recording=false, speakingKey=null, speechToken=0, toastTimer=null;
  const canRecord=!!(navigator.mediaDevices?.getUserMedia&&window.AudioContext);
  let busy=false, backendError='', speechAvailable=null, orderPollTimer=null, refreshInFlight=false;
  let voiceState={phase:canRecord?'idle':'error',transcript:'',error:canRecord?null:'unsupported'};
  const voice=createBackendVoice({onChange(state){
    voiceState=state;
    recording=['starting','listening','processing'].includes(state.phase);
    if(state.phase!=='idle')draft=state.transcript;
    voiceControls();
  }});
  const t = key => words[language][key]||String(key).replaceAll('_',' ');
  const name = item => language==='zh' ? item.zh : item.display;
  const description = item => language==='zh' ? item.descriptionZh : item.description;
  const optionsText = options => Object.values(options).filter(v=>!['normal','regular','hot','condensed_milk'].includes(v)).map(t).join(language==='zh'?'，':', ');
  const snapshot = () => ({ tab:currentTab, itemCount:order?.count||0, total:money(order?.total||0), confirmed:order?.confirmed||false });
  function announce(text) { const el=document.querySelector('#order-announcement'); if(el)el.textContent=text; }
  function toast(text) { const el=document.querySelector('#order-feedback'); if(!el)return; el.textContent=text; el.hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>{el.hidden=true;},3500); }
  function stopSpeech() { speechToken++; window.speechSynthesis?.cancel(); speakingKey=null; updateSpeechButtons(); }
  function updateSpeechButtons() { document.querySelectorAll('[data-speech-key]').forEach(button=>{ const isSpeaking=button.dataset.speechKey===speakingKey; button.setAttribute('aria-pressed',String(isSpeaking)); const label=button.querySelector('.speak-label'); if(label)label.textContent=isSpeaking?t('stop'):button.dataset.listenLabel||t('listen'); }); }
  function speak(text,key) {
    if(speakingKey===key){stopSpeech();return;}
    stopSpeech();
    if(!window.speechSynthesis||!window.SpeechSynthesisUtterance){toast(t('speechError'));return;}
    const token=speechToken; const utterance=new SpeechSynthesisUtterance(text); utterance.lang=language==='zh'?'zh-CN':'en-SG';utterance.rate=.85;
    speakingKey=key;updateSpeechButtons();
    utterance.onend=()=>{if(token===speechToken){speakingKey=null;updateSpeechButtons();}};
    utterance.onerror=event=>{if(token!==speechToken)return;speakingKey=null;updateSpeechButtons();if(!['canceled','interrupted'].includes(event.error))toast(t('speechError'));};
    speechSynthesis.speak(utterance);
  }
  function listenButton(text,key,label=t('listen'),extra='') { return `<button class="listen-button ${extra}" data-say="${esc(text)}" data-speech-key="${esc(key)}" data-listen-label="${esc(label)}" aria-pressed="false">${svg('sound')}<span class="speak-label">${esc(label)}</span></button>`; }
  function picture(item,small=false) {
    const photo=photos[item.canonical.toUpperCase()];
    return `<div class="dish-picture ${small?'is-small':''} ${photo?'has-photo':''}">${photo?`<img src="${photo.url}" alt="" loading="lazy" referrerpolicy="no-referrer" />`:svg(item.category==='Drinks'?'cup':'food')}</div>`;
  }
  function stockText(item) {
    if(!isMenuItemAvailable(item))return t('outOfStock');
    const remaining=Number(item.remaining_stock);
    return Number.isFinite(remaining)?t('stockLeft').replace('{count}',String(remaining)):'';
  }
  function addAction(item,className) {
    const available=isMenuItemAvailable(item);
    return `<button class="${className}${available?'':' is-unavailable'}" data-add="${item.canonical}" aria-label="${available?t('add'):t('outOfStock')} ${esc(name(item))}" ${available?'':'disabled'}>${available?svg('plus')+t('add'):t('outOfStock')}</button>`;
  }
  function menuView() {
    const visible=items.filter(item=>item.category===category);
    return `<div class="view-heading"><div><span class="restaurant-name">${t('restaurant')}</span><h1>${t('welcome')}</h1><p>${t('menuHint')}</p></div><span class="menu-number">${visible.length} ${language==='zh'?'款选择':'choices'}</span></div>
      <div class="category-switch" role="group" aria-label="${t('menu')}">${['Food','Drinks'].map(c=>`<button data-category="${c}" aria-pressed="${category===c}" class="${category===c?'selected':''}">${svg(c==='Food'?'food':'cup')}${t(c.toLowerCase())}</button>`).join('')}</div>
      <div class="dish-grid">${visible.map(item=>{const count=order.lines.filter(l=>l.id===item.canonical).reduce((n,l)=>n+l.quantity,0);const available=isMenuItemAvailable(item);return `<article class="dish-card${available?'':' is-unavailable'}">${picture(item)}<div class="dish-info"><h2>${esc(name(item))}</h2><p class="dish-description">${esc(description(item))}</p><strong class="dish-price">${money(item.cents)}</strong><span class="dish-stock${available?'':' is-unavailable'}">${esc(stockText(item))}</span>${count?`<span class="dish-count">${svg('check')}${count} ${t('inOrder')}</span>`:''}<div class="dish-actions">${listenButton(`${name(item)}. ${money(item.cents)}. ${description(item)}`,`dish-${item.canonical}`)}${addAction(item,'add-button')}</div></div></article>`;}).join('')}</div>
      <p class="photo-note">${t('photos')} <button data-action="credits">${t('credits')}</button></p>
      <div class="view-order-dock"><button class="primary-button" data-tab="order">${svg('cart')}<span>${t('viewOrder')} <span class="dock-count">(${order.count})</span></span><strong>${money(order.total)}</strong>${svg('arrow')}</button></div>`;
  }
  function orderSummary() { return order.lines.length ? order.lines.map(line=>`${line.quantity} × ${name(order.item(line.id))}${optionsText(line.options)?`, ${optionsText(line.options)}`:''}. ${money(line.subtotal_cents)}`).join('. ')+`. ${t('total')}: ${money(order.total)}.` : t('readbackEmpty'); }
  function orderView() {
    return `<div class="view-heading"><div><h1>${t('yourOrder')}</h1><p>${t('reviewHint')}</p></div></div>${!order.lines.length?`<div class="empty-order"><span class="empty-icon">${svg('cart')}</span><h2>${t('empty')}</h2><p>${t('emptyHint')}</p><button class="primary-button" data-tab="menu">${t('browse')}${svg('arrow')}</button></div>`:`${order.confirmed?`<div class="confirmation-banner" role="status">${svg('check')}<div><strong>${t('confirmed')}</strong><p>${t('confirmedHint')}</p></div></div>`:''}<div class="order-lines">${order.lines.map(line=>{const item=order.item(line.id);const status=line.sent?kitchenStatusLabel(line.kitchen_status,language):'';const statusClass=kitchenStatusClass(line.kitchen_status);const cancelable=canCancelLine(line);return `<article class="order-line" aria-label="${esc(name(item))}">${picture(item,true)}<div class="line-details"><h2>${esc(name(item))}</h2>${optionsText(line.options)?`<p>${esc(optionsText(line.options))}</p>`:''}<strong class="line-price">${money(line.subtotal_cents)}</strong>${status?`<p class="kitchen-status kitchen-status-${statusClass}" role="status">${esc(status)}</p>`:''}<div class="line-bottom"><div class="quantity-control" role="group" aria-label="${t('quantity')} ${esc(name(item))}"><button data-quantity="${esc(line.key)}" data-delta="-1" aria-label="${t('minus')} ${esc(name(item))}" ${line.quantity<=1||line.sent?'disabled':''}>${svg('minus')}</button><span aria-label="${t('quantity')}: ${line.quantity}">${line.quantity}</span><button data-quantity="${esc(line.key)}" data-delta="1" aria-label="${t('plus')} ${esc(name(item))}" ${line.quantity>=20||line.sent?'disabled':''}>${svg('plus')}</button></div><div class="line-edit-buttons"><button data-edit="${esc(line.key)}" ${line.sent?'disabled':''}>${svg('edit')}${t('change')}</button><button data-remove="${esc(line.key)}" ${cancelable?'':'disabled'} ${cancelable?'':`title="${esc(t('cancellationUnavailable'))}"`}>${svg('trash')}${t('remove')}</button></div></div></div></article>`;}).join('')}</div><div class="order-total"><span>${t('total')}</span><strong>${money(order.total)}</strong></div><div class="order-final-actions">${listenButton(orderSummary(),'order-summary',t('readOrder'),'read-order')}${order.confirmed?`<button class="primary-button" data-action="new-order">${t('newOrder')}</button>`:`<button class="primary-button" data-action="confirm">${svg('check')}${t('confirm')}</button>`}<p class="demo-caption">${t('notSent')}</p></div>`}`;
  }
  function chatView() {
    const status=voicePresentation();
    return `<div class="view-heading chat-heading"><div><h1>${t('helpTitle')}</h1><p>${t('helpHint')}</p></div><span class="helper-symbol">${svg('chat')}</span></div><div class="chat-log" role="log" aria-live="off" aria-label="${t('chat')}">${messages.map((message,index)=>`<div class="chat-message ${message.role}">${message.role==='assistant'?`<span class="message-author">${svg('menu')}${t('helper')}</span>`:''}<div class="chat-bubble"><p>${esc(message.key?t(message.key):message.text)}</p>${message.ids?.length?`<div class="chat-menu-list">${message.ids.slice(0,6).map(id=>{const item=order.item(id);return `<div><span>${esc(name(item))}<strong>${money(item.cents)}</strong></span>${addAction(item,'chat-add-button')}</div>`;}).join('')}</div>`:''}${message.role==='assistant'?listenButton((message.key?t(message.key):message.text)+(message.ids?.map(id=>{const item=order.item(id);return ` ${name(item)}, ${money(item.cents)}.`;}).join('')||''),`message-${index}`):''}</div></div>`).join('')}</div>
      <div class="chat-composer"><div class="connection-status"><span>${t(speechAvailable===null?'voiceChecking':speechAvailable?'voiceReady':'voiceOffline')}</span><button data-action="check-services">${t('checkServices')}</button></div><div class="suggestions"><button data-prompt="drinks">${svg('cup')}${t('showDrinks')}</button><button data-prompt="budget">${t('under5')}</button><button data-tab="order">${svg('cart')}${t('review')}</button></div>
      <button class="voice-button ${recording?'is-recording':''}" id="voice-button" aria-pressed="${recording}" aria-describedby="voice-status" ${canRecord&&!busy?'':'disabled'}>${svg(recording?'stop':'mic')}<span>${status.button}</span></button><div id="voice-status" class="voice-status ${status.error?'has-error':''}" role="status" aria-live="polite" aria-atomic="true"><strong>${status.title}</strong><p>${status.hint}</p></div><button class="type-instead" data-action="type-instead" ${status.error?'':'hidden'}>${t('useTyping')}</button>
      <form id="chat-form" class="message-form"><label class="sr-only" for="chat-input">${t('typeLabel')}</label><textarea id="chat-input" rows="1" maxlength="400" placeholder="${t('placeholder')}" ${recording||busy?'readonly':''}>${esc(draft)}</textarea><button type="submit" aria-label="${t('send')}" ${recording||busy?'disabled':''}>${svg('arrow')}<span>${t('send')}</span></button></form></div>`;
  }
  function render() {
    if(!active)return;
    root.innerHTML=`<div class="ordering-topline"><button data-action="home">${svg('arrow')}<span>${t('back')}</span></button><span class="demo-pill"><span></span>${t('demo')}</span></div>
      <div class="ordering-navigation" role="tablist" aria-label="${language==='zh'?'点餐导航':'Ordering sections'}">${['menu','chat','order'].map(tab=>`<button role="tab" id="tab-${tab}" aria-controls="panel-${tab}" aria-selected="${currentTab===tab}" tabindex="${currentTab===tab?0:-1}" data-tab="${tab}">${svg(tab==='order'?'cart':tab)}<span>${t(tab)}</span>${tab==='order'?`<span class="order-badge">${order?.count||0}</span>`:''}</button>`).join('')}</div>
      ${backendError?`<div class="backend-notice" role="alert"><p>${esc(backendError)}</p><button data-action="retry-connection">${t('retryConnection')}</button>${order?.sessionExpired?` <button data-action="new-order">${t('newOrder')}</button>`:''}</div>`:''}${busy?`<p role="status" class="connection-status">${t('saving')}</p>`:''}${order?.pending?`<div class="backend-notice"><p>${esc(order.pending)}</p><button data-tab="chat">${t('chat')}</button></div>`:''}
      ${!order?`<div class="loading-menu" role="status"><h2>${t(error?'loadError':'waiting')}</h2>${error?`<p>${esc(backendError)}</p>`:''}${error?`<button class="primary-button" data-action="retry">${t('retry')}</button>`:''}</div>`:['menu','chat','order'].map(tab=>`<section role="tabpanel" id="panel-${tab}" aria-labelledby="tab-${tab}" tabindex="0" ${currentTab===tab?'':'hidden'}>${tab==='menu'?menuView():tab==='chat'?chatView():orderView()}</section>`).join('')}
      <p id="order-announcement" class="sr-only" role="status"></p><div id="order-feedback" class="order-toast" role="status" hidden></div>`;
    root.querySelectorAll('img').forEach(img=>{img.addEventListener('error',()=>{img.parentElement.classList.remove('has-photo');img.parentElement.innerHTML=svg('food');},{once:true});});
    updateSpeechButtons();
  }
  function scrollChat() { const log=root.querySelector('.chat-log');if(log)log.scrollTop=log.scrollHeight; }
  function navigate(tab,{focus=false}={}) {
    if(!['menu','chat','order'].includes(tab))return;
    stopVoice();stopSpeech();currentTab=tab;history.replaceState({},'',`#${tab}`);render();syncOrderPolling();
    if(tab==='chat')scrollChat();
    if(focus)root.querySelector(`#tab-${tab}`)?.focus();
    window.scrollTo({top:0,behavior:'instant'});
  }
  async function open(nextLanguage='en',{fromHistory=false}={}) {
    language=nextLanguage;active=true;error=false;backendError='';
    currentTab=['menu','chat','order'].includes(location.hash.slice(1))?location.hash.slice(1):'menu';
    document.querySelector('#main').hidden=true;root.hidden=false;document.body.classList.add('is-ordering');
    if(!fromHistory && !location.hash)history.pushState({},'',`#${currentTab}`);
    render();
    try {
      if(!order){loading ||= new BackendOrder().open();const connected=await loading;items=connected.items;order=connected;messages=order.messages;if(order.sessionRestarted)toast(language==='zh'?'上次体验已过期，已开始新的订单。':'The previous demo session expired. A new order has been started.');}
      checkSpeech();
      render();syncOrderPolling();return snapshot();
    }catch(problem){loading=null;error=true;backendError=problem.message||'The ordering backend is offline.';render();throw problem;}
  }
  function hide() {active=false;stopOrderPolling();stopVoice();stopSpeech();root.hidden=true;document.querySelector('#main').hidden=false;document.body.classList.remove('is-ordering');if(choiceDialog.open)choiceDialog.close();}
  function showDialog(body){stopVoice();stopSpeech();choiceDialog.innerHTML=`<div class="dialog-header"><span class="dialog-kicker">${t('helper')}</span><button class="close-button" data-dialog-close aria-label="${t('close')}">${svg('close')}</button></div>${body}`;choiceDialog.showModal();choiceDialog.querySelector('h2')?.focus();}
  async function checkSpeech(){
    try{const health=await requestJSON('/api/stt/health',{timeout:5000});speechAvailable=health.engine_ready===true;}
    catch{speechAvailable=false;}
    if(active)render();
  }
  function errorText(problem) {
    const message=problem.message||'The ordering backend could not be reached.';
    return problem.code==='stock_unavailable'?`${message} ${t('stockChanged')}`:message;
  }
  function stopOrderPolling() {
    if(orderPollTimer){clearInterval(orderPollTimer);orderPollTimer=null;}
  }
  async function refreshOrderSnapshot() {
    if(refreshInFlight||!active||currentTab!=='order'||document.hidden||!order||order.pendingRequest)return;
    refreshInFlight=true;
    try {
      await order.refresh();
      if(active&&currentTab==='order'){messages=order.messages;render();}
    } catch(problem) {
      if(active&&currentTab==='order'){backendError=errorText(problem);render();}
    } finally { refreshInFlight=false; }
  }
  function syncOrderPolling() {
    stopOrderPolling();
    if(active&&currentTab==='order'&&!document.hidden&&order){
      refreshOrderSnapshot();
      orderPollTimer=setInterval(refreshOrderSnapshot,4000);
    }
  }
  async function runChange(action){
    if(busy)return false;
    stopVoice();busy=true;backendError='';render();
    try{await action();messages=order.messages;return true;}
    catch(problem){
      if(problem.code==='stock_unavailable'&&order){try{items=await order.refreshMenu();}catch{}}
      backendError=errorText(problem);return false;
    }
    finally{busy=false;render();if(!backendError)announce(messages.at(-1)?.text||t('updated'));if(currentTab==='chat')scrollChat();}
  }
  function editLine(key,addId=null) {
    const line=addId?{id:addId,quantity:1,options:defaultOptions(order.item(addId))}:order.lines.find(l=>l.key===key);
    if(!line)return;const item=order.item(line.id);
    showDialog(`<h2 id="choice-title" tabindex="-1">${esc(name(item))}</h2><p>${t('chooseOptions')}</p><form id="choice-form" data-key="${esc(key||'')}" data-add-id="${esc(addId||'')}"><label class="field-label" for="choice-quantity">${t('quantity')}</label><input class="text-input" id="choice-quantity" name="quantity" type="number" min="1" max="20" step="1" value="${line.quantity}" required />${item.modifier_groups.map(group=>`<fieldset class="preference-group"><legend>${t(group.type)}</legend><div>${group.options.map(option=>`<label><input type="radio" name="${group.type}" value="${option.id}" ${line.options[group.type]===option.id?'checked':''} required/><span>${esc(t(option.id))}${option.price_delta?` (${option.price_delta>0?'+':'−'}${money(Math.round(Math.abs(option.price_delta)*100))})`:''}</span></label>`).join('')}</div></fieldset>`).join('')}<p id="choice-error" class="error" role="status"></p><button class="primary-button" type="submit">${t(addId?'add':'save')}</button><button class="secondary-button" type="button" data-dialog-close>${t('cancel')}</button></form>`);
  }
  function confirmDialog(){
    if(!order?.count)return;
    if(order.pending){navigate('chat');return;}
    showDialog(`<h2 id="choice-title" tabindex="-1">${t('confirmTitle')}</h2><p>${t('confirmHint')}</p><div class="confirm-lines">${order.lines.map(line=>`<div><span>${line.quantity} × ${esc(name(order.item(line.id)))}<small>${esc(optionsText(line.options))}</small></span><strong>${money(line.subtotal_cents)}</strong></div>`).join('')}</div><div class="order-total"><span>${t('total')}</span><strong>${money(order.total)}</strong></div><fieldset class="preference-group"><legend>${t('serviceType')}</legend><div><label><input type="radio" name="takeaway" value="false" ${order.takeaway!==true?'checked':''}/><span>${t('dineIn')}</span></label><label><input type="radio" name="takeaway" value="true" ${order.takeaway===true?'checked':''}/><span>${t('takeaway')}</span></label></div></fieldset><p class="error" id="choice-error" role="status"></p><button class="primary-button" data-final-confirm>${t('yesConfirm')}</button><button class="secondary-button" data-dialog-close>${t('keepEditing')}</button>`);
  }
  async function sendMessage(text){
    const value=text.trim();if(!value||!order||busy)return;
    voice.cancel();
    if(await runChange(()=>order.send(value))){draft='';render();scrollChat();}
    root.querySelector('#chat-input')?.focus();
  }
  function stopVoice(){if(recording)voice.cancel();}
  function voicePresentation(){
    const {phase,error}=voiceState;
    const errors={'network':'voiceNetwork','not-allowed':'voiceDenied','service-not-allowed':'voiceDenied','audio-capture':'noMicrophone','no-speech':'noSpeech','unsupported':'noVoice','language-not-supported':'voiceLanguage','start-timeout':'voiceTimeout','timeout':'voiceTimeout','backend-offline':'backendVoiceOffline','backend-unavailable':'backendVoiceUnavailable','backend-error':'backendVoiceError'};
    if(phase==='error')return {error:true,button:t('retryVoice'),title:t('voiceProblem'),hint:t(errors[error]||'voiceError')+(draft?` ${t('voiceReview')}`:'')};
    if(phase==='starting')return {button:t('cancelVoice'),title:t('startingVoice'),hint:t('startingHint')};
    if(phase==='listening')return {button:t('speaking'),title:t('hearing'),hint:t('recordingHint')};
    if(phase==='processing')return {button:t('cancelVoice'),title:t('processingVoice'),hint:t('processingHint')};
    return {button:t('speak'),title:phase==='ready'?(voiceState.lowConfidence?(language==='zh'?'识别不太确定，请仔细检查文字。':'Some words were unclear. Please check the transcript carefully.'):t('heard')):'',hint:t('voiceHint')};
  }
  function voiceControls(){
    const button=root.querySelector('#voice-button');if(!button)return;
    const status=voicePresentation();
    button.innerHTML=svg(recording?'stop':'mic')+`<span>${status.button}</span>`;
    button.setAttribute('aria-pressed',String(recording));button.classList.toggle('is-recording',recording);
    const notice=root.querySelector('#voice-status');notice.classList.toggle('has-error',!!status.error);
    // Avoid repeating the live announcement on every partial transcript.
    if(notice.querySelector('strong').textContent!==status.title)notice.querySelector('strong').textContent=status.title;
    if(notice.querySelector('p').textContent!==status.hint)notice.querySelector('p').textContent=status.hint;
    root.querySelector('[data-action="type-instead"]').hidden=!status.error;
    const input=root.querySelector('#chat-input');input.readOnly=recording||busy;input.value=draft;
    root.querySelector('#chat-form button').disabled=recording||busy;
  }
  function startVoice(){
    if(voiceState.phase==='listening'){voice.stop();return;}
    if(recording){voice.cancel();return;}
    stopSpeech();voice.start({language:language==='zh'?'zh-CN':'en-SG',initialText:draft});
  }
  root.addEventListener('click',async event=>{
    if(busy)return;
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.tab){navigate(button.dataset.tab,{focus:true});return;}
    if(button.dataset.category){category=button.dataset.category;render();root.querySelector(`[data-category="${category}"]`).focus();return;}
    if(button.dataset.add){const item=order.item(button.dataset.add);if(!isMenuItemAvailable(item)){toast(t('outOfStock'));return;}if(item.modifier_groups.some(group=>group.required)){editLine(null,item.id);return;}await runChange(()=>order.add(item.id));root.querySelector(`[data-add="${item.id}"]`)?.focus();return;}
    if(button.dataset.quantity){const line=order.lines.find(l=>l.key===button.dataset.quantity);await runChange(()=>order.edit(line.key,line.quantity+Number(button.dataset.delta),line.options));return;}
    if(button.dataset.remove){await runChange(()=>order.remove(button.dataset.remove));return;}
    if(button.dataset.edit){editLine(button.dataset.edit);return;}
    if(button.dataset.say){speak(button.dataset.say,button.dataset.speechKey);return;}
    if(button.dataset.prompt){sendMessage(button.dataset.prompt==='budget'?'Under $5':'Show drinks');return;}
    if(button.id==='voice-button'){startVoice();return;}
    if(button.dataset.action==='type-instead'){stopVoice();root.querySelector('#chat-input')?.focus();return;}
    if(button.dataset.action==='home'){hide();history.pushState({},'','/');onHome();return;}
    if(button.dataset.action==='retry'){open(language).catch(()=>{});return;}
    if(button.dataset.action==='check-services'){checkSpeech();return;}
    if(button.dataset.action==='retry-connection'){if(order)await runChange(()=>order.retry());else open(language).catch(()=>{});return;}
    if(button.dataset.action==='confirm'){confirmDialog();return;}
    if(button.dataset.action==='new-order'){if(await runChange(()=>order.reset())){draft='';navigate('menu');toast(t('startAgain'));}return;}
    if(button.dataset.action==='credits')showDialog(`<h2 id="choice-title" tabindex="-1">${t('sources')}</h2><p>${t('photos')} ${t('infoNote')}</p><ul class="photo-credits">${Object.entries(photos).map(([id,p])=>`<li><a href="${p.source}" target="_blank" rel="noopener noreferrer">${esc(name(order.item(id.toLowerCase())))} — ${p.credit}</a></li>`).join('')}</ul>`);
  });
  root.addEventListener('input',event=>{if(event.target.id==='chat-input')draft=event.target.value;});
  root.addEventListener('submit',event=>{if(event.target.id==='chat-form'){event.preventDefault();if(!recording&&!busy)sendMessage(draft);}});
  root.addEventListener('keydown',event=>{
    if(event.target.id==='chat-input'&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(!recording&&!busy)sendMessage(draft);}
    if(event.target.getAttribute('role')==='tab'&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const tabs=['menu','chat','order'];const index=tabs.indexOf(currentTab);navigate(event.key==='Home'?'menu':event.key==='End'?'order':tabs[(index+(event.key==='ArrowRight'?1:2))%3],{focus:true});}
  });
  choiceDialog.addEventListener('click',async event=>{
    if(busy)return;
    if(event.target.closest('[data-dialog-close]'))choiceDialog.close();
    if(event.target.closest('[data-final-confirm]')){
      const takeaway=choiceDialog.querySelector('[name="takeaway"]:checked').value==='true';
      if(await runChange(()=>order.confirm(takeaway))){choiceDialog.close();navigate('order');}
      else choiceDialog.querySelector('#choice-error').textContent=backendError;
    }
  });
  choiceDialog.addEventListener('submit',async event=>{
    if(event.target.id!=='choice-form')return;event.preventDefault();if(busy)return;
    const form=event.target;const data=new FormData(form);const options=Object.fromEntries([...data].filter(([key])=>key!=='quantity'));
    const success=await runChange(()=>form.dataset.addId?order.add(form.dataset.addId,Number(data.get('quantity')),options):order.edit(form.dataset.key,Number(data.get('quantity')),options));
    if(success){choiceDialog.close();toast(t('updated'));}
    else choiceDialog.querySelector('#choice-error').textContent=backendError;
  });
  choiceDialog.addEventListener('close',stopSpeech);
  window.addEventListener('pagehide',()=>{stopOrderPolling();stopSpeech();stopVoice();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stopOrderPolling();stopSpeech();stopVoice();}else syncOrderPolling();});
  return { open, hide, snapshot, get active(){return active;}, setLanguage(next){language=next;stopSpeech();stopVoice();if(choiceDialog.open)choiceDialog.close();render();}, navigate };
}
