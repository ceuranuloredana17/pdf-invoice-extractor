"use strict";

// All user-controlled text (file names, extracted fields) is inserted with
// textContent, never innerHTML, so a malicious PDF cannot inject markup.

const $ = (selector) => document.querySelector(selector);

const dropzone = $("#dropzone");
const fileInput = $("#file-input");
const demoButton = $("#demo-btn");
const statusEl = $("#status");
const resultsEl = $("#results");
const cardsEl = $("#cards");
const template = $("#card-template");

let lastFiles = [];
let lastResults = [];

const FIELDS = [
  ["invoice_number", "Invoice no."],
  ["vendor", "Vendor"],
  ["customer", "Customer"],
  ["invoice_date", "Issue date"],
  ["due_date", "Due date"],
  ["currency", "Currency"],
  ["subtotal", "Subtotal", "money"],
  ["tax", "Tax", "money"],
  ["previous_balance", "Previous balance", "money", { optional: true }],
  ["total", "Total", "money"],
];

// ---------------------------------------------------------------- upload

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  handleFiles([...event.dataTransfer.files]);
});
fileInput.addEventListener("change", () => {
  handleFiles([...fileInput.files]);
  fileInput.value = ""; // allow re-selecting the same file
});

demoButton.addEventListener("click", async () => {
  setBusy(true, "Loading demo invoices…");
  try {
    const names = await fetchJson("/api/samples");
    const files = await Promise.all(names.map(async (name) => {
      const response = await fetch(`/static/samples/${encodeURIComponent(name)}`);
      return new File([await response.blob()], name, { type: "application/pdf" });
    }));
    await handleFiles(files);
  } catch (error) {
    setBusy(false, error.message);
  }
});

async function handleFiles(files) {
  const pdfs = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"));
  if (pdfs.length === 0) {
    statusEl.textContent = "Please choose PDF files.";
    return;
  }
  setBusy(true, `Extracting ${pdfs.length} file(s)…`);
  try {
    const results = await postFiles(pdfs, "json");
    lastFiles = pdfs;
    lastResults = results;
    render(results);
    setBusy(false, "");
  } catch (error) {
    setBusy(false, error.message);
  }
}

async function postFiles(files, format) {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  const response = await fetch(`/api/extract?format=${format}`, { method: "POST", body });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(typeof detail.detail === "string" ? detail.detail : `Request failed (${response.status})`);
  }
  return format === "json" ? response.json() : response.blob();
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

function setBusy(busy, message) {
  demoButton.disabled = busy;
  statusEl.textContent = message;
}

// --------------------------------------------------------------- results

function render(results) {
  const valid = results.filter((r) => r.valid).length;
  const unreadable = results.filter((r) => r.error).length;
  const review = results.length - valid - unreadable;
  const parts = [`<strong>${results.length}</strong> processed`, `${valid} valid`];
  if (review) parts.push(`${review} need review`);
  if (unreadable) parts.push(`${unreadable} unreadable`);
  $("#summary-text").innerHTML = parts.join(" · "); // numbers only, safe

  cardsEl.replaceChildren(...results.map(renderCard));
  resultsEl.hidden = false;
  resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderCard(result) {
  const card = template.content.firstElementChild.cloneNode(true);
  const invoice = result.invoice;

  card.querySelector(".file-name").textContent = result.source;
  const badge = card.querySelector(".badge");
  if (result.error) setBadge(badge, "failed", "Unreadable");
  else if (result.valid) setBadge(badge, "ok", "Valid");
  else setBadge(badge, "review", "Needs review");

  const confidence = invoice ? invoice.confidence : 0;
  card.querySelector(".meter-fill").style.width = `${confidence * 100}%`;
  card.querySelector(".confidence-value").textContent = `${Math.round(confidence * 100)}%`;
  card.querySelector(".error").textContent = result.error || "";

  if (invoice) {
    const fields = card.querySelector(".fields");
    for (const [key, label, kind, options] of FIELDS) {
      if (options?.optional && invoice[key] === null) continue;
      fields.append(renderField(key, label, kind, invoice));
    }
    const tbody = card.querySelector("tbody");
    for (const item of invoice.line_items) {
      const row = document.createElement("tr");
      row.append(
        cell(item.description),
        cell(formatNumber(item.quantity), "num"),
        cell(formatMoney(item.unit_price, invoice.currency), "num"),
        cell(formatMoney(item.amount, invoice.currency), "num"),
      );
      tbody.append(row);
    }
  }

  const issues = card.querySelector(".issues");
  for (const issue of result.issues) {
    const li = document.createElement("li");
    li.className = issue.severity;
    li.textContent = issue.message;
    issues.append(li);
  }
  return card;
}

function renderField(key, label, kind, invoice) {
  const wrapper = document.createElement("div");
  if (key === "total") wrapper.className = "total";
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = label;

  let value = invoice[key];
  if (value !== null && kind === "money") value = formatMoney(value, invoice.currency);
  if (key === "tax" && invoice.tax_rate !== null && value !== null) value += ` (${invoice.tax_rate}%)`;
  if (value === null) {
    dd.textContent = "not found";
    dd.className = "missing";
  } else {
    dd.textContent = value;
  }
  wrapper.append(dt, dd);
  return wrapper;
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function setBadge(badge, kind, text) {
  badge.classList.add(kind);
  badge.textContent = text;
}

// Amounts arrive as decimal strings ("1234.50") to avoid float rounding.
function formatMoney(value, currency) {
  if (value === null) return "";
  const number = Number(value);
  if (!currency) return number.toLocaleString(undefined, { minimumFractionDigits: 2 });
  try {
    return number.toLocaleString(undefined, { style: "currency", currency });
  } catch {
    return `${number.toFixed(2)} ${currency}`;
  }
}

function formatNumber(value) {
  return Number(value).toLocaleString();
}

// ------------------------------------------------------------- downloads

$("#dl-json").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(lastResults, null, 2)], { type: "application/json" });
  download(blob, "invoices.json");
});

$("#dl-csv").addEventListener("click", async () => {
  try {
    download(await postFiles(lastFiles, "csv"), "invoices.csv");
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  URL.revokeObjectURL(url);
}
