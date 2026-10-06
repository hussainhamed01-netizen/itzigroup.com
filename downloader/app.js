/* ItziGroup Downloader — front end.
 * Talks to the Downloader API (see /downloader-api in the repository). */
(function () {
  "use strict";

  var CONFIG = window.ITZI_DOWNLOADER_CONFIG || {};
  var API = String(CONFIG.apiBase || "").replace(/\/+$/, "");
  var PLATFORMS = window.ITZI_PLATFORMS || {};
  var HISTORY_KEY = "itzi-downloader-history";
  var HISTORY_MAX = 12;
  var BLOB_LIMIT = 500 * 1024 * 1024; // bigger direct files go straight to the browser's downloader

  // ------------------------------------------------------------------ icons

  var ICONS = {
    link: ["M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71", "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"],
    download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
    arrowDown: ["M12 5v14", "M19 12l-7 7-7-7"],
    clipboard: ["M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2", "M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"],
    x: ["M18 6L6 18", "M6 6l12 12"],
    check: ["M20 6L9 17l-5-5"],
    spinner: ["M21 12a9 9 0 1 1-6.22-8.56"],
    alert: ["M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0z", "M12 8v4", "M12 16h.01"],
    eye: ["M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z", "M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
    heart: ["M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"],
    comment: ["M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"],
    video: ["M23 7l-7 5 7 5V7z", "M3 5h11a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"],
    image: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M10 8.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z", "M21 15l-5-5L5 21"],
    music: ["M9 18V5l12-2v13", "M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z", "M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
    archive: ["M21 8v13H3V8", "M1 3h22v5H1z", "M10 12h4"],
    refresh: ["M23 4v6h-6", "M20.49 15a9 9 0 1 1-2.12-9.36L23 10"],
    shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", "M9 12l2 2 4-4"],
    hd: ["M2 6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z", "M7 9v6", "M11 9v6", "M7 12h4", "M14 9h2a3 3 0 0 1 0 6h-2z"],
    stack: ["M12 2L2 7l10 5 10-5-10-5z", "M2 17l10 5 10-5", "M2 12l10 5 10-5"],
    globe: ["M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0z", "M2 12h20", "M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"],
    clock: ["M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0z", "M12 6v6l4 2"],
    calendar: ["M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M16 2v4", "M8 2v4", "M3 10h18"],
    sparkle: ["M12 3l1.9 5.8L20 10l-6.1 1.2L12 17l-1.9-5.8L4 10l6.1-1.2z"],
    info: ["M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0z", "M12 16v-4", "M12 8h.01"]
  };

  var SVG_NS = "http://www.w3.org/2000/svg";

  function icon(name) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    (ICONS[name] || ICONS.globe).forEach(function (d) {
      var path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  function brandIcon(key) {
    var platform = PLATFORMS[key];
    if (!platform) return icon("globe");
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "currentColor");
    svg.setAttribute("aria-hidden", "true");
    var path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", platform.path);
    svg.appendChild(path);
    return svg;
  }

  // ------------------------------------------------------------------ DOM helpers

  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === null || value === undefined || value === false) return;
        if (key === "class") el.className = value;
        else if (key === "text") el.textContent = value;
        else if (key.slice(0, 2) === "on") el.addEventListener(key.slice(2), value);
        else el.setAttribute(key, value === true ? "" : value);
      });
    }
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }

  function append(parent, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { append(parent, c); }); return; }
    parent.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }

  function $(id) { return document.getElementById(id); }

  // ------------------------------------------------------------------ formatting

  function formatBytes(bytes) {
    if (!bytes && bytes !== 0) return "";
    var units = ["B", "KB", "MB", "GB"];
    var i = 0;
    while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
    return (i === 0 ? bytes : bytes.toFixed(bytes < 10 ? 1 : 0)) + " " + units[i];
  }

  function formatDuration(seconds) {
    if (!seconds && seconds !== 0) return "";
    seconds = Math.round(seconds);
    var hh = Math.floor(seconds / 3600);
    var mm = Math.floor((seconds % 3600) / 60);
    var ss = seconds % 60;
    var pad = function (n) { return n < 10 ? "0" + n : String(n); };
    return hh ? hh + ":" + pad(mm) + ":" + pad(ss) : mm + ":" + pad(ss);
  }

  var compact = (window.Intl && Intl.NumberFormat) ? new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }) : null;
  function formatCount(n) { return compact ? compact.format(n) : String(n); }

  function formatDate(iso) {
    if (!iso) return "";
    var date = new Date(iso + "T00:00:00");
    if (isNaN(date.getTime())) return iso;
    return date.toLocaleDateString("en", { year: "numeric", month: "short", day: "numeric" });
  }

  function timeAgo(ts) {
    var diff = Math.max(0, (Date.now() - ts) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + " min ago";
    if (diff < 86400) return Math.floor(diff / 3600) + " h ago";
    return Math.floor(diff / 86400) + " d ago";
  }

  // ------------------------------------------------------------------ platforms

  function hostOf(url) {
    try { return new URL(url).hostname.toLowerCase(); } catch (e) { return ""; }
  }

  function findUrl(text) {
    var match = String(text || "").match(/https?:\/\/[^\s<>"'`]+/i);
    if (match) return match[0].replace(/[.,;:!?)\]}>'"]+$/, "");
    var bare = String(text || "").trim();
    if (/^(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#]\S*)?$/i.test(bare)) return "https://" + bare;
    return "";
  }

  function detectPlatform(url) {
    var host = hostOf(url);
    if (!host) return null;
    var keys = Object.keys(PLATFORMS);
    for (var i = 0; i < keys.length; i++) {
      var domains = PLATFORMS[keys[i]].domains;
      for (var j = 0; j < domains.length; j++) {
        if (host === domains[j] || host.slice(-(domains[j].length + 1)) === "." + domains[j]) return keys[i];
      }
    }
    if (/(^|\.)pinterest\.[a-z.]{2,6}$/.test(host)) return "pinterest";
    return null;
  }

  var HINTS = {
    tiktok: "videos & photo slideshows, without the watermark",
    instagram: "posts, reels, stories & carousels",
    youtube: "videos & Shorts up to 4K, or MP3",
    facebook: "videos & reels in HD",
    x: "videos, GIFs & photos",
    snapchat: "Spotlight & public stories",
    threads: "videos & photos",
    pinterest: "pins, videos & original-size images",
    reddit: "videos with sound, images & galleries",
    bluesky: "videos & photos",
    tumblr: "posts, photos & videos",
    vimeo: "videos in every quality",
    twitch: "clips & VODs",
    kick: "clips & VODs",
    soundcloud: "tracks as MP3",
    dailymotion: "videos in every quality",
    bilibili: "videos in every quality",
    rumble: "videos in every quality",
    vk: "videos & clips",
    "9gag": "videos & GIFs"
  };

  // ------------------------------------------------------------------ API

  function ApiError(code, message, detail, status) {
    this.code = code;
    this.message = message;
    this.detail = detail;
    this.status = status;
  }

  function api(path, options) {
    options = options || {};
    var init = { method: options.method || "GET", headers: {}, signal: options.signal };
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    return fetch(API + path, init).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!res.ok) {
          var err = (data && data.error) || {};
          throw new ApiError(err.code || "http_" + res.status, err.message || "Something went wrong (HTTP " + res.status + ").", err.detail, res.status);
        }
        return data;
      });
    }, function (e) {
      if (e && e.name === "AbortError") throw e;
      throw new ApiError("network", "Can't reach the download engine. Check your connection, or try again in a moment.");
    });
  }

  function readError(res) {
    return res.text().then(function (text) {
      try {
        var err = JSON.parse(text).error || {};
        return new ApiError(err.code || "http_" + res.status, err.message || "Download failed (HTTP " + res.status + ").", err.detail, res.status);
      } catch (e) {
        return new ApiError("http_" + res.status, "Download failed (HTTP " + res.status + ").", null, res.status);
      }
    });
  }

  // ------------------------------------------------------------------ state & elements

  var els = {
    form: $("grabForm"),
    input: $("urlInput"),
    icon: $("grabIcon"),
    paste: $("pasteBtn"),
    clear: $("clearBtn"),
    go: $("goBtn"),
    detect: $("detectLine"),
    platforms: $("platformList"),
    result: $("result"),
    recent: $("recent"),
    recentList: $("recentList"),
    clearHistory: $("clearHistory"),
    engine: $("engineStatus"),
    toast: $("toast"),
    viewer: $("viewer"),
    viewerImg: $("viewerImg"),
    viewerClose: $("viewerClose")
  };

  var state = {
    busy: false,
    media: null,
    lastUrl: "",
    analyzedAt: 0,
    loadingTimer: null,
    analyzeController: null
  };

  // ------------------------------------------------------------------ toast & viewer

  var toastTimer = null;
  function toast(message, isError) {
    els.toast.textContent = "";
    els.toast.classList.toggle("is-error", !!isError);
    append(els.toast, [icon(isError ? "alert" : "check"), h("span", { text: message })]);
    els.toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { els.toast.classList.remove("is-visible"); }, 3200);
  }

  function openViewer(src, alt) {
    els.viewerImg.src = src;
    els.viewerImg.alt = alt || "";
    els.viewer.hidden = false;
    els.viewerClose.focus();
  }

  function closeViewer() {
    els.viewer.hidden = true;
    els.viewerImg.removeAttribute("src");
  }

  // ------------------------------------------------------------------ input box

  function updateInputUI() {
    var value = els.input.value.trim();
    els.clear.hidden = !value;
    els.paste.hidden = !!value;
    var url = findUrl(value);
    var key = url ? detectPlatform(url) : null;
    els.icon.textContent = "";
    els.icon.classList.toggle("is-brand", !!key);
    els.icon.style.color = key ? PLATFORMS[key].color : "";
    els.icon.appendChild(key ? brandIcon(key) : icon("link"));

    Array.prototype.forEach.call(els.platforms.children, function (chip) {
      chip.classList.toggle("is-active", !!key && chip.getAttribute("data-key") === key);
    });

    els.detect.textContent = "";
    if (!value || state.busy) return;
    if (!url) {
      append(els.detect, [icon("info"), h("span", { text: "Paste a full link — for example https://www.tiktok.com/@user/video/…" })]);
    } else if (key) {
      append(els.detect, [h("strong", { text: PLATFORMS[key].name + " link" }), h("span", { text: "· " + (HINTS[key] || "videos & photos") })]);
    } else {
      append(els.detect, [h("strong", { text: hostOf(url).replace(/^www\./, "") }), h("span", { text: "· we'll look for every video, photo and sound" })]);
    }
  }

  function setBusy(busy) {
    state.busy = busy;
    els.go.disabled = busy;
    els.go.classList.toggle("is-busy", busy);
    els.form.classList.toggle("is-busy", busy);
    els.go.querySelector(".grab-go-text").textContent = busy ? "Fetching…" : "Download";
    var goIcon = els.go.querySelector(".grab-go-icon");
    goIcon.textContent = "";
    goIcon.appendChild(icon(busy ? "spinner" : "arrowDown"));
    if (!busy) updateInputUI();
  }

  function renderPlatformStrip() {
    Object.keys(PLATFORMS).forEach(function (key) {
      var p = PLATFORMS[key];
      var chip = h("li", { class: "platform-chip", "data-key": key, title: p.name + ": " + (HINTS[key] || "") }, brandIcon(key), h("span", { text: p.name }));
      chip.style.setProperty("--brand", p.color);
      els.platforms.appendChild(chip);
    });
    els.platforms.appendChild(h("li", { class: "platform-chip more", text: "+ 1,000 more" }));
  }

  // ------------------------------------------------------------------ result rendering

  function showResult(node) {
    els.result.textContent = "";
    els.result.appendChild(node);
    els.result.hidden = false;
  }

  function renderLoading(url) {
    var key = detectPlatform(url);
    var name = key ? PLATFORMS[key].name : (hostOf(url).replace(/^www\./, "") || "the site");
    var steps = [
      "Connecting to " + name + "…",
      "Reading the post…",
      key === "tiktok" ? "Finding the watermark-free version…" : "Finding the best quality…",
      "Collecting every photo, video and sound…",
      "Still working. Some sites are slow…"
    ];
    var label = h("span", { text: steps[0] });
    var panel = h("div", { class: "panel" },
      h("div", { class: "loading" },
        h("div", { class: "skel skel-media" }),
        h("div", null,
          h("div", { class: "skel skel-line w80" }),
          h("div", { class: "skel skel-line w50" }),
          h("div", { class: "skel skel-line w30" }),
          h("div", { class: "skel skel-row" }),
          h("div", { class: "skel skel-row" }),
          h("div", { class: "loading-status" }, icon("spinner"), label))));
    showResult(panel);
    var step = 0;
    clearInterval(state.loadingTimer);
    state.loadingTimer = setInterval(function () {
      step = Math.min(step + 1, steps.length - 1);
      label.textContent = steps[step];
    }, 2200);
  }

  var ERROR_TITLES = {
    invalid_url: "That link doesn't look right",
    login_required: "This needs a signed-in account",
    private: "This post is private",
    not_found: "Nothing found at this link",
    unsupported: "This link isn't supported",
    no_media: "No media found",
    blocked: "The platform blocked the request",
    rate_limited: "Slow down a little",
    geo: "Blocked in the server's region",
    timeout: "That took too long",
    network: "Can't reach the download engine",
    busy: "The server is busy"
  };

  function renderError(err, url) {
    var retry = h("button", { type: "button", class: "btn btn-primary", onclick: function () { analyze(url, true); } }, icon("refresh"), "Try again");
    var edit = h("button", { type: "button", class: "btn btn-ghost", onclick: function () { els.input.focus(); els.input.select(); } }, "Edit link");
    showResult(h("div", { class: "panel error-panel", role: "alert" },
      h("div", { class: "error-icon" }, icon("alert")),
      h("div", { class: "error-body" },
        h("h2", { text: ERROR_TITLES[err.code] || "Couldn't fetch that link" }),
        h("p", { text: err.message }),
        err.detail ? h("details", { class: "error-detail" }, h("summary", { text: "Technical details" }), h("p", { text: err.detail })) : null,
        h("div", { class: "error-actions" }, err.code === "invalid_url" ? null : retry, edit))));
  }

  var KIND_META = {
    video: { label: "Video", icon: "video" },
    image: { label: "Photo", icon: "image" },
    audio: { label: "Audio", icon: "music" }
  };

  function bestHeight(media) {
    var best = 0;
    media.items.forEach(function (item) {
      item.options.forEach(function (o) {
        var m = /^(\d{3,4})p/.exec(o.label);
        if (o.kind === "video" && m) best = Math.max(best, parseInt(m[1], 10));
      });
    });
    return best;
  }

  function mediaKindLabel(media) {
    var types = {};
    media.items.forEach(function (item) { types[item.type] = (types[item.type] || 0) + 1; });
    if (media.items.length === 1) return KIND_META[media.items[0].type] || KIND_META.video;
    if (types.image && types.audio && !types.video) return { label: "Slideshow", icon: "stack" };
    if (types.image && !types.video) return { label: "Photo carousel", icon: "stack" };
    return { label: "Carousel", icon: "stack" };
  }

  function coverImage(src, alt, fallbackIcon) {
    var wrap = document.createDocumentFragment();
    var fallback = h("div", { class: "cover-fallback" }, icon(fallbackIcon || "video"));
    if (src) {
      var img = h("img", { src: API + src, alt: alt || "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
      img.addEventListener("error", function () { img.remove(); });
      append(wrap, [fallback, img]);
    } else {
      append(wrap, fallback);
    }
    return wrap;
  }

  function renderMedia(media) {
    var items = media.items;
    var single = items.length === 1;
    var first = items[0];
    var key = PLATFORMS[media.platform.key] ? media.platform.key : null;
    var wide = single && first.width && first.height && first.width > first.height * 1.1;
    var kind = mediaKindLabel(media);

    var platformBadge = h("span", { class: "cover-badge cover-platform" }, key ? brandIcon(key) : icon("globe"), media.platform.name);
    if (key) platformBadge.style.color = PLATFORMS[key].color;
    var cover = h("div", { class: "cover" },
      coverImage(media.thumbnail, media.title, KIND_META[first.type] ? KIND_META[first.type].icon : "video"),
      platformBadge,
      media.duration ? h("span", { class: "cover-badge cover-duration", text: formatDuration(media.duration) }) : null);
    if (media.thumbnail && first.type === "image") {
      cover.addEventListener("click", function () { openViewer(API + (single ? first.thumbnail || media.thumbnail : media.thumbnail), media.title); });
      cover.style.cursor = "zoom-in";
    }

    var pills = h("div", { class: "pills" });
    if (media.watermark_free) append(pills, h("span", { class: "pill pill-ok" }, icon("check"), "No watermark"));
    var height = bestHeight(media);
    if (height >= 2160) append(pills, h("span", { class: "pill pill-hot" }, "4K"));
    else if (height >= 1440) append(pills, h("span", { class: "pill pill-hot" }, "2K"));
    else if (height >= 720) append(pills, h("span", { class: "pill pill-hot" }, "HD"));
    append(pills, h("span", { class: "pill" }, icon(kind.icon), single ? kind.label : kind.label + " · " + items.length + " items"));
    if (media.truncated) append(pills, h("span", { class: "pill", title: "Only the first items are shown" }, "First " + items.length));

    var by = [];
    if (media.uploader) {
      var safeUploaderUrl = /^https?:\/\//i.test(media.uploader_url || "") ? media.uploader_url : null;
      by.push(safeUploaderUrl ? h("a", { href: safeUploaderUrl, target: "_blank", rel: "noopener noreferrer nofollow", text: media.uploader }) : media.uploader);
    }
    if (media.upload_date) by.push((by.length ? " · " : "") + formatDate(media.upload_date));

    var stats = h("div", { class: "stats" });
    if (media.stats.views) append(stats, h("span", { class: "stat" }, icon("eye"), formatCount(media.stats.views)));
    if (media.stats.likes) append(stats, h("span", { class: "stat" }, icon("heart"), formatCount(media.stats.likes)));
    if (media.stats.comments) append(stats, h("span", { class: "stat" }, icon("comment"), formatCount(media.stats.comments)));

    var body = h("div", { class: "media-body" },
      pills,
      h("h2", { class: "media-title", text: media.title || (media.platform.name + " " + kind.label.toLowerCase()) }),
      by.length ? h("p", { class: "media-by" }, by) : null,
      stats.children.length ? stats : null,
      media.notice ? h("p", { class: "notice" }, icon("info"), h("span", { text: media.notice })) : null,
      single ? optionsPanel(media, first) : bundleBar(media));

    var panel = h("div", { class: "panel" }, h("div", { class: "media" + (wide ? " is-wide" : "") }, cover, body));
    if (!single) panel.appendChild(itemGrid(media));
    showResult(panel);
  }

  function optionsPanel(media, item) {
    var groups = { video: [], image: [], audio: [] };
    item.options.forEach(function (o) { (groups[o.kind] || groups.video).push(o); });
    var order = ["video", "image", "audio"].filter(function (k) { return groups[k].length; });
    var wrap = h("div");
    var list = h("div", { class: "options", role: "tabpanel" });

    function show(kind) {
      list.textContent = "";
      groups[kind].forEach(function (o, i) { list.appendChild(optionRow(media, o, { best: i === 0 })); });
      Array.prototype.forEach.call(tabs.children, function (t) {
        t.setAttribute("aria-selected", t.getAttribute("data-kind") === kind ? "true" : "false");
      });
    }

    var tabs = h("div", { class: "tabs", role: "tablist" });
    order.forEach(function (kind) {
      var meta = KIND_META[kind];
      tabs.appendChild(h("button", { type: "button", class: "tab", role: "tab", "data-kind": kind, onclick: function () { show(kind); } },
        icon(meta.icon), meta.label, h("span", { class: "tab-count", text: String(groups[kind].length) })));
    });
    if (order.length > 1) wrap.appendChild(tabs);
    wrap.appendChild(list);
    show(order[0]);
    return wrap;
  }

  function bundleBar(media) {
    if (!media.bundle) return null;
    var row = optionRow(media, { id: "all", kind: "archive", label: "ZIP", ext: "zip", mode: "process", note: "" }, { bundle: true });
    return h("div", { class: "bundle" },
      h("div", { class: "bundle-text" },
        h("strong", { text: "Download all " + media.bundle.count + " items" }),
        h("span", { text: "Best quality of each, packed into one ZIP" })),
      row);
  }

  function itemGrid(media) {
    var grid = h("div", { class: "items" });
    media.items.forEach(function (item, position) {
      var meta = KIND_META[item.type] || KIND_META.video;
      var mediaBox = h("div", { class: "tile-media" }, coverImage(item.thumbnail, item.title, meta.icon));
      if (item.thumbnail && item.type === "image") {
        mediaBox.appendChild(h("button", { type: "button", "aria-label": "Preview item " + (position + 1), onclick: function () { openViewer(API + item.thumbnail, item.title); } }));
      }
      append(mediaBox, [
        h("span", { class: "tile-index", text: (position + 1) + "/" + media.items.length }),
        h("span", { class: "tile-type" }, icon(meta.icon))
      ]);
      var bodyEl = h("div", { class: "tile-body" }, optionRow(media, item.options[0], { compact: true }));
      if (item.options.length > 1) {
        var more = h("div", { class: "tile-options", hidden: true });
        item.options.slice(1).forEach(function (o) { more.appendChild(optionRow(media, o, { compact: true })); });
        var toggle = h("button", { type: "button", class: "tile-more", text: "More formats (" + (item.options.length - 1) + ")" });
        toggle.addEventListener("click", function () {
          more.hidden = !more.hidden;
          toggle.textContent = more.hidden ? "More formats (" + (item.options.length - 1) + ")" : "Fewer formats";
        });
        append(bodyEl, [toggle, more]);
      }
      grid.appendChild(h("div", { class: "tile" }, mediaBox, bodyEl));
    });
    return grid;
  }

  function optionRow(media, option, flags) {
    flags = flags || {};
    var label = flags.bundle ? "" : option.label;
    var note = option.note || "";
    var main = h("div", { class: "opt-main" });
    if (!flags.bundle) {
      append(main, [
        h("span", { class: "opt-q", text: label }),
        h("span", { class: "opt-ext", text: option.ext }),
        flags.best ? h("span", { class: "opt-best-tag", text: "Best" }) : null,
        note ? h("span", { class: "opt-note" + (option.watermark ? " is-warn" : ""), text: note }) : null
      ]);
    }
    var size = option.size ? h("span", { class: "opt-size", text: (option.size_approx ? "~" : "") + formatBytes(option.size) }) : h("span", { class: "opt-size" });
    var button = h("button", { type: "button", class: "btn btn-primary dl-btn" }, icon(flags.bundle ? "archive" : "download"), h("span", { text: flags.bundle ? "Download ZIP" : (flags.compact ? "Save" : "Download") }));
    var bar = h("div", { class: "bar" }, h("div", { class: "bar-fill" }));
    var left = h("span", { class: "progress-stage" });
    var right = h("span", { class: "mono progress-numbers" });
    var cancel = h("button", { type: "button", class: "cancel-btn", text: "Cancel" });
    var progress = h("div", { class: "opt-progress" }, bar, h("div", { class: "progress-line" }, left, h("span", null, right, " ", cancel)));
    var row = h("div", { class: "opt" + (flags.best ? " is-best" : "") }, main, size, button, progress);

    var ui = {
      row: row, button: button, bar: bar, left: left, right: right, cancel: cancel,
      setButton: function (iconName, text, cls) {
        button.className = "btn dl-btn " + (cls || "btn-primary");
        button.textContent = "";
        append(button, [icon(iconName), h("span", { text: text })]);
      }
    };
    button.addEventListener("click", function () {
      if (ui.again) { ui.again(); return; }
      startDownload(media, option, ui);
    });
    return row;
  }

  // ------------------------------------------------------------------ downloads

  function setProgress(ui, fraction, stage, numbers) {
    ui.row.classList.add("is-working");
    ui.row.classList.remove("is-failed");
    var indeterminate = fraction === null || fraction === undefined;
    ui.bar.classList.toggle("is-indeterminate", indeterminate);
    if (!indeterminate) ui.bar.style.setProperty("--p", String(Math.max(0, Math.min(1, fraction))));
    ui.left.textContent = stage || "";
    ui.right.textContent = numbers || (indeterminate ? "" : Math.round(fraction * 100) + "%");
  }

  function numbersLine(done, total, speed, eta) {
    var parts = [];
    if (total) parts.push(Math.round((done / total) * 100) + "%");
    if (done) parts.push(formatBytes(done) + (total ? " / " + formatBytes(total) : ""));
    if (speed) parts.push(formatBytes(speed) + "/s");
    if (eta) parts.push(formatDuration(eta) + " left");
    return parts.join(" · ");
  }

  function markDone(ui, again) {
    ui.row.classList.remove("is-working", "is-failed");
    ui.setButton("check", "Saved", "btn-done");
    ui.button.disabled = false;
    ui.button.title = "Save again";
    ui.again = again || null;
  }

  function markFailed(ui, message) {
    ui.again = null;
    ui.row.classList.remove("is-working");
    ui.row.classList.add("is-failed");
    ui.left.textContent = message;
    ui.right.textContent = "";
    ui.cancel.hidden = true;
    ui.button.disabled = false;
    ui.setButton("refresh", "Retry", "btn-primary");
  }

  function resetRow(ui) {
    ui.again = null;
    ui.row.classList.remove("is-working", "is-failed");
    ui.button.disabled = false;
    ui.setButton("download", "Download", "btn-primary");
  }

  function saveUrl(url, filename) {
    // Cross-origin links ignore the name and use the server's Content-Disposition instead.
    var a = h("a", { href: url, rel: "noopener" });
    a.setAttribute("download", filename || "");
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function saveBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = h("a", { href: url, download: filename || "download" });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }

  function handleExpired(err) {
    if (err && (err.code === "expired" || err.code === "upstream_refused")) {
      toast("That link went stale. Fetching it again…", true);
      analyze(state.lastUrl, true);
      return true;
    }
    return false;
  }

  function startDownload(media, option, ui) {
    if (ui.button.disabled) return;
    ui.button.disabled = true;
    ui.cancel.hidden = false;
    if (option.mode === "direct") downloadDirect(media, option, ui);
    else runJob(media, option, ui);
  }

  function downloadDirect(media, option, ui) {
    if ((option.size && option.size > BLOB_LIMIT) || !window.fetch || !window.ReadableStream) {
      saveUrl(API + option.url, option.filename);
      toast("Download started");
      markDone(ui);
      return;
    }
    var controller = new AbortController();
    var started = Date.now();
    ui.setButton("spinner", "Saving", "btn-primary");
    setProgress(ui, option.size ? 0 : null, "Downloading", "");
    ui.cancel.onclick = function () { controller.abort(); };

    fetch(API + option.url, { signal: controller.signal }).then(function (res) {
      if (!res.ok) return readError(res).then(function (err) { throw err; });
      var total = parseInt(res.headers.get("content-length") || "", 10) || option.size || 0;
      var type = res.headers.get("content-type") || "application/octet-stream";
      var reader = res.body.getReader();
      var chunks = [];
      var received = 0;
      var lastPaint = 0;
      function pump() {
        return reader.read().then(function (step) {
          if (step.done) return new Blob(chunks, { type: type });
          chunks.push(step.value);
          received += step.value.length;
          var now = Date.now();
          if (now - lastPaint > 120) {
            lastPaint = now;
            var speed = received / Math.max((now - started) / 1000, 0.001);
            var eta = total ? (total - received) / speed : null;
            setProgress(ui, total ? received / total : null, "Downloading", numbersLine(received, total, speed, eta));
          }
          return pump();
        });
      }
      return pump();
    }).then(function (blob) {
      saveBlob(blob, option.filename);
      toast("Saved " + (option.filename || "file"));
      markDone(ui, function () { saveBlob(blob, option.filename); });
    }).catch(function (err) {
      if (err && err.name === "AbortError") { resetRow(ui); return; }
      if (handleExpired(err)) return;
      if (!(err instanceof ApiError)) {
        // Network or CORS trouble mid-stream: let the browser try on its own.
        saveUrl(API + option.url, option.filename);
        markDone(ui);
        return;
      }
      markFailed(ui, err.message);
    });
  }

  function runJob(media, option, ui) {
    var stopped = false;
    var jobId = null;
    ui.setButton("spinner", "Preparing", "btn-primary");
    setProgress(ui, null, "Starting…", "");
    ui.cancel.onclick = function () {
      stopped = true;
      if (jobId) api("/api/jobs/" + jobId, { method: "DELETE" }).catch(function () {});
      resetRow(ui);
    };

    api("/api/media/" + media.id + "/jobs", { method: "POST", body: { option: option.id } }).then(function (job) {
      jobId = job.id;
      poll(job);
    }).catch(function (err) {
      if (handleExpired(err)) return;
      markFailed(ui, err.message);
    });

    function poll(job) {
      if (stopped) return;
      if (job.status === "done") {
        saveUrl(API + job.url, job.filename);
        toast("Saved " + (job.filename || "file"));
        markDone(ui, function () { saveUrl(API + job.url, job.filename); });
        if (job.stage && job.stage !== "Ready") ui.left.textContent = job.stage;
        return;
      }
      if (job.status === "error") { markFailed(ui, job.error || "The download failed."); return; }
      if (job.status === "cancelled") { resetRow(ui); return; }
      var stage = job.status === "queued" ? "Waiting for a free slot…" : job.stage;
      setProgress(ui, job.progress, stage, numbersLine(job.downloaded, job.total, job.speed, job.eta));
      setTimeout(function () {
        if (stopped) return;
        api("/api/jobs/" + jobId).then(poll).catch(function (err) {
          if (err.code === "network") { setTimeout(function () { poll(job); }, 1500); return; }
          markFailed(ui, err.message);
        });
      }, 700);
    }
  }

  // ------------------------------------------------------------------ analyze

  function analyze(rawUrl, fresh) {
    var url = findUrl(rawUrl);
    if (!url) {
      updateInputUI();
      renderError(new ApiError("invalid_url", "Paste the full link to a post, reel, story or video, starting with https://"), rawUrl);
      return;
    }
    if (state.analyzeController) state.analyzeController.abort();
    var controller = new AbortController();
    state.analyzeController = controller;
    state.lastUrl = url;
    setBusy(true);
    renderLoading(url);
    els.result.scrollIntoView({ behavior: "smooth", block: "start" });

    api("/api/extract", { method: "POST", body: { url: url, fresh: !!fresh }, signal: controller.signal }).then(function (media) {
      state.media = media;
      state.analyzedAt = Date.now();
      renderMedia(media);
      remember(url, media);
    }).catch(function (err) {
      if (err && err.name === "AbortError") return;
      renderError(err instanceof ApiError ? err : new ApiError("failed", "Something went wrong. Try again."), url);
    }).then(function () {
      if (state.analyzeController !== controller) return;
      clearInterval(state.loadingTimer);
      state.analyzeController = null;
      setBusy(false);
    });
  }

  // ------------------------------------------------------------------ history (this browser only)

  function loadHistory() {
    try {
      var list = JSON.parse(window.localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(list) ? list.filter(function (x) { return x && typeof x.url === "string"; }) : [];
    } catch (e) {
      return [];
    }
  }

  function saveHistory(list) {
    try { window.localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, HISTORY_MAX))); } catch (e) { /* storage unavailable */ }
  }

  function remember(url, media) {
    var list = loadHistory().filter(function (x) { return x.url !== url; });
    list.unshift({
      url: url,
      title: media.title || media.platform.name + " post",
      platform: media.platform.key,
      platformName: media.platform.name,
      count: media.items.length,
      at: Date.now()
    });
    saveHistory(list);
    renderHistory();
  }

  function renderHistory() {
    var list = loadHistory();
    els.recentList.textContent = "";
    els.recent.hidden = !list.length;
    list.forEach(function (entry) {
      var key = PLATFORMS[entry.platform] ? entry.platform : null;
      var iconBox = h("span", { class: "recent-icon" }, key ? brandIcon(key) : icon("globe"));
      if (key) iconBox.style.setProperty("--brand", PLATFORMS[key].color);
      var meta = (entry.platformName || "") + (entry.count > 1 ? " · " + entry.count + " items" : "") + " · " + timeAgo(entry.at || Date.now());
      els.recentList.appendChild(h("li", null, h("button", {
        type: "button", class: "recent-item", title: entry.url,
        onclick: function () { els.input.value = entry.url; updateInputUI(); analyze(entry.url); }
      }, iconBox, h("span", { class: "recent-text" }, h("span", { class: "recent-title", text: entry.title }), h("span", { class: "recent-meta", text: meta })))));
    });
  }

  // ------------------------------------------------------------------ engine status

  function checkEngine() {
    els.engine.setAttribute("data-state", "checking");
    api("/api/health").then(function (data) {
      els.engine.setAttribute("data-state", "online");
      els.engine.querySelector(".engine-label").textContent = "Engine online";
      var notes = ["yt-dlp " + (data.engines.yt_dlp || "?"), "gallery-dl " + (data.engines.gallery_dl || "?")];
      if (!data.ffmpeg) notes.push("ffmpeg missing: merging and MP3 disabled");
      els.engine.title = notes.join(" · ");
    }).catch(function () {
      els.engine.setAttribute("data-state", "offline");
      els.engine.querySelector(".engine-label").textContent = "Engine offline";
      els.engine.title = "The download engine can't be reached right now.";
      setTimeout(checkEngine, 30000);
    });
  }

  // ------------------------------------------------------------------ wiring

  function init() {
    renderPlatformStrip();
    renderHistory();
    setBusy(false);
    els.clear.appendChild(icon("x"));
    els.paste.querySelector(".grab-paste-icon").appendChild(icon("clipboard"));
    document.querySelectorAll(".feature-icon[data-icon]").forEach(function (el) {
      el.appendChild(icon(el.getAttribute("data-icon")));
    });
    els.viewerClose.appendChild(icon("x"));

    els.form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!state.busy) analyze(els.input.value);
    });

    els.input.addEventListener("input", updateInputUI);
    els.input.addEventListener("paste", function () {
      setTimeout(function () {
        updateInputUI();
        if (findUrl(els.input.value) && !state.busy) analyze(els.input.value);
      }, 0);
    });

    els.clear.addEventListener("click", function () {
      els.input.value = "";
      updateInputUI();
      els.input.focus();
    });

    els.paste.addEventListener("click", function () {
      if (!navigator.clipboard || !navigator.clipboard.readText) {
        els.input.focus();
        toast("Press Ctrl+V (or long-press → Paste) in the box", false);
        return;
      }
      navigator.clipboard.readText().then(function (text) {
        if (!text) { toast("Your clipboard is empty", true); return; }
        els.input.value = text.trim();
        updateInputUI();
        if (findUrl(text)) analyze(text);
      }, function () {
        els.input.focus();
        toast("Allow clipboard access, or press Ctrl+V in the box", true);
      });
    });

    document.addEventListener("paste", function (e) {
      var target = e.target;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      var text = e.clipboardData && e.clipboardData.getData("text");
      if (!text || !findUrl(text)) return;
      e.preventDefault();
      els.input.value = text.trim();
      updateInputUI();
      analyze(text);
    });

    els.clearHistory.addEventListener("click", function () {
      saveHistory([]);
      renderHistory();
    });

    els.viewer.addEventListener("click", function (e) { if (e.target !== els.viewerImg) closeViewer(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !els.viewer.hidden) closeViewer();
      if (e.key === "/" && document.activeElement === document.body) { e.preventDefault(); els.input.focus(); }
    });

    checkEngine();

    var params = new URLSearchParams(window.location.search);
    var shared = params.get("url") || params.get("text") || params.get("u");
    if (shared && findUrl(shared)) {
      els.input.value = findUrl(shared);
      updateInputUI();
      analyze(shared);
    }
  }

  init();
})();
