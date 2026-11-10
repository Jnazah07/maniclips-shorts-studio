// Shortsmith service worker
// Cache-first app shell for installability and offline use.
// Whisper weights are never precached (too large, cached by library).

var CACHE = "shortsmith-v1.3.0";
var SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(SHELL);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (key !== CACHE) return caches.delete(key);
        return null;
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  // External assets (fonts, preview image) go network-first.
  if (url.origin !== location.origin) return;

  // Page updates must always land: navigations are network-first, cache is the offline copy.
  var accept = req.headers.get("accept") || "";
  if (req.mode === "navigate" || accept.indexOf("text/html") !== -1) {
    event.respondWith(
      fetch(req).then(function (response) {
        if (response && response.status === 200) {
          var copy = response.clone();
          caches.open(CACHE).then(function (cache) { cache.put(req, copy); });
        }
        return response;
      }).catch(function () {
        return caches.match(req).then(function (hit) {
          return hit || caches.match("./index.html");
        });
      })
    );
    return;
  }

  event.respondWith(
    caches.match(req).then(function (cached) {
      var fetchPromise = fetch(req).then(function (networkResponse) {
        if (networkResponse && networkResponse.status === 200 && req.destination !== "image") {
          var copy = networkResponse.clone();
          caches.open(CACHE).then(function (cache) {
            cache.put(req, copy);
          });
        }
        return networkResponse;
      }).catch(function () {
        if (cached) return cached;
        if (req.mode === "navigate") return caches.match("./index.html");
        return new Response("", { status: 504, statusText: "offline" });
      });
      return cached || fetchPromise;
    })
  );
});
