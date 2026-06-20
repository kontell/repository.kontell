// Reverse-proxy in front of the Kontell repo on GitHub Pages, so every repo
// request (addons.xml, .md5, addon zips, art) is logged for analytics.
//
// github.io stays the origin and source of truth; this Worker is a transparent
// pass-through. See worker/../addon.xml for the URLs that point clients here.

const ORIGIN = "https://kontell.github.io/repository.kontell";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/+/, "");

    // Fresh fetch to github.io. Do NOT forward the client Host header --
    // GitHub Pages routes by Host, so it must see kontell.github.io.
    let response = await fetch(`${ORIGIN}/${path}${url.search}`);

    if (env.REPO_ANALYTICS) {
      const { dir, addon, platform, version } = classify(path);
      env.REPO_ANALYTICS.writeDataPoint({
        blobs: [
          dir,                                          // blob1: omega | piers | root
          addon,                                        // blob2: pvr.kofin, ...
          platform,                                     // blob3: linux-x86_64
          version,                                      // blob4: 0.10.1
          request.headers.get("cf-ipcountry") || "",    // blob5: country
          path.endsWith(".zip") ? "zip" : "meta",       // blob6: request kind
          request.method,                               // blob7: GET | HEAD | ...
        ],
        doubles: [response.status],                     // double1: HTTP status
        indexes: [addon || dir || "other"],             // sampling key (<=96B)
      });
    }

    // GitHub Pages serves 404s with `cache-control: max-age=600`, and Cloudflare
    // edge-caches static extensions (.zip/.png/...) by default -- so a request
    // for a not-yet-deployed URL, made in the gap between a publish push and
    // Pages finishing its build, would pin a stale 404 at the edge for up to
    // 10 minutes. Never let a non-2xx be cached.
    if (!response.ok) {
      response = new Response(response.body, response);
      response.headers.set("Cache-Control", "no-store");
    }
    return response;
  },
};

// "omega/pvr.kofin+linux-x86_64/pvr.kofin-0.10.1.zip" -> structured fields.
function classify(path) {
  const parts = path.split("/");
  // Root-level files (the installer zip, index.html) have no version dir.
  const dir = parts.length > 1 ? parts[0] : "root";
  const [addon, platform = ""] = (parts[1] || "").split("+");
  const vm = (parts.at(-1) || "").match(/-([0-9][0-9.]*)\.zip$/);
  return { dir, addon: addon || "", platform, version: vm ? vm[1] : "" };
}
