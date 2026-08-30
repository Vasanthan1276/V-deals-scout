let allDeals = [];
let activeFilter = "all";
let payloadStats = {};

const categoryLabels = {
  hotel: "Hotel",
  food: "Food",
  sale: "Sale",
  idea: "Idea for us"
};


function escapeHtml(value) {
  return String(
    value ?? ""
  )
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
    const url = new URL(
      value,
      window.location.href
    );

    if (
      url.protocol === "https:"
      ||
      url.protocol === "http:"
    ) {
      return url.href;
    }
  }

  catch (error) {
    console.warn(
      "Ignoring invalid deal URL",
      error
    );
  }

  return "";
}


function money(
  value,
  currency = "SGD"
) {
  if (
    value === undefined
    ||
    value === null
    ||
    value === ""
  ) {
    return "";
  }

  return new Intl.NumberFormat(
    "en-SG",
    {
      style: "currency",
      currency,
      maximumFractionDigits: 0
    }
  ).format(value);
}


function formatDate(value) {
  if (!value) {
    return "";
  }

  const date = new Date(
    value + "T12:00:00"
  );

  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return value;
  }

  return date.toLocaleDateString(
    "en-SG",
    {
      day: "numeric",
      month: "short"
    }
  );
}


function pctBelow(
  current,
  reference
) {
  current = Number(
    current
  );

  reference = Number(
    reference
  );

  if (
    !current
    ||
    !reference
    ||
    reference <= 0
    ||
    current >= reference
  ) {
    return 0;
  }

  return Math.round(
    (
      (
        reference
        - current
      )
      / reference
    )
    * 100
  );
}


function titleCaseToken(value) {
  return String(
    value || ""
  )
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(
      /\b\w/g,
      character =>
        character.toUpperCase()
    );
}


function detailPills(
  item
) {
  const parts = [];

  if (
    item.category === "hotel"
  ) {
    if (
      item.current_price
    ) {
      parts.push(
        `Nightly ${
          money(
            item.current_price,
            item.currency
          )
        }`
      );
    }

    if (
      item.reference_source
      === "observed price history"
      &&
      item.historical_median
    ) {
      parts.push(
        `Observed median ${
          money(
            item.historical_median,
            item.currency
          )
        }`
      );
    }

    else if (
      item.reference_source
      === "same-date peer comparison"
      &&
      item.peer_median
    ) {
      parts.push(
        `Peer median ${
          money(
            item.peer_median,
            item.currency
          )
        }`
      );
    }

    if (
      item.check_in
    ) {
      parts.push(
        `${
          formatDate(
            item.check_in
          )
        } → ${
          formatDate(
            item.check_out
          )
        }`
      );
    }

    if (
      item.nights
    ) {
      parts.push(
        `${item.nights} night${
          item.nights > 1
            ? "s"
            : ""
        }`
      );
    }
  }

  if (
    item.category === "food"
  ) {
    if (
      item.discount_percent
    ) {
      parts.push(
        `${item.discount_percent}% off`
      );
    }

    if (
      item.meal_period
    ) {
      parts.push(
        titleCaseToken(
          item.meal_period
        )
      );
    }

    if (
      item.rating
    ) {
      parts.push(
        `${Number(
          item.rating
        ).toFixed(1)} ★`
      );
    }

    if (
      Array.isArray(
        item.best_discount_times
      )
      &&
      item.best_discount_times.length
    ) {
      parts.push(
        `Best slots ${
          item.best_discount_times
            .slice(0, 2)
            .join(", ")
        }`
      );
    }
  }

  if (
    item.category === "sale"
  ) {
    if (
      item.discount_percent
    ) {
      parts.push(
        `${item.discount_percent}% off`
      );
    }

    if (
      item.subcategory
    ) {
      parts.push(
        titleCaseToken(
          item.subcategory
        )
      );
    }

    if (
      item.valid_until
    ) {
      parts.push(
        `Until ${
          formatDate(
            item.valid_until
          )
        }`
      );
    }

    if (
      item.source
    ) {
      parts.push(
        item.source
      );
    }
  }

  if (
    item.category === "idea"
    &&
    item.estimated_cost
  ) {
    parts.push(
      `Est. ${
        money(
          item.estimated_cost,
          item.currency
        )
      }`
    );
  }

  return parts.slice(
    0,
    4
  );
}


function description(
  item
) {
  if (
    item.category
    === "hotel"
  ) {
    if (
      item.reference_source
      === "observed price history"
    ) {
      const saving = pctBelow(
        item.current_price,
        item.historical_median
      );

      if (
        saving > 0
      ) {
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

    if (
      item.reference_source
      === "same-date peer comparison"
    ) {
      const saving = pctBelow(
        item.current_price,
        item.peer_median
      );

      if (
        saving > 0
      ) {
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

  if (
    item.why
  ) {
    return item.why;
  }

  if (
    item.description
  ) {
    return item.description;
  }

  return "";
}


function scoreCaption(
  item
) {
  if (
    item.score_basis
    === "observed_history"
  ) {
    return "history";
  }

  if (
    item.score_basis
    === "peer_comparison"
  ) {
    return "peer";
  }

  return "/100";
}


function dataNote(
  item
) {
  if (
    item.is_demo
  ) {
    return (
      `<div class="data-note note-warning">` +
      `Illustrative demo entry — not a live quoted price or promotion.` +
      `</div>`
    );
  }

  if (
    item.category === "hotel"
    &&
    item.is_evaluation
  ) {
    return (
      `<div class="data-note note-warning">` +
      `Hotelbeds Evaluation/net rate. Useful for testing and price trends, ` +
      `but not yet a consumer booking quote.` +
      `</div>`
    );
  }

  if (
    item.category === "food"
    &&
    item.is_live
  ) {
    return (
      `<div class="data-note note-live">` +
      `Live/beta dining promotion. Time-slot discounts and availability can change; ` +
      `confirm the offer on Eatigo before booking.` +
      `</div>`
    );
  }

  if (
    item.category === "sale"
    &&
    item.verification_required
  ) {
    return (
      `<div class="data-note note-warning">` +
      `Live/beta promotion discovery. Verify eligible products, stock, dates and final ` +
      `price with the retailer before purchase.` +
      `</div>`
    );
  }

  return "";
}


function renderStatusBadges(
  payload
) {
  const row =
    document.querySelector(
      ".status-row"
    );

  if (
    !row
  ) {
    return;
  }

  row
    .querySelectorAll(
      ".data-status-badge"
    )
    .forEach(
      node =>
        node.remove()
    );

  const legacy =
    document.querySelector(
      "#demoBadge"
    );

  if (
    legacy
  ) {
    legacy.hidden = true;
  }

  const status =
    payload.status || {};

  function addBadge(
    text,
    tone = "warning"
  ) {
    const badge =
      document.createElement(
        "span"
      );

    badge.className =
      `badge ${tone} data-status-badge`;

    badge.textContent =
      text;

    row.appendChild(
      badge
    );
  }

  if (
    status.hotels
    === "evaluation"
  ) {
    addBadge(
      "HOTELS: EVALUATION",
      "warning"
    );
  }

  else if (
    status.hotels
    === "live"
  ) {
    addBadge(
      "HOTELS: LIVE",
      "live"
    );
  }

  if (
    status.food
    === "live"
  ) {
    addBadge(
      "FOOD: LIVE/BETA",
      "live"
    );
  }

  else if (
    status.food
    === "demo"
  ) {
    addBadge(
      "FOOD: DEMO",
      "warning"
    );
  }

  if (
    status.sales
    === "live"
  ) {
    addBadge(
      "SALES: LIVE/BETA",
      "live"
    );
  }

  else if (
    status.sales
    === "demo"
  ) {
    addBadge(
      "SALES: DEMO",
      "warning"
    );
  }
}


function updateEmptyMessage() {
  const empty =
    document.querySelector(
      "#empty"
    );

  if (
    !empty
  ) {
    return;
  }

  const heading =
    empty.querySelector(
      "h2"
    );

  const text =
    empty.querySelector(
      "p"
    );

  if (
    activeFilter === "all"
  ) {
    heading.textContent =
      "No Best deals above your threshold yet.";

    text.textContent =
      "Check the Hotels, Food and Sales tabs for all currently monitored results.";
  }

  else if (
    activeFilter === "hotel"
  ) {
    heading.textContent =
      "No hotel availability in this view.";

    text.textContent =
      "The next successful daily scan will check again.";
  }

  else if (
    activeFilter === "food"
  ) {
    heading.textContent =
      "No qualifying live Food deals right now.";

    text.textContent =
      "The next scan will check Eatigo again.";
  }

  else if (
    activeFilter === "sale"
  ) {
    heading.textContent =
      "No qualifying live Sales deals right now.";

    text.textContent =
      "The next scan will check current Singapore promotions again.";
  }

  else {
    heading.textContent =
      "No ideas in this view yet.";

    text.textContent =
      "Ideas will expand as more live sources are combined.";
  }
}


function render() {
  let data;

  if (
    activeFilter
    === "all"
  ) {
    data =
      allDeals.filter(
        item =>
          !item.exclude_from_best
          &&
          !item.is_demo
      );
  }

  else {
    data =
      allDeals.filter(
        item =>
          item.category
          === activeFilter
      );
  }

  const root =
    document.querySelector(
      "#deals"
    );

  const empty =
    document.querySelector(
      "#empty"
    );

  root.innerHTML = "";

  empty.hidden =
    data.length > 0;

  updateEmptyMessage();

  for (
    const item
    of data
  ) {
    const card =
      document.createElement(
        "article"
      );

    card.className =
      "card";

    const where =
      item.destination
      ||
      item.location
      ||
      "";

    const pills =
      detailPills(
        item
      )
        .map(
          text =>
            `<div class="pill">` +
            `${escapeHtml(text)}` +
            `</div>`
        )
        .join("");

    const action =
      safeExternalUrl(
        item.booking_url
        ||
        item.url
      );

    const safeCategory =
      escapeHtml(
        categoryLabels[
          item.category
        ]
        ||
        item.category
      );

    const safeName =
      escapeHtml(
        item.name
      );

    const safeWhere =
      escapeHtml(
        where
      );

    const safeDescription =
      escapeHtml(
        description(
          item
        )
      );

    const score =
      Math.round(
        Number(
          item.deal_score
          || 0
        )
      );

    card.innerHTML = `
      <div class="card-top">

        <div>
          <div class="kind">
            ${safeCategory}
          </div>

          <h2>
            ${safeName}
          </h2>

          <div class="location">
            ${safeWhere}
          </div>
        </div>

        <div class="score">

          <strong>
            ${score}
          </strong>

          <span>
            ${
              escapeHtml(
                scoreCaption(
                  item
                )
              )
            }
          </span>

        </div>

      </div>

      <div class="details">
        ${pills}
      </div>

      <div class="desc">
        ${safeDescription}
      </div>

      ${
        action
          ? `
            <a
              class="action"
              href="${escapeHtml(action)}"
              target="_blank"
              rel="noopener noreferrer"
            >
              View deal →
            </a>
          `
          : ""
      }

      ${
        dataNote(
          item
        )
      }
    `;

    root.appendChild(
      card
    );
  }

  const bestCount =
    payloadStats.best_deals
    ??
    allDeals.filter(
      item =>
        !item.exclude_from_best
        &&
        !item.is_demo
    ).length;

  const availabilityCount =
    payloadStats.availability_results
    ??
    payloadStats.hotel_results
    ??
    allDeals.filter(
      item =>
        item.category
        === "hotel"
    ).length;

  const historyReady =
    payloadStats.history_ready
    ??
    allDeals.filter(
      item =>
        item.score_basis
        === "observed_history"
    ).length;

  const foodCount =
    payloadStats.food_results
    ??
    allDeals.filter(
      item =>
        item.category
        === "food"
    ).length;

  const salesCount =
    payloadStats.sales_results
    ??
    allDeals.filter(
      item =>
        item.category
        === "sale"
    ).length;

  document.querySelector(
    "#summary"
  ).innerHTML = `

    <div class="metric">
      <b>
        ${bestCount}
      </b>

      <span>
        Best deals
      </span>
    </div>

    <div class="metric">
      <b>
        ${availabilityCount}
      </b>

      <span>
        Hotel availability
      </span>

      <small>
        ${historyReady} history-ready
      </small>
    </div>

    <div class="metric">
      <b>
        ${foodCount}
      </b>

      <span>
        Live Food deals
      </span>
    </div>

    <div class="metric">
      <b>
        ${salesCount}
      </b>

      <span>
        Live Sales deals
      </span>
    </div>

  `;
}


async function load() {
  try {
    const response =
      await fetch(
        `data/deals.json?v=${Date.now()}`
      );

    if (
      !response.ok
    ) {
      throw new Error(
        `Deals data HTTP ${response.status}`
      );
    }

    const payload =
      await response.json();

    allDeals =
      payload.items || [];

    payloadStats =
      payload.stats || {};

    const updated =
      document.querySelector(
        "#updated"
      );

    if (
      payload.updated_at
    ) {
      updated.textContent =
        `Last scan: ${
          new Date(
            payload.updated_at
          )
            .toLocaleString(
              "en-SG"
            )
        }`;
    }

    else {
      updated.textContent =
        "Not scanned yet";
    }

    renderStatusBadges(
      payload
    );

    render();
  }

  catch (
    error
  ) {
    document.querySelector(
      "#updated"
    ).textContent =
      "Unable to load deal data";

    document.querySelector(
      "#empty"
    ).hidden =
      false;

    updateEmptyMessage();

    console.error(
      error
    );
  }
}


document
  .querySelectorAll(
    ".tab"
  )
  .forEach(
    button => {
      button.addEventListener(
        "click",
        () => {
          document
            .querySelectorAll(
              ".tab"
            )
            .forEach(
              item =>
                item.classList.remove(
                  "active"
                )
            );

          button.classList.add(
            "active"
          );

          activeFilter =
            button.dataset.filter;

          render();
        }
      );
    }
  );


load();
