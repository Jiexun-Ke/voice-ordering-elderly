import { details } from './demo-model.js';

export async function requestJSON(path, { timeout = 20000, ...options } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(path, { ...options, signal: options.signal || controller.signal });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail;
      const message = typeof detail === 'string'
        ? detail
        : detail && typeof detail.message === 'string'
          ? detail.message
          : 'The server could not accept this request. Please check your choices.';
      const error = new Error(message);
      error.status = response.status;
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        error.detail = detail;
        error.code = detail.code;
        error.itemId = detail.item_id;
        error.requestedQuantity = detail.requested_quantity;
        error.availableQuantity = detail.available_quantity;
      }
      throw error;
    }
    return data;
  } finally { clearTimeout(timer); }
}

const infoIds = { chicken_rice:'CHICKEN_RICE', nasi_lemak:'NASI_LEMAK', fishball_noodles:'FISHBALL_NOODLES', wonton_noodles:'WANTON_MEE', roti_prata:'ROTI_PRATA', kopi:'KOPI', teh:'TEH' };
const extraDetails = {
  beef_noodles:['牛肉面','Beef with your choice of noodles.','牛肉配您选择的面条。'],
  fried_rice:['蛋炒饭','Rice stir-fried with egg.','加入鸡蛋炒制的米饭。'],
  curry_puff:['咖喱角','A pastry with a curry filling.','包有咖喱馅的酥皮点心。'],
  barley:['薏米水','A traditional barley drink.','传统薏米饮品。'],
  soya_milk:['豆奶','A traditional soya bean drink.','传统豆制饮品。'],
};
export function prepareBackendMenu(data) {
  return data.items.map(item => {
    const known = details[infoIds[item.id]];
    const [zh, description, descriptionZh] = known ? known.slice(1) : extraDetails[item.id] || [item.name,'',''];
    return { ...item, canonical:item.id, display:item.name, category:item.category==='Drinks'?'Drinks':'Food', zh, description, descriptionZh, cents:Math.round(item.price*100) };
  }).sort((a,b)=>({chicken_rice:0,nasi_lemak:1}[a.id]??2)-({chicken_rice:0,nasi_lemak:1}[b.id]??2));
}
export function defaultOptions(item) {
  return Object.fromEntries(item.modifier_groups.map(group=>[group.type,group.default]));
}

export class BackendOrder {
  constructor(){this.items=[];this.lines=[];this.confirmed=false;this.total=0;this.messages=[];this.pending=null;this.pendingRequest=null;}
  apply(data) { Object.assign(this, data.snapshot); this.total=data.snapshot.total_cents; return data; }
  item(id){const item=this.items.find(item=>item.id===id);if(!item)throw new Error('Item not on the menu');return item;}
  get count(){return this.lines.reduce((count,line)=>count+line.quantity,0);}
  async open(){
    this.items=prepareBackendMenu(await requestJSON('/api/order/menu'));
    let sessionId;try{sessionId=sessionStorage.getItem('menu-helper-session');}catch{}
    let result;
    if(sessionId){
      try{result=await requestJSON(`/api/order/sessions/${encodeURIComponent(sessionId)}`);}
      catch(error){if(error.status!==404)throw error;this.sessionRestarted=true;}
    }
    if(!result)result=await requestJSON('/api/order/sessions',{method:'POST'});
    this.apply(result);try{sessionStorage.setItem('menu-helper-session',this.session_id);}catch{}
    return this;
  }
  async mutate(path, method, payload={}) {
    if(this.pendingRequest)throw new Error('A change is waiting for a connection. Press Retry connection before making another change.');
    const request={path:`/api/order/sessions/${this.session_id}${path}`,options:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,request_id:crypto.randomUUID()})}};
    this.pendingRequest=request;
    return this.retry();
  }
  async retry(){
    if(!this.pendingRequest)return this.apply(await requestJSON(`/api/order/sessions/${this.session_id}`));
    const {path,options}=this.pendingRequest;
    try { const data=await requestJSON(path,options);this.pendingRequest=null;return this.apply(data); }
    catch(error){
      if(error.status && error.status<500){this.pendingRequest=null;this.sessionExpired=error.status===404;throw error;}
      throw new Error('Connection interrupted. Press Retry connection to check this change without adding it twice.');
    }
  }
  add(id,quantity=1,options={}){return this.mutate('/lines','POST',{item_id:id,quantity,options});}
  edit(key,quantity,options){const line=this.lines.find(line=>line.key===key);return this.mutate(`/lines/${key}`,'PATCH',{item_id:line.id,quantity,options});}
  remove(key){return this.mutate(`/lines/${key}`,'DELETE');}
  send(text){return this.mutate('/messages','POST',{text});}
  confirm(takeaway){return this.mutate('/confirm','POST',{takeaway});}
  async reset(){
    if(this.pendingRequest)throw new Error('Press Retry connection to resolve the pending change first.');
    this.apply(await requestJSON('/api/order/sessions',{method:'POST'}));this.sessionExpired=false;
    try{sessionStorage.setItem('menu-helper-session',this.session_id);}catch{}
  }
}
