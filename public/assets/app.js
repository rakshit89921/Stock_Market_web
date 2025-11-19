const $ = (sel, ctx=document)=>ctx.querySelector(sel);
const $$ = (sel, ctx=document)=>[...ctx.querySelectorAll(sel)];

async function fetchJSON(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

function parseChangePercent(s){
  if(typeof s!=='string') return NaN;
  return parseFloat(s.replace('%',''));
}
function setPill(el, percentStr){
  const p = parseChangePercent(percentStr);
  el.textContent = (isNaN(p)?percentStr : (p>=0?'+':'') + p.toFixed(2) + '%');
  el.className = 'pill ' + (isNaN(p)?'':'') + (p>=0?' up':' down');
}

async function hydrateCards(){
  const cards = $$("#cards .stock-card");
  for(const card of cards){
    const symbol = card.dataset.symbol;
    try{
      const data = await fetchJSON(`/api/quote?symbol=${encodeURIComponent(symbol)}`);
      const q = data?.["Global Quote"] || data;
      const price = q["05. price"] || q.price || "—";
      const changeP = q["10. change percent"] || q.changePercent || "0%";
      card.querySelector(".price").textContent = price;
      setPill(card.querySelector(".pill"), changeP);
      const badge = card.querySelector(".badge");
      const p = parseChangePercent(changeP);
      badge.textContent = isNaN(p) ? "—" : (p>=0 ? "▲ Up" : "▼ Down");
    }catch(e){ console.error(symbol, e); }
  }
}

function getParam(name){return new URLSearchParams(location.search).get(name)}

async function hydrateStockPage(){
  const title = $("#stock-title"); if(!title) return;
  const symbol = getParam('symbol') || "RELIANCE.BSE";
  title.textContent = symbol;
  try{
    const data = await fetchJSON(`/api/quote?symbol=${encodeURIComponent(symbol)}`);
    const q = data?.["Global Quote"] || data;
    const price = q["05. price"] || q.price || "—";
    const changeP = q["10. change percent"] || q.changePercent || "0%";
    $("#price").textContent = price;
    setPill($("#delta"), changeP);
  }catch(e){ console.error(e); }
  try{
    const p = await fetchJSON(`/api/insight?symbol=${encodeURIComponent(symbol)}`);
    const box = $("#insight-box"); const txt = $("#insight");
    if(p && p.summary){ box.hidden = false; txt.textContent = p.summary; }
  }catch(e){ /* ok if GROQ not configured */ }
}

async function wireSearch(){
  const input = $("#q"); const list = $("#search-results ul");
  if(!input || !list) return;
  input.addEventListener("input", async () => {
    const q = input.value.trim(); if(q.length<1){ list.innerHTML=''; return; }
    try{
      const res = await fetchJSON(`/api/search?q=${encodeURIComponent(q)}`);
      const best = res.bestMatches || [];
      list.innerHTML = best.slice(0,5).map(x=>`<li><a href="stock.html?symbol=${x['1. symbol']||x.symbol}">${x['1. symbol']||x.symbol} <span class="muted">${x['2. name']||x.name||''}</span></a></li>`).join('');
    }catch(e){ console.error(e); }
  });
}

window.addEventListener("DOMContentLoaded", () => {
  hydrateCards();
  hydrateStockPage();
  wireSearch();
});
