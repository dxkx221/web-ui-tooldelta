"use strict";

// ---------- 工具 ----------
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function actionButton(label, action, data, extraClass) {
  return `<button class="quick-btn ${extraClass || ""}" data-easy-action="${escapeHtml(action)}" data-easy-data="${escapeHtml(JSON.stringify(data || {}))}">${label}</button>`;
}

// 解析 MC 颜色代码 §x 为 <span class="cx">
function renderMc(text) {
  let s = escapeHtml(text);
  // 逐个 §x 替换
  s = s.replace(/§([0-9a-z])/g, (m, c) => `<span class="c${c}">`);
  s = s.replace(/§r/g, "</span>");
  // 平衡 span（简化处理，结束时闭合）
  let opens = (s.match(/<span/g) || []).length;
  let closes = (s.match(/<\/span>/g) || []).length;
  for (let i = closes; i < opens; i++) s += "</span>";
  return s;
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toTimeString().slice(0, 8);
}

// ---------- 物品图标/名称映射 ----------
let ITEM_ICONS = {};  // id(去 minecraft: 前缀) -> {icon, name}
let ITEM_NAMES = {};  // id(去 minecraft: 前缀) -> 中文名
async function loadItemMeta() {
  try {
    const [icons, names] = await Promise.all([
      fetch(`/item_icons.json?v=${Date.now()}`, { cache: "no-store" }),
      fetch(`/item_names.json?v=${Date.now()}`, { cache: "no-store" }),
    ]);
    ITEM_ICONS = await icons.json();
    ITEM_NAMES = await names.json();
  } catch (e) {
    ITEM_ICONS = {};
    ITEM_NAMES = {};
  }
}

const ITEM_ALIASES = {
  apple_enchanted: "enchanted_golden_apple",
  cooked_beef: "beef_cooked",
  beef: "beef_raw",
  cooked_chicken: "chicken_cooked",
  chicken: "chicken_raw",
  cooked_mutton: "mutton_cooked",
  mutton: "mutton_raw",
  cooked_porkchop: "porkchop_cooked",
  porkchop: "porkchop_raw",
  cooked_cod: "fish_cooked",
  cod: "fish_raw",
  baked_potato: "potato_baked",
  poisonous_potato: "potato_poisonous",
  golden_carrot: "carrot_golden",
  golden_apple: "apple_golden",
  enchanted_golden_apple: "apple_golden",
  oak_boat: "boat_oak",
  spruce_boat: "boat_spruce",
  birch_boat: "boat_birch",
  jungle_boat: "boat_jungle",
  acacia_boat: "boat_acacia",
  dark_oak_boat: "boat_darkoak",
  wooden_sword: "wood_sword",
  wooden_pickaxe: "wood_pickaxe",
  wooden_axe: "wood_axe",
  wooden_shovel: "wood_shovel",
  wooden_hoe: "wood_hoe",
  lapis_lazuli: "dye_powder_blue",
  white_candle: "candles__white_candle",
  banner: "banner_pattern",
  music_disc_otherside: "record_otherside",
  fermented_spider_eye: "spider_eye_fermented",
  soul_sand: "soul_sand",
  wither_skeleton_skull: "wither_skeleton_skull",
  warden_spawn_egg: "spawn_eggs__spawn_egg_warden",
  wither_skeleton_spawn_egg: "spawn_eggs__spawn_egg_wither_skeleton",
  spawn_egg_warden: "spawn_eggs__spawn_egg_warden",
  spawn_egg_wither_skeleton: "spawn_eggs__spawn_egg_wither_skeleton",
};

const ITEM_NAME_OVERRIDES = {
  lapis_lazuli: "青金石",
  dye_powder_blue: "青金石",
  white_candle: "白色蜡烛",
  candles__white_candle: "白色蜡烛",
  banner: "旗帜",
  banner_pattern: "旗帜",
  music_disc_otherside: "音乐唱片 Otherside",
  record_otherside: "音乐唱片 Otherside",
  fermented_spider_eye: "发酵蛛眼",
  spider_eye_fermented: "发酵蛛眼",
  beef_raw: "生牛肉",
  chicken_raw: "生鸡肉",
  porkchop_raw: "生猪排",
  fish_raw: "生鳕鱼",
  mutton_raw: "生羊肉",
  rabbit_raw: "生兔肉",
  beef_cooked: "熟牛排",
  chicken_cooked: "熟鸡肉",
  porkchop_cooked: "熟猪排",
  fish_cooked: "熟鳕鱼",
  mutton_cooked: "熟羊肉",
  rabbit_cooked: "熟兔肉",
  carrot_golden: "金胡萝卜",
  potato_baked: "烤马铃薯",
  potato_poisonous: "毒马铃薯",
  bucket_milk: "牛奶桶",
  book_written: "成书",
  book_writable: "书与笔",
  book_normal: "书",
  bow_standby: "弓",
  fishing_rod_cast: "钓鱼竿",
  gold_shovel: "金锹",
  gold_horse_armor: "金马铠",
  minecart_hopper: "漏斗矿车",
  minecart_command_block: "命令方块矿车",
  boat: "橡木船",
  lodestonecompass_item: "磁石指南针",
  recovery_compass_item: "追溯指针",
  broken_elytra: "损坏的鞘翅",
  spawn_egg: "刷怪蛋",
  soul_sand: "灵魂沙",
  wither_skeleton_skull: "凋灵骷髅头颅",
  warden_spawn_egg: "监守者刷怪蛋",
  wither_skeleton_spawn_egg: "凋灵骷髅刷怪蛋",
  spawn_eggs__spawn_egg_warden: "监守者刷怪蛋",
  spawn_eggs__spawn_egg_wither_skeleton: "凋灵骷髅刷怪蛋",
};

const ITEM_ICON_OVERRIDES = {
  wither_skeleton_skull: "blocks/skull_pottery_pattern.png",
};

const COLOR_NAMES = {
  white: "白色",
  orange: "橙色",
  magenta: "品红色",
  light_blue: "淡蓝色",
  yellow: "黄色",
  lime: "黄绿色",
  pink: "粉红色",
  gray: "灰色",
  light_gray: "淡灰色",
  cyan: "青色",
  purple: "紫色",
  blue: "蓝色",
  brown: "棕色",
  green: "绿色",
  red: "红色",
  black: "黑色",
};

const ENCHANT_NAMES = {
  protection: "保护",
  fire_protection: "火焰保护",
  feather_falling: "摔落保护",
  blast_protection: "爆炸保护",
  projectile_protection: "弹射物保护",
  thorns: "荆棘",
  respiration: "水下呼吸",
  aqua_affinity: "水下速掘",
  depth_strider: "深海探索者",
  frost_walker: "冰霜行者",
  binding: "绑定诅咒",
  soul_speed: "灵魂疾行",
  swift_sneak: "迅捷潜行",
  sharpness: "锋利",
  smite: "亡灵杀手",
  bane_of_arthropods: "节肢杀手",
  knockback: "击退",
  fire_aspect: "火焰附加",
  looting: "抢夺",
  sweeping: "横扫之刃",
  efficiency: "效率",
  silk_touch: "精准采集",
  unbreaking: "耐久",
  fortune: "时运",
  power: "力量",
  punch: "冲击",
  flame: "火矢",
  infinity: "无限",
  luck_of_the_sea: "海之眷顾",
  lure: "饵钓",
  loyalty: "忠诚",
  impaling: "穿刺",
  riptide: "激流",
  channeling: "引雷",
  multishot: "多重射击",
  piercing: "穿透",
  quick_charge: "快速装填",
  mending: "经验修补",
  vanishing: "消失诅咒",
  density: "密度",
  breach: "突袭",
  wind_burst: "风爆",
  arrowdamage: "力量",
  arrowfire: "火矢",
  arrowinfinite: "无限",
  arrowknockback: "冲击",
  damage_all: "锋利",
  damage_arthropods: "节肢杀手",
  damage_undead: "亡灵杀手",
  digging: "效率",
  durability: "耐久",
  lootbonus: "抢夺",
  lootbonusdigger: "时运",
  lootbonusfishing: "海之眷顾",
  oxygen: "水下呼吸",
  untouching: "精准采集",
  waterwalker: "深海探索者",
  waterworker: "水下速掘",
};

const ENCHANT_TYPE_NAMES = {
  0: "保护",
  1: "火焰保护",
  2: "摔落保护",
  3: "爆炸保护",
  4: "弹射物保护",
  5: "荆棘",
  6: "水下呼吸",
  7: "水下速掘",
  8: "深海探索者",
  9: "锋利",
  10: "亡灵杀手",
  11: "节肢杀手",
  12: "击退",
  13: "火焰附加",
  14: "抢夺",
  15: "效率",
  16: "精准采集",
  17: "耐久",
  18: "时运",
  19: "力量",
  20: "冲击",
  21: "火矢",
  22: "无限",
  23: "海之眷顾",
  24: "饵钓",
  25: "冰霜行者",
  26: "经验修补",
  27: "绑定诅咒",
  28: "消失诅咒",
  29: "穿刺",
  30: "激流",
  31: "忠诚",
  32: "引雷",
  33: "多重射击",
  34: "穿透",
  35: "快速装填",
  36: "灵魂疾行",
};

const ENCHANT_LEVELS = {
  1: "I",
  2: "II",
  3: "III",
  4: "IV",
  5: "V",
  6: "VI",
  7: "VII",
  8: "VIII",
  9: "IX",
  10: "X",
};

function itemKeys(id, namespace) {
  const raw = [id, namespace].filter((v) => v !== undefined && v !== null && String(v).trim() !== "");
  const keys = [];
  for (const value of raw) {
    let key = String(value).trim().replace(/^minecraft:/, "");
    key = key.split(":")[0];
    key = key.replace(/\s+/g, "_").toLowerCase();
    if (!key || key === "minecraft" || /^\d+$/.test(key)) continue;
    keys.push(key);
    if (ITEM_ALIASES[key]) keys.push(ITEM_ALIASES[key]);
    if (key.includes("__")) keys.push(key.split("__").pop());
    if (/^[a-z_]+_candle$/.test(key)) keys.push("candles__" + key);
    if (/^[a-z_]+_harness$/.test(key)) keys.push("harness__harness_" + key.replace(/_harness$/, ""));
    if (key.endsWith("_planks")) keys.push(key.replace("_planks", "_wood"));
    if (key.endsWith("_log")) keys.push(key.replace("_log", "_wood"));
    if (key.startsWith("spawn_eggs__spawn_egg_")) keys.push("spawn_egg");
    if (key.endsWith("_spawn_egg")) keys.push("spawn_eggs__spawn_egg_" + key.replace(/_spawn_egg$/, ""));
    if (key.startsWith("egg_")) keys.push("spawn_egg");
    if (key.startsWith("potion_bottle")) keys.push("potion_bottle");
    if (key.startsWith("tipped_arrow")) keys.push("tipped_arrow");
    if (key.startsWith("music_disc_")) keys.push(key.replace("music_disc_", "record_"));
    if (key.startsWith("record_") || key.startsWith("music_disc_")) keys.push("record_13");
    keys.push(key.replace(/_bucket$/, "_bucket"));
  }
  return [...new Set(keys)];
}

function itemIcon(id, namespace) {
  for (const key of itemKeys(id, namespace)) {
    const m = ITEM_ICONS[key];
    if (m && m.icon) return m;
  }
  return null;
}

function itemIconCandidates(id, namespace) {
  const paths = [];
  for (const key of itemKeys(id, namespace)) {
    if (ITEM_ICON_OVERRIDES[key]) paths.push(ITEM_ICON_OVERRIDES[key]);
    const m = ITEM_ICONS[key];
    if (m && m.icon) paths.push(m.icon);
    paths.push(`items/${key}.png`);
    paths.push(`blocks/${key}.png`);
  }
  return [...new Set(paths)];
}

function itemImageHtml(id, namespace) {
  const candidates = itemIconCandidates(id, namespace);
  if (!candidates.length) return '<span class="inv-nopic">?</span>';
  const encoded = candidates.map((p) => "/" + escapeHtml(p));
  return `<img class="inv-img" src="${encoded[0]}" alt="" loading="lazy" data-icon-candidates="${escapeHtml(encoded.join("|"))}" data-icon-index="0" onerror="nextItemIcon(this)">`;
}

function nextItemIcon(img) {
  const candidates = (img.dataset.iconCandidates || "").split("|").filter(Boolean);
  const next = Number(img.dataset.iconIndex || 0) + 1;
  if (next < candidates.length) {
    img.dataset.iconIndex = String(next);
    img.src = candidates[next];
    return;
  }
  img.replaceWith(Object.assign(document.createElement("span"), { className: "inv-nopic", textContent: "?" }));
}

function itemName(id, namespace) {
  for (const key of itemKeys(id, namespace)) {
    if (ITEM_NAME_OVERRIDES[key]) return ITEM_NAME_OVERRIDES[key];
    if (ITEM_NAMES[key]) return ITEM_NAMES[key];
    const m = ITEM_ICONS[key];
    if (m && m.name && m.name !== key && m.name !== "未知物品" && m.name !== "未知方块") return m.name;
    const candle = key.match(/^(?:candles__)?([a-z_]+)_candle$/);
    if (candle && COLOR_NAMES[candle[1]]) return COLOR_NAMES[candle[1]] + "蜡烛";
    const harness = key.match(/^(?:harness__harness_)?([a-z_]+)_harness$/) || key.match(/^harness__harness_([a-z_]+)$/);
    if (harness && COLOR_NAMES[harness[1]]) return COLOR_NAMES[harness[1]] + "挽具";
  }
  return readableItemKey(namespace || id || "");
}

function readableItemKey(value) {
  const key = String(value || "").replace(/^minecraft:/, "").split(":")[0];
  if (!key || key === "minecraft" || /^\d+$/.test(key)) return "";
  return key.replace(/_/g, " ");
}

function normalizeEnchantName(name) {
  return String(name || "")
    .replace(/^minecraft:/, "")
    .replace(/^enchantment\./, "")
    .replace(/[.\-\s]+/g, "_")
    .toLowerCase();
}

function enchantText(enchant) {
  if (!enchant) return "";
  const rawName = enchant.name || enchant.id || enchant.key || "";
  const key = normalizeEnchantName(rawName);
  const name = ENCHANT_NAMES[key] || ENCHANT_TYPE_NAMES[Number(enchant.type)] || rawName || "附魔";
  const level = Number(enchant.level || enchant.lvl || 0);
  return level > 0 ? `${name} ${ENCHANT_LEVELS[level] || level}` : name;
}

function enchantSummary(enchantments) {
  const list = (enchantments || []).map(enchantText).filter(Boolean);
  return list.join("、");
}

// ---------- 状态 ----------
let STATUS = { state: "idle", ready: false };

// 数字滚动：把目标数字从当前值缓动到新值
function tweenNumber(el, to) {
  if (!el) return;
  const target = Number(to) || 0;
  const from = Number(el.dataset.num || 0);
  if (from === target) { el.textContent = target; el.dataset.num = target; return; }
  const start = performance.now();
  const dur = 420;
  function step(now) {
    const p = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = Math.round(from + (target - from) * eased);
    el.textContent = val;
    if (p < 1) requestAnimationFrame(step);
    else el.dataset.num = target;
  }
  requestAnimationFrame(step);
}

function applyStatus(st) {
  STATUS = st || STATUS;
  const running = STATUS.state === "running";
  const starting = STATUS.state === "starting";
  const failed = STATUS.state === "error";

  const chipState = $("#chip-state");
  chipState.textContent = running
    ? "运行中" : (starting ? "启动中" : (failed ? "异常" : "未启动"));
  chipState.className = "chip " + (running ? "running" : "stopped");

  $("#chip-launcher").textContent = STATUS.launch_type || "—";
  $("#chip-players").textContent = "在线 " + (STATUS.players ? STATUS.players.length : 0);
  $("#chip-bot").textContent = "机器人 " + (STATUS.bot_name || "—");

  $("#dash-state").textContent = running ? "运行中" : (starting ? "启动中" : (failed ? "异常" : "未启动"));
  $("#dash-launcher").textContent = STATUS.launch_type || "—";
  tweenNumber($("#dash-players"), STATUS.players ? STATUS.players.length : 0);
  $("#dash-bot").textContent = STATUS.bot_name || "—";

  $("#btn-start").disabled = running || starting;
  $("#btn-stop").disabled = !(running || starting || failed);
  syncWorldRules();
  syncManageButtons(running);

  if (STATUS.error) {
    appendLog("ERROR", STATUS.error);
  }
}

// 服务器未运行时禁用世界/玩家管理按钮，避免点了才报“未就绪”
function syncManageButtons(running) {
  const locked = !running;
  const tip = locked ? "请先在控制台启动服务器，机器人上线后才能操作" : "";
  $$("[data-world-action]").forEach((b) => {
    b.disabled = locked;
    b.title = tip;
  });
  $$(".rule-card").forEach((b) => {
    b.disabled = locked;
    b.title = tip;
  });
  $$("#mgr-templates button, #mgr-set-gamerule").forEach((b) => {
    b.disabled = locked;
    b.title = tip;
  });
  $$("[data-player-action]").forEach((b) => {
    b.disabled = locked;
    b.title = tip;
  });
  $$("#view-chat .send-actions button, #send-mode").forEach((b) => {
    if (b && b.id !== "send-mode") b.disabled = locked;
  });
  // 视觉置灰
  $$(".view.active .pill-action:disabled, .view.active .rule-card:disabled, .view.active .command-card:disabled, .view.active .quick-btn:disabled").forEach((b) => {
    b.classList.toggle("is-locked", locked);
  });
}

async function fetchStatus() {
  try {
    const r = await fetch("/api/status");
    const j = await r.json();
    if (j.ok) applyStatus(j.data);
  } catch (e) {}
}

// ---------- 日志 ----------
const dashLog = $("#dash-log");

function appendLog(level, msg) {
  const div = document.createElement("div");
  div.className = "logline";
  const ts = document.createElement("span");
  ts.className = "ts";
  ts.textContent = fmtTime(Date.now() / 1000);
  div.appendChild(ts);
  const body = document.createElement("span");
  body.innerHTML = renderMc(msg);
  div.appendChild(body);
  dashLog.appendChild(div);
  while (dashLog.children.length > 500) dashLog.removeChild(dashLog.firstChild);
  dashLog.scrollTop = dashLog.scrollHeight;
}

// ---------- Toast 轻提示 ----------
const toastRoot = $("#toast-root");
const TOAST_TYPES = { ok: "ok", info: "info", warn: "warn", err: "err" };
function showToast(msg, type) {
  if (!toastRoot) return;
  const kind = TOAST_TYPES[type] || "info";
  const el = document.createElement("div");
  el.className = "toast toast-" + kind;
  el.innerHTML = renderMc(String(msg || ""));
  toastRoot.appendChild(el);
  // 至多同时显示 3 条
  while (toastRoot.children.length > 3) toastRoot.removeChild(toastRoot.firstChild);
  setTimeout(() => {
    el.classList.add("toast-out");
    setTimeout(() => el.remove(), 260);
  }, 2600);
}

// ---------- 通用二次确认弹层（替代原生 confirm） ----------
function askConfirm(title, bodyHtml, opts) {
  opts = opts || {};
  return new Promise((resolve) => {
    const sheet = $("#confirm-sheet");
    if (!sheet) return resolve(window.confirm(bodyHtml));
    $("#confirm-title").textContent = title || "请确认";
    $("#confirm-body").innerHTML = bodyHtml || "";
    const yesBtn = $("#confirm-yes");
    const noBtn = $("#confirm-no");
    const cancelBtn = $("#confirm-cancel");
    yesBtn.textContent = opts.yesText || "确认";
    noBtn.textContent = opts.noText || "再想想";
    yesBtn.className = "mini-btn " + (opts.danger === false ? "primary" : "danger");
    sheet.style.display = "grid";
    syncOverlayState();
    const cleanup = () => {
      yesBtn.onclick = null;
      noBtn.onclick = null;
      cancelBtn.onclick = null;
      sheet.onclick = null;
      sheet.style.display = "none";
      syncOverlayState();
    };
    yesBtn.onclick = () => { cleanup(); resolve(true); };
    noBtn.onclick = () => { cleanup(); resolve(false); };
    cancelBtn.onclick = () => { cleanup(); resolve(false); };
    sheet.onclick = (e) => {
      if (e.target.id === "confirm-sheet") { cleanup(); resolve(false); }
    };
  });
}

// ---------- 通用输入弹层（替代原生 prompt，移动端友好） ----------
// fields: [{ key, label, value, placeholder, type: text|number|select, options: [...] }]
function askPrompt(title, fields, opts) {
  opts = opts || {};
  return new Promise((resolve) => {
    const sheet = $("#prompt-sheet");
    if (!sheet) return resolve(null);
    $("#prompt-title").textContent = title || "输入信息";
    const body = $("#prompt-body");
    const valueMap = {};
    body.innerHTML = fields.map((f, fi) => {
      const label = `<label>${escapeHtml(f.label)}</label>`;
      let input;
      if (f.type === "select") {
        const optsHtml = (f.options || []).map((o) => `<option value="${escapeHtml(String(o))}">${escapeHtml(String(o))}</option>`).join("");
        input = `<select data-pf="${fi}">${optsHtml}</select>`;
      } else if (f.type === "number") {
        input = `<input data-pf="${fi}" type="number" ${f.min !== undefined ? `min="${f.min}"` : ""} value="${escapeHtml(String(f.value ?? ""))}" placeholder="${escapeHtml(f.placeholder || "")}" />`;
      } else {
        input = `<input data-pf="${fi}" type="text" value="${escapeHtml(String(f.value ?? ""))}" placeholder="${escapeHtml(f.placeholder || "")}" ${f.autofocus ? "autofocus" : ""} />`;
      }
      return `<div class="prompt-field">${label}${input}</div>`;
    }).join("");
    if (opts.hint) body.innerHTML += `<p class="pmeta">${escapeHtml(opts.hint)}</p>`;
    const okBtn = $("#prompt-yes");
    const cancelBtn = $("#prompt-cancel");
    okBtn.textContent = opts.yesText || "确认";
    okBtn.className = "mini-btn primary";
    sheet.style.display = "grid";
    syncOverlayState();
    const cleanup = () => {
      okBtn.onclick = null;
      cancelBtn.onclick = null;
      sheet.onclick = null;
      sheet.style.display = "none";
      syncOverlayState();
    };
    okBtn.onclick = () => {
      const result = {};
      body.querySelectorAll("[data-pf]").forEach((el) => {
        const field = fields[Number(el.dataset.pf)];
        result[field.key] = el.value.trim();
      });
      cleanup();
      resolve(result);
    };
    cancelBtn.onclick = () => { cleanup(); resolve(null); };
    sheet.onclick = (e) => {
      if (e.target.id === "prompt-sheet") { cleanup(); resolve(null); }
    };
    // 回车确认
    body.querySelectorAll("input[data-pf]").forEach((el) => {
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); okBtn.click(); }
      });
    });
  });
}

// ---------- 聊天 ----------
const unifiedFeed = $("#unified-feed");

function appendChat(d) {
  if (!unifiedFeed) return;
  const div = document.createElement("div");
  const cls = "msg-" + (d.kind || "chat");
  div.className = "feed-line " + cls;
  if (d.kind === "system") {
    div.innerHTML = `<span class="ts">${fmtTime(d.ts)}</span> ${renderMc(d.msg)}`;
  } else {
    div.innerHTML = `<span class="ts">${fmtTime(d.ts)}</span> <span class="who">${escapeHtml(d.player)}</span> ${renderMc(d.msg)}`;
  }
  unifiedFeed.appendChild(div);
  trimUnifiedFeed();
  // 同步到控制台首页的“最近消息”摘要
  mirrorRecentChat(d);
}

function mirrorRecentChat(d) {
  const box = $("#dash-recent");
  if (!box) return;
  const ph = box.querySelector(".pmeta");
  if (ph) ph.remove();
  const line = document.createElement("div");
  line.className = "logline";
  if (d.kind === "system") {
    line.innerHTML = `<span class="ts">${fmtTime(d.ts)}</span> ${renderMc(d.msg)}`;
  } else {
    line.innerHTML = `<span class="ts">${fmtTime(d.ts)}</span> <span class="who">${escapeHtml(d.player)}</span> ${renderMc(d.msg)}`;
  }
  box.appendChild(line);
  while (box.children.length > 80) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}

// ---------- 启动配置（全局，供新手引导等提前引用） ----------
let CONFIG_SCHEMA = [];
let CONFIG_DATA = null;

// ---------- 玩家 ----------
let playersCache = [];

function renderPlayerList() {
  const q = ($("#player-search").value || "").toLowerCase();
  const list = $("#player-list");
  list.innerHTML = "";
  const filtered = playersCache.filter((p) => p.name.toLowerCase().includes(q));
  if (!filtered.length) {
    if (q) {
      list.innerHTML = '<div class="empty-guide"><strong>没有找到匹配的玩家</strong><span>换个关键词试试，或确认玩家名拼写。</span></div>';
    } else if (!(STATUS && STATUS.state === "running")) {
      list.innerHTML = '<div class="empty-guide"><strong>服务器还没有启动</strong><span>启动服务后，进入服务器的玩家会出现在这里。你可以在“服务器”页一键调整规则，或在“消息”页发公告。</span></div>';
    } else {
      list.innerHTML = '<div class="empty-guide"><strong>还没有玩家来过</strong><span>把服务器地址发给朋友试试；玩家进入后会自动出现在这里，点击即可管理。</span></div>';
    }
    return;
  }
  let idx = 0;
  for (const p of filtered) {
    const item = document.createElement("div");
    item.className = "player-item";
    item.dataset.name = p.name;
    item.style.animationDelay = Math.min(idx++ * 18, 220) + "ms";
    item.innerHTML = `
      <div class="player-avatar">${escapeHtml(p.name[0] || "?")}</div>
      <div class="player-name">${escapeHtml(p.name)}</div>
      <div class="player-meta">${p.online ? "在线" : "离线"}</div>
    `;
    item.onclick = () => loadPlayerDetail(p.name);
    list.appendChild(item);
  }
}

async function loadPlayerDetail(name) {
  const box = $("#player-detail");
  const extra = $("#player-extra");
  const panel = $("#player-sheet");
  if (panel) panel.style.display = "grid";
  syncOverlayState();
  const sheetTitle = $("#player-sheet-title");
  if (sheetTitle) sheetTitle.textContent = `玩家操作 · ${name}`;
  // 同步到“玩家处理”选择器，方便直接操作该玩家
  const mgrPlayer = $("#mgr-player");
  if (mgrPlayer && name) {
    refreshManagerPlayers();
    mgrPlayer.value = name;
  }
  extra.style.display = "none";
  extra.innerHTML = "";
  try {
    const r = await fetch("/api/players/" + encodeURIComponent(name));
    const j = await r.json();
    if (!j.ok) { box.textContent = j.error; return; }
    const p = j.data;
    const ab = p.abilities;
    let html = `<div class="kv">`;
    html += `<div class="k">名称</div><div>${escapeHtml(p.name)}</div>`;
    html += `<div class="k">UUID</div><div style="word-break:break-all">${escapeHtml(p.uuid)}</div>`;
    html += `<div class="k">UniqueID</div><div>${p.unique_id}</div>`;
    html += `<div class="k">XUID</div><div>${escapeHtml(p.xuid)}</div>`;
    html += `<div class="k">设备ID</div><div>${escapeHtml(p.device_id || "—")}</div>`;
    html += `<div class="k">平台</div><div>${p.build_platform}</div>`;
    html += `<div class="k">权限</div><div>${p.is_op === null ? "—" : (p.is_op ? '<span class="badge op">OP</span>' : '<span class="badge notop">普通</span>')}</div>`;
    html += `</div>`;
    if (ab) {
      html += `<div style="margin-top:12px;font-weight:700">能力权限</div><div class="kv" style="margin-top:6px">`;
      const labels = {
        build: "建造", mine: "挖掘", doors_and_switches: "门/开关", open_containers: "开容器",
        attack_players: "攻击玩家", attack_mobs: "攻击生物", operator_commands: "操作员命令", teleport: "传送",
      };
      for (const [k, v] of Object.entries(ab)) {
        if (k in labels) html += `<div class="k">${labels[k]}</div><div>${v ? "允许" : "关闭"}</div>`;
      }
      html += `<div class="k">命令等级</div><div>${ab.command_permissions}</div>`;
      html += `</div>`;
    }
    html += `<div class="easy-player-card" style="margin-top:14px">`;
    html += `<div class="easy-title">玩家管理入口</div>`;
    html += `<div class="easy-actions">`;
    html += actionButton("查看背包", "inventory", { player: p.name });
    html += actionButton("查看位置", "position", { player: p.name });
    html += actionButton("选入处理区", "manage", { player: p.name });
    html += actionButton("加入黑名单", "blacklist", { player: p.name });
    html += `</div>`;
    html += `</div>`;
    box.innerHTML = html;
    box.querySelectorAll("[data-easy-action]").forEach((b) => {
      b.onclick = () => runEasyPlayerAction(b.dataset.easyAction, JSON.parse(b.dataset.easyData || "{}"));
    });
  } catch (e) {
    box.textContent = "加载失败";
  }
}

async function loadInventory(name) {
  const extra = $("#player-extra");
  const panel = $("#player-sheet");
  if (panel) panel.style.display = "grid";
  syncOverlayState();
  extra.style.display = "";
  extra.innerHTML = '<div class="subhead">背包（加载中…）</div>';
  try {
    const r = await fetch("/api/players/" + encodeURIComponent(name) + "/inventory");
    const j = await r.json();
    if (!j.ok) { extra.innerHTML = `<div class="subhead">背包</div><div class="cmd-err">${escapeHtml(j.error)}</div>`; return; }
    const inv = j.data;
    const slots = inv.slots || [];
    let html = `<div class="subhead">背包 <span style="font-weight:400;color:var(--muted);font-size:12px">共 ${inv.slotCount} 格（${inv.first}~${inv.last}）</span> <button class="mini-btn" onclick="loadInventory('${escapeHtml(name)}')">刷新</button></div>`;
    html += '<div class="inv-grid">';
    for (let i = 0; i < slots.length; i++) {
      const s = slots[i];
      if (!s) {
        html += `<div class="inv-slot empty"><span class="idx">${inv.first + i}</span></div>`;
      } else {
        const baseName = s.displayName || itemName(s.id, s.namespace) || readableItemKey(s.id) || readableItemKey(s.namespace) || "未知物品";
        const customName = (s.customName || "").trim();
        const disp = customName || baseName;
        const ench = enchantSummary(s.enchantments);
        const img = itemImageHtml(s.id, s.namespace);
        const title = `${disp}${customName ? '\n原物品：' + baseName : ''}${ench ? '\n' + ench : ''}\n${s.namespace || s.id || ''}`;
        const detail = customName ? [baseName, ench].filter(Boolean).join(" · ") : ench;
        html += `<div class="inv-slot${ench || customName ? ' enchanted' : ''}" title="${escapeHtml(title)}"><span class="idx">${inv.first + i}</span>${img}<span class="cnt">${s.stackSize}</span>${ench ? '<span class="ench-badge">附</span>' : ''}<span class="name">${renderMc(disp)}</span>${detail ? `<span class="ench-name">${escapeHtml(detail)}</span>` : ''}</div>`;
      }
    }
    html += '</div>';
    extra.innerHTML = html;
  } catch (e) {
    extra.innerHTML = '<div class="subhead">背包</div><div class="cmd-err">加载失败</div>';
  }
}

async function loadPosition(name) {
  const extra = $("#player-extra");
  const panel = $("#player-sheet");
  if (panel) panel.style.display = "grid";
  syncOverlayState();
  extra.style.display = "";
  extra.innerHTML = '<div class="subhead">位置（加载中…）</div>';
  try {
    const r = await fetch("/api/players/" + encodeURIComponent(name) + "/position");
    const j = await r.json();
    if (!j.ok) { extra.innerHTML = `<div class="subhead">位置</div><div class="cmd-err">${escapeHtml(j.error)}</div>`; return; }
    const pos = j.data;
    const p = pos.position || {};
    let html = `<div class="subhead">位置 <button class="mini-btn" onclick="loadPosition('${escapeHtml(name)}')">刷新</button></div>`;
    html += `<div class="kv">`;
    html += `<div class="k">维度</div><div>${pos.dimension}</div>`;
    html += `<div class="k">X</div><div>${p.x}</div>`;
    html += `<div class="k">Y</div><div>${p.y}</div>`;
    html += `<div class="k">Z</div><div>${p.z}</div>`;
    html += `<div class="k">朝向</div><div>${pos.yRot}°</div>`;
    html += `</div>`;
    extra.innerHTML = html;
  } catch (e) {
    extra.innerHTML = '<div class="subhead">位置</div><div class="cmd-err">加载失败</div>';
  }
}

async function fetchPlayers() {
  try {
    const r = await fetch("/api/players");
    const j = await r.json();
    if (j.ok) { playersCache = j.data || []; renderPlayerList(); refreshManagerPlayers(); }
  } catch (e) {}
}

$("#player-sheet-close").onclick = () => {
  $("#player-sheet").style.display = "none";
  syncOverlayState();
};

// ---------- 控制台 ----------
const consoleOut = unifiedFeed;

function trimUnifiedFeed() {
  if (!unifiedFeed) return;
  while (unifiedFeed.children.length > 500) unifiedFeed.removeChild(unifiedFeed.firstChild);
  unifiedFeed.scrollTop = unifiedFeed.scrollHeight;
}

function appendConsole(html, cls) {
  if (!unifiedFeed) return;
  const div = document.createElement("div");
  div.className = "feed-line msg-command " + (cls || "");
  div.innerHTML = html;
  unifiedFeed.appendChild(div);
  trimUnifiedFeed();
}

async function sendCommand() {
  const identity = $("#cmd-identity")?.value || "ws";
  const cmd = ($("#unified-input")?.value || "").trim();
  if (!cmd) return;
  $("#unified-input").value = "";
  appendConsole(`<span class="ts">${fmtTime(Date.now()/1000)}</span> <span style="color:#888">&gt; [${identity}] ${escapeHtml(cmd)}</span>`);
  try {
    const r = await fetch("/api/command", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identity, cmd }),
    });
    const j = await r.json();
    if (j.ok) {
      if (j.messages && j.messages.length) {
        for (const m of j.messages) appendConsole(renderMc(m), j.success ? "cmd-ok" : "");
      } else if (j.raw) {
        appendConsole(`<pre>${escapeHtml(JSON.stringify(j.raw, null, 2))}</pre>`, j.success ? "cmd-ok" : "cmd-err");
      } else if (j.note) {
        appendConsole(escapeHtml(j.note));
      } else {
        appendConsole("已发送", "cmd-ok");
      }
    } else {
      appendConsole(escapeHtml(humanizeError(j.error)), "cmd-err");
    }
  } catch (e) {
    appendConsole("请求失败，请检查网络连接", "cmd-err");
  }
}

async function sendChatMessage() {
  const input = $("#unified-input");
  const text = (input?.value || "").trim();
  if (!text) return;
  input.value = "";
  const identity = $("#chat-identity")?.value || "console";
  const customName = ($("#chat-custom-name")?.value || "").trim();
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identity, text, custom_name: customName }),
    });
    const j = await r.json();
    if (!j.ok) {
      appendChat({ kind: "system", ts: Date.now() / 1000, msg: "§c发送失败：" + (j.error || "未知错误") });
    } else {
      appendChat({ kind: "system", ts: Date.now() / 1000, msg: "§7已发送：" + text });
    }
  } catch (e) {
    appendChat({ kind: "system", ts: Date.now() / 1000, msg: "§c聊天请求失败" });
  }
}

function updateUnifiedComposer() {
  const mode = $("#send-mode")?.value || "chat";
  const isCommand = mode === "command";
  const chatIdentity = $("#chat-identity");
  const customName = $("#chat-custom-name");
  const cmdIdentity = $("#cmd-identity");
  const input = $("#unified-input");
  const hint = $("#composer-hint");
  if (chatIdentity) chatIdentity.style.display = isCommand ? "none" : "";
  if (customName) customName.style.display = (!isCommand && chatIdentity?.value === "custom") ? "" : "none";
  if (cmdIdentity) cmdIdentity.style.display = isCommand ? "" : "none";
  if (input) input.placeholder = isCommand ? "输入命令，如 /list，回车执行…" : "输入聊天内容，回车发送…";
  if (hint) {
    hint.textContent = isCommand
      ? (cmdIdentity?.value === "native"
        ? "这里执行 ToolDelta 原生命令，例如 help、list、reload；输出会回到终端日志。"
        : "命令默认使用 WebSocket(ws) 身份；需要特殊身份时再切换。")
      : "聊天会发到游戏公共聊天；选择“自定义身份”可以自己填写显示名字。";
  }
}

function sendUnifiedInput() {
  const mode = $("#send-mode")?.value || "chat";
  if (mode === "command") return sendCommand();
  return sendChatMessage();
}

// ---------- 视图切换 ----------
function pageUrlForView(name) {
  if (name === "dashboard") return "/";
  return `/${name}`;
}

function currentViewFromLocation() {
  const path = window.location.pathname.replace(/^\//, "").replace(/\/$/, "");
  const top = path.split("/")[0];
  // 旧路由兼容：/manage/* -> world，/config 与 /files -> settings
  if (top === "manage") return "world";
  if (top === "config" || top === "files") return "settings";
  return ["dashboard", "players", "world", "chat", "plugins", "market", "settings"].includes(top) ? top : "dashboard";
}

function switchView(name, options = {}) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => {
    const active = v.id === "view-" + name;
    v.classList.toggle("active", active);
    v.classList.remove("view-enter");
    if (active) {
      void v.offsetWidth;
      v.classList.add("view-enter");
    }
  });
  const titles = { dashboard: "控制台", players: "玩家", world: "服务器", chat: "消息", plugins: "插件", market: "市场", settings: "设置" };
  const pageTitle = titles[name] || name;
  $("#topbar-title").textContent = pageTitle;
  document.title = `神翼面板 · ${pageTitle}`;
  // 启动/停止服务只在控制台页展示
  const topActions = $("#topbar-actions");
  if (topActions) topActions.style.display = name === "dashboard" ? "" : "none";
  if (name === "dashboard") renderGuide();
  if (name === "players") { fetchPlayers(); loadBlacklist(); }
  if (name === "world") { fetchPlayers(); loadOperationLog(); syncWorldRules(); }
  if (name === "plugins") loadPlugins();
  if (name === "market") marketSearch();
  if (name === "settings") { loadConfig(); loadFiles(""); }
  if (options.pushState !== false) {
    history.pushState({ view: name }, "", pageUrlForView(name));
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
  syncOverlayState();
}

// ---------- 新手引导条 ----------
const GUIDE_KEY = "shenyi:guideDone";
function configDone() {
  // CONFIG_DATA 里存在有效配置字段（启动器编号或配置内容）即视为已配置
  const d = CONFIG_DATA || {};
  const keys = Object.keys(d).filter((k) => !["launch_mode", "record_log", "github_mirror", "plugin_market", "fbtoken"].includes(k));
  return keys.some((k) => d[k] !== undefined && d[k] !== null && String(d[k]) !== "") || (d.launch_mode > 0);
}
function renderGuide() {
  const card = $("#guide-card");
  const stepsBox = $("#guide-steps");
  if (!card || !stepsBox) return;
  if (localStorage.getItem(GUIDE_KEY) === "1") { card.style.display = "none"; return; }

  const running = STATUS && STATUS.state === "running";
  const startedEver = localStorage.getItem("shenyi:startedOnce") === "1" || running;
  const hasPlugins = (window.PLUGIN_COUNT || 0) > 0;

  const steps = [
    {
      done: configDone(),
      no: "01",
      title: "填写启动配置",
      desc: "告诉面板怎么连上你的服务器：选好接入方式、填入账号验证信息，一次填好永久生效",
      btn: "去设置",
      go: "settings",
      doneText: "启动配置已完成",
    },
    {
      done: startedEver,
      no: "02",
      title: "启动服务，接入服务器",
      desc: "回到控制台点“启动服务”，机器人会自动连上你的服务器并开始工作",
      btn: "去启动",
      go: "dashboard",
      doneText: "已启动过",
    },
    {
      done: hasPlugins,
      no: "03",
      title: "安装插件，解锁新功能",
      desc: "服务器原本不支持的功能，装上插件就能用——去市场挑一个试试",
      btn: "去市场",
      go: "market",
      doneText: "已安装插件",
    },
  ];
  const allDone = steps.every((s) => s.done);
  if (allDone) {
    localStorage.setItem(GUIDE_KEY, "1");
    card.style.display = "none";
    return;
  }
  card.style.display = "";
  stepsBox.innerHTML = steps.map((s) => `
    <div class="guide-step ${s.done ? "done" : ""}">
      <div class="guide-no ${s.done ? "done" : ""}">${s.done ? "✓" : s.no}</div>
      <div class="guide-main">
        <div class="guide-title">${s.title}</div>
        <div class="guide-desc">${s.desc}</div>
      </div>
      ${s.done ? `<span class="guide-done-tag">${s.doneText}</span>` : `<button class="mini-btn primary guide-go" data-go="${s.go}">${s.btn}</button>`}
    </div>
  `).join("");
  $$(".guide-go").forEach((b) => {
    b.onclick = () => {
      if (b.dataset.go === "dashboard") {
        $("#btn-start").click();
      } else {
        switchView(b.dataset.go);
      }
    };
  });
}

// ---------- 服务器管理 ----------
const COMMAND_TEMPLATES = [
  { title: "在线列表", desc: "查看当前在线玩家", icon: "LIST", cmd: "/list" },
  { title: "保存世界", desc: "立即保存当前存档", icon: "SAVE", cmd: "/save-all" },
  { title: "白天晴天", desc: "切换为适合建设的环境", icon: "DAY", cmd: "/time set day" },
  { title: "关闭天气循环", desc: "保持当前天气状态", icon: "SKY", cmd: "/gamerule doWeatherCycle false" },
  { title: "开启死亡不掉落", desc: "降低玩家损失风险", icon: "KEEP", cmd: "/gamerule keepInventory true" },
  { title: "关闭死亡不掉落", desc: "恢复默认生存规则", icon: "RISK", cmd: "/gamerule keepInventory false" },
];

const DIFFICULTY_STORAGE_KEY = "shenyi:lastDifficulty";
const MOBILE_SHEET_QUERY = window.matchMedia("(max-width: 760px)");

function syncOverlayState() {
  const anyOpen = ["#plugin-config-drawer", "#market-detail-panel", "#file-editor-panel", "#player-sheet", "#blacklist-sheet", "#confirm-sheet", "#prompt-sheet"].some((selector) => {
    const el = $(selector);
    return !!el && getComputedStyle(el).display !== "none";
  });
  document.body.classList.toggle("modal-open", anyOpen && MOBILE_SHEET_QUERY.matches);
}

function syncDifficultyButtons(value) {
  const selected = String(value || "").trim();
  $$('[data-world-action="difficulty"]').forEach((button) => {
    const isSelected = button.dataset.value === selected;
    button.classList.toggle("is-selected", isSelected);
  });
  if (selected) localStorage.setItem(DIFFICULTY_STORAGE_KEY, selected);
}

// 世界规则卡当前状态回显：根据后端记录的规则状态点亮对应卡片
function syncWorldRules() {
  const rules = (STATUS && STATUS.world_rules) || {};
  $$("[data-rule]").forEach((b) => {
    const key = "rule:" + b.dataset.rule;
    const cur = rules[key];
    const want = b.dataset.ruleValue;
    const isOn = cur !== undefined && String(cur) === String(want);
    b.classList.toggle("is-selected", isOn);
    if (isOn) {
      b.setAttribute("title", "当前已开启此规则");
    }
  });
  // 难度回显：后端记录优先，其次本地记忆
  const diff = rules["difficulty"] || localStorage.getItem(DIFFICULTY_STORAGE_KEY) || "";
  if (diff) syncDifficultyButtons(diff);
}

function refreshManagerPlayers() {
  const online = $("#mgr-online");
  if (online) online.textContent = playersCache.length;
  const currentPlayer = $("#mgr-player")?.value || "";
  const currentTarget = $("#mgr-tp-target")?.value || "";
  const playerOptions = playersCache.map((p) => `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)}</option>`).join("");
  const playerSelect = $("#mgr-player");
  if (playerSelect) {
    playerSelect.innerHTML = playerOptions || '<option value="">暂无在线玩家</option>';
    if (currentPlayer && playersCache.some((p) => p.name === currentPlayer)) playerSelect.value = currentPlayer;
  }
  const targetSelect = $("#mgr-tp-target");
  if (targetSelect) {
    targetSelect.innerHTML = playerOptions || '<option value="">暂无在线玩家</option>';
    if (currentTarget && playersCache.some((p) => p.name === currentTarget)) targetSelect.value = currentTarget;
  }
  const blacklistOptions = $("#blacklist-player-options");
  if (blacklistOptions) blacklistOptions.innerHTML = playerOptions;
}

async function managerPost(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const j = await r.json();
  const humanError = humanizeError(j && j.error);
  if (!j.ok) {
    appendLog("ERROR", humanError);
    showToast(humanError, "err");
  } else if (j.success === false) {
    const msg = (j.messages && j.messages[0]) || "操作未生效";
    appendLog("WARNING", msg);
    showToast(msg, "warn");
  } else {
    appendLog("INFO", (j.messages && j.messages[0]) || "管理操作已执行");
  }
  await loadOperationLog();
  return j;
}

// 把后端技术报错翻译成客户能看懂的提示
function humanizeError(err) {
  const e = String(err || "");
  if (!e) return "操作失败，请稍后重试";
  if (e.includes("框架尚未就绪") || e.includes("原生命令管理器尚未就绪")) {
    return "服务器还没有启动完成：请到控制台页点“启动服务”，等机器人上线后再操作";
  }
  if (e.includes("超时")) return "命令执行超时：服务器可能繁忙或无响应，请稍后再试";
  if (e.includes("登录") && e.includes("过")) return "与服务器的连接已断开，请重新启动服务";
  return e;
}

async function runPlayerAction(action, data) {
  const result = await managerPost("/api/server/player_action", Object.assign({ action }, data || {}));
  if (result && result.ok && result.success !== false) {
    const p = data && data.player ? String(data.player) : "";
    const tips = {
      kick: `已把 ${p} 移出服务器`,
      op: `已授予 ${p} 管理员权限`,
      deop: `已取消 ${p} 的管理员权限`,
      gamemode: `已切换 ${p} 的游戏模式`,
      tp_player: `已把 ${p} 传送到目标玩家`,
      tp_pos: `已把 ${p} 传送到坐标`,
      give: `已给 ${p} 发放物品`,
      clear: `已清空 ${p} 的背包`,
      kill: `已执行：${p}`,
    };
    showToast(tips[action] || "操作已执行", "ok");
  }
  return result;
}

async function runWorldAction(action, extra) {
  const payload = Object.assign({ action }, extra || {});
  const result = await managerPost("/api/server/world_action", payload);
  const ok = result && result.ok && result.success !== false;
  if (action === "difficulty" && ok) {
    syncDifficultyButtons(payload.value);
    showToast("难度已切换为 " + ({ peaceful: "和平", easy: "简单", normal: "普通", hard: "困难" }[payload.value] || payload.value), "ok");
  }
  if (action === "gamerule" && ok) {
    const on = payload.value === "true";
    showToast("已" + (on ? "开启" : "关闭") + " " + ({ keepInventory: "死亡不掉落", mobGriefing: "生物破坏", doDaylightCycle: "昼夜循环", doWeatherCycle: "天气循环", doMobSpawning: "生物生成", doImmediateRespawn: "立即重生", showCoordinates: "显示坐标", commandBlockOutput: "命令方块输出", sendCommandFeedback: "命令反馈", doFireTick: "火焰蔓延", pvp: "PVP", showDeathMessages: "死亡消息" }[payload.rule] || payload.rule), "ok");
  }
  if (action === "time" && ok) showToast("时间已设置", "ok");
  if (action === "weather" && ok) showToast("天气已" + ({ clear: "放晴", rain: "转雨", thunder: "转雷暴" }[payload.value] || "设置"), "ok");
  // 规则卡选中态即时刷新（后端已持久化状态）
  if (action === "gamerule" && ok) {
    const rules = (STATUS && STATUS.world_rules) || {};
    rules["rule:" + payload.rule] = payload.value;
    if (STATUS) STATUS.world_rules = rules;
    syncWorldRules();
  }
  return result;
}

async function runTemplate(title, cmd) {
  await managerPost("/api/server/template", { title, cmd, identity: "ws" });
}

function playerNamesExcept(name) {
  return playersCache.map((p) => p.name).filter((p) => p !== name);
}

async function runEasyPlayerAction(action, data) {
  const player = data.player;
  if (action === "inventory") return loadInventory(player);
  if (action === "position") return loadPosition(player);
  if (action === "manage") return focusManagePlayer(player);
  if (action === "blacklist") return focusBlacklistPlayer(player);
  if (action === "gamemode") return runPlayerAction("gamemode", { player, mode: data.mode });
  if (action === "give") return easyGiveItem(player);
  if (action === "tp_player") return easyTpToPlayer(player);
  if (action === "tp_pos") return easyTpToPos(player);
  if (action === "kick") return easyKick(player);
  if (action === "clear") return easyClear(player);
  if (action === "kill") return easyKill(player);
  if (action === "op") return easyOp(player, data.enabled);
}

function focusManagePlayer(player) {
  switchView("players");
  // 处理区已并入玩家操作卡：直接打开并选中该玩家，滚动到处理区
  const panel = $("#player-sheet");
  if (panel && panel.style.display === "none") loadPlayerDetail(player || (($("#mgr-player")?.value) || ""));
  refreshManagerPlayers();
  const select = $("#mgr-player");
  if (select && player) select.value = player;
  const manageBox = $("#player-sheet .sheet-manage");
  if (panel && panel.style.display !== "none") {
    const target = manageBox || select;
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  } else {
    select?.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function focusBlacklistPlayer(player) {
  // 黑名单添加已改为弹层卡：打开它并带入玩家名
  const sheet = $("#blacklist-sheet");
  if (sheet) sheet.style.display = "grid";
  syncOverlayState();
  refreshManagerPlayers();
  const input = $("#blacklist-name");
  if (input && player) input.value = player;
  if (input) setTimeout(() => input.focus(), 60);
}

function selectedManagerPlayer() {
  const player = ($("#mgr-player")?.value || "").trim();
  if (!player) appendLog("WARNING", "请先选择玩家");
  return player;
}

async function runManagerPlayerAction(button) {
  const action = button.dataset.playerAction;
  const player = selectedManagerPlayer();
  if (!player) return;
  if (action === "gamemode") return runPlayerAction("gamemode", { player, mode: button.dataset.mode });
  if (action === "give") {
    const item = ($("#mgr-give-item")?.value || "").trim();
    if (!item) { appendLog("WARNING", "请填写要给予的物品"); return; }
    return runPlayerAction("give", { player, item, count: $("#mgr-give-count")?.value || 1 });
  }
  if (action === "tp_player") {
    const target = ($("#mgr-tp-target")?.value || "").trim();
    if (!target) { appendLog("WARNING", "请选择传送目标"); return; }
    return runPlayerAction("tp_player", { player, target });
  }
  if (action === "tp_pos") {
    const x = ($("#mgr-tp-x")?.value || "").trim();
    const y = ($("#mgr-tp-y")?.value || "").trim();
    const z = ($("#mgr-tp-z")?.value || "").trim();
    if (!x || !y || !z) { appendLog("WARNING", "请填写完整坐标 X/Y/Z"); return; }
    return runPlayerAction("tp_pos", { player, x, y, z });
  }
  if (action === "kick") {
    if (!(await askConfirm("踢出玩家", `<p>确认把 <b>${escapeHtml(player)}</b> 移出服务器？</p><p class=\"pmeta\">玩家会断开连接，可随时重新进入。</p>`))) return;
    return runPlayerAction("kick", { player, reason: $("#mgr-kick-reason")?.value || "由 Web 面板移出" });
  }
  if (action === "clear") {
    if (!(await askConfirm("清空背包", `<p>确认清空 <b>${escapeHtml(player)}</b> 的背包？</p><p class=\"pmeta\">背包内所有物品会被移除，此操作不可恢复。</p>`))) return;
    return runPlayerAction("clear", { player });
  }
  if (action === "kill") {
    if (!(await askConfirm("击杀玩家", `<p>确认击杀 <b>${escapeHtml(player)}</b>？</p><p class=\"pmeta\">该玩家会死亡并掉落背包物品。</p>`))) return;
    return runPlayerAction("kill", { player });
  }
  if (action === "op" || action === "deop") {
    if (!(await askConfirm(action === "op" ? "授予 OP" : "取消 OP", `<p>确认${action === "op" ? "授予" : "取消"} <b>${escapeHtml(player)}</b> 的管理员权限？</p>`))) return;
    return runPlayerAction(action, { player });
  }
}

async function easyGiveItem(player) {
  const res = await askPrompt("给物品", [
    { key: "item", label: "物品（如 diamond_sword / apple）", value: "", placeholder: "输入物品 ID 或名称", autofocus: true },
    { key: "count", label: "数量", type: "number", value: "1", min: 1 },
  ], { hint: `将发放给 ${player}` });
  if (!res) return;
  if (!res.item) { showToast("请填写物品", "warn"); return; }
  await runPlayerAction("give", { player, item: res.item, count: res.count || 1 });
}

async function easyTpToPlayer(player) {
  const names = playerNamesExcept(player);
  if (!names.length) { showToast("没有其他在线玩家可传送", "warn"); return; }
  const res = await askPrompt("传送到玩家", [
    { key: "target", label: "选择目标玩家", type: "select", options: names },
  ]);
  if (!res) return;
  await runPlayerAction("tp_player", { player, target: res.target });
}

async function easyTpToPos(player) {
  const res = await askPrompt("传送到坐标", [
    { key: "x", label: "X", type: "number", value: "0", autofocus: true },
    { key: "y", label: "Y", type: "number", value: "80" },
    { key: "z", label: "Z", type: "number", value: "0" },
  ]);
  if (!res) return;
  if (res.x === "" || res.y === "" || res.z === "") { showToast("请填写完整坐标", "warn"); return; }
  await runPlayerAction("tp_pos", { player, x: res.x, y: res.y, z: res.z });
}

async function easyKick(player) {
  const res = await askPrompt("踢出玩家", [
    { key: "reason", label: "原因（可留空）", value: "由 Web 面板移出", placeholder: "例如：违反服务器规则" },
  ], { hint: `确认把 ${player} 移出服务器？` });
  if (!res) return;
  await runPlayerAction("kick", { player, reason: res.reason || "由 Web 面板移出" });
}

async function easyClear(player) {
  if (!(await askConfirm("清空背包", `<p>确认清空 <b>${escapeHtml(player)}</b> 的背包？</p><p class=\"pmeta\">背包内所有物品会被移除，此操作不可恢复。</p>`))) return;
  await runPlayerAction("clear", { player });
}

async function easyKill(player) {
  if (!(await askConfirm("击杀玩家", `<p>确认击杀 <b>${escapeHtml(player)}</b>？</p><p class=\"pmeta\">该玩家会死亡并掉落背包物品。</p>`))) return;
  await runPlayerAction("kill", { player });
}

async function easyOp(player, enabled) {
  if (!(await askConfirm(enabled ? "授予 OP" : "取消 OP", `<p>确认${enabled ? "授予" : "取消"} <b>${escapeHtml(player)}</b> 的管理员权限？</p>`))) return;
  await runPlayerAction(enabled ? "op" : "deop", { player });
}

async function loadOperationLog() {
  const box = $("#mgr-op-log");
  if (!box) return;
  try {
    const r = await fetch("/api/server/ops");
    const j = await r.json();
    const items = j.data || [];
    const count = $("#mgr-op-count");
    if (count) count.textContent = items.length;
    if (!items.length) { box.innerHTML = '<div class="pmeta">暂无操作记录</div>'; return; }
    box.innerHTML = items.map((it) => {
      const msg = (it.error || (it.messages || []).join("\n") || "").trim();
      return `<div class="op-item ${it.ok ? 'ok' : 'fail'}"><div class="op-title">${escapeHtml(it.title || it.kind)} <span class="ts">${fmtTime(it.ts || Date.now()/1000)}</span></div><div class="op-cmd">${escapeHtml(it.cmd || "")}</div>${msg ? `<div class="op-msg">${escapeHtml(msg)}</div>` : ""}</div>`;
    }).join("");
  } catch (e) {
    box.innerHTML = '<div class="cmd-err">操作记录加载失败</div>';
  }
}

function fmtRemaining(seconds) {
  if (seconds === null || seconds === undefined) return "永久";
  const n = Math.max(0, Number(seconds) || 0);
  if (n <= 0) return "即将到期";
  const days = Math.floor(n / 86400);
  const hours = Math.floor((n % 86400) / 3600);
  const minutes = Math.ceil((n % 3600) / 60);
  if (days > 0) return `${days} 天 ${hours} 小时`;
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟`;
  return `${minutes || 1} 分钟`;
}

async function loadBlacklist() {
  const box = $("#blacklist-list");
  if (!box) return;
  box.innerHTML = '<div class="pmeta">正在读取黑名单…</div>';
  try {
    const r = await fetch("/api/blacklist");
    const j = await r.json();
    const items = j.data || [];
    if (!items.length) {
      box.innerHTML = '<div class="empty-guide">当前没有黑名单玩家。这里适合处理临时封禁、熊孩子、刷屏和违规物品问题。</div>';
      return;
    }
    box.innerHTML = items.map((it) => `
      <div class="blacklist-item">
        <div>
          <strong>${escapeHtml(it.name)}</strong>
          <span>${escapeHtml(it.reason || "未填写原因")}</span>
          <small>剩余：${escapeHtml(fmtRemaining(it.remaining_seconds))} · 操作人：${escapeHtml(it.operator || "Web 面板")}</small>
        </div>
        <button class="mini-btn danger" data-blacklist-remove="${escapeHtml(it.id)}" data-blacklist-name="${escapeHtml(it.name)}">移出</button>
      </div>
    `).join("");
    $$("[data-blacklist-remove]").forEach((b) => {
      b.onclick = () => removeBlacklistEntry(b.dataset.blacklistRemove, b.dataset.blacklistName);
    });
  } catch (e) {
    box.innerHTML = '<div class="cmd-err">黑名单加载失败</div>';
  }
}

function selectedBlacklistDuration() {
  const value = $("#blacklist-duration")?.value || "0";
  if (value !== "custom") return Number(value) || 0;
  return Math.max(1, Number($("#blacklist-custom-duration")?.value || 0) || 1);
}

async function addBlacklistEntry() {
  const name = ($("#blacklist-name")?.value || "").trim();
  const reason = ($("#blacklist-reason")?.value || "").trim();
  if (!name) { appendLog("WARNING", "请填写要加入黑名单的玩家名"); return; }
  const r = await fetch("/api/blacklist/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, reason, duration_minutes: selectedBlacklistDuration(), kick_now: true }),
  });
  const j = await r.json();
  if (!j.ok) { appendLog("ERROR", j.error || "加入黑名单失败"); showToast(j.error || "加入黑名单失败", "err"); }
  else { appendLog("WARNING", `${name} 已加入黑名单`); showToast(`${name} 已加入黑名单并拦截`, "ok"); }
  await loadBlacklist();
  await loadOperationLog();
}

async function removeBlacklistEntry(id, name) {
  if (!(await askConfirm("移出黑名单", `<p>确认把 <b>${escapeHtml(name || "该玩家")}</b> 移出黑名单？移出后可正常进入服务器。</p>`))) return;
  const r = await fetch("/api/blacklist/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, name }),
  });
  const j = await r.json();
  if (!j.ok) { appendLog("ERROR", j.error || "移出黑名单失败"); showToast(j.error || "移出黑名单失败", "err"); }
  else { appendLog("INFO", `${name || "玩家"} 已移出黑名单`); showToast(`${name || "该玩家"} 已移出黑名单`, "ok"); }
  await loadBlacklist();
}

function initServerManager() {
  const templateBox = $("#mgr-templates");
  if (templateBox) {
    templateBox.innerHTML = COMMAND_TEMPLATES.map((t) => `
      <button class="command-card" data-template="${escapeHtml(t.title)}">
        <span class="command-icon">${escapeHtml(t.icon)}</span>
        <strong>${escapeHtml(t.title)}</strong>
        <small>${escapeHtml(t.desc)}</small>
      </button>
    `).join("");
    $$("[data-template]").forEach((b) => {
      const t = COMMAND_TEMPLATES.find((x) => x.title === b.dataset.template);
      b.onclick = () => runTemplate(t.title, t.cmd);
    });
  }
  const bind = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
  $$("[data-world-action]").forEach((b) => {
    b.onclick = () => runWorldAction(b.dataset.worldAction, { value: b.dataset.value });
  });
  $$("[data-rule]").forEach((b) => {
    b.onclick = () => runWorldAction("gamerule", { rule: b.dataset.rule, value: b.dataset.ruleValue });
  });
  $$("[data-player-action]").forEach((b) => {
    b.onclick = () => runManagerPlayerAction(b);
  });
  bind("#mgr-set-gamerule", () => runWorldAction("gamerule", { rule: $("#mgr-gamerule").value, value: $("#mgr-gamerule-value").value }));
  bind("#blacklist-refresh", loadBlacklist);
  bind("#blacklist-add", addBlacklistEntry);
  bind("#blacklist-open-add", () => {
    const sheet = $("#blacklist-sheet");
    if (sheet) sheet.style.display = "grid";
    syncOverlayState();
    const input = $("#blacklist-name");
    if (input) setTimeout(() => input.focus(), 60);
  });
  bind("#blacklist-sheet-close", () => {
    const sheet = $("#blacklist-sheet");
    if (sheet) sheet.style.display = "none";
    syncOverlayState();
  });
  const blSheet = $("#blacklist-sheet");
  if (blSheet) blSheet.addEventListener("click", (e) => {
    if (e.target.id === "blacklist-sheet") {
      blSheet.style.display = "none";
      syncOverlayState();
    }
  });
  // 加黑名单成功/关闭后收起弹层
  const origAdd = addBlacklistEntry;
  addBlacklistEntry = async function () {
    await origAdd.apply(this, arguments);
    const sheet = $("#blacklist-sheet");
    if (sheet && sheet.style.display !== "none") {
      const name = ($("#blacklist-name")?.value || "").trim();
      if (name) { sheet.style.display = "none"; syncOverlayState(); }
    }
  };
  // 玩家操作卡：遮罩点击关闭 + Esc
  const pSheet = $("#player-sheet");
  if (pSheet) pSheet.addEventListener("click", (e) => {
    if (e.target.id === "player-sheet") {
      pSheet.style.display = "none";
      syncOverlayState();
    }
  });
  const psClose = $("#player-sheet-close");
  if (psClose) psClose.onclick = () => {
    pSheet.style.display = "none";
    syncOverlayState();
  };
  // 市场详情卡：遮罩点击关闭
  const mPanel = $("#market-detail-panel");
  if (mPanel) mPanel.addEventListener("click", (e) => {
    if (e.target.id === "market-detail-panel") {
      mPanel.style.display = "none";
      syncOverlayState();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      ["#player-sheet", "#blacklist-sheet", "#confirm-sheet", "#prompt-sheet", "#market-detail-panel"].forEach((sel) => {
        const el = $(sel);
        if (el && el.style.display !== "none") {
          el.style.display = "none";
          syncOverlayState();
        }
      });
    }
  });
}

// ---------- 事件绑定 ----------
$$(".nav-item").forEach((b) => b.onclick = (e) => {
  e.preventDefault();
  switchView(b.dataset.view);
});
$$(".quick-link").forEach((b) => b.onclick = () => switchView(b.dataset.go));
$("#btn-start").onclick = async () => {
  const r = await fetch("/api/start", { method: "POST" });
  const j = await r.json();
  if (!j.ok) {
    // 配置缺失：引导去启动配置页，并附上具体原因
    appendLog("ERROR", j.error || "启动失败");
    showToast((j.error || "启动失败") + "，请先完成启动配置", "err");
    switchView("settings");
    const msg = $("#config-msg");
    if (msg) { msg.textContent = "请先完成启动配置：" + (j.error || "缺少必要配置"); msg.style.color = "var(--red)"; }
    return;
  }
  appendLog("INFO", "已发送启动请求");
  showToast("启动请求已发送，正在启动…", "ok");
  // 标记曾成功发起启动（供新手引导判断），随后刷新引导进度
  localStorage.setItem("shenyi:startedOnce", "1");
  renderGuide();
};
$("#btn-stop").onclick = async () => {
  const r = await fetch("/api/stop", { method: "POST" });
  const j = await r.json();
  if (!j.ok) appendLog("ERROR", j.error || "停止失败");
  await fetchStatus();
};
$("#unified-send").onclick = sendUnifiedInput;
$("#unified-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendUnifiedInput(); });
$("#send-mode").addEventListener("change", updateUnifiedComposer);
$("#chat-identity").addEventListener("change", updateUnifiedComposer);
$("#cmd-identity").addEventListener("change", updateUnifiedComposer);
$("#player-search").addEventListener("input", renderPlayerList);
window.addEventListener("popstate", () => {
  switchView(currentViewFromLocation(), { pushState: false });
});

// ---------- WebSocket ----------
function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    $("#conn-dot").className = "conn-dot ok";
    $("#conn-text").textContent = "已连接";
  };
  ws.onclose = () => {
    $("#conn-dot").className = "conn-dot bad";
    $("#conn-text").textContent = "重连中…";
    setTimeout(connectWs, 2000);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (ev) => {
    let item;
    try { item = JSON.parse(ev.data); } catch (e) { return; }
    if (item.type === "log") {
      appendLog(item.level, item.msg);
    } else if (item.type === "chat") {
      appendChat(item.data);
    } else if (item.type === "status") {
      applyStatus(item.data);
    }
  };
}

// ---------- 初始化 ----------
loadItemMeta();
initServerManager();
syncDifficultyButtons(localStorage.getItem(DIFFICULTY_STORAGE_KEY) || "hard");
updateUnifiedComposer();
fetchStatus();
fetchPlayers();
connectWs();
setInterval(fetchStatus, 5000);
setInterval(fetchPlayers, 5000);
setInterval(loadOperationLog, 10000);

// 新手引导：跳过按钮 + 状态变化时刷新
const guideDismiss = $("#guide-dismiss");
if (guideDismiss) guideDismiss.onclick = () => {
  localStorage.setItem(GUIDE_KEY, "1");
  const card = $("#guide-card");
  if (card) card.style.display = "none";
};
loadConfig().then(() => renderGuide());
renderGuide();

// ============ 插件管理 ============
function pluginNotice(target, text, kind) {
  const box = $(target);
  if (!box) return;
  if (!text) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }
  box.style.display = "";
  box.className = "plugin-notice " + (kind || "info");
  box.innerHTML = text;
}

function pluginResultHtml(j) {
  const message = escapeHtml(j.message || j.error || (j.ok ? "操作完成" : "操作失败"));
  const steps = (j.next_steps || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("");
  const restart = j.needs_restart ? '<div class="restart-warn">需要重启 ToolDelta 后完全生效</div>' : "";
  const actions = j.ok ? '<div class="notice-actions"><button class="mini-btn primary" onclick="switchView(\'plugins\')">去插件管理</button><button class="mini-btn" onclick="loadPlugins(); marketSearch();">刷新插件状态</button></div>' : "";
  return `${restart}<div>${message}</div>${steps ? `<ol>${steps}</ol>` : ""}${actions}`;
}

async function pluginPost(url, noticeTarget, loadingText) {
  pluginNotice(noticeTarget, escapeHtml(loadingText || "正在处理…"), "info");
  try {
    const r = await fetch(url, { method: "POST" });
    const j = await r.json();
    pluginNotice(noticeTarget, pluginResultHtml(j), j.ok ? (j.needs_restart ? "warn" : "ok") : "err");
    if (!j.ok) appendLog("ERROR", j.error || "插件操作失败");
    else appendLog(j.needs_restart ? "WARNING" : "INFO", j.message || "插件操作完成");
    return j;
  } catch (e) {
    pluginNotice(noticeTarget, "请求失败", "err");
    appendLog("ERROR", "插件请求失败");
    return { ok: false, error: "请求失败" };
  }
}

async function loadPlugins() {
  await loadPluginConfigs(false);
  const list = $("#plugin-list");
  if (list) list.innerHTML = '<div class="skeleton-row"></div><div class="skeleton-row"></div><div class="skeleton-row"></div>';
  return fetch("/api/plugins").then(r => r.json()).then(j => {
    list.innerHTML = "";
    const plugins = j.data || [];
    window.PLUGIN_COUNT = plugins.length;
    renderGuide();
    if (!plugins.length) {
      list.innerHTML = '<div class="empty-guide"><strong>还没有安装插件</strong><span>去“市场”页挑一个装上，插件会自动出现在这里。常用的有：Timetable（定时公告）、BedrockTools（基岩工具）等。</span><div class="action-row"><button class="mini-btn primary" onclick="switchView(\'market\')">去市场逛逛</button></div></div>';
      return;
    }
    let idx = 0;
    for (const p of plugins) {
      const cfgs = pluginConfigsFor(p.name);
      const cfgBtn = cfgs.length
        ? `<button class="mini-btn primary" onclick="openPluginConfigFor('${escapeHtml(p.name)}')">配置</button>`
        : '<button class="mini-btn" disabled title="这个插件暂时没有生成可配置文件">暂无配置</button>';
      const div = document.createElement("div");
      div.className = "plugin-item";
      div.style.animationDelay = Math.min(idx++ * 22, 220) + "ms";
      div.innerHTML = `
        <div class="pinfo">
          <div class="pname">${escapeHtml(p.name)} <span class="badge ${p.is_enabled ? 'op' : 'notop'}">${p.is_enabled ? '启用' : '禁用'}</span></div>
          <div class="pmeta">v${escapeHtml(p.version)} · ${escapeHtml(p.author)}${p.is_registered ? '' : ' · <span style="color:var(--yellow)">未登记</span>'}</div>
          <div class="pmeta">${escapeHtml(p.description || '')}</div>
        </div>
        <div class="plugin-actions">
          ${cfgBtn}
          <button class="mini-btn" onclick="togglePlugin('${escapeHtml(p.name)}')">${p.is_enabled ? '禁用' : '启用'}</button>
          ${p.has_update ? `<button class="mini-btn primary" onclick="updatePlugin('${escapeHtml(p.name)}')">更新到 ${p.latest_version ? 'v' + escapeHtml(p.latest_version) : '最新'}</button>` : ''}
          <button class="mini-btn danger" onclick="deletePlugin('${escapeHtml(p.name)}')">删除</button>
        </div>
      `;
      list.appendChild(div);
    }
  });
}

async function togglePlugin(name) {
  await pluginPost(`/api/plugins/${encodeURIComponent(name)}/toggle`, "#plugin-notice", `正在切换 ${name}…`);
  loadPlugins();
  marketSearch();
}
async function deletePlugin(name) {
  if (!(await askConfirm("删除插件", `<p>确认删除插件 <b>${escapeHtml(name)}</b>？</p><p class=\"pmeta\">插件文件会被移除，此操作不可逆。</p>`))) return;
  await pluginPost(`/api/plugins/${encodeURIComponent(name)}/delete`, "#plugin-notice", `正在删除 ${name}…`);
  loadPlugins();
  marketSearch();
}
async function updatePlugin(name) {
  await pluginPost(`/api/plugins/${encodeURIComponent(name)}/update`, "#plugin-notice", `正在更新 ${name}…`);
  loadPlugins();
  marketSearch();
}
$("#plugin-update-all").onclick = async () => {
  await pluginPost("/api/plugins/update_all", "#plugin-notice", "正在检查并更新全部插件…");
  loadPlugins();
  marketSearch();
};

// ============ 插件配置 ============
let pluginConfigItems = [];
let currentPluginConfigPath = "";
let pluginDrawerOpen = false;

function setPluginDrawerOpen(open) {
  pluginDrawerOpen = !!open;
  document.body.classList.toggle("modal-open", pluginDrawerOpen);
  syncOverlayState();
}

function fieldInputHtml(field) {
  const value = field.value ?? "";
  const name = escapeHtml(field.path);
  if (field.type === "bool") {
    return `<select data-config-field="${name}"><option value="true" ${value ? "selected" : ""}>开启</option><option value="false" ${!value ? "selected" : ""}>关闭</option></select>`;
  }
  if (field.type === "list") {
    return `<textarea data-config-field="${name}" rows="4">${escapeHtml(value)}</textarea>`;
  }
  if (field.type === "int" || field.type === "float") {
    return `<input data-config-field="${name}" type="number" value="${escapeHtml(value)}" />`;
  }
  return `<input data-config-field="${name}" type="text" value="${escapeHtml(value)}" />`;
}

async function loadPluginConfigs(renderDrawer) {
  try {
    const r = await fetch("/api/plugin-configs");
    const j = await r.json();
    pluginConfigItems = j.data || [];
    if (renderDrawer && currentPluginConfigPath) await openPluginConfig(currentPluginConfigPath);
  } catch (e) {
    pluginConfigItems = [];
  }
}

function pluginConfigsFor(pluginName) {
  const raw = String(pluginName || "");
  const variants = new Set([
    raw,
    raw.replace(/^前置_/, ""),
    raw.replace(/^前置-/, ""),
    raw.replace(/^前置_?/, ""),
  ]);
  return pluginConfigItems.filter((it) => variants.has(it.plugin) || variants.has(String(it.plugin || "").replace(/^前置_/, "")));
}

async function openPluginConfigFor(pluginName) {
  await loadPluginConfigs(false);
  const cfgs = pluginConfigsFor(pluginName);
  const drawer = $("#plugin-config-drawer");
  const title = $("#plugin-config-title");
  const box = $("#plugin-config-form");
  if (!drawer || !box) return;
  drawer.style.display = "grid";
  setPluginDrawerOpen(true);
  title.textContent = `${pluginName} · 插件配置`;
  if (!cfgs.length) {
    currentPluginConfigPath = "";
    box.innerHTML = '<div class="empty-guide"><strong>暂无配置项</strong><span>这个插件还没有生成配置文件。通常需要启动一次 ToolDelta，或者插件首次运行后才会生成。</span></div>';
    return;
  }
  if (cfgs.length > 1) {
    box.innerHTML = `<div class="config-file-tabs">${cfgs.map((it) => `<button class="mini-btn ${it.path === currentPluginConfigPath ? 'primary' : ''}" data-config-path="${escapeHtml(it.path)}">${escapeHtml(it.name)}</button>`).join("")}</div><div id="plugin-config-inner"></div>`;
    box.querySelectorAll("[data-config-path]").forEach((b) => {
      b.onclick = () => openPluginConfig(b.dataset.configPath);
    });
  }
  await openPluginConfig(cfgs[0].path);
}

async function openPluginConfig(path) {
  currentPluginConfigPath = path;
  $$("#plugin-config-form [data-config-path]").forEach((b) => b.classList.toggle("primary", b.dataset.configPath === path));
  const box = $("#plugin-config-inner") || $("#plugin-config-form");
  box.innerHTML = '<div class="pmeta">正在读取配置项…</div>';
  try {
    const r = await fetch("/api/plugin-configs/read?path=" + encodeURIComponent(path));
    const j = await r.json();
    if (!j.ok) { box.innerHTML = `<div class="cmd-err">${escapeHtml(j.error)}</div>`; return; }
    const cfg = j.data;
    if (!cfg.fields.length) {
      box.innerHTML = '<div class="empty-guide"><strong>没有可表单化的配置项</strong><span>这个配置可能是复杂列表或特殊格式，暂时不适合给小白直接改。</span></div>';
      return;
    }
    let currentGroup = "";
    let html = `<div class="config-form-head"><div><strong>${escapeHtml(cfg.plugin)}</strong><span>${escapeHtml(cfg.name)}</span></div><button class="btn" onclick="savePluginConfig()">保存配置</button></div>`;
    html += '<div class="plugin-field-grid">';
    for (const field of cfg.fields) {
      const group = field.group || field.path.split(".").slice(0, -1).join(".");
      if (group && group !== currentGroup) {
        currentGroup = group;
        html += `<div class="field-group-title">${escapeHtml(group)}</div>`;
      }
      html += `
        <label class="plugin-field">
          <span>${escapeHtml(field.label || field.path)}</span>
          ${fieldInputHtml(field)}
          ${field.hint ? `<small>${escapeHtml(field.hint)}</small>` : ""}
        </label>
      `;
    }
    html += '</div><div class="plugin-notice" id="plugin-config-notice" style="display:none"></div>';
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = '<div class="cmd-err">读取配置失败</div>';
  }
}

async function savePluginConfig() {
  const values = {};
  $$("[data-config-field]").forEach((el) => {
    values[el.dataset.configField] = el.value;
  });
  pluginNotice("#plugin-config-notice", "正在保存配置…", "info");
  try {
    const r = await fetch("/api/plugin-configs/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: currentPluginConfigPath, values }),
    });
    const j = await r.json();
    pluginNotice("#plugin-config-notice", pluginResultHtml(j), j.ok ? "warn" : "err");
  } catch (e) {
    pluginNotice("#plugin-config-notice", "保存失败", "err");
  }
}

$("#plugin-config-close").onclick = () => {
  $("#plugin-config-drawer").style.display = "none";
  setPluginDrawerOpen(false);
};
$("#plugin-config-drawer").addEventListener("click", (e) => {
  if (e.target.id === "plugin-config-drawer") {
    $("#plugin-config-drawer").style.display = "none";
    setPluginDrawerOpen(false);
  }
});

// ============ 插件市场 ============
let marketItems = [];
let marketPage = 0;
const MARKET_PAGE_SIZE = 20;

function marketSearch() {
  const rule = $("#market-rule").value;
  const kw = $("#market-kw").value;
  marketPage = 0;
  const list = $("#market-list");
  if (list) list.innerHTML = '<div class="skeleton-row"></div><div class="skeleton-row"></div><div class="skeleton-row"></div>';
  fetch(`/api/market/search?rule=${rule}&kw=${encodeURIComponent(kw)}`).then(r => r.json()).then(j => {
    marketItems = j.data || [];
    renderMarketPage();
  });
}

function renderMarketPage() {
  const list = $("#market-list");
  const pager = $("#market-pager");
  list.innerHTML = "";
  if (!marketItems.length) {
    const kw = ($("#market-kw")?.value || "").trim();
    if (kw) {
      list.innerHTML = '<div class="empty-guide"><strong>没有找到相关插件</strong><span>换个关键词，或清空搜索随便逛逛。</span></div>';
    } else {
      list.innerHTML = '<div class="empty-guide"><strong>市场暂时没有可安装的插件</strong><span>可能是市场源暂时不可用。你可以稍后重试，或先看看“插件”页已有的插件。</span></div>';
    }
    pager.innerHTML = "";
    return;
  }
  const totalPages = Math.ceil(marketItems.length / MARKET_PAGE_SIZE);
  if (marketPage >= totalPages) marketPage = totalPages - 1;
  if (marketPage < 0) marketPage = 0;
  const start = marketPage * MARKET_PAGE_SIZE;
  const pageItems = marketItems.slice(start, start + MARKET_PAGE_SIZE);
  let idx = 0;
  for (const it of pageItems) {
    const div = document.createElement("div");
    div.className = "market-item";
    div.style.animationDelay = Math.min(idx++ * 24, 240) + "ms";
    let installedBadge = "";
    if (it.is_package) {
      if (it.is_installed) installedBadge = '<span class="badge op" style="margin-left:6px">已安装</span>';
      else if (it.is_partial_installed) installedBadge = `<span class="badge notop" style="margin-left:6px">部分安装 ${it.installed_count}/${it.total_count}</span>`;
    } else if (it.is_installed) {
      installedBadge = '<span class="badge op" style="margin-left:6px">已安装</span>';
    }
    div.innerHTML = `
      <div class="pinfo">
        <div class="pname">${it.is_package ? '<span class="pkg-tag">[整合包]</span> ' : ''}${escapeHtml(it.is_package ? it.name.replace(/^\[pkg\]/, '') : it.name)}${installedBadge}</div>
        <div class="pmeta">${it.version ? 'v' + escapeHtml(it.version) + ' · ' : ''}${escapeHtml(it.author)}${it.is_package && it.total_count ? ' · ' + it.installed_count + '/' + it.total_count + ' 已安装' : ''}</div>
      </div>
    `;
    div.onclick = () => it.is_package ? marketPackageDetail(it.id) : marketPluginDetail(it.id);
    list.appendChild(div);
  }
  // 分页器
  let ph = `<button ${marketPage === 0 ? 'disabled' : ''} onclick="gotoMarketPage(${marketPage - 1})">‹ 上一页</button>`;
  ph += `<span class="pg-cur">${marketPage + 1} / ${totalPages}</span>`;
  ph += `<button ${marketPage >= totalPages - 1 ? 'disabled' : ''} onclick="gotoMarketPage(${marketPage + 1})">下一页 ›</button>`;
  ph += `<span style="margin-left:8px">共 ${marketItems.length} 个</span>`;
  pager.innerHTML = ph;
}

function gotoMarketPage(p) {
  marketPage = p;
  renderMarketPage();
  $("#market-list").scrollTop = 0;
}

$("#market-search").onclick = marketSearch;
$("#market-kw").addEventListener("keydown", (e) => { if (e.key === "Enter") marketSearch(); });

async function marketPluginDetail(pluginId) {
  const r = await fetch(`/api/market/plugin/${encodeURIComponent(pluginId)}`);
  const j = await r.json();
  const panel = $("#market-detail-panel");
  const box = $("#market-detail");
  const title = $("#market-detail-title");
  if (title) title.textContent = "插件详情";
  if (!j.ok) { panel.style.display = "grid"; box.innerHTML = `<div class="cmd-err">${escapeHtml(j.error)}</div>`; syncOverlayState(); return; }
  const p = j.data;
  panel.style.display = "grid";
  syncOverlayState();
  const dlBtn = p.is_installed
    ? '<button class="mini-btn primary" onclick="downloadPlugin(\'' + escapeHtml(p.plugin_id) + '\')">重新下载</button>'
    : '<button class="mini-btn primary" onclick="downloadPlugin(\'' + escapeHtml(p.plugin_id) + '\')">下载安装</button>';
  const installedBadge = p.is_installed ? '<span class="badge op">已安装</span>' : '';
  box.innerHTML = `
    <div class="kv">
      <div class="k">名称</div><div>${escapeHtml(p.name)} ${installedBadge}</div>
      <div class="k">版本</div><div>${escapeHtml(p.version)}</div>
      <div class="k">作者</div><div>${escapeHtml(p.author)}</div>
      <div class="k">类型</div><div>${escapeHtml(p.plugin_type_str)}</div>
      <div class="k">前置插件</div><div>${escapeHtml(Object.entries(p.pre_plugins || {}).map(([k,v]) => k + ' v' + v).join(', ') || '无')}</div>
      <div class="k">介绍</div><div>${escapeHtml(p.description || '无')}</div>
    </div>
    <div class="market-actions" style="margin-top:10px">
      ${dlBtn}
      ${p.has_doc ? `<button class="mini-btn" onclick="viewMarketDoc('${escapeHtml(p.plugin_id)}')">查看文档</button>` : ''}
    </div>
  `;
}

async function marketPackageDetail(pkgId) {
  const r = await fetch(`/api/market/package/${encodeURIComponent(pkgId)}`);
  const j = await r.json();
  const panel = $("#market-detail-panel");
  const box = $("#market-detail");
  const title = $("#market-detail-title");
  if (title) title.textContent = "整合包详情";
  panel.style.display = "grid";
  syncOverlayState();
  if (!j.ok) { box.innerHTML = `<div class="cmd-err">${escapeHtml(j.error)}</div>`; return; }
  const p = j.data;
  const statusBadge = p.is_installed
    ? '<span class="badge op">已安装</span>'
    : (p.is_partial_installed ? `<span class="badge notop">部分安装 ${p.installed_count}/${p.total_count}</span>` : '<span class="badge notop">未安装</span>');
  const missing = (p.missing_plugins || []).map((it) => escapeHtml(it.name || it.id)).join("、") || "无";
  const installed = (p.installed_plugins || []).map((it) => escapeHtml(it.name || it.id)).join("、") || "无";
  const btnText = p.is_installed ? "重新下载整合包" : (p.is_partial_installed ? "补全整合包" : "下载安装整合包");
  box.innerHTML = `
    <div class="kv">
      <div class="k">整合包</div><div>${escapeHtml(p.name.replace(/^\[pkg\]/, ''))} ${statusBadge}</div>
      <div class="k">版本</div><div>${escapeHtml(p.version || '')}</div>
      <div class="k">作者</div><div>${escapeHtml(p.author || '')}</div>
      <div class="k">安装进度</div><div>${p.installed_count}/${p.total_count}</div>
      <div class="k">已安装</div><div>${installed}</div>
      <div class="k">未安装</div><div>${missing}</div>
      <div class="k">介绍</div><div>${escapeHtml(p.description || '无')}</div>
    </div>
    <div class="market-actions" style="margin-top:10px">
      <button class="mini-btn primary" onclick="downloadPackage('${escapeHtml(pkgId)}')">${btnText}</button>
    </div>
  `;
}

async function downloadPlugin(pluginId) {
  pluginNotice("#market-notice", "正在下载插件和前置依赖…", "info");
  const r = await fetch("/api/market/download_plugin", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plugin_id: pluginId }) });
  const j = await r.json();
  pluginNotice("#market-notice", pluginResultHtml(j), j.ok ? (j.needs_restart ? "warn" : "ok") : "err");
  if (j.ok) {
    await loadPlugins();
    marketSearch();
  } else {
    appendLog("ERROR", j.error || "插件下载失败");
  }
}
async function downloadPackage(pkgId) {
  pluginNotice("#market-notice", "正在下载整合包、配置和插件数据…", "info");
  const r = await fetch("/api/market/download_package", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pkg_id: pkgId }) });
  const j = await r.json();
  pluginNotice("#market-notice", pluginResultHtml(j), j.ok ? (j.needs_restart ? "warn" : "ok") : "err");
  if (j.ok) {
    await loadPlugins();
    marketSearch();
  } else {
    appendLog("ERROR", j.error || "整合包下载失败");
  }
}

async function viewMarketDoc(pluginId) {
  const r = await fetch("/api/market/doc/" + encodeURIComponent(pluginId));
  const j = await r.json();
  if (!j.ok) { showToast(j.error || "文档加载失败", "err"); return; }
  const panel = $("#market-detail-panel");
  const box = $("#market-detail");
  const title = $("#market-detail-title");
  if (title) title.textContent = "插件文档";
  panel.style.display = "grid";
  syncOverlayState();
  box.innerHTML = `<pre style="white-space:pre-wrap;word-break:break-all">${escapeHtml(j.content)}</pre>`;
}

// ============ 启动配置 ============
// CONFIG_SCHEMA / CONFIG_DATA 已在文件前部全局声明

function findLauncher(index) {
  return CONFIG_SCHEMA.find((l) => l.index === index) || null;
}

async function loadConfig() {
  const [s, c] = await Promise.all([
    fetch("/api/config/schema").then(r => r.json()),
    fetch("/api/config").then(r => r.json()),
  ]);
  const raw = s.data || [];
  CONFIG_SCHEMA = raw.slice().sort((a, b) => a.index - b.index);
  CONFIG_DATA = c.data || {};
  renderConfigForm();
}

function renderConfigForm() {
  const form = $("#config-form");
  const d = CONFIG_DATA;
  const launchMode = d.launch_mode || 0;
  let html = '<div class="fgroup"><label>启动器（选择后下方显示对应配置项）</label><select id="cfg-launcher" onchange="onLauncherChange()">';
  html += '<option value="0">' + (launchMode === 0 ? '（当前：交互选择）' : '启动时交互选择') + '</option>';
  for (const l of CONFIG_SCHEMA) {
    const rec = l.recommended ? ' 推荐' : '';
    const sel = launchMode === l.index ? 'selected' : '';
    html += `<option value="${l.index}" ${sel}>${l.index}. ${escapeHtml(l.name)} — ${escapeHtml(l.desc)}${rec}</option>`;
  }
  html += '</select></div>';

  html += '<div class="frow">';
  html += '<div class="fgroup"><label>记录日志</label><select id="cfg-log"><option value="1" ' + (d.record_log ? 'selected' : '') + '>开启</option><option value="0" ' + (!d.record_log ? 'selected' : '') + '>关闭</option></select></div>';
  html += '<div class="fgroup"><label>全局 GitHub 镜像（留空则启动时自动测速选择）</label><input id="cfg-mirror" value="' + escapeHtml(d.github_mirror || '') + '" placeholder="https://github.tooldelta.top" /></div>';
  html += '</div>';
  html += '<div class="fgroup"><label>插件市场源（留空=默认官方）</label><input id="cfg-market" value="' + escapeHtml(d.plugin_market || '') + '" placeholder="https://pm.tooldelta.top" /></div>';

  if (launchMode >= 1 && launchMode <= CONFIG_SCHEMA.length) {
    const meta = findLauncher(launchMode);
    if (!meta) return;
    html += `<h4>${escapeHtml(meta.name)} 专属配置</h4>`;
    const seg = d.current_section || {};

    if (!meta.fields.length) {
      html += '<div class="pmeta">该启动器无需额外配置。</div>';
    }
    let first = true;
    for (const f of meta.fields) {
      if (first) { html += '<div class="frow">'; first = false; }
      html += `<div class="fgroup"><label>${escapeHtml(f.label)}</label><input id="seg-${escapeHtml(f.k)}" type="${f.type}" value="${escapeHtml(seg[f.k] || '')}" /></div>`;
    }
    if (!first) html += '</div>';
    html += '<h4>验证凭证</h4>';
    html += '<div class="fgroup"><label>fbtoken（原版验证需填写）</label><input id="cfg-fbtoken" value="' + escapeHtml(d.fbtoken || '') + '" placeholder="粘贴 fbtoken…" /></div>';
  }

  form.innerHTML = html;
}

function onLauncherChange() {
  const v = parseInt($("#cfg-launcher").value);
  CONFIG_DATA.launch_mode = v;
  renderConfigForm();
}

$("#config-save").onclick = async () => {
  const launchMode = parseInt($("#cfg-launcher").value);
  const fbtokenEl = $("#cfg-fbtoken");
  const payload = {
    launch_mode: launchMode,
    record_log: $("#cfg-log").value === "1",
    github_mirror: $("#cfg-mirror").value.trim(),
    plugin_market: $("#cfg-market").value.trim(),
    section: {},
    fbtoken: fbtokenEl ? fbtokenEl.value.trim() : "",
  };
  if (launchMode >= 1 && launchMode <= CONFIG_SCHEMA.length) {
    const meta = findLauncher(launchMode);
    if (meta) {
      for (const f of meta.fields) {
        const el = document.getElementById(`seg-${f.k}`);
        if (el) payload.section[f.k] = el.value.trim();
      }
    }
  }
  const r = await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const j = await r.json();
  const msg = $("#config-msg");
  if (j.ok) { msg.textContent = "已保存"; msg.style.color = "var(--green)"; CONFIG_DATA = j.data; renderConfigForm(); }
  else { msg.textContent = j.error || "保存失败"; msg.style.color = "var(--red)"; }
};

// ============ 文件管理 ============
let currentDir = "";
let editingPath = null;
let filePage = 1;
const FILE_PAGE_SIZE = 100;

function fmtSize(n) {
  if (n == null) return "—";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

function renderCrumb(path) {
  const segs = (path || "").split("/").filter(Boolean);
  let html = '<span class="crumb-seg" onclick="loadFiles(\'\')">根目录</span>';
  let acc = "";
  for (const s of segs) {
    acc = acc ? acc + "/" + s : s;
    html += `<span class="crumb-sep">/</span><span class="crumb-seg" onclick="loadFiles('${escapeHtml(acc)}')">${escapeHtml(s)}</span>`;
  }
  $("#file-crumb").innerHTML = html;
}

async function loadFiles(path) {
  currentDir = path || "";
  filePage = 1;
  renderCrumb(currentDir);
  $("#file-editor-panel").style.display = "none";
  editingPath = null;
  syncOverlayState();
  const r = await fetch("/api/files?path=" + encodeURIComponent(currentDir) + "&page=1&page_size=" + FILE_PAGE_SIZE);
  const j = await r.json();
  const list = $("#file-list");
  list.innerHTML = "";
  if (!j.ok) { list.innerHTML = `<div class="cmd-err">${escapeHtml(j.error)}</div>`; $("#file-pager").innerHTML = ""; return; }
  const entries = j.data.entries || [];
  if (currentDir) {
    const parent = currentDir.split("/").slice(0, -1).join("/");
    const row = document.createElement("div");
    row.className = "file-row";
    row.innerHTML = `<span class="fname">目录 ..</span>`;
    row.onclick = () => loadFiles(parent);
    list.appendChild(row);
  }
  for (const e of entries) {
    const row = document.createElement("div");
    row.className = "file-row";
    const icon = e.is_dir ? "目录" : "文件";
    row.innerHTML = `
      <span>${icon}</span>
      <span class="fname">${escapeHtml(e.name)}</span>
      <span class="fmeta">${e.is_dir ? '' : fmtSize(e.size)}</span>
      <span class="fop">
        ${!e.is_dir && isZipFile(e.name) ? `<button class="mini-btn" onclick="event.stopPropagation();extractZip('${escapeHtml(currentDir ? currentDir + '/' + e.name : e.name)}')">解压</button>` : ''}
        ${!e.is_dir ? `<button class="mini-btn" onclick="event.stopPropagation();editFile('${escapeHtml(currentDir ? currentDir + '/' + e.name : e.name)}')">编辑</button>` : ''}
        <button class="mini-btn danger" onclick="event.stopPropagation();delFile('${escapeHtml(currentDir ? currentDir + '/' + e.name : e.name)}')">删除</button>
      </span>
    `;
    row.onclick = () => e.is_dir ? loadFiles(currentDir ? currentDir + "/" + e.name : e.name) : readFileView(currentDir ? currentDir + "/" + e.name : e.name);
    list.appendChild(row);
  }
  if (!(j.data.entries || []).length && currentDir) {
    const empty = document.createElement("div");
    empty.className = "empty-guide";
    empty.innerHTML = `<strong>这个文件夹还是空的</strong><span>可以点右上角“上传”把文件或压缩包传进来；zip 压缩包上传后会出现“解压”按钮。</span>`;
    list.appendChild(empty);
  }
  renderFilePager(j.data);
}

function renderFilePager(data) {
  const pager = $("#file-pager");
  const total = data.total || 0;
  const totalPages = data.total_pages || 1;
  const page = data.page || 1;
  if (total <= FILE_PAGE_SIZE) { pager.innerHTML = ""; return; }
  let ph = `<button ${page === 1 ? 'disabled' : ''} onclick="gotoFilePage(${page - 1})">‹ 上一页</button>`;
  ph += `<span class="pg-cur">${page} / ${totalPages}</span>`;
  ph += `<button ${page >= totalPages ? 'disabled' : ''} onclick="gotoFilePage(${page + 1})">下一页 ›</button>`;
  ph += `<span style="margin-left:8px">共 ${total} 项</span>`;
  pager.innerHTML = ph;
}

async function gotoFilePage(p) {
  filePage = p;
  const r = await fetch("/api/files?path=" + encodeURIComponent(currentDir) + "&page=" + p + "&page_size=" + FILE_PAGE_SIZE);
  const j = await r.json();
  if (!j.ok) return;
  const list = $("#file-list");
  list.innerHTML = "";
  if (currentDir) {
    const parent = currentDir.split("/").slice(0, -1).join("/");
    const row = document.createElement("div");
    row.className = "file-row";
    row.innerHTML = `<span class="fname">目录 ..</span>`;
    row.onclick = () => loadFiles(parent);
    list.appendChild(row);
  }
  for (const e of (j.data.entries || [])) {
    const row = document.createElement("div");
    row.className = "file-row";
    const icon = e.is_dir ? "目录" : "文件";
    row.innerHTML = `
      <span>${icon}</span>
      <span class="fname">${escapeHtml(e.name)}</span>
      <span class="fmeta">${e.is_dir ? '' : fmtSize(e.size)}</span>
      <span class="fop">
        ${!e.is_dir && isZipFile(e.name) ? `<button class="mini-btn" onclick="event.stopPropagation();extractZip('${escapeHtml(currentDir ? currentDir + '/' + e.name : e.name)}')">解压</button>` : ''}
        ${!e.is_dir ? `<button class="mini-btn" onclick="event.stopPropagation();editFile('${escapeHtml(currentDir ? currentDir + '/' + e.name : e.name)}')">编辑</button>` : ''}
        <button class="mini-btn danger" onclick="event.stopPropagation();delFile('${escapeHtml(currentDir ? currentDir + '/' + e.name : e.name)}')">删除</button>
      </span>
    `;
    row.onclick = () => e.is_dir ? loadFiles(currentDir ? currentDir + "/" + e.name : e.name) : readFileView(currentDir ? currentDir + "/" + e.name : e.name);
    list.appendChild(row);
  }
  if (!(j.data.entries || []).length && currentDir) {
    const empty = document.createElement("div");
    empty.className = "empty-guide";
    empty.innerHTML = `<strong>这个文件夹还是空的</strong><span>可以点右上角“上传”把文件或压缩包传进来；zip 压缩包上传后会出现“解压”按钮。</span>`;
    list.appendChild(empty);
  }
  renderFilePager(j.data);
}

async function readFileView(path) {
  const r = await fetch("/api/files/read?path=" + encodeURIComponent(path));
  const j = await r.json();
  const panel = $("#file-editor-panel");
  panel.style.display = "";
  syncOverlayState();
  $("#file-editor-name").textContent = path;
  const box = $("#file-editor");
  if (!j.ok) { box.innerHTML = `<div class="cmd-err">${escapeHtml(j.error)}</div>`; return; }
  if (j.data.is_binary) {
    box.innerHTML = `<div class="pmeta">二进制文件（${fmtSize(j.data.size)}），不支持在线编辑。Base64 预览：</div><pre style="white-space:pre-wrap;word-break:break-all;font-size:11px">${escapeHtml(j.data.content.slice(0, 4000))}</pre>`;
    $("#file-save").style.display = "none";
  } else {
    box.innerHTML = `<textarea id="file-content"></textarea>`;
    $("#file-content").value = j.data.content || "";
    $("#file-save").style.display = "";
    editingPath = path;
  }
}

function editFile(path) { readFileView(path); }

$("#file-save").onclick = async () => {
  if (!editingPath) return;
  const content = $("#file-content").value;
  const r = await fetch("/api/files/write", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: editingPath, content }) });
  const j = await r.json();
  if (j.ok) {
    showToast("已保存", "ok");
    loadFiles(currentDir);
  } else {
    showToast(j.error || "保存失败", "err");
  }
};

$("#file-close").onclick = () => {
  $("#file-editor-panel").style.display = "none";
  editingPath = null;
  syncOverlayState();
};

$("#market-detail-close").onclick = () => {
  $("#market-detail-panel").style.display = "none";
  syncOverlayState();
};

async function delFile(path) {
  if (!(await askConfirm("删除文件", `<p>确认删除 <b>${escapeHtml(path)}</b>？</p><p class=\"pmeta\">删除后无法恢复。</p>`))) return;
  const r = await fetch("/api/files/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
  const j = await r.json();
  if (!j.ok) { showToast(j.error || "删除失败", "err"); }
  else showToast("已删除 " + path.split("/").pop(), "ok");
  loadFiles(currentDir);
}

function isZipFile(name) {
  return /\.[zZ][iI][pP]$/.test(name || "");
}

async function extractZip(path) {
  if (!(await askConfirm("解压压缩包", `<p>确认把 <b>${escapeHtml(path.split("/").pop())}</b> 解压到当前文件夹？</p><p class=\"pmeta\">如有同名文件会被覆盖。</p>`))) return;
  const r = await fetch("/api/files/extract", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
  const j = await r.json();
  if (!j.ok) { showToast(j.error || "解压失败", "err"); }
  else showToast("解压完成，共 " + (j.data ? j.data.extracted : 0) + " 个文件", "ok");
  loadFiles(currentDir);
}

function uploadFiles(files) {
  if (!files || !files.length) return;
  if (!currentDir) {
    showToast("请先进入具体文件夹再上传（如：插件文件）", "warn");
    loadFiles("");
    return;
  }
  const fd = new FormData();
  fd.append("path", currentDir);
  let total = 0;
  for (const f of files) {
    fd.append("files", f, f.name);
    total += f.size || 0;
  }
  showToast("正在上传 " + files.length + " 个文件…", "info");
  fetch("/api/files/upload", { method: "POST", body: fd })
    .then((r) => r.json())
    .then((j) => {
      if (j.ok) {
        const n = (j.uploaded || []).length;
        showToast("上传成功 " + n + " 个文件" + (j.errors && j.errors.length ? "，" + j.errors.length + " 个失败" : ""), "ok");
        if (j.errors && j.errors.length) showToast(j.errors[0], "warn");
      } else {
        showToast(j.error || "上传失败", "err");
      }
      loadFiles(currentDir);
    })
    .catch(() => {
      showToast("上传失败：网络错误", "err");
    });
}

$("#file-upload-btn").onclick = () => $("#file-upload-input").click();
$("#file-upload-input").onchange = (e) => {
  uploadFiles(e.target.files);
  e.target.value = "";
};

$("#file-new-file").onclick = async () => {
  const res = await askPrompt("新建文件", [
    { key: "name", label: "文件名（如 xxx.json）", value: "", placeholder: "输入文件名", autofocus: true },
  ]);
  if (!res || !res.name) return;
  const name = res.name;
  const path = currentDir ? currentDir + "/" + name : name;
  const r = await fetch("/api/files/write", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, content: "" }) });
  const j = await r.json();
  if (!j.ok) { showToast(j.error || "创建失败", "err"); }
  else showToast("已创建 " + name, "ok");
  loadFiles(currentDir);
  if (j.ok) editFile(path);
};

$("#file-new-dir").onclick = async () => {
  const res = await askPrompt("新建目录", [
    { key: "name", label: "目录名", value: "", placeholder: "输入目录名", autofocus: true },
  ]);
  if (!res || !res.name) return;
  const name = res.name;
  const path = currentDir ? currentDir + "/" + name : name;
  const r = await fetch("/api/files/mkdir", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
  const j = await r.json();
  if (!j.ok) { showToast(j.error || "创建失败", "err"); }
  else showToast("已创建目录 " + name, "ok");
  loadFiles(currentDir);
};

const initialView = currentViewFromLocation();
switchView(initialView, { pushState: false });
