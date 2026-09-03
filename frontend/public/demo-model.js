// A deliberately bounded frontend demo. No backend calls or AI responses.
export const details = {
  CHICKEN_RICE: ['Food', '海南鸡饭', 'A classic chicken and rice dish.', '经典的鸡肉配米饭。'],
  NASI_LEMAK: ['Food', '椰浆饭', 'Coconut rice, usually served with sambal on the side.', '椰香米饭，通常配有参巴辣椒酱。'],
  CHAR_KWAY_TEOW: ['Food', '炒粿条', 'Stir-fried flat rice noodles.', '炒制的扁米粉。'],
  WANTON_MEE: ['Food', '云吞面', 'Noodles served with wontons.', '配有云吞的面食。'],
  LAKSA: ['Food', '叻沙', 'Noodles in a spiced coconut-based broth.', '带有香料和椰香汤底的面食。'],
  MEE_GORENG: ['Food', '炒面', 'A hawker favourite of stir-fried noodles.', '经典小贩炒面。'],
  ROTI_PRATA: ['Food', '印度煎饼', 'A flaky pan-fried flatbread.', '层次酥香的煎饼。'],
  FISHBALL_NOODLES: ['Food', '鱼圆面', 'Noodles served with fishballs.', '配有鱼圆的面食。'],
  CARROT_CAKE: ['Food', '菜头粿', 'A savoury fried radish cake dish.', '咸香的炒萝卜糕。'],
  BEE_HOON: ['Food', '米粉', 'Thin rice vermicelli noodles.', '细细的米制面条。'],
  KAYA_TOAST: ['Food', '咖椰吐司', 'Toast with kaya, a coconut and egg spread.', '涂有咖椰酱的吐司。'],
  HALF_BOILED_EGGS: ['Food', '半熟蛋', 'Soft, half-boiled eggs.', '口感嫩滑的半熟鸡蛋。'],
  TAU_HUAY: ['Food', '豆花', 'A soft soya beancurd dessert.', '柔软的豆制甜品。'],
  KOPI: ['Drinks', '咖啡', 'Traditional coffee with condensed milk.', '加入炼乳的传统咖啡。'],
  KOPI_O: ['Drinks', '咖啡乌', 'Traditional black coffee, without milk.', '不加奶的传统黑咖啡。'],
  KOPI_C: ['Drinks', '咖啡西', 'Traditional coffee with evaporated milk.', '加入淡奶的传统咖啡。'],
  TEH: ['Drinks', '奶茶', 'Traditional tea with condensed milk.', '加入炼乳的传统茶饮。'],
  TEH_O: ['Drinks', '茶乌', 'Traditional tea, without milk.', '不加奶的传统茶饮。'],
  TEH_C: ['Drinks', '茶西', 'Traditional tea with evaporated milk.', '加入淡奶的传统茶饮。'],
  MILO: ['Drinks', '美禄', 'A chocolate malt drink.', '巧克力麦芽饮品。'],
};
export const optionGroups = {
  sweetness: ['normal', 'less', 'none'], temperature: ['hot', 'iced'], chilli: ['regular', 'no', 'little'],
};
export function defaultOptions(item) { return item.category === 'Drinks' ? { sweetness: 'normal', temperature: 'hot' } : { chilli: 'regular' }; }
export function prepareMenu(catalogue) {
  if (!Array.isArray(catalogue.items)) throw new Error('Missing menu');
  const seen = new Set();
  return catalogue.items.map(item => {
    if (typeof item.canonical !== 'string' || seen.has(item.canonical) || typeof item.display !== 'string' || !Number.isFinite(item.price) || item.price < 0) throw new Error('Invalid menu');
    seen.add(item.canonical);
    const [category = 'Food', zh = item.display, description = '', descriptionZh = ''] = details[item.canonical] || [];
    return { ...item, category, zh, description, descriptionZh, cents: Math.round(item.price * 100) };
  }).sort((a,b) => ({CHICKEN_RICE:0,NASI_LEMAK:1}[a.canonical]??2) - ({CHICKEN_RICE:0,NASI_LEMAK:1}[b.canonical]??2));
}
export class DemoOrder {
  constructor(items) { this.items = items; this.lines = []; this.confirmed = false; }
  item(id) { const item = this.items.find(i => i.canonical === id); if (!item) throw new Error('Unknown dish'); return item; }
  validate(item, quantity, options) {
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 20) throw new Error('Choose a quantity from 1 to 20.');
    const defaults = defaultOptions(item);
    if (!options || Object.keys(options).some(k => !(k in defaults) || !optionGroups[k].includes(options[k]))) throw new Error('Invalid options');
    return { ...defaults, ...options };
  }
  key(id, options) { return `${id}:${Object.entries(options).sort().map(([k,v])=>`${k}=${v}`).join('|')}`; }
  add(id, quantity = 1, options = {}) {
    const item = this.item(id); const opts = this.validate(item, quantity, options); const key = this.key(id, opts);
    const line = this.lines.find(l => l.key === key);
    if (line && line.quantity + quantity > 20) throw new Error('A maximum of 20 of the same choice is available in this demo.');
    if (line) line.quantity += quantity; else this.lines.push({ key, id, quantity, options: opts });
    this.confirmed = false; return key;
  }
  edit(key, quantity, options) {
    const line = this.lines.find(l => l.key === key); if (!line) throw new Error('Item no longer in order');
    const opts = this.validate(this.item(line.id), quantity, options); const newKey = this.key(line.id, opts);
    const other = this.lines.find(l => l.key === newKey && l.key !== key);
    if (other && other.quantity + quantity > 20) throw new Error('A maximum of 20 of the same choice is available in this demo.');
    if (other) { other.quantity += quantity; this.lines = this.lines.filter(l => l.key !== key); }
    else Object.assign(line, { key: newKey, quantity, options: opts });
    this.confirmed = false;
  }
  remove(key) { this.lines = this.lines.filter(l => l.key !== key); this.confirmed = false; }
  get count() { return this.lines.reduce((n,l) => n + l.quantity, 0); }
  get total() { return this.lines.reduce((n,l) => n + this.item(l.id).cents * l.quantity, 0); }
  confirm() { if (!this.lines.length) throw new Error('Add a dish first'); this.confirmed = true; }
  reset() { this.lines = []; this.confirmed = false; }
}
const numbers = { a:1, an:1, one:1, two:2, three:3, four:4, five:5, six:6, seven:7, eight:8, nine:9, ten:10, 一:1, 二:2, 两:2, 三:3, 四:4, 五:5, 六:6, 七:7, 八:8, 九:9, 十:10 };
const normalize = text => text.toLowerCase().replace(/[’']/g,'').replace(/-/g,' ').replace(/\s+/g,' ').trim();
const regexEscape = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
export function mentionedItems(text, items) {
  const candidates = [];
  for (const item of items) for (const alias of new Set([item.display, item.zh, ...(item.aliases || [])].map(normalize))) {
    const re = new RegExp(`(^|[^a-z0-9])(${regexEscape(alias)})(?=$|[^a-z0-9])`, 'g');
    for (const match of text.matchAll(re)) candidates.push({ item, start: match.index + match[1].length, end: match.index + match[0].length });
  }
  candidates.sort((a,b) => (b.end-b.start)-(a.end-a.start));
  const selected = [];
  for (const candidate of candidates) if (!selected.some(s => candidate.start < s.end && candidate.end > s.start)) selected.push(candidate);
  return selected.sort((a,b) => a.start-b.start);
}
export function interpret(text, items) {
  const value = normalize(text);
  const found = mentionedItems(value, items);
  if (!value) return { type:'help' };
  if (/\b(allerg|diabet|healthy|safe|ingredient|nuts?|peanut|gluten|halal)\b|过敏|糖尿|健康|成分|清真/.test(value)) return { type:'unknownDetails' };
  if (/\b(review|checkout|confirm|my order|my cart|total|bill|thats all)\b|查看订单|确认|我的订单|总共|总价/.test(value)) return { type:'review' };
  const budget = value.match(/(?:under|below|less than|不超过|低于|少于)\s*\$?\s*(\d+(?:\.\d+)?)/);
  if (budget) return { type:'list', ids:items.filter(i=>i.cents < Number(budget[1])*100 || (value.includes('不超过') && i.cents === Number(budget[1])*100)).map(i=>i.canonical), budget:budget[1] };
  const controlValue=value.replace(/(?:dont want|do not want)\s+(?:chilli|chili|sugar)|不要(?:辣椒?|糖)/g,'');
  if (/\b(remove|delete|cancel|dont want|do not want)\b|不要|删除|取消/.test(controlValue)) return { type:'remove', ids:[...new Set(found.map(f=>f.item.canonical))] };
  if (/\b(change|instead|make it|actually)\b|改成|换成|修改/.test(value)) return { type:'edit', ids:[...new Set(found.map(f=>f.item.canonical))] };
  if (/\b(maybe|might|thinking|dont add|do not add|not sure|dont order|do not order)\b|可能|不确定|别加|不要加/.test(value)) return { type:'help' };
  const question = /[?？]|\b(what|which|explain|tell|show|how much|is there|do you|does|can i|can you)\b|介绍|有什么|多少钱|是什么|看看/.test(value);
  const explicit = /\b(add|want|order|give me|i would like|id like|ill have|can i have|can you add)\b|我要|我想要|加一|来一|帮我加/.test(value);
  const numbered = /^(?:please\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\s|^[一二两三四五六七八九十]\s*[杯份碗个]/.test(value);
  if (found.length && (explicit || numbered) && !(question && !/\b(can i have|can you add)\b/.test(value))) {
    // A demo must not silently add only the recognised half of a request.
    let remainder=value;
    for (const match of [...found].reverse()) remainder=remainder.slice(0,match.start)+' '.repeat(match.end-match.start)+remainder.slice(match.end);
    remainder=remainder.replace(/\b(?:less sweet|less sugar|siew dai|siu dai|no sugar|kosong|dont want sugar|do not want sugar|no chilli|no chili|not spicy|without chilli|less chilli|little chilli|dont want chilli|do not want chilli)\b/g,' ')
      .replace(/\b(?:please|thanks|thank you|lah|can|could|you|i|me|my|id|would|like|ill|have|want|add|order|give|and|also|plus|with|of|a|an|one|two|three|four|five|six|seven|eight|nine|ten|hot|iced|ice|peng|cold)\b/g,' ')
      .replace(/不要辣椒|不要辣|不辣|少辣|微辣|少糖|无糖|不加糖|不要糖|冰|热|我想要|我要|帮我加|请|和|还有|再来|来|加|杯|份|碗|个|一|二|两|三|四|五|六|七|八|九|十/g,' ')
      .replace(/[\d\s,，.!！?？$]/g,'');
    if(remainder) return { type:'help' };
    const additions = found.map((match,index) => {
      const prefix = value.slice(index ? found[index-1].end : 0, match.start);
      const quantityToken = prefix.match(/(?:\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\b|([一二两三四五六七八九十]))\s*(?:份|杯|碗|个)?\s*$/);
      const raw = quantityToken?.[1] || quantityToken?.[2];
      const quantity = raw ? numbers[raw] ?? Number(raw) : 1;
      const context = value.slice(index ? found[index-1].end : 0, found[index+1]?.start ?? value.length);
      const options = defaultOptions(match.item);
      if (match.item.category === 'Drinks') {
        if (/less sweet|less sugar|siew dai|siu dai|少糖/.test(context)) options.sweetness='less';
        if (/no sugar|kosong|dont want sugar|do not want sugar|无糖|不加糖|不要糖/.test(context)) options.sweetness='none';
        if (/\b(iced|ice|peng|cold)\b|冰/.test(context)) options.temperature='iced';
      } else {
        if (/no chill?i|not spicy|without chill?i|dont want chill?i|do not want chill?i|不要辣|不辣/.test(context)) options.chilli='no';
        else if (/less chill?i|little chill?i|少辣|微辣/.test(context)) options.chilli='little';
      }
      return { id:match.item.canonical, quantity, options };
    });
    if (additions.some(a=>!Number.isInteger(a.quantity)||a.quantity<1||a.quantity>20)) return { type:'quantityError' };
    return { type:'add', additions };
  }
  if (found.length) return { type:'info', ids:[...new Set(found.map(f=>f.item.canonical))] };
  if (/\b(drink|drinks|coffee|tea)\b|饮料|喝/.test(value)) return { type:'list', ids:items.filter(i=>i.category==='Drinks').map(i=>i.canonical) };
  if (/\b(food|eat|menu|show|hungry)\b|食物|吃|菜单/.test(value)) return { type:'list', ids:items.filter(i=>i.category==='Food').map(i=>i.canonical) };
  return { type:'help' };
}
