const API_BASE = "/api/v1/ui";
const POLL_INTERVAL_MS = 2000;
const LINKEDIN_URL_RE = /^https?:\/\/(www\.)?linkedin\.com\/in\/[\w-]+\/?$/i;

const urlsInput = document.getElementById("profile-urls");
const scrapeBtn = document.getElementById("scrape-btn");
const inputError = document.getElementById("input-error");
const progressSection = document.getElementById("progress-section");
const progressList = document.getElementById("progress-list");
const resultsSection = document.getElementById("results-section");
const resultsContainer = document.getElementById("results");

function normalizeUrl(url) {
  let normalized = url.trim();
  if (normalized.endsWith("/")) {
    normalized = normalized.slice(0, -1);
  }
  return normalized;
}

function parseUrls(raw) {
  return raw
    .split(",")
    .map((part) => normalizeUrl(part))
    .filter(Boolean);
}

function validateUrls(urls) {
  const invalid = urls.filter((url) => !LINKEDIN_URL_RE.test(url));
  return invalid;
}

function formatDateRange(dates) {
  if (!dates) return "";

  const fmt = (d) => {
    if (!d) return null;
    if (d.month) {
      return new Date(d.year, d.month - 1).toLocaleDateString(undefined, {
        month: "short",
        year: "numeric",
      });
    }
    return String(d.year);
  };

  const start = fmt(dates.start);
  const end = dates.is_current ? "Present" : fmt(dates.end);
  if (start && end) return `${start} – ${end}`;
  if (start) return `${start} – Present`;
  return end || "";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function setProgress(url, status, label) {
  const item = document.querySelector(`[data-url="${CSS.escape(url)}"]`);
  if (!item) return;
  const badge = item.querySelector(".status-badge");
  badge.textContent = label || status;
  badge.className = `status-badge status-${status}`;
}

function renderErrorCard(url, message) {
  const card = document.createElement("article");
  card.className = "profile-card error-card";
  card.innerHTML = `
    <div class="error-message">
      <strong>Failed: ${escapeHtml(url)}</strong>
      <span>${escapeHtml(message)}</span>
    </div>
  `;
  return card;
}

function renderProfileCard(data) {
  const profile = data.profile || {};
  const name = profile.full_name || [profile.first_name, profile.last_name].filter(Boolean).join(" ") || "Unknown";
  const location = profile.location?.name || profile.location?.country || "";
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const card = document.createElement("article");
  card.className = "profile-card";

  const bannerStyle = profile.background_image_url
    ? `style="background-image: url('${escapeHtml(profile.background_image_url)}')"`
    : "";

  const avatarHtml = profile.profile_image_url
    ? `<img class="avatar" src="${escapeHtml(profile.profile_image_url)}" alt="${escapeHtml(name)}" />`
    : `<div class="avatar avatar-placeholder">${escapeHtml(initials)}</div>`;

  card.innerHTML = `
    <div class="card-banner" ${bannerStyle}></div>
    <div class="card-header">
      ${avatarHtml}
      <div class="header-text">
        <h3>${escapeHtml(name)}</h3>
        ${profile.headline ? `<p class="headline">${escapeHtml(profile.headline)}</p>` : ""}
        ${location ? `<p class="location">${escapeHtml(location)}</p>` : ""}
      </div>
    </div>
    <div class="card-body">
      ${renderAbout(profile.about)}
      ${renderExperience(data.experience)}
      ${renderEducation(data.education)}
      ${renderSkills(data.skills)}
      ${renderCertifications(data.certifications)}
      ${renderLanguages(data.languages)}
    </div>
  `;

  return card;
}

function renderAbout(about) {
  if (!about) {
    return `<div class="section"><h4>About</h4><p class="empty-note">Not available</p></div>`;
  }
  return `<div class="section"><h4>About</h4><p>${escapeHtml(about)}</p></div>`;
}

function renderExperience(items) {
  if (!items?.length) {
    return `<div class="section"><h4>Experience</h4><p class="empty-note">Not available</p></div>`;
  }
  const entries = items
    .map((item) => {
      const company = item.company?.name || "";
      const dates = formatDateRange(item.dates);
      return `
        <div class="entry">
          <div class="entry-title">${escapeHtml(item.title || "Role")}</div>
          ${company ? `<div class="entry-sub">${escapeHtml(company)}</div>` : ""}
          ${dates ? `<div class="entry-meta">${escapeHtml(dates)}</div>` : ""}
          ${item.location ? `<div class="entry-meta">${escapeHtml(item.location)}</div>` : ""}
          ${item.description ? `<div class="entry-desc">${escapeHtml(item.description)}</div>` : ""}
        </div>
      `;
    })
    .join("");
  return `<div class="section"><h4>Experience</h4>${entries}</div>`;
}

function renderEducation(items) {
  if (!items?.length) {
    return `<div class="section"><h4>Education</h4><p class="empty-note">Not available</p></div>`;
  }
  const entries = items
    .map((item) => {
      const school = item.institution?.name || "Institution";
      const degree = [item.degree, item.field_of_study].filter(Boolean).join(", ");
      const dates = formatDateRange(item.dates);
      return `
        <div class="entry">
          <div class="entry-title">${escapeHtml(school)}</div>
          ${degree ? `<div class="entry-sub">${escapeHtml(degree)}</div>` : ""}
          ${dates ? `<div class="entry-meta">${escapeHtml(dates)}</div>` : ""}
        </div>
      `;
    })
    .join("");
  return `<div class="section"><h4>Education</h4>${entries}</div>`;
}

function renderSkills(items) {
  if (!items?.length) {
    return `<div class="section"><h4>Skills</h4><p class="empty-note">Not available</p></div>`;
  }
  const chips = items
    .map((s) => `<span class="chip">${escapeHtml(s.name || "Skill")}</span>`)
    .join("");
  return `<div class="section"><h4>Skills</h4><div class="chips">${chips}</div></div>`;
}

function renderCertifications(items) {
  if (!items?.length) {
    return `<div class="section"><h4>Certifications</h4><p class="empty-note">Not available</p></div>`;
  }
  const entries = items
    .map((item) => {
      const issueYear = item.issue_date?.year ? ` (${item.issue_date.year})` : "";
      return `
        <div class="entry">
          <div class="entry-title">${escapeHtml(item.name || "Certification")}</div>
          ${item.issuer ? `<div class="entry-sub">${escapeHtml(item.issuer)}${issueYear}</div>` : ""}
        </div>
      `;
    })
    .join("");
  return `<div class="section"><h4>Certifications</h4>${entries}</div>`;
}

function renderLanguages(items) {
  if (!items?.length) {
    return `<div class="section"><h4>Languages</h4><p class="empty-note">Not available</p></div>`;
  }
  const entries = items
    .map(
      (item) =>
        `<div class="entry"><div class="entry-title">${escapeHtml(item.name || "Language")}${
          item.proficiency ? ` <span class="entry-meta">(${escapeHtml(item.proficiency)})</span>` : ""
        }</div></div>`
    )
    .join("");
  return `<div class="section"><h4>Languages</h4>${entries}</div>`;
}

async function submitJob(url) {
  const response = await fetch(`${API_BASE}/scrape`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_url: url }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message = body.detail?.error?.message || body.detail || response.statusText;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return response.json();
}

async function pollJob(jobId) {
  while (true) {
    const response = await fetch(`${API_BASE}/scrape/${jobId}`);
    if (!response.ok) {
      throw new Error(`Poll failed (${response.status})`);
    }
    const data = await response.json();
    if (data.status === "completed" || data.status === "failed") {
      return data;
    }
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
}

async function scrapeProfile(url) {
  setProgress(url, "queued", "queued");
  const accepted = await submitJob(url);
  setProgress(url, "processing", accepted.status);

  const result = await pollJob(accepted.job_id);

  if (result.status === "failed") {
    setProgress(url, "failed", "failed");
    return renderErrorCard(url, result.error?.message || "Scrape failed");
  }

  setProgress(url, "completed", "done");
  return renderProfileCard(result.data);
}

function showInputError(message) {
  inputError.textContent = message;
  inputError.hidden = !message;
}

scrapeBtn.addEventListener("click", async () => {
  showInputError("");
  const urls = parseUrls(urlsInput.value);

  if (!urls.length) {
    showInputError("Enter at least one LinkedIn profile URL.");
    return;
  }

  const invalid = validateUrls(urls);
  if (invalid.length) {
    showInputError(`Invalid URL(s): ${invalid.join(", ")}`);
    return;
  }

  scrapeBtn.disabled = true;
  progressList.innerHTML = "";
  resultsContainer.innerHTML = "";
  progressSection.hidden = false;
  resultsSection.hidden = false;

  urls.forEach((url) => {
    const li = document.createElement("li");
    li.className = "progress-item";
    li.dataset.url = url;
    li.innerHTML = `
      <span class="progress-url">${escapeHtml(url)}</span>
      <span class="status-badge status-queued">pending</span>
    `;
    progressList.appendChild(li);
  });

  await Promise.all(
    urls.map(async (url) => {
      try {
        const card = await scrapeProfile(url);
        resultsContainer.appendChild(card);
      } catch (err) {
        setProgress(url, "failed", "failed");
        resultsContainer.appendChild(renderErrorCard(url, err.message));
      }
    })
  );

  scrapeBtn.disabled = false;
});
