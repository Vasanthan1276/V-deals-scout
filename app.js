let allDeals = [];
let activeFilter = "all";

const categoryLabels = {
  hotel: "Hotel",
  food: "Food",
  sale: "Sale",
  idea: "Idea for us"
};

function money(v, currency="SGD"){
  if(v === undefined || v === null || v === "") return "";
  return new Intl.NumberFormat("en-SG", {
    style:"currency", currency, maximumFractionDigits:0
  }).format(v);
}

function formatDate(d){
  if(!d) return "";
  const dt = new Date(d + "T12:00:00");
  return dt.toLocaleDateString("en-SG",{day:"numeric",month:"short"});
}

function detailPills(item){
  const parts = [];
  if(item.current_price) parts.push(`Nightly ${money(item.current_price,item.currency)}`);
  if(item.historical_median) parts.push(`Reference ${money(item.historical_median,item.currency)}`);
  if(item.check_in) parts.push(`${formatDate(item.check_in)} → ${formatDate(item.check_out)}`);
  if(item.nights) parts.push(`${item.nights} night${item.nights>1?"s":""}`);
  if(item.discount_percent) parts.push(`${item.discount_percent}% off`);
  if(item.estimated_cost) parts.push(`Est. ${money(item.estimated_cost,item.currency)}`);
  return parts.slice(0,4);
}

function description(item){
  if(item.why) return item.why;
  if(item.description) return item.description;
  if(item.category === "hotel"){
    const saving = item.historical_median && item.current_price
      ? Math.round((item.historical_median-item.current_price)/item.historical_median*100)
      : 0;
    return saving > 0
      ? `${saving}% below the current reference price used by the scout.`
      : "Hotel opportunity on the watchlist.";
  }
  return "";
}

function render(){
  const data = activeFilter === "all"
    ? allDeals
    : allDeals.filter(x => x.category === activeFilter);

  const root = document.querySelector("#deals");
  const empty = document.querySelector("#empty");
  root.innerHTML = "";
  empty.hidden = data.length > 0;

  for(const item of data){
    const div = document.createElement("article");
    div.className = "card";
    const where = item.destination || item.location || "";
    const pills = detailPills(item).map(x=>`<div class="pill">${x}</div>`).join("");
    const action = item.booking_url || item.url;
    div.innerHTML = `
      <div class="card-top">
        <div>
          <div class="kind">${categoryLabels[item.category] || item.category}</div>
          <h2>${item.name}</h2>
          <div class="location">${where}</div>
        </div>
        <div class="score"><strong>${Math.round(item.deal_score || 0)}</strong><span>/100</span></div>
      </div>
      <div class="details">${pills}</div>
      <div class="desc">${description(item)}</div>
      ${action ? `<a class="action" href="${action}" target="_blank" rel="noopener">View deal →</a>` : ""}
      ${item.is_demo ? `<div class="demo-note">Illustrative demo entry — not a live quoted price or promotion.</div>` : ""}
    `;
    root.appendChild(div);
  }

  const hotelCount = allDeals.filter(x=>x.category==="hotel").length;
  const excellent = allDeals.filter(x=>(x.deal_score||0)>=85).length;
  document.querySelector("#summary").innerHTML = `
    <div class="metric"><b>${allDeals.length}</b><span>Deals shown</span></div>
    <div class="metric"><b>${excellent}</b><span>Excellent ≥85</span></div>
    <div class="metric"><b>${hotelCount}</b><span>Hotel ideas</span></div>
  `;
}

async function load(){
  try{
    const r = await fetch(`data/deals.json?v=${Date.now()}`);
    const payload = await r.json();
    allDeals = payload.items || [];
    document.querySelector("#updated").textContent =
      payload.updated_at ? `Last scan: ${new Date(payload.updated_at).toLocaleString("en-SG")}` : "Not scanned yet";
    document.querySelector("#demoBadge").hidden = !payload.demo_mode;
    render();
  }catch(e){
    document.querySelector("#updated").textContent = "Unable to load deal data";
    document.querySelector("#empty").hidden = false;
  }
}

document.querySelectorAll(".tab").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
    btn.classList.add("active");
    activeFilter = btn.dataset.filter;
    render();
  });
});

load();
