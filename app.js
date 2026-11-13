let allDeals = [];
let activeFilter = "all";
let activeSubfilter = "all";
let activeDealTypeFilter = "all";
let payloadStats = {};
let currentPayload = {};
let sourceHealth = {};
let hotelLoadError = false;
let pageLoaded = false;
let stored;
try {
  stored = Scout.loadSaved(window.localStorage);
} catch {
  stored = { data: {}, error: true };
}
let savedItems = stored.data;
let duplicateGroups = new Map();

const categoryLabels = {
  hotel: "Hotel",
  food: "Food",
  sale: "Sale",
  idea: "Idea for us",
};

const foodGroupLabels = {
  hotel_dining: "Hotel Dining",
  japanese: "Japanese",
  korean: "Korean",
  indian: "Indian",
  chinese_hotpot: "Chinese & Hotpot",
  southeast_asian: "Southeast Asian",
  western_international: "Western & International",
  cafe_casual: "Cafe & Casual",
  other_dining: "Other Dining",
};

const salesGroupLabels = {
  electronics: "Electronics",
  sportswear_footwear: "Sportswear & Footwear",
  outlet_clearance: "Outlet & Clearance",
  travel_luggage: "Travel & Luggage",
  fashion_clearance: "Fashion & Accessories",
};

const foodGroupOrder = [
  "indian",
  "hotel_dining",
  "japanese",
  "korean",
  "chinese_hotpot",
  "southeast_asian",
  "western_international",
  "cafe_casual",
  "other_dining",
];

const salesGroupOrder = [
  "electronics",
  "sportswear_footwear",
  "outlet_clearance",
  "travel_luggage",
  "fashion_clearance",
];

const foodDealTypeLabels = {
  app_deal: "Eatigo / App",
  card_deal: "Card Deals",
  direct: "Direct",
  membership_deal: "Member Deals",
  discovery: "Discovery",
};

const salesDealTypeLabels = {
  direct_brand: "Direct Brand",
  direct_retailer: "Direct Retailer",
  card_deal: "Card Deals",
  mall_outlet: "Mall / Outlet",
  discovery: "Discovery",
};

const foodDealTypeOrder = [
  "direct",
  "card_deal",
  "app_deal",
  "membership_deal",
  "discovery",
];

const salesDealTypeOrder = [
  "direct_brand",
  "direct_retailer",
  "mall_outlet",
  "card_deal",
  "discovery",
];

function groupForItem(item) {
  if (item.category === "food") {
    return item.food_category || "other_dining";
  }

  if (item.category === "sale") {
    return item.subcategory || "fashion_clearance";
  }

  return "all";
}

function groupLabel(item) {
  const group = groupForItem(item);

  if (item.category === "food") {
    return foodGroupLabels[group] || titleCaseToken(group);
  }

  if (item.category === "sale") {
    return salesGroupLabels[group] || titleCaseToken(group);
  }

  return "";
}

function dealTypeForItem(item) {
  return (
    item.deal_type ||
    (item.category === "food" &&
    String(item.source || "")
      .toLowerCase()
      .includes("eatigo")
      ? "app_deal"
      : "discovery")
  );
}

function dealTypeLabel(item) {
  const key = dealTypeForItem(item);
  const labels =
    item.category === "food" ? foodDealTypeLabels : salesDealTypeLabels;
  return labels[key] || titleCaseToken(key);
}

function cardCategoryLabel(item) {
  const base = categoryLabels[item.category] || item.category || "Deal";
  const group = groupLabel(item);

  return group ? `${base} · ${group}` : base;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeExternalUrl(value) {
  if (!value) {
    return "";
  }

  try {
    const url = new URL(value, window.location.href);

    if (url.protocol === "https:" || url.protocol === "http:") {
      return url.href;
    }
  } catch (error) {
    console.warn("Ignoring invalid deal URL", error);
  }

  return "";
}

function money(value, currency = "SGD") {
  if (value === undefined || value === null || value === "") {
    return "";
  }

  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency,
    currencyDisplay: "code",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value + "T12:00:00+08:00");

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleDateString("en-SG", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Singapore",
  });
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-SG", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Asia/Singapore",
    timeZoneName: "short",
  });
}

function pctBelow(current, reference) {
  current = Number(current);

  reference = Number(reference);

  if (!current || !reference || reference <= 0 || current >= reference) {
    return 0;
  }

  return Math.round(((reference - current) / reference) * 100);
}

function titleCaseToken(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function detailPills(item) {
  const parts = [];

  if (["hotel", "idea"].includes(item.category)) {
    if (item.current_price) {
      parts.push(
        `${item.is_evaluation ? "Eval. net / night" : "Nightly"} ${money(
          item.current_price,
          item.currency,
        )}`,
      );
    }

    if (
      item.reference_source === "observed price history" &&
      item.historical_median
    ) {
      parts.push(
        `Observed median ${money(item.historical_median, item.currency)}`,
      );
    } else if (
      item.reference_source === "same-date peer comparison" &&
      item.peer_median
    ) {
      parts.push(`Peer median ${money(item.peer_median, item.currency)}`);
    }

    if (item.check_in) {
      parts.push(
        `${formatDate(item.check_in)} → ${
          formatDate(item.check_out) || "unknown check-out"
        }`,
      );
    }

    if (item.nights) {
      parts.push(`${item.nights} night${item.nights > 1 ? "s" : ""}`);
    }
  }

  if (item.category === "food") {
    if (item.discount_percent) {
      parts.push(Scout.discountLabel(item));
    }

    if (item.meal_period) {
      parts.push(titleCaseToken(item.meal_period));
    }

    if (item.rating) {
      parts.push(`${Number(item.rating).toFixed(1)} ★`);
    }

    if (
      Array.isArray(item.best_discount_times) &&
      item.best_discount_times.length
    ) {
      parts.push(
        `Best slots ${item.best_discount_times.slice(0, 2).join(", ")}`,
      );
    }

    if (item.deal_type) {
      parts.push(dealTypeLabel(item));
    }

    if (item.source) {
      parts.push(item.source);
    }
  }

  if (item.category === "sale") {
    if (item.discount_percent) {
      parts.push(Scout.discountLabel(item));
    }

    if (item.subcategory) {
      parts.push(groupLabel(item));
    }

    if (item.valid_until) {
      parts.push(`Until ${formatDate(item.valid_until)}`);
    }

    if (item.source) {
      parts.push(item.source);
    }
  }

  if (item.category === "idea" && item.estimated_cost) {
    parts.push(`Hotel total ${money(item.estimated_cost, item.currency)}`);
  }

  return parts.slice(0, 4);
}

function description(item) {
  if (item.category === "hotel") {
    if (item.reference_source === "observed price history") {
      const saving = pctBelow(item.current_price, item.historical_median);

      if (saving > 0) {
        return (
          `${saving}% below the median ` +
          `price observed previously ` +
          `for this same hotel and ` +
          `stay date.`
        );
      }

      return (
        "Price is being compared with " +
        "previous observations for this " +
        "same hotel and stay date."
      );
    }

    if (item.reference_source === "same-date peer comparison") {
      const saving = pctBelow(item.current_price, item.peer_median);

      if (saving > 0) {
        return (
          `Peer comparison: ${saving}% ` +
          `below the median of other ` +
          `monitored hotels for the same ` +
          `destination and dates. ` +
          `This is not historical pricing yet.`
        );
      }

      return (
        "Peer comparison only. " +
        "We do not yet have enough " +
        "observations to call this " +
        "a historical price drop."
      );
    }

    return (
      "Live Hotelbeds Evaluation " +
      "availability. More daily " +
      "observations are needed before " +
      "historical deal scoring becomes " +
      "available."
    );
  }

  if (item.why) {
    return item.why;
  }

  if (item.description) {
    return item.description;
  }

  return "";
}

function scoreCaption(item) {
  if (item.score_basis === "observed_history") {
    return "history";
  }

  if (item.score_basis === "peer_comparison") {
    return "peer";
  }

  return "/100";
}

function scoreBand(value) {
  const score = Number(value || 0);

  if (score >= 90) {
    return "Exceptional";
  }

  if (score >= 80) {
    return "Strong";
  }

  if (score >= 70) {
    return "Worth a look";
  }

  if (score >= 60) {
    return "Moderate";
  }

  return "Low priority";
}

function scoreBreakdownForItem(item) {
  return Scout.score(item);
}

function scoreHoverText(item) {
  const details = scoreBreakdownForItem(item);
  const score = Number(details.total ?? item.deal_score ?? 0);
  const components = Array.isArray(details.components)
    ? details.components
    : [];

  const componentText = components
    .slice(0, 5)
    .map(
      (part) =>
        `${part.label}: ${Number(part.points || 0).toFixed(1)}/${Number(part.max_points || 0).toFixed(0)}`,
    )
    .join(" · ");

  return componentText
    ? `Score ${Scout.round(score)}/100 (${details.band || scoreBand(score)}). ${componentText}. Click for details.`
    : `Score ${Scout.round(score)}/100 (${details.band || scoreBand(score)}). Click for scoring details.`;
}

function ensureScoreDialog() {
  let dialog = document.querySelector("#scoreExplainDialog");

  if (dialog) {
    return dialog;
  }

  dialog = document.createElement("dialog");
  dialog.id = "scoreExplainDialog";
  dialog.className = "score-dialog";
  dialog.setAttribute("aria-labelledby", "score-dialog-title");
  dialog.innerHTML = `
    <div class="score-dialog-shell">
      <button
        type="button"
        class="score-dialog-close"
        aria-label="Close scoring details"
        autofocus
      >×</button>
      <div id="scoreExplainContent"></div>
    </div>
  `;

  document.body.appendChild(dialog);

  dialog
    .querySelector(".score-dialog-close")
    .addEventListener("click", () => dialog.close());

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  return dialog;
}

function openScoreDialog(item) {
  const dialog = ensureScoreDialog();
  const root = dialog.querySelector("#scoreExplainContent");
  const details = scoreBreakdownForItem(item);
  const score = Number(details.total ?? item.deal_score ?? 0);
  const scaleMax = Number(details.scale_max || 100);
  const components = Array.isArray(details.components)
    ? details.components
    : [];
  const notes = Array.isArray(details.notes) ? details.notes : [];

  const rows = components
    .map((part) => {
      const points = Number(part.points || 0);
      const maxPoints = Math.max(1, Number(part.max_points || 0));
      const width = Math.max(0, Math.min(100, (points / maxPoints) * 100));

      return `
          <div class="score-component">
            <div class="score-component-top">
              <strong>${escapeHtml(part.label || "Score component")}</strong>
              <span>${points.toFixed(1)} / ${maxPoints.toFixed(0)}</span>
            </div>
            <div class="score-bar" aria-hidden="true">
              <span style="width:${width.toFixed(1)}%"></span>
            </div>
            <small>${escapeHtml(part.detail || "")}</small>
          </div>
        `;
    })
    .join("");

  const noteHtml = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");

  root.innerHTML = `
    <div class="score-dialog-kicker">Why this score?</div>
    <h2 id="score-dialog-title">${escapeHtml(item.name || "Deal")}</h2>

    <div class="score-dialog-total">
      <strong>${Scout.round(score)}</strong>
      <span>/ ${Math.round(scaleMax)}</span>
      <em>${escapeHtml(details.band || scoreBand(score))}</em>
    </div>

    ${
      rows
        ? `<div class="score-components">${rows}</div>`
        : `<p class="score-no-components">Detailed point components are not yet stored for this record.</p>`
    }

    <div class="score-adjustments">${(details.adjustments || []).map((a) => `<p>${escapeHtml(a.label)} <strong>${Number(a.points) > 0 ? "+" : ""}${Scout.round(a.points)}</strong></p>`).join("")}</div>
    <p class="hint">Final score: ${Scout.round(score)}/100. Component amounts and adjustments above use the stored one-decimal precision.</p>
    ${noteHtml ? `<ul class="score-notes">${noteHtml}</ul>` : ""}

    <div class="score-scale-note">
      <strong>Score scale:</strong>
      90–100 Exceptional · 80–89 Strong · 70–79 Worth a look.
      Scores below 70 normally do not enter 🔥 Best.
    </div>
  `;

  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
}

function dataNote(item) {
  if (item.is_demo)
    return '<p class="data-note note-warning">Illustrative demo; not a current offer.</p>';
  if (item.is_evaluation || /evaluation|net rate/i.test(item.price_type || ""))
    return '<p class="data-note note-warning">Hotelbeds evaluation/net rate — not a confirmed consumer-bookable price. Verify retail price, taxes and availability separately.</p>';
  return "";
}

function renderStatusBadges(payload) {
  const row = document.querySelector(".status-row");

  if (!row) {
    return;
  }

  row.querySelectorAll(".data-status-badge").forEach((node) => node.remove());

  const legacy = document.querySelector("#demoBadge");

  if (legacy) {
    legacy.hidden = true;
  }

  const status = payload.status || {};

  function addBadge(text, tone = "warning") {
    const badge = document.createElement("span");

    badge.className = `badge ${tone} data-status-badge`;

    badge.textContent = text;

    row.appendChild(badge);
  }

  if (status.hotels === "evaluation") {
    addBadge("HOTELS: EVALUATION", "warning");
  } else if (status.hotels === "live") {
    addBadge("HOTELS: LIVE", "live");
  }

  if (status.food === "live") {
    addBadge("FOOD: LIVE/BETA", "live");
  } else if (status.food === "demo") {
    addBadge("FOOD: DEMO", "warning");
  }

  if (status.sales === "live") {
    addBadge("SALES: LIVE/BETA", "live");
  } else if (status.sales === "demo") {
    addBadge("SALES: DEMO", "warning");
  }
}

function renderSubfilters() {
  const panel = document.querySelector("#subfilters");
  const title = document.querySelector("#subfilter-title");
  const note = document.querySelector("#subfilter-note");
  const buttons = document.querySelector("#subfilter-buttons");
  const dealTitle = document.querySelector("#dealtype-title");
  const dealButtons = document.querySelector("#dealtype-buttons");

  if (!panel || !title || !note || !buttons || !dealTitle || !dealButtons) {
    return;
  }

  if (!["food", "sale"].includes(activeFilter)) {
    panel.hidden = true;
    buttons.innerHTML = "";
    dealButtons.innerHTML = "";
    return;
  }

  const categoryItems = allDeals.filter(
    (item) => item.category === activeFilter,
  );

  const counts = new Map();
  const dealCounts = new Map();

  for (const item of categoryItems) {
    const group = groupForItem(item);
    counts.set(group, (counts.get(group) || 0) + 1);

    const dtype = dealTypeForItem(item);
    dealCounts.set(dtype, (dealCounts.get(dtype) || 0) + 1);
  }

  const labels = activeFilter === "food" ? foodGroupLabels : salesGroupLabels;
  const order = activeFilter === "food" ? foodGroupOrder : salesGroupOrder;
  const typeLabels =
    activeFilter === "food" ? foodDealTypeLabels : salesDealTypeLabels;
  const typeOrder =
    activeFilter === "food" ? foodDealTypeOrder : salesDealTypeOrder;

  title.textContent =
    activeFilter === "food"
      ? "Browse Food by cuisine / dining category"
      : "Browse Sales by category";

  note.textContent =
    activeFilter === "food"
      ? "Indian is prioritised. Some cuisine tags are inferred from the venue or promotion text."
      : "Categories are based on the promotion listing and product type.";

  dealTitle.textContent =
    activeFilter === "food" ? "Filter by deal source" : "Filter by sale source";

  const options = [
    {
      key: "all",
      label: activeFilter === "food" ? "All Food" : "All Sales",
      count: categoryItems.length,
    },
    ...order
      .filter((key) => counts.get(key))
      .map((key) => ({
        key,
        label: labels[key] || titleCaseToken(key),
        count: counts.get(key),
      })),
  ];

  const dealOptions = [
    { key: "all", label: "All Sources", count: categoryItems.length },
    ...typeOrder
      .filter((key) => dealCounts.get(key))
      .map((key) => ({
        key,
        label: typeLabels[key] || titleCaseToken(key),
        count: dealCounts.get(key),
      })),
  ];

  if (activeSubfilter !== "all" && !counts.get(activeSubfilter)) {
    activeSubfilter = "all";
  }

  if (activeDealTypeFilter !== "all" && !dealCounts.get(activeDealTypeFilter)) {
    activeDealTypeFilter = "all";
  }

  buttons.innerHTML = options
    .map(
      (option) => `
      <button
        class="subfilter ${option.key === activeSubfilter ? "active" : ""}"
        data-subfilter="${escapeHtml(option.key)}"
        type="button"
      >
        ${escapeHtml(option.label)}
        <span>${option.count}</span>
      </button>
    `,
    )
    .join("");

  dealButtons.innerHTML = dealOptions
    .map(
      (option) => `
      <button
        class="subfilter source-filter ${option.key === activeDealTypeFilter ? "active" : ""}"
        data-dealtype="${escapeHtml(option.key)}"
        type="button"
      >
        ${escapeHtml(option.label)}
        <span>${option.count}</span>
      </button>
    `,
    )
    .join("");

  buttons.querySelectorAll(".subfilter").forEach((button) => {
    button.addEventListener("click", () => {
      activeSubfilter = button.dataset.subfilter || "all";
      render();
    });
  });

  dealButtons.querySelectorAll(".subfilter").forEach((button) => {
    button.addEventListener("click", () => {
      activeDealTypeFilter = button.dataset.dealtype || "all";
      render();
    });
  });

  panel.hidden = false;
}

function renderUpdated(payload) {
  const updated = document.querySelector("#updated");
  if (!updated) {
    return;
  }

  const sourceTimes = payload.source_updated_at || {};
  const hotelTime = sourceTimes.hotels || payload.updated_at;
  const foodTime =
    sourceTimes.food || payload.nonhotel_updated_at || payload.updated_at;
  const salesTime =
    sourceTimes.sales || payload.nonhotel_updated_at || payload.updated_at;

  if (hotelTime && foodTime && salesTime) {
    if (hotelTime === foodTime && foodTime === salesTime) {
      updated.textContent = `Full scan: ${formatDateTime(hotelTime)}`;
      return;
    }

    if (foodTime === salesTime) {
      updated.textContent =
        `Hotels: ${formatDateTime(hotelTime)} · ` +
        `Food/Sales: ${formatDateTime(foodTime)}`;
      return;
    }

    updated.textContent =
      `Hotels: ${formatDateTime(hotelTime)} · ` +
      `Food: ${formatDateTime(foodTime)} · ` +
      `Sales: ${formatDateTime(salesTime)}`;
    return;
  }

  if (payload.updated_at) {
    updated.textContent = `Last full scan: ${formatDateTime(payload.updated_at)}`;
    return;
  }

  updated.textContent = "Not scanned yet";
}

function updateEmptyMessage() {
  document.querySelector("#empty h2").textContent =
    "No recommendations match this view.";
  document.querySelector("#empty p").textContent =
    "Try another category, reset filters, or include expired items. Source health above explains failed and empty scans.";
}

function filterValues() {
  const value = (id) => document.getElementById(id)?.value || "";
  return {
    search: value("search"),
    destination: value("destination"),
    from: value("date-from"),
    to: value("date-to"),
    budget: value("budget"),
    kind: value("offer-kind"),
    expiry: value("expiry"),
    sort: value("sort"),
  };
}
function updateStorageNote(failed = false) {
  const node = document.querySelector("#storage-note");
  node.textContent = failed
    ? "Browser storage unavailable or damaged. Changes work for this session only and may be lost on reload."
    : "Saved and dismissed items stay in this browser only. They do not sync across devices.";
  node.classList.toggle("warning", failed);
}
function setSaved(item, state) {
  const id = Scout.key(item);
  if (state)
    savedItems[id] = { state, item, saved_at: new Date().toISOString() };
  else delete savedItems[id];
  let ok = false;
  try {
    ok = Scout.save(window.localStorage, savedItems);
  } catch {}
  updateStorageNote(!ok);
  render();
}
function offerDetails(item) {
  const e = escapeHtml;
  const rows = [
    ["Source", item.source || item.provider || "Not recorded"],
    [
      "Last observed",
      item.observed_at ? formatDateTime(item.observed_at) : "Unknown",
    ],
    [
      "Last verified terms",
      item.verified_at
        ? formatDateTime(item.verified_at)
        : "Not recorded; source observation is not full terms verification",
    ],
    [
      "Expiry",
      item.valid_until
        ? formatDate(item.valid_until)
        : "Unknown; do not assume ongoing validity",
    ],
    [
      "Eligibility",
      item.access_requirement || "Not recorded; check original source",
    ],
    [
      "Restrictions",
      item.booking_restrictions ||
        "Full booking, blackout and exclusion terms not recorded",
    ],
  ];
  if (item.check_in)
    rows.push([
      "Recorded stay",
      `${formatDate(item.check_in)} → ${item.check_out ? formatDate(item.check_out) : "check-out unknown"}`,
    ]);
  if (item.valid_from) rows.push(["Offer starts", formatDate(item.valid_from)]);
  if (item.room_name)
    rows.push([
      "Room / board",
      `${item.room_name} · ${item.board_name || "Board unknown"}`,
    ]);
  if (item.total_price != null)
    rows.push([
      "Hotel stay total",
      `${money(item.total_price, item.currency)} · ${item.price_type || "price basis unknown"} · taxes/fees not confirmed`,
    ]);
  if (item.cost_scope) rows.push(["Cost scope", item.cost_scope]);
  if (item.food_category_inferred)
    rows.push(["Cuisine", "Inferred from listing text; may need correction"]);
  if (item.best_discount_times?.length)
    rows.push([
      "Observed time slots",
      item.best_discount_times.join(", ") + " · applicable dates not recorded",
    ]);
  if (item.history_observations != null)
    rows.push([
      "Price reference",
      `${item.reference_source || "Unknown"} · ${item.history_observations} observations`,
    ]);
  if (item.category === "hotel")
    rows.push([
      "Suitability inputs",
      "Quiet, couples, location and date fit include configured assumptions; room amenities need verification",
    ]);
  if (item.source_confidence)
    rows.push([
      "Source classification",
      item.source_confidence === "verified"
        ? "Official/direct source observed; eligibility and availability still require verification"
        : titleCaseToken(item.source_confidence),
    ]);
  const dup = duplicateGroups.get(Scout.key(item));
  const peers = dup
    ? `<p>Likely duplicate group ${dup.group}; compare the sources. Listings remain separate.</p><ul>${dup.peers.map((p) => `<li>${safeExternalUrl(p.url) ? `<a href="${e(safeExternalUrl(p.url))}" target="_blank" rel="noopener noreferrer">${e(p.name)}</a>` : e(p.name)}</li>`).join("")}</ul>`
    : "";
  return `<details class="offer-details"><summary>Source, terms & price context</summary><dl>${rows.map(([k, v]) => `<dt>${e(k)}</dt><dd>${e(v)}</dd>`).join("")}</dl>${peers}</details>`;
}
function renderHealth(payload, status) {
  const categories = ["hotels", "food", "sales"];
  const times = payload.source_updated_at || {};
  document.querySelector("#source-health").innerHTML = categories
    .map((c) => {
      const entry = status.sources?.[c] || {};
      const result = Scout.health(entry, times[c] || payload.updated_at);
      return `<section class="health-source"><h3>${titleCaseToken(c)} <span class="${result.stale || /failed|partial|retained/.test(entry.state) ? "warning" : ""}">${escapeHtml(result.label)}</span></h3>
    <p>Last attempted: ${escapeHtml(entry.last_attempt ? formatDateTime(entry.last_attempt) : "Not recorded in legacy data")}<br>Last successful: ${escapeHtml(entry.last_success ? formatDateTime(entry.last_success) : "Not recorded")}<br>Published data: ${escapeHtml(formatDateTime(times[c] || payload.updated_at) || "Unknown")}</p>
    ${entry.message ? `<p>${escapeHtml(entry.message)}</p>` : ""}
    ${entry.sources?.length ? `<ul>${entry.sources.map((s) => `<li><strong>${escapeHtml(s.name)}</strong> · ${escapeHtml(s.status)} · ${s.results == null ? "result count unknown" : s.results + " parsed candidates"}<br><small>Attempt: ${escapeHtml(formatDateTime(s.last_attempt) || "Unknown")} · Success: ${escapeHtml(formatDateTime(s.last_success) || "Unknown")}</small></li>`).join("")}</ul>` : "<p>Per-source outcomes will be recorded by the updated scanner.</p>"}</section>`;
    })
    .join("");
  const issues = categories.filter((c) => {
    const r = Scout.health(status.sources?.[c], times[c] || payload.updated_at);
    return (
      r.stale ||
      ["failed", "failed_retained", "empty_retained", "partial"].includes(
        status.sources?.[c]?.state,
      )
    );
  });
  document.querySelector("#health-summary").textContent =
    `Source health & refresh times · Singapore (SGT, UTC+8)${issues.length ? " · " + issues.length + " categories need attention" : ""}`;
}
function render() {
  if (!pageLoaded) return;
  renderSubfilters();
  const mode = document.getElementById("list-mode").value;
  let pool = allDeals;
  if (mode !== "browse") {
    const liveByKey = new Map(allDeals.map((i) => [Scout.key(i), i]));
    pool = Object.entries(savedItems)
      .filter(([, v]) => v.state === mode)
      .map(([k, v]) => liveByKey.get(k) || { ...v.item, saved_snapshot: true });
  } else
    pool = pool.filter((i) => savedItems[Scout.key(i)]?.state !== "dismissed");
  let data = pool.filter((i) =>
    activeFilter === "all"
      ? mode !== "browse" || (!i.exclude_from_best && !i.is_demo)
      : i.category === activeFilter,
  );
  if (["food", "sale"].includes(activeFilter)) {
    if (activeSubfilter !== "all")
      data = data.filter((i) => groupForItem(i) === activeSubfilter);
    if (activeDealTypeFilter !== "all")
      data = data.filter((i) => dealTypeForItem(i) === activeDealTypeFilter);
  }
  data = Scout.filter(data, filterValues());
  const root = document.querySelector("#deals");
  root.innerHTML = "";
  document.querySelector("#empty").hidden = data.length > 0;
  updateEmptyMessage();
  const hotelCount = allDeals.filter((i) => i.category === "hotel").length;
  document.querySelector("#view-status").textContent =
    `${data.length} shown · ${mode === "browse" ? (activeFilter === "all" ? "Best is a curated selection, not all results" : "Filtered recommendations") : mode + " items"}${activeFilter === "hotel" ? ` · ${hotelCount} hotel results loaded of ${payloadStats.availability_results ?? hotelCount} scanned` : ""}${hotelLoadError ? " · Full hotel file unavailable; showing the dashboard subset" : ""}`;
  for (const item of data) {
    const card = document.createElement("article");
    card.className = "card";
    const id = Scout.key(item),
      state = Scout.expiry(item),
      dup = duplicateGroups.get(id),
      saved = savedItems[id]?.state;
    const action = safeExternalUrl(item.booking_url || item.url);
    const score = Scout.round(item.deal_score || 0);
    card.innerHTML = `<div class="card-top"><div><div class="kind">${escapeHtml(cardCategoryLabel(item))}</div><h2>${escapeHtml(item.name)}</h2><div class="location">${escapeHtml(item.destination || item.location || "Location not recorded")}</div></div>
      <button type="button" class="score score-button" title="${escapeHtml(scoreHoverText(item))}" aria-label="Explain score ${score} out of 100 for ${escapeHtml(item.name)}"><strong>${score}</strong><span>/100 · ${escapeHtml(scoreCaption(item) === "/100" ? "score" : scoreCaption(item))}</span></button></div>
      <div class="offer-label">${escapeHtml(Scout.kindLabels[Scout.kind(item)] || "Offer lead")}</div>
      ${["expired", "past_stay", "upcoming"].includes(state) ? `<p class="validity warning">${state === "expired" ? "Expired offer" : state === "past_stay" ? "Past stay dates" : "Upcoming offer"} · verify current alternatives</p>` : ""}
      ${item.saved_snapshot ? '<p class="warning">Saved snapshot · no longer in the current feed. Availability unverified.</p>' : ""}
      ${dup ? `<p class="duplicate-note">Likely duplicate · group ${dup.group} (${dup.count} listings kept separate)</p>` : ""}
      <div class="details">${detailPills(item)
        .map((p) => `<div class="pill">${escapeHtml(p)}</div>`)
        .join("")}</div>
      <div class="desc">${escapeHtml(description(item))}</div>
      ${dataNote(item)}
      <p class="card-freshness">${escapeHtml(item.source || item.provider || "Source unknown")} · ${item.observed_at ? "Observed " + escapeHtml(formatDateTime(item.observed_at)) : "Observation time unknown"}${Scout.health({}, item.observed_at).stale ? " · stale / age unknown" : ""}</p>
      ${offerDetails(item)}
      <div class="card-actions">${action ? `<a class="action" href="${escapeHtml(action)}" target="_blank" rel="noopener noreferrer">View source ↗</a>` : '<span class="hint">Consumer booking link not provided</span>'}<button type="button" class="save-button" aria-pressed="${saved === "saved"}">${saved === "saved" ? "Saved ✓" : "Save"}</button><button type="button" class="dismiss-button">${saved === "dismissed" ? "Restore" : "Dismiss"}</button></div>`;
    card
      .querySelector(".score-button")
      .addEventListener("click", () => openScoreDialog(item));
    card
      .querySelector(".save-button")
      .addEventListener("click", () =>
        setSaved(item, saved === "saved" ? null : "saved"),
      );
    card
      .querySelector(".dismiss-button")
      .addEventListener("click", () =>
        setSaved(item, saved === "dismissed" ? null : "dismissed"),
      );
    root.appendChild(card);
  }
  const hotelScanned = payloadStats.availability_results ?? hotelCount;
  document.querySelector("#summary").innerHTML = [
    [
      allDeals.filter(
        (i) =>
          !i.exclude_from_best &&
          !["expired", "past_stay"].includes(Scout.expiry(i)),
      ).length,
      "Best selection",
      "Balanced across categories · max 14",
    ],
    [
      hotelScanned,
      "Hotel results",
      `${hotelCount} loaded · ${payloadStats.history_ready || 0} history-ready`,
    ],
    [
      allDeals.filter((i) => i.category === "food").length,
      "Food recommendations",
      `${payloadStats.indian_food_deals || 0} Indian · cuisine & source filters`,
    ],
    [
      allDeals.filter((i) => i.category === "sale").length,
      "Retail recommendations",
      "Specific offers & ongoing promotions",
    ],
  ]
    .map(
      ([n, label, note]) =>
        `<div class="metric"><b>${n}</b><span>${label}</span><small>${note}</small></div>`,
    )
    .join("");
}

async function load() {
  pageLoaded = false;
  try {
    const response = await fetch(`data/deals.json?v=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (
      !Array.isArray(payload.items) ||
      payload.items.some((i) => !i || typeof i !== "object")
    )
      throw new Error("Invalid deal data");
    currentPayload = payload;
    payloadStats = payload.stats || {};
    let hotels = [];
    hotelLoadError = false;
    sourceHealth = {};
    try {
      const r = await fetch(`data/hotels.json?v=${Date.now()}`);
      if (!r.ok) throw Error("hotels");
      const h = await r.json();
      if (!Array.isArray(h.items)) throw Error("hotels");
      const expected = payload.source_updated_at?.hotels || payload.updated_at;
      if (h.updated_at && expected && h.updated_at !== expected)
        throw Error("Hotel snapshot differs");
      hotels = h.items;
    } catch {
      hotelLoadError = true;
    }
    const items = Scout.normalize(payload.items, hotels);
    const present = new Set(
      items.filter((i) => i.category === "hotel").map(Scout.key),
    );
    allDeals = items.concat(
      Scout.normalize(hotels)
        .filter((i) => !present.has(Scout.key(i)))
        .map((i) => ({ ...i, exclude_from_best: true })),
    );
    duplicateGroups = Scout.duplicates(allDeals);
    try {
      const r = await fetch(`data/scan-status.json?v=${Date.now()}`);
      if (r.ok) sourceHealth = await r.json();
    } catch {
      /* Explicit legacy/unknown health below. */
    }
    const select = document.querySelector("#destination");
    select.innerHTML =
      '<option value="">All locations</option>' +
      [
        ...new Set(
          allDeals.map((i) => i.destination || i.location).filter(Boolean),
        ),
      ]
        .sort()
        .map((x) => `<option>${escapeHtml(x)}</option>`)
        .join("");
    renderUpdated(payload);
    renderHealth(payload, sourceHealth);
    pageLoaded = true;
    updateStorageNote(stored.error);
    render();
  } catch (error) {
    document.querySelector("#updated").textContent =
      "Page-loading error · deal data unavailable";
    document.querySelector("#deals").innerHTML = "";
    document.querySelector("#summary").innerHTML = "";
    document.querySelector("#empty").hidden = false;
    document.querySelector("#empty h2").textContent =
      "The dashboard could not load its data.";
    document.querySelector("#empty p").innerHTML =
      'This is a page-loading error, not an empty scan. <button type="button" id="retry-load">Retry loading</button>';
    document.querySelector("#retry-load").addEventListener("click", load);
    document.querySelector("#view-status").textContent =
      "Saved items remain in this browser. Reload when the data file is available.";
    console.error(error);
  }
}

for (const id of [
  "search",
  "list-mode",
  "sort",
  "destination",
  "date-from",
  "date-to",
  "budget",
  "offer-kind",
  "expiry",
])
  document.getElementById(id).addEventListener("input", render);
document.getElementById("reset-filters").addEventListener("click", () => {
  for (const id of [
    "search",
    "destination",
    "date-from",
    "date-to",
    "budget",
    "offer-kind",
  ])
    document.getElementById(id).value = "";
  document.getElementById("expiry").value = "active";
  document.getElementById("sort").value = "score";
  activeSubfilter = "all";
  activeDealTypeFilter = "all";
  render();
});

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document
      .querySelectorAll(".tab")
      .forEach((item) => item.classList.remove("active"));

    button.classList.add("active");
    document
      .querySelectorAll(".tab")
      .forEach((t) => t.setAttribute("aria-pressed", String(t === button)));

    activeFilter = button.dataset.filter;

    activeSubfilter = "all";
    activeDealTypeFilter = "all";

    render();
  });
});

load();
