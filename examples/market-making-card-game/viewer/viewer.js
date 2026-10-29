// Market making card game viewer. A replay reads the full snapshot; a live page reads frame(),
// the same shape with the unrevealed community cards removed and the other seat's private
// cards masked as "??" until the hand settles. Both depend on this environment's state shape,
// so viewer.json lists the definition versions it was checked against.
(() => {
  "use strict";
  const SUITS = { C: "♣", D: "♦", H: "♥", S: "♠" };
  const $ = (id) => document.getElementById(id);
  const models = Object.fromEntries(env.meta.seats.map((seat) => [seat.id, seat.model || seat.occupant || ""]));

  const el = (tag, attributes = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attributes)) {
      if (value === false || value == null) continue;
      if (key === "class") node.className = value;
      else if (key === "style") node.style.cssText = value;
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child != null && child !== false) node.append(child instanceof Node ? child : String(child));
    }
    return node;
  };

  const card = (code, extra = "") => {
    if (code === "??") return el("div", { class: `card back ${extra}`, title: "hidden" });
    const suit = code.slice(-1);
    const color = suit === "H" || suit === "D" ? "red" : "black";
    return el("div", { class: `card ${color} ${extra}`, title: code }, code.slice(0, -1) + SUITS[suit]);
  };
  const emptyCard = (extra = "") => el("div", { class: `card empty ${extra}` });

  const RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
  const rankOf = (code) => RANKS.indexOf(code.slice(0, -1)) + 1;
  const signed = (value) => (value > 0 ? `+${value}` : String(value));
  const tone = (value) => (value > 0 ? "up" : value < 0 ? "down" : "");
  const settledPhase = (state) => state.phase === "settled" || state.phase === "finished";
  // Hands are numbered from 1; a settled hand keeps its number until the next one is dealt.
  const handNumber = (state) => (settledPhase(state) ? state.settlement_round : state.settlement_round + 1);
  const roundCount = (state) => state.config.community_card_count;

  // Chapter marks: the first step of every hand, extended as live steps arrive.
  const marks = [];
  let scanned = 0;
  let lastHand = 0;
  const extendMarks = () => {
    const before = marks.length;
    for (; scanned < env.length; scanned += 1) {
      const hand = handNumber(env.frame(scanned).state);
      if (hand !== lastHand) marks.push({ index: scanned, label: `Hand ${hand}` });
      lastHand = hand;
    }
    if (marks.length !== before) env.setMarks(marks);
  };

  const describeEvent = (event) => {
    const who = el("strong", {}, event.actor);
    if (event.kind === "chat") return [who, ` says: ${event.text}${event.truncated ? "…" : ""}`];
    if (event.kind === "buy") {
      return [who, ` buys at ${event.price} from ${event.counterparty}`,
        event.revealed && ` · reveals ${event.revealed}`];
    }
    if (event.kind === "sell") {
      return [who, ` sells at ${event.price} to ${event.counterparty}`,
        event.revealed && ` · reveals ${event.revealed}`];
    }
    return [who, ` ${event.kind === "open_market" ? "quotes" : "improves to"} ${event.bid} / ${event.ask}`];
  };

  // A live page receives other seats' operations only through the frame, so the move is read
  // from the event the step appended; a replay adds the rejected operations, which change nothing.
  const describeStep = (frame) => {
    const { state, previous, op } = frame;
    if (op && op.success === false && (op.method === "invoke" || op.method === "handle_input")) {
      const attempt = op.method === "invoke" ? op.action : "chat";
      const args = op.arguments && Object.keys(op.arguments).length
        ? ` ${op.arguments.bid}/${op.arguments.ask}` : "";
      return [el("strong", {}, op.seat), ` tried ${attempt}${args}: `,
        el("span", { class: "rejected" }, `rejected (${String(op.result)})`)];
    }
    if (!previous) return ["Cards are dealt."];
    if (state.event_seq > previous.event_seq) {
      const nodes = describeEvent(state.events[state.events.length - 1]);
      if (settledPhase(state) && !settledPhase(previous)) {
        nodes.push(` · hand ${state.settlement_round} settles at ${state.settlement.value}`);
      }
      return nodes;
    }
    if (previous.phase === "settled" && state.phase === "trading") return [`Hand ${handNumber(state)} is dealt.`];
    return [""];
  };

  const roundOpener = (state) => state.players[(state.settlement_round + state.round) % 2];

  const renderPlayer = (frame, state, index) => {
    const player = state.players[index];
    const position = state.positions[player];
    const trading = state.phase === "trading";
    const tags = [];
    if (state.active === player) tags.push(el("span", { class: "tag active" }, trading ? "To act" : "Deals next"));
    if (trading && roundOpener(state) === player) tags.push(el("span", { class: "tag" }, "Opens round"));
    const total = state.total_pnl[player];
    $(`player-${index}`).replaceChildren(
      el("div", { class: "name" }, el("span", { title: player }, player)),
      el("div", { class: "model", title: models[player] }, models[player]),
      el("div", { class: "tags" }, tags),
      el("div", { class: "hole" }, state.hands[player].map((code) => card(code))),
      el("dl", {},
        el("dt", {}, "Position"), el("dd", { class: tone(position) }, position === 0 ? "Flat" : position > 0 ? `Long ${position}` : `Short ${-position}`),
        el("dt", {}, "Cash"), el("dd", { class: tone(state.cash[player]) }, signed(state.cash[player]))),
      el("div", { class: "total" }, el("span", {}, "Total P&L"), el("strong", { class: tone(total) }, signed(total))));
    const node = $(`player-${index}`);
    node.className = `player${state.active === player ? " turn" : ""}`;
    node.style.setProperty("--accent", `var(--p${index})`);
  };

  const renderMarket = (frame, state) => {
    const previous = frame.previous;
    const rounds = roundCount(state);
    const trading = state.phase === "trading";
    $("round").textContent = state.phase === "finished" ? "Match complete"
      : trading ? `Hand ${handNumber(state)} · round ${Math.min(state.round + 1, rounds)} of ${rounds}`
      : `Hand ${handNumber(state)} settled`;

    const sameHand = previous && handNumber(previous) === handNumber(state);
    const seen = new Set(sameHand ? previous.revealed : []);
    const slots = state.revealed.map((code) => card(code, seen.has(code) ? "" : "fresh"));
    while (slots.length < rounds) slots.push(emptyCard());
    $("board").replaceChildren(...slots);

    const trades = state.config.trades_per_round;
    $("pips").replaceChildren(...(trading ? Array.from({ length: trades }, (_, i) =>
      el("i", { class: i < state.trades_this_round ? "done" : "", title: `trade ${i + 1} of ${trades}` })) : []));

    const quote = $("quote");
    const market = state.market;
    const changed = market && !(previous && JSON.stringify(previous.market) === JSON.stringify(market));
    quote.className = `quote${changed ? " flash" : ""}`;
    quote.replaceChildren(market
      ? el("div", {},
        el("div", { class: "sides" },
          el("div", { class: "bid" }, el("div", { class: "side-label" }, "Bid"), el("div", { class: "price" }, market.bid),
            el("div", { class: "owner", title: market.bid_owner }, market.bid_owner)),
          el("div", { class: "ask" }, el("div", { class: "side-label" }, "Ask"), el("div", { class: "price" }, market.ask),
            el("div", { class: "owner", title: market.ask_owner }, market.ask_owner))),
        el("div", { class: "spread" }, `Spread ${market.ask - market.bid}`))
      : el("div", { class: "none" }, trading ? "No market" : "No market while settled"));
  };

  const renderSettlement = (state) => {
    const box = $("settle");
    if (!settledPhase(state)) {
      box.hidden = true;
      return;
    }
    const { value, pnl } = state.settlement;
    const handSum = (player) => state.hands[player].reduce((sum, code) => sum + rankOf(code), 0);
    const boardSum = state.community.reduce((sum, code) => sum + rankOf(code), 0);
    const best = Math.max(...Object.values(pnl));
    box.replaceChildren(
      el("h3", {}, `Settles at ${value}`),
      el("div", { class: "sum" },
        `${state.players.map((player) => `${player} ${handSum(player)}`).join(" + ")} + board ${boardSum}`),
      ...state.players.map((player) => el("div", { class: "row" },
        el("span", { title: player }, player, pnl[player] === best && best !== Math.min(...Object.values(pnl)) ? " ★" : ""),
        el("strong", { class: tone(pnl[player]) }, `${signed(pnl[player])} this hand`))));
    box.hidden = false;
  };

  const renderLog = (frame, state) => {
    const hand = handNumber(state);
    const events = state.events.filter((event) => event.hand === hand);
    const log = $("log");
    if (!events.length) {
      log.replaceChildren(el("li", { class: "empty" }, "No activity yet."));
      return;
    }
    log.replaceChildren(...events.map((event, index) => el("li", {
      class: `${index === events.length - 1 ? "latest" : ""}${event.kind === "chat" ? " chat" : ""}`.trim(),
    },
    el("span", {}, el("span", { class: "round-tag" }, `R${event.round}`), describeEvent(event)),
    el("span", {}, event.kind === "buy" || event.kind === "sell" ? event.price : ""))));
    log.scrollTop = log.scrollHeight;
  };

  // Quotes and trades of the hand on screen, in the order they happened: each quote is a bid-to-ask
  // bar in the quoter's color, each trade a diamond at its price filled with the buyer's color and
  // outlined with the seller's. Rounds are separated by dashed lines and reveal their card.
  const renderTape = (frame, state) => {
    const hand = handNumber(state);
    $("tape-title").textContent = `Quotes and trades · hand ${hand}`;
    const events = state.events.filter((event) => event.hand === hand && event.kind !== "chat");
    const box = $("tape");
    if (!events.length) {
      box.replaceChildren(el("div", { class: "none" }, "No quotes yet."));
      return;
    }
    const color = (player) => `var(--p${Math.max(0, state.players.indexOf(player))})`;
    const settled = settledPhase(state) ? state.settlement.value : null;
    const prices = events.flatMap((event) => (event.kind === "buy" || event.kind === "sell" ? [event.price]
      : [event.bid, event.ask]));
    if (settled != null) prices.push(settled);
    const rawLow = Math.min(...prices);
    const rawHigh = Math.max(...prices);
    const margin = Math.max(2, (rawHigh - rawLow) * 0.12);
    const low = Math.max(0, Math.floor(rawLow - margin));
    const high = Math.ceil(rawHigh + margin);
    const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500].find((s) => (high - low) / s <= 6) || 1000;

    const width = Math.max(320, box.clientWidth);
    const height = 250;
    const left = 34;
    const right = 10;
    const top = 22;
    const bottom = 14;
    const slots = Math.max(events.length, 12);
    const slot = (width - left - right) / slots;
    const x = (index) => left + (index + 0.5) * slot;
    const y = (price) => top + ((height - top - bottom) * (high - price)) / (high - low);

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("height", String(height));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Quotes and trades in order");
    const add = (tag, attributes, text) => {
      const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
      if (text != null) node.textContent = text;
      svg.append(node);
      return node;
    };
    const tip = (node, text) => {
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = text;
      node.append(title);
    };

    for (let price = Math.ceil(low / step) * step; price <= high; price += step) {
      add("line", { class: "grid", x1: left, x2: width - right, y1: y(price), y2: y(price) });
      add("text", { x: left - 5, y: y(price) + 3, "text-anchor": "end" }, String(price));
    }
    if (settled != null) {
      add("line", { class: "value", x1: left, x2: width - right, y1: y(settled), y2: y(settled) });
      add("text", { x: width - right - 2, y: y(settled) - 4, "text-anchor": "end" }, `settles at ${settled}`);
    }

    // One group per round: a divider and label where it starts, the revealed card where it ends.
    let start = 0;
    while (start < events.length) {
      let end = start;
      while (end + 1 < events.length && events[end + 1].round === events[start].round) end += 1;
      if (start > 0) add("line", { class: "divider", x1: left + start * slot, x2: left + start * slot, y1: top - 6, y2: height - bottom });
      add("text", { x: left + start * slot + 4, y: 11 }, `R${events[start].round}`);
      const revealed = events.slice(start, end + 1).find((event) => event.revealed);
      if (revealed) add("text", { x: left + (end + 1) * slot - 4, y: 11, "text-anchor": "end" }, `reveals ${revealed.revealed}`);
      start = end + 1;
    }

    events.forEach((event, index) => {
      const cx = x(index);
      if (event.kind === "open_market" || event.kind === "improve_market") {
        const stroke = color(event.actor);
        const bar = add("line", { x1: cx, x2: cx, y1: y(event.bid), y2: y(event.ask), stroke, "stroke-width": 4,
          "stroke-linecap": "round", opacity: 0.55 });
        tip(bar, `${event.actor} ${event.kind === "open_market" ? "quotes" : "improves to"} ${event.bid} / ${event.ask}`);
        for (const price of [event.bid, event.ask]) {
          add("line", { x1: cx - 6, x2: cx + 6, y1: y(price), y2: y(price), stroke, "stroke-width": 2 });
        }
        add("text", { x: cx, y: y(event.ask) - 5, "text-anchor": "middle" }, String(event.ask));
        add("text", { x: cx, y: y(event.bid) + 12, "text-anchor": "middle" }, String(event.bid));
      } else {
        const buyer = event.kind === "buy" ? event.actor : event.counterparty;
        const seller = event.kind === "buy" ? event.counterparty : event.actor;
        // The quote that was hit: the counterparty's latest quote before this trade.
        const quoted = events.slice(0, index).map((e, i) => [e, i]).reverse()
          .find(([e]) => (e.kind === "open_market" || e.kind === "improve_market") && e.actor === event.counterparty);
        if (quoted) add("line", { class: "hit", x1: x(quoted[1]), x2: cx, y1: y(event.price), y2: y(event.price) });
        const mark = add("path", { d: `M${cx} ${y(event.price) - 9} l9 9 l-9 9 l-9 -9 z`, fill: color(buyer),
          stroke: color(seller), "stroke-width": 2.5 });
        tip(mark, `${buyer} buys at ${event.price} from ${seller}`);
        add("text", { class: "price", x: cx, y: y(event.price) - 14, "text-anchor": "middle" }, String(event.price));
      }
    });

    // Ring the newest quote or trade when the step on screen is the one that added it.
    const newest = events[events.length - 1];
    const added = frame.previous && state.event_seq > frame.previous.event_seq
      && state.events[state.events.length - 1].seq === newest.seq;
    if (added) {
      const marked = newest.kind === "buy" || newest.kind === "sell" ? [newest.price] : [newest.bid, newest.ask];
      const topY = y(Math.max(...marked)) - 24;
      const bottomY = y(Math.min(...marked)) + 14;
      add("rect", { class: "latest", x: x(events.length - 1) - 12, y: topY, width: 24, height: bottomY - topY, rx: 6 });
    }
    box.replaceChildren(svg);
  };

  const renderChart = (state) => {
    const players = state.players;
    const series = players.map((player) => {
      let sum = 0;
      return [0, ...state.history.map((hand) => (sum += hand.pnl[player]))];
    });
    const hands = Math.max(1, state.config.settlement_rounds);
    const extent = Math.max(10, ...series.flat().map(Math.abs)) * 1.15;
    const width = Math.max(240, $("chart").clientWidth);
    const height = 150;
    const pad = 28;
    const x = (i) => pad + ((width - pad - 8) * i) / hands;
    const y = (v) => height / 2 - ((height / 2 - 16) * v) / extent;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Cumulative profit and loss after each hand");
    const add = (tag, attributes) => {
      const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
      svg.append(node);
      return node;
    };
    add("line", { class: "axis", x1: pad, x2: width - 8, y1: y(0), y2: y(0) });
    add("text", { x: 2, y: y(0) + 3 }).textContent = "0";
    add("text", { x: 2, y: 12 }).textContent = `+${Math.round(extent)}`;
    add("text", { x: 2, y: height - 16 }).textContent = `-${Math.round(extent)}`;
    add("text", { x: pad, y: height - 3 }).textContent = "hand 0";
    add("text", { x: width - 44, y: height - 3 }).textContent = `hand ${hands}`;
    series.forEach((points, index) => {
      const color = `var(--p${index})`;
      add("polyline", { points: points.map((v, h) => `${x(h)},${y(v)}`).join(" "), fill: "none",
        stroke: color, "stroke-width": 2, "stroke-linejoin": "round" });
      points.forEach((v, h) => add("circle", { cx: x(h), cy: y(v), r: 2.5, fill: color }));
    });
    const legend = el("div", { class: "legend" },
      players.map((player, index) => el("span", { style: `--swatch:var(--p${index})` }, player)));
    $("chart").replaceChildren(svg, legend);
  };

  const renderHands = (state) => {
    const head = el("tr", {}, el("th", {}, "Hand"), el("th", {}, "Value"),
      state.players.map((player) => el("th", { title: player }, player)));
    const rows = state.history.map((hand) => el("tr", {}, el("td", {}, hand.hand), el("td", {}, hand.value),
      state.players.map((player) => el("td", { class: tone(hand.pnl[player]) }, signed(hand.pnl[player])))));
    const body = rows.length ? rows
      : [el("tr", {}, el("td", { class: "none", colspan: 2 + state.players.length }, "No hand has settled yet."))];
    if (rows.length) {
      body.push(el("tr", { class: "total" }, el("td", {}, "Total"), el("td", {}),
        state.players.map((player) => el("td", { class: tone(state.total_pnl[player]) }, signed(state.total_pnl[player])))));
    }
    $("hands").replaceChildren(el("thead", {}, head), el("tbody", {}, body));
  };

  env.onFrame((frame) => {
    extendMarks();
    const state = frame.state;
    const cfg = state.config;
    const view = env.meta.perspective;
    $("title").textContent = env.meta.name;
    $("subtitle").textContent =
      `${cfg.settlement_rounds} ${cfg.settlement_rounds === 1 ? "hand" : "hands"} · ` +
      `${cfg.community_card_count} rounds of ${cfg.trades_per_round} trades · ` +
      `${cfg.private_cards_per_player} private ${cfg.private_cards_per_player === 1 ? "card" : "cards"} each` +
      (view.kind === "seat" ? ` · viewing as ${view.seat}` : view.kind === "public" ? " · public view" : "");
    renderPlayer(frame, state, 0);
    renderPlayer(frame, state, 1);
    renderMarket(frame, state);
    renderSettlement(state);
    $("move").replaceChildren(...describeStep(frame).filter(Boolean),
      frame.op && frame.op.finished ? " · match complete" : "");
    renderLog(frame, state);
    renderTape(frame, state);
    renderChart(state);
    renderHands(state);
  });
})();
