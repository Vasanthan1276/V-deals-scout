const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { JSDOM, VirtualConsole } = require("jsdom");
const F = require("./fixtures/review.json");
const payload = JSON.parse(fs.readFileSync("data/deals.json"));
const hotels = JSON.parse(fs.readFileSync("data/hotels.json"));
async function app(options = {}) {
  const html = fs
    .readFileSync(options.legacy ? "old-dashboard.html" : "index.html", "utf8")
    .replace(/<script[^>]+src=[^>]+><\/script>/g, "");
  const dom = new JSDOM(html, {
    url: "https://fixture.example/",
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: new VirtualConsole(),
  });
  const w = dom.window;
  const errors = [];
  w.addEventListener("error", (e) => errors.push(e.message));
  w.fetch = async (url) => {
    const name = url.split("?")[0];
    if (name === "data/deals.json" && options.fail) throw Error("offline");
    const data =
      name === "data/deals.json"
        ? options.payload || payload
        : name === "data/hotels.json"
          ? options.hotels || hotels
          : options.status;
    return {
      ok: Boolean(data),
      status: data ? 200 : 404,
      json: async () => structuredClone(data),
    };
  };
  if (options.saved)
    w.localStorage.setItem("vv-scout-saved-v1", JSON.stringify(options.saved));
  w.eval(fs.readFileSync("scout-core.js", "utf8"));
  w.eval(fs.readFileSync("app.js", "utf8"));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(errors, []);
  return dom;
}
function change(w, id, value) {
  const el = w.document.getElementById(id);
  el.value = value;
  el.dispatchEvent(new w.Event("input", { bubbles: true }));
}
test("initial load, all hotels, up-to wording, idea caveat and dialog accessible name", async () => {
  const dom = await app();
  const w = dom.window,
    d = w.document;
  assert.equal(d.querySelectorAll(".card").length, 13);
  const sale = [...d.querySelectorAll(".card")].find((c) =>
    c.textContent.includes("Under Armour"),
  );
  assert.match(sale.textContent, /Up to 70% off/);
  assert.match(sale.textContent, /Ongoing promotion/);
  d.querySelector('[data-filter="hotel"]').click();
  assert.equal(d.querySelectorAll(".card").length, 93);
  assert.match(
    d.querySelector("#view-status").textContent,
    /93 hotel results loaded of 93/,
  );
  change(w, "search", "Adiwana");
  const button = d.querySelector(".score-button");
  button.click();
  const dialog = d.querySelector("dialog");
  assert.equal(dialog.getAttribute("aria-labelledby"), "score-dialog-title");
  assert.match(dialog.textContent, /Same-date peer bonus\s+\+25/);
  assert.match(dialog.textContent, /Final score: 72\/100/);
  assert.equal(
    dialog
      .querySelector('[aria-label="Close scoring details"]')
      .hasAttribute("autofocus"),
    true,
  );
  change(w, "search", "");
  d.querySelector('[data-filter="idea"]').click();
  assert.ok(d.querySelectorAll(".note-warning").length);
  assert.match(d.querySelector("#deals").textContent, /Adiwana|Dusit/);
  assert.match(d.querySelector("#deals").textContent, /2027/);
  dom.window.close();
});
test("save reload dismiss restore and saved snapshot", async () => {
  let dom = await app();
  let w = dom.window,
    d = w.document;
  d.querySelector(".save-button").click();
  const stored = JSON.parse(w.localStorage.getItem("vv-scout-saved-v1"));
  assert.equal(Object.keys(stored).length, 1);
  dom.window.close();
  dom = await app({ saved: stored });
  w = dom.window;
  d = w.document;
  change(w, "list-mode", "saved");
  assert.equal(d.querySelectorAll(".card").length, 1);
  assert.match(d.querySelector(".save-button").textContent, /Saved/);
  d.querySelector(".dismiss-button").click();
  assert.equal(d.querySelectorAll(".card").length, 0);
  change(w, "list-mode", "dismissed");
  assert.equal(d.querySelectorAll(".card").length, 1);
  d.querySelector(".dismiss-button").click();
  assert.equal(d.querySelectorAll(".card").length, 0);
  dom.window.close();
  dom = await app({
    saved: stored,
    payload: { items: [], stats: {} },
    hotels: { items: [] },
  });
  w = dom.window;
  d = w.document;
  change(w, "list-mode", "saved");
  assert.match(d.querySelector("#deals").textContent, /Saved snapshot/);
  dom.window.close();
});
test("loading error is not empty scan; retry exists", async () => {
  const dom = await app({ fail: true });
  const d = dom.window.document;
  assert.match(
    d.querySelector("#empty").textContent,
    /page-loading error, not an empty scan/,
  );
  assert.ok(d.querySelector("#retry-load"));
  assert.equal(d.querySelectorAll(".card").length, 0);
  dom.window.close();
});
test("successful empty, failed-retained and stale source UI", async () => {
  const dom = await app({
    payload: { items: [], stats: {}, updated_at: "2026-01-01T07:00:00+08:00" },
    hotels: { items: [] },
    status: {
      sources: {
        hotels: { state: "failed_retained" },
        food: { state: "empty" },
        sales: { state: "partial" },
      },
    },
  });
  const text = dom.window.document.querySelector("#source-health").textContent;
  assert.match(text, /Refresh failed/);
  assert.match(text, /no qualifying results/);
  assert.match(text, /stale/);
  assert.match(text, /Singapore|Partial/);
  dom.window.close();
});
test("unknown fields and unsafe HTML render safely", async () => {
  const dom = await app({
    payload: {
      items: [
        {
          id: "x",
          category: "food",
          name: "<img src=x onerror=alert(1)>",
          deal_score: 10,
          url: "javascript:alert(1)",
        },
      ],
    },
    hotels: { items: [] },
  });
  const d = dom.window.document;
  assert.equal(d.querySelectorAll(".card img").length, 0);
  assert.equal(d.querySelectorAll(".card .action").length, 0);
  assert.match(d.querySelector(".card").textContent, /ExpiryUnknown/);
  dom.window.close();
});
test("old layout uses corrected shared behavior and link back", async () => {
  const dom = await app({ legacy: true });
  assert.ok(dom.window.document.body.classList.contains("legacy-layout"));
  assert.equal(
    dom.window.document.querySelector(".layout-link").getAttribute("href"),
    "index.html",
  );
  assert.equal(dom.window.document.querySelectorAll(".card").length, 13);
  dom.window.close();
});
test("mixed hotel snapshots fall back visibly to the dashboard subset", async () => {
  const dom = await app({
    hotels: { ...hotels, updated_at: "2000-01-01T00:00:00Z" },
  });
  const d = dom.window.document;
  d.querySelector('[data-filter="hotel"]').click();
  assert.equal(d.querySelectorAll(".card").length, 20);
  assert.match(d.querySelector("#view-status").textContent, /dashboard subset/);
  dom.window.close();
});
