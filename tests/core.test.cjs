const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const S = require("../scout-core.js");
const F = require("./fixtures/review.json");
const sum = (d) =>
  S.round(
    d.components.reduce((n, p) => n + Number(p.points), 0) +
      (d.adjustments || []).reduce((n, p) => n + Number(p.points), 0),
  );
test("72 score includes 47 base +25 peer; repeat normalisation is stable", () => {
  const h = S.normalize([F.hotel_peer])[0],
    d = h.score_breakdown;
  assert.equal(d.total, 72);
  assert.equal(d.base_total, 47);
  assert.equal(d.adjustments[0].points, 25);
  assert.equal(sum(d), 72);
  assert.deepEqual(S.score(h), d);
});
test("all existing stored scores reconcile to displayed arithmetic", () => {
  for (const f of ["deals", "hotels", "food", "sales"])
    for (const i of JSON.parse(fs.readFileSync(`data/${f}.json`)).items) {
      const d = S.score(i);
      assert.equal(d.total, i.deal_score);
      if (d.components.length) assert.equal(sum(d), d.total, `${f}: ${i.name}`);
    }
});
test("up to and equivalent wording, ongoing classification", () => {
  assert.equal(S.discountLabel(F.up_to), "Up to 70% off");
  assert.match(S.discountLabel(F.one_for_one), /1-for-1.*equivalent/);
  assert.equal(S.kind(F.up_to), "ongoing_promotion");
});
test("legacy derived ideas recover context only with an unambiguous parent", () => {
  const idea = F.ideas.find((i) => i.description.includes(F.hotel_peer.name));
  const i = S.normalize([idea], [F.hotel_peer])[0];
  assert.equal(i.hotel_name, F.hotel_peer.name);
  assert.equal(i.check_in, F.hotel_peer.check_in);
  assert.equal(i.source, F.hotel_peer.source);
  assert.equal(i.is_evaluation, true);
  assert.equal(i.price_type, F.hotel_peer.price_type);
  assert.equal(i.score_breakdown.total, 72);
  const ambiguous = S.normalize(
    [idea],
    [F.hotel_peer, { ...F.hotel_peer, id: "different" }],
  )[0];
  assert.equal(ambiguous.check_in, undefined);
});
test("duplicates flag likely retail overlap without removing either listing", () => {
  const map = S.duplicates(F.duplicates);
  assert.equal(F.duplicates.length, 2);
  assert.equal(map.size, 2);
  const a = {
    id: "a",
    category: "food",
    name: "Restaurant @ A",
    meal_period: "lunch",
    deal_type: "app_deal",
  };
  assert.equal(
    S.duplicates([
      a,
      { ...a, id: "b", meal_period: "dinner" },
      { ...a, id: "c", access_requirement: "Card" },
    ]).size,
    0,
  );
});
test("expiry follows Singapore midnight and includes expiry day", () => {
  assert.equal(S.today(new Date("2026-11-13T16:00:00Z")), "2026-11-14");
  assert.equal(S.expiry({ valid_until: "2026-11-13" }, "2026-11-13"), "dated");
  assert.equal(
    S.expiry({ valid_until: "2026-11-13" }, "2026-11-14"),
    "expired",
  );
  assert.equal(S.expiry({ valid_until: "unknown" }, "2026-11-14"), "unknown");
  assert.equal(S.validDate("2026-02-31"), false);
});
test("filters never invent dates or prices; sorting and date/budget bounds", () => {
  const a = {
      id: "a",
      category: "hotel",
      destination: "Bali",
      check_in: "2027-01-08",
      current_price: 99,
      currency: "SGD",
      deal_score: 72,
    },
    b = { id: "b", name: "Bali inspiration", deal_score: 90 },
    c = { ...a, id: "c", current_price: 150 };
  assert.deepEqual(
    S.filter(
      [a, b, c],
      { from: "2027-01-08", to: "2027-01-08", budget: "100" },
      "2026-11-13",
    ).map((i) => i.id),
    ["a"],
  );
  assert.deepEqual(
    S.filter([a, b, c], { sort: "price" }, "2026-11-13").map((i) => i.id),
    ["a", "c", "b"],
  );
  assert.equal(
    S.filter([a], { from: "2027-01-09", to: "2027-01-07" }, "2026-11-13")
      .length,
    0,
  );
});
test("saved and dismissed records persist; corrupt/denied storage is explicit", () => {
  let value = null;
  const storage = { getItem: () => value, setItem: (_, v) => (value = v) };
  const data = {
    [S.key(F.hotel_peer)]: { state: "saved", item: F.hotel_peer },
  };
  assert.equal(S.save(storage, data), true);
  assert.deepEqual(S.loadSaved(storage).data, data);
  data[S.key(F.hotel_peer)].state = "dismissed";
  S.save(storage, data);
  assert.equal(
    S.loadSaved(storage).data[S.key(F.hotel_peer)].state,
    "dismissed",
  );
  value = "broken";
  assert.equal(S.loadSaved(storage).error, true);
  assert.equal(
    S.save(
      {
        setItem() {
          throw Error("denied");
        },
      },
      data,
    ),
    false,
  );
});
test("failed, empty, stale, partial and unknown health remain distinct", () => {
  const now = new Date("2026-11-13T10:00:00+08:00");
  assert.match(
    S.health({ state: "failed_retained" }, "2026-11-13T09:00:00+08:00", now)
      .label,
    /failed.*retained/,
  );
  assert.match(
    S.health({ state: "empty" }, null, now).label,
    /no qualifying results/,
  );
  assert.match(
    S.health({ state: "empty_retained" }, null, now).label,
    /Complete empty.*retained/,
  );
  assert.match(S.health({ state: "partial" }, null, now).label, /Partial/);
  assert.equal(S.health({}, "2026-11-10T09:00:00+08:00", now).stale, true);
});
