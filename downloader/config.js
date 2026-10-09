/* Where the Downloader API runs.
 *
 * ""  → same origin. Use this when the API server also serves this page
 *       (the Docker image does that out of the box).
 *
 * On itzigroup.com (GitHub Pages) the API has to live on its own server. If you
 * deploy it somewhere other than https://dl.itzigroup.com, change the URL below
 * AND the two matching entries (connect-src, img-src) in index.html's
 * Content-Security-Policy.
 */
(function () {
  "use strict";
  var host = window.location.hostname;
  var onMainSite = host === "itzigroup.com" || host === "www.itzigroup.com";
  window.ITZI_DOWNLOADER_CONFIG = {
    apiBase: onMainSite ? "https://dl.itzigroup.com" : ""
  };
})();
