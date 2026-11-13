/* Pure data rules shared by the dashboard and offline regression tests. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Scout = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const round = (n) => Math.round((Number(n) + Number.EPSILON) * 10) / 10;
  const band = (n) =>
    n >= 90
      ? "Exceptional"
      : n >= 80
        ? "Strong"
        : n >= 70
          ? "Worth a look"
          : n >= 60
            ? "Moderate"
            : "Low priority";
  const text = (i) =>
    [i.offer_text, i.name, i.description].filter(Boolean).join(" ");
  function validDate(v) {
    return (
      typeof v === "string" &&
      /^\d{4}-\d{2}-\d{2}$/.test(v) &&
      !isNaN(Date.parse(v)) &&
      new Date(v).toISOString().slice(0, 10) === v
    );
  }
  function today(now = new Date()) {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Singapore",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(now);
  }
  function expiry(i, date = today()) {
    if (validDate(i.valid_until) && i.valid_until < date) return "expired";
    if (validDate(i.check_in) && i.check_in < date) return "past_stay";
    if (validDate(i.valid_from) && i.valid_from > date) return "upcoming";
    return validDate(i.valid_until) || validDate(i.check_in)
      ? "dated"
      : "unknown";
  }
  function discountLabel(i) {
    if (!i.discount_percent) return "";
    const t = text(i);
    if (
      i.discount_qualifier === "up_to" ||
      /up\s+to/i.test(t) ||
      i.price_type === "time_slot_discount"
    )
      return `Up to ${i.discount_percent}% off`;
    if (
      i.discount_qualifier === "equivalent" ||
      /1[- ]for[- ]1|buy\s+1\s+get\s+1/i.test(t)
    )
      return `1-for-1 · up to ${i.discount_percent}% equivalent`;
    return `${i.discount_percent}% advertised saving`;
  }
  function kind(i) {
    if (i.category === "idea") return "inspiration";
    if (i.is_evaluation || /evaluation|net rate/i.test(i.price_type || ""))
      return "evaluation_rate";
    if (i.offer_kind) return i.offer_kind;
    if (i.category === "hotel") return "dated_rate";
    if (/all year|year.round|mall.wide|outlet positioning/i.test(text(i)))
      return "ongoing_promotion";
    if (
      i.valid_until ||
      i.meal_period ||
      ["direct", "card_deal", "membership_deal"].includes(i.deal_type)
    )
      return "specific_offer";
    return "promotion_lead";
  }
  const kindLabels = {
    inspiration: "Inspiration · hotel only",
    evaluation_rate: "Evaluation rate · research only",
    dated_rate: "Dated hotel rate · verify",
    ongoing_promotion: "Ongoing promotion",
    specific_offer: "Specific offer · verify terms",
    promotion_lead: "Promotion lead · details incomplete",
  };
  function score(i) {
    const d = JSON.parse(JSON.stringify(i.score_breakdown || {}));
    const total = Number(i.deal_score || 0);
    d.components = Array.isArray(d.components) ? d.components : [];
    d.notes = d.notes || [];
    if (d.model === "hotel_v1" && ["hotel", "idea"].includes(i.category)) {
      const base = Number(d.total || 0);
      const peer = Number(i.peer_median || 0),
        price = Number(i.current_price || 0);
      const bonus =
        i.score_basis === "peer_comparison" && peer > 0 && price > 0
          ? round(
              Math.min(
                25,
                (Math.max(0, ((peer - price) / peer) * 100) / 30) * 25,
              ),
            )
          : 0;
      const cap =
        i.score_basis === "peer_comparison"
          ? 84
          : i.score_basis === "observed_history"
            ? 100
            : 69;
      d.model = "hotel_v2_legacy_reconciled";
      d.base_total = base;
      d.cap = cap;
      d.adjustments = [
        { label: "Same-date peer bonus", points: bonus },
        {
          label: `Score cap (${cap})`,
          points: round(Math.min(cap, base + bonus) - base - bonus),
        },
      ];
      const reconstructed = round(Math.min(cap, base + bonus));
      if (reconstructed !== total)
        d.adjustments.push({
          label: "Stored-score reconciliation (legacy record)",
          points: round(total - reconstructed),
        });
      d.notes = [
        "Base components + peer bonus + cap adjustment = final score.",
        "Peer-only scores are capped at 84; current-observation-only scores at 69.",
        "Suitability includes configured assumptions, not verified room amenities.",
      ];
    }
    // Preserve the recorded ranking. Any old rounding/reconciliation is explicit.
    if (d.components.length) {
      const sum = round(
        d.components.reduce((s, p) => s + Number(p.points || 0), 0) +
          (d.adjustments || []).reduce((s, p) => s + Number(p.points || 0), 0),
      );
      if (sum !== total) {
        d.adjustments = d.adjustments || [];
        d.adjustments.push({
          label:
            Math.abs(total - sum) <= 0.2
              ? "Stored rounding adjustment"
              : "Stored-score adjustment (details incomplete)",
          points: round(total - sum),
        });
      }
    }
    d.total = total;
    d.band = band(total);
    d.scale_max = 100;
    if (!d.components.length)
      d.notes.push("Component details are unavailable in this stored record.");
    return d;
  }
  function key(i) {
    if (i.category === "hotel" || (i.category === "idea" && i.hotel_id))
      return [
        i.category,
        i.hotel_id || i.id,
        i.check_in || "",
        i.check_out || "",
      ].join("|");
    return `${i.category}|${i.id || [i.name, i.url, i.meal_period, i.valid_until, i.access_requirement].join("|")}`;
  }
  function normalize(items, hotels = []) {
    const parents = hotels.length
      ? hotels
      : items.filter((i) => i.category === "hotel");
    return items.map((original) => {
      let i = { ...original };
      if (i.category === "idea") {
        const candidates = parents.filter((h) =>
          i.hotel_id
            ? h.id === i.hotel_id
            : (i.description || "").includes(h.name) &&
              Number(h.total_price) === Number(i.estimated_cost) &&
              Number(h.deal_score) === Number(i.deal_score),
        );
        if (candidates.length === 1) {
          const h = candidates[0];
          i = { ...h, ...i, hotel_id: h.id, hotel_name: h.name };
          for (const f of [
            "check_in",
            "check_out",
            "destination",
            "source",
            "provider",
            "booking_url",
            "url",
            "current_price",
            "total_price",
            "nights",
            "price_type",
            "observed_at",
            "score_breakdown",
            "peer_median",
            "historical_median",
          ])
            i[f] = h[f];
          i.is_evaluation = Boolean(h.is_evaluation || i.is_evaluation);
          i.name = `${h.destination} · ${h.name}`;
        }
        i.cost_scope =
          i.cost_scope ||
          "Hotel stay only; transport, meals and other costs excluded. Taxes/fees not confirmed.";
      }
      i.offer_kind = kind(i);
      i.score_breakdown = score(i);
      return i;
    });
  }
  function duplicates(items) {
    const groups = new Map();
    for (const i of items) {
      if (!["food", "sale"].includes(i.category)) continue;
      let name = (i.restaurant_name || i.name || "")
        .toLowerCase()
        .split(/\s[—–]\s/)[0]
        .replace(/\batrium\b/g, "")
        .replace(/\s+/g, " ")
        .trim();
      const group = [
        i.category,
        name,
        i.location || "",
        i.meal_period || "",
        i.deal_type || "",
        i.access_requirement || "",
        i.discount_percent || "",
        i.valid_until || "",
      ].join("|");
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(i);
    }
    const result = new Map();
    let n = 0;
    for (const members of groups.values())
      if (members.length > 1) {
        n++;
        for (const i of members)
          result.set(key(i), {
            group: n,
            count: members.length,
            peers: members
              .filter((x) => x !== i)
              .map((x) => ({ name: x.name, url: x.url })),
          });
      }
    return result;
  }
  function filter(items, f = {}, now) {
    return items
      .filter((i) => {
        const state = expiry(i, now || today());
        if (
          f.expiry === "expired"
            ? !["expired", "past_stay"].includes(state)
            : f.expiry !== "all" && ["expired", "past_stay"].includes(state)
        )
          return false;
        if (
          f.search &&
          ![
            i.name,
            i.hotel_name,
            i.description,
            i.destination,
            i.location,
            i.source,
          ]
            .join(" ")
            .toLowerCase()
            .includes(f.search.toLowerCase())
        )
          return false;
        if (f.destination && (i.destination || i.location) !== f.destination)
          return false;
        if (f.kind && kind(i) !== f.kind) return false;
        const start = i.check_in || i.valid_from;
        if (
          (f.from || f.to) &&
          (!validDate(start) ||
            (f.from && start < f.from) ||
            (f.to && start > f.to))
        )
          return false;
        if (
          f.budget &&
          (!(Number(i.current_price) > 0) ||
            i.currency !== "SGD" ||
            Number(i.current_price) > Number(f.budget))
        )
          return false;
        return true;
      })
      .sort((a, b) => {
        if (f.sort === "price")
          return (
            (a.currency === "SGD" && Number(a.current_price) > 0
              ? Number(a.current_price)
              : Infinity) -
            (b.currency === "SGD" && Number(b.current_price) > 0
              ? Number(b.current_price)
              : Infinity)
          );
        if (f.sort === "expiry")
          return (
            validDate(a.valid_until || a.check_in)
              ? a.valid_until || a.check_in
              : "9999"
          ).localeCompare(
            validDate(b.valid_until || b.check_in)
              ? b.valid_until || b.check_in
              : "9999",
          );
        if (f.sort === "fresh")
          return (
            (Date.parse(b.observed_at) || 0) - (Date.parse(a.observed_at) || 0)
          );
        return Number(b.deal_score || 0) - Number(a.deal_score || 0);
      });
  }
  function health(entry = {}, timestamp, now = new Date()) {
    const time = timestamp || entry.data_updated_at;
    const stale =
      !time ||
      !Number.isFinite(Date.parse(time)) ||
      now - Date.parse(time) > 36 * 3600000;
    const labels = {
      failed_retained: "Refresh failed · previous data retained",
      failed: "Refresh failed · no new data",
      empty_retained: "Complete empty hotel scan · previous data retained",
      empty: "Successful fetch · no qualifying results",
      partial: "Partial refresh · some sources failed",
      success: "Refresh successful",
    };
    return {
      stale,
      label:
        (labels[entry.state] || "Refresh outcome not recorded") +
        (stale ? " · stale / age unknown" : ""),
    };
  }
  function loadSaved(storage) {
    try {
      const raw = storage.getItem("vv-scout-saved-v1");
      const data = raw ? JSON.parse(raw) : {};
      if (!data || typeof data !== "object" || Array.isArray(data))
        throw Error("invalid");
      for (const v of Object.values(data))
        if (
          !v ||
          !["saved", "dismissed"].includes(v.state) ||
          !v.item ||
          typeof v.item !== "object"
        )
          throw Error("invalid");
      return { data, error: false };
    } catch {
      return { data: {}, error: true };
    }
  }
  function save(storage, data) {
    try {
      storage.setItem("vv-scout-saved-v1", JSON.stringify(data));
      return true;
    } catch {
      return false;
    }
  }
  return {
    round,
    band,
    validDate,
    today,
    expiry,
    discountLabel,
    kind,
    kindLabels,
    score,
    key,
    normalize,
    duplicates,
    filter,
    health,
    loadSaved,
    save,
  };
});
