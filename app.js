let allDeals = [];
let activeFilter = "all";
let payloadStats = {};

const categoryLabels = {
  hotel: "Hotel",
  food: "Food",
  sale: "Sale",
  idea: "Idea for us"
};


function money(
  value,
  currency = "SGD"
) {
  if (
    value === undefined ||
    value === null ||
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
    !current ||
    !reference ||
    reference <= 0 ||
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


function detailPills(
  item
) {
  const parts = [];

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

  if (
    item.discount_percent
  ) {
    parts.push(
      `${item.discount_percent}% off`
    );
  }

  if (
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
      `<div class="demo-note">` +
      `Illustrative demo entry — ` +
      `not a live quoted price or promotion.` +
      `</div>`
    );
  }

  if (
    item.category
    === "hotel"
    &&
    item.is_evaluation
  ) {
    return (
      `<div class="demo-note">` +
      `Hotelbeds Evaluation/net rate. ` +
      `Useful for testing and price trends, ` +
      `but not yet a consumer booking quote.` +
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

  const old =
    row.querySelectorAll(
      ".data-status-badge"
    );

  old.forEach(
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
    text
  ) {
    const badge =
      document.createElement(
        "span"
      );

    badge.className =
      "badge warning data-status-badge";

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
      "HOTELS: EVALUATION"
    );
  }

  if (
    status.food
    === "demo"
  ) {
    addBadge(
      "FOOD: DEMO"
    );
  }

  if (
    status.sales
    === "demo"
  ) {
    addBadge(
      "SALES: DEMO"
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
    activeFilter
    === "all"
  ) {
    heading.textContent =
      "No Best deals above your threshold yet.";

    text.textContent =
      "Current monitored availability is still available under the Hotels tab.";
  }

  else if (
    activeFilter
    === "hotel"
  ) {
    heading.textContent =
      "No hotel availability in this view.";

    text.textContent =
      "The next successful daily scan will check again.";
  }

  else {
    heading.textContent =
      "No deals in this category yet.";

    text.textContent =
      "This section will update as live sources are added.";
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
          `${text}` +
          `</div>`
      )
      .join("");

    const action =
      item.booking_url
      ||
      item.url;

    card.innerHTML = `
      <div class="card-top">

        <div>
          <div class="kind">
            ${
              categoryLabels[
                item.category
              ]
              ||
              item.category
            }
          </div>

          <h2>
            ${item.name}
          </h2>

          <div class="location">
            ${where}
          </div>
        </div>

        <div class="score">

          <strong>
            ${
              Math.round(
                item.deal_score
                || 0
              )
            }
          </strong>

          <span>
            ${
              scoreCaption(
                item
              )
            }
          </span>

        </div>

      </div>

      <div class="details">
        ${pills}
      </div>

      <div class="desc">
        ${
          description(
            item
          )
        }
      </div>

      ${
        action
          ? `
            <a
              class="action"
              href="${action}"
              target="_blank"
              rel="noopener"
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
        ${historyReady}
      </b>

      <span>
        History-ready
      </span>
    </div>

    <div class="metric">
      <b>
        ${availabilityCount}
      </b>

      <span>
        Availability results
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
